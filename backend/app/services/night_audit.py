"""Night audit: close one business date for one hotel.

For business date D it
  1. posts the room charge (with GST) for the night of D to the folio of every
     checked-in reservation in house that night, and
  2. marks as no-show every confirmed reservation that was due to arrive on or
     before D and never checked in, which releases its inventory.

It is safe to run more than once for the same date: nights already charged are
skipped, and the database refuses a second room charge for the same folio and
night.
"""

from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import exists, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import UnprocessableError
from app.database import current_hotel_id
from app.models import (
    Folio,
    FolioStatus,
    FolioTransaction,
    NightAuditRun,
    Reservation,
    ReservationStatus,
    TransactionCategory,
)
from app.services.channel_sync import request_availability_push
from app.services.folios import build_room_charge, ensure_folio, hotel_today


async def _post_room_charges(
    session: AsyncSession, business_date: date, run_by: UUID | None
) -> list[FolioTransaction]:
    already_charged = exists().where(
        FolioTransaction.folio_id == Folio.id,
        FolioTransaction.business_date == business_date,
        FolioTransaction.category == TransactionCategory.ROOM_CHARGE,
        FolioTransaction.reverses_transaction_id.is_(None),
    )
    # One query for every in-house stay and its folio.
    rows = await session.execute(
        select(Reservation, Folio)
        .outerjoin(Folio, Folio.reservation_id == Reservation.id)
        .where(
            Reservation.status == ReservationStatus.CHECKED_IN,
            Reservation.check_in_date <= business_date,
            Reservation.check_out_date > business_date,
            ~already_charged,
        )
        .order_by(Reservation.id)
    )

    charges = []
    for reservation, folio in rows:
        folio = folio or await ensure_folio(session, reservation)
        if folio.status != FolioStatus.OPEN:
            continue
        charges.append(build_room_charge(folio, reservation, business_date, run_by))
    session.add_all(charges)
    await session.flush()
    return charges


async def _mark_no_shows(session: AsyncSession, business_date: date) -> int:
    result = await session.execute(
        update(Reservation)
        .where(
            Reservation.status == ReservationStatus.CONFIRMED,
            Reservation.check_in_date <= business_date,
        )
        .values(status=ReservationStatus.NO_SHOW)
        .returning(Reservation.room_type_id, Reservation.check_in_date, Reservation.check_out_date)
        .execution_options(synchronize_session=False)
    )
    released = result.all()
    # Each no-show frees its nights, so connected channels can sell them again.
    for room_type_id, check_in, check_out in released:
        await request_availability_push(session, room_type_id, check_in, check_out)
    return len(released)


async def run_night_audit(
    session: AsyncSession, business_date: date, *, run_by: UUID | None = None
) -> NightAuditRun:
    if business_date > await hotel_today(session):
        raise UnprocessableError("Night audit cannot be run for a future date")

    # One audit at a time per hotel; released when the transaction ends.
    await session.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
        {"key": f"night_audit:{current_hotel_id(session)}"},
    )

    charges = await _post_room_charges(session, business_date, run_by)
    no_shows = await _mark_no_shows(session, business_date)

    run = await session.scalar(
        select(NightAuditRun).where(NightAuditRun.business_date == business_date)
    )
    if run is None:
        run = NightAuditRun(
            hotel_id=current_hotel_id(session),
            business_date=business_date,
            room_charges_posted=0,
            no_shows_marked=0,
            room_revenue=Decimal("0.00"),
            tax_amount=Decimal("0.00"),
        )
        session.add(run)
    run.room_charges_posted += len(charges)
    run.no_shows_marked += no_shows
    run.room_revenue += sum((c.amount for c in charges), Decimal("0.00"))
    run.tax_amount += sum((c.cgst_amount + c.sgst_amount for c in charges), Decimal("0.00"))
    run.run_by = run_by
    await session.flush()
    return run
