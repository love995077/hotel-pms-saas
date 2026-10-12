"""Folio ledger. Lines are only ever appended; corrections are reversing lines."""

import secrets
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError
from app.database import current_hotel_id
from app.models import (
    EntryType,
    Folio,
    FolioStatus,
    FolioTransaction,
    Hotel,
    PaymentMethod,
    Reservation,
    TransactionCategory,
)
from app.services.crud import flush_or_conflict, get_or_404
from app.services.gst import (
    SAC_ACCOMMODATION,
    GstBreakdown,
    calculate_gst,
    calculate_room_gst,
    round_money,
)

_FOLIO_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
_ZERO = Decimal("0.00")


@dataclass(frozen=True, slots=True)
class FolioTotals:
    total_debits: Decimal
    total_credits: Decimal

    @property
    def balance(self) -> Decimal:
        """What the guest still owes; negative means the hotel owes the guest."""
        return self.total_debits - self.total_credits


async def hotel_today(session: AsyncSession) -> date:
    """Today's date on the hotel's own clock."""
    hotel = await get_or_404(session, Hotel, current_hotel_id(session))
    return datetime.now(ZoneInfo(hotel.timezone)).date()


async def ensure_folio(session: AsyncSession, reservation: Reservation) -> Folio:
    """The reservation's folio, opened on first use."""
    folio = await session.scalar(select(Folio).where(Folio.reservation_id == reservation.id))
    if folio is None:
        folio = Folio(
            hotel_id=reservation.hotel_id,
            reservation_id=reservation.id,
            folio_number="F-" + "".join(secrets.choice(_FOLIO_ALPHABET) for _ in range(8)),
            status=FolioStatus.OPEN,
        )
        session.add(folio)
        await session.flush()
    return folio


async def _lock_open_folio(session: AsyncSession, folio_id: UUID) -> Folio:
    """Lock the folio so posting and closing cannot interleave."""
    folio = await session.scalar(
        select(Folio)
        .where(Folio.id == folio_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if folio is None:
        raise NotFoundError("Folio not found")
    if folio.status != FolioStatus.OPEN:
        raise ConflictError("Folio is closed; no further postings are allowed")
    return folio


async def folio_totals(session: AsyncSession, folio_id: UUID) -> FolioTotals:
    debit = case((FolioTransaction.entry_type == EntryType.DEBIT, FolioTransaction.total_amount))
    credit = case((FolioTransaction.entry_type == EntryType.CREDIT, FolioTransaction.total_amount))
    row = (
        await session.execute(
            select(func.coalesce(func.sum(debit), 0), func.coalesce(func.sum(credit), 0)).where(
                FolioTransaction.folio_id == folio_id
            )
        )
    ).one()
    return FolioTotals(
        total_debits=round_money(Decimal(row[0])), total_credits=round_money(Decimal(row[1]))
    )


async def list_transactions(session: AsyncSession, folio_id: UUID) -> list[FolioTransaction]:
    result = await session.scalars(
        select(FolioTransaction)
        .where(FolioTransaction.folio_id == folio_id)
        .order_by(FolioTransaction.created_at, FolioTransaction.id)
    )
    return list(result)


def build_room_charge(
    folio: Folio, reservation: Reservation, business_date: date, created_by: UUID | None
) -> FolioTransaction:
    """Room charge for one night, taxed by the tariff slab. Not yet persisted."""
    gst = calculate_room_gst(reservation.rate_per_night)
    return _build_line(
        folio,
        entry_type=EntryType.DEBIT,
        category=TransactionCategory.ROOM_CHARGE,
        description=f"Room charge for {business_date.isoformat()}",
        gst=gst,
        business_date=business_date,
        created_by=created_by,
        sac_code=SAC_ACCOMMODATION,
    )


def _build_line(
    folio: Folio,
    *,
    entry_type: EntryType,
    category: TransactionCategory,
    description: str,
    gst: GstBreakdown,
    business_date: date,
    created_by: UUID | None,
    sac_code: str | None = None,
    payment_method: PaymentMethod | None = None,
    reference: str | None = None,
    reverses_transaction_id: UUID | None = None,
) -> FolioTransaction:
    return FolioTransaction(
        hotel_id=folio.hotel_id,
        folio_id=folio.id,
        business_date=business_date,
        entry_type=entry_type,
        category=category,
        description=description,
        amount=gst.taxable_amount,
        gst_rate=round_money(gst.gst_rate),
        cgst_amount=gst.cgst_amount,
        sgst_amount=gst.sgst_amount,
        total_amount=gst.total_amount,
        sac_code=sac_code,
        payment_method=payment_method,
        reference=reference,
        reverses_transaction_id=reverses_transaction_id,
        created_by=created_by,
    )


async def post_charge(
    session: AsyncSession,
    folio_id: UUID,
    *,
    description: str,
    amount: Decimal,
    gst_rate: Decimal,
    sac_code: str | None,
    business_date: date | None,
    created_by: UUID,
) -> FolioTransaction:
    """Post a non-room charge (food, laundry, ...) at the GST rate supplied."""
    folio = await _lock_open_folio(session, folio_id)
    line = _build_line(
        folio,
        entry_type=EntryType.DEBIT,
        category=TransactionCategory.EXTRA_CHARGE,
        description=description,
        gst=calculate_gst(amount, gst_rate),
        business_date=business_date or await hotel_today(session),
        created_by=created_by,
        sac_code=sac_code,
    )
    session.add(line)
    await session.flush()
    return line


async def post_payment(
    session: AsyncSession,
    folio_id: UUID,
    *,
    amount: Decimal,
    payment_method: PaymentMethod,
    reference: str | None,
    created_by: UUID,
) -> FolioTransaction:
    folio = await _lock_open_folio(session, folio_id)
    line = _build_line(
        folio,
        entry_type=EntryType.CREDIT,
        category=TransactionCategory.PAYMENT,
        description=f"Payment received ({payment_method.value})",
        gst=calculate_gst(amount, _ZERO),
        business_date=await hotel_today(session),
        created_by=created_by,
        payment_method=payment_method,
        reference=reference,
    )
    session.add(line)
    await session.flush()
    return line


async def reverse_transaction(
    session: AsyncSession, folio_id: UUID, transaction_id: UUID, *, reason: str, created_by: UUID
) -> FolioTransaction:
    """Cancel a posted line by appending its mirror image. The original stays."""
    folio = await _lock_open_folio(session, folio_id)
    original = await session.get(FolioTransaction, transaction_id)
    if original is None or original.folio_id != folio.id:
        raise NotFoundError("FolioTransaction not found")
    if original.reverses_transaction_id is not None:
        raise ConflictError("A reversal cannot itself be reversed; post a new entry instead")

    reversal = FolioTransaction(
        hotel_id=folio.hotel_id,
        folio_id=folio.id,
        business_date=await hotel_today(session),
        entry_type=(
            EntryType.CREDIT if original.entry_type == EntryType.DEBIT else EntryType.DEBIT
        ),
        category=original.category,
        description=f"Reversal of '{original.description}': {reason}",
        amount=original.amount,
        gst_rate=original.gst_rate,
        cgst_amount=original.cgst_amount,
        sgst_amount=original.sgst_amount,
        total_amount=original.total_amount,
        sac_code=original.sac_code,
        payment_method=original.payment_method,
        reference=original.reference,
        reverses_transaction_id=original.id,
        created_by=created_by,
    )
    session.add(reversal)
    await flush_or_conflict(session, "This transaction has already been reversed")
    return reversal


async def close_folio(session: AsyncSession, folio_id: UUID) -> Folio:
    folio = await _lock_open_folio(session, folio_id)
    balance = (await folio_totals(session, folio.id)).balance
    if balance != 0:
        raise ConflictError(f"Folio has an outstanding balance of {balance}; settle it first")
    folio.status = FolioStatus.CLOSED
    folio.closed_at = datetime.now(UTC)
    await session.flush()
    return folio
