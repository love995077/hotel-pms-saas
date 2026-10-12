"""Reservation lifecycle. All inventory-changing operations go through here."""

import secrets
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    ConflictError,
    DuplicateBookingError,
    NotFoundError,
    UnprocessableError,
)
from app.database import current_hotel_id
from app.models import (
    INVENTORY_HOLDING_STATUSES,
    FolioStatus,
    Guest,
    Reservation,
    ReservationStatus,
    Room,
    RoomType,
)
from app.schemas.reservation import ReservationCreate, validate_stay
from app.services.availability import ensure_available
from app.services.channel_sync import request_availability_push
from app.services.crud import apply_changes, flush_or_conflict, get_or_404
from app.services.folios import close_folio, ensure_folio

# No 0/O or 1/I, so numbers survive being read over the phone.
_CONFIRMATION_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
_ROOM_TAKEN = "Room is already allocated to another stay on these dates"


def _new_confirmation_number() -> str:
    return "".join(secrets.choice(_CONFIRMATION_ALPHABET) for _ in range(10))


async def _lock_room_type(session: AsyncSession, room_type_id: UUID) -> RoomType:
    """Lock the room type row for the rest of the transaction.

    Serialises bookings of the same room type so the availability check and the
    insert that follows it cannot interleave with another booking.
    """
    room_type = await session.scalar(
        select(RoomType)
        .where(RoomType.id == room_type_id)
        .with_for_update(key_share=True)
        .execution_options(populate_existing=True)
    )
    if room_type is None:
        raise NotFoundError("RoomType not found")
    if not room_type.is_active:
        raise ConflictError("Room type is not active")
    return room_type


async def _push_availability(session: AsyncSession, reservation: Reservation) -> None:
    """Tell connected channels that the nights of this stay have changed."""
    await request_availability_push(
        session, reservation.room_type_id, reservation.check_in_date, reservation.check_out_date
    )


def _check_occupancy(room_type: RoomType, adults: int, children: int) -> None:
    if adults + children > room_type.max_occupancy:
        raise UnprocessableError(f"Room type allows at most {room_type.max_occupancy} occupants")


async def _check_room_assignable(
    session: AsyncSession, reservation: Reservation, room_id: UUID
) -> None:
    room = await get_or_404(session, Room, room_id)
    if room.room_type_id != reservation.room_type_id:
        raise UnprocessableError("Room does not belong to the reserved room type")
    if not room.is_active:
        raise ConflictError("Room is not active")

    clash = select(Reservation.id).where(
        Reservation.room_id == room_id,
        Reservation.status.in_(INVENTORY_HOLDING_STATUSES),
        Reservation.check_in_date < reservation.check_out_date,
        Reservation.check_out_date > reservation.check_in_date,
    )
    if reservation.id is not None:
        clash = clash.where(Reservation.id != reservation.id)
    if await session.scalar(clash.limit(1)) is not None:
        raise ConflictError(_ROOM_TAKEN)


async def create_reservation(session: AsyncSession, data: ReservationCreate) -> Reservation:
    room_type = await _lock_room_type(session, data.room_type_id)
    await get_or_404(session, Guest, data.guest_id)
    _check_occupancy(room_type, data.adults, data.children)
    if data.external_reference is not None:
        # Checked under the room type lock, so concurrent deliveries of the
        # same channel booking cannot both get past it.
        duplicate = await session.scalar(
            select(Reservation.id).where(
                Reservation.source == data.source,
                Reservation.external_reference == data.external_reference,
            )
        )
        if duplicate is not None:
            raise DuplicateBookingError(
                "A reservation with this source and external reference already exists"
            )
    await ensure_available(session, room_type.id, data.check_in_date, data.check_out_date)

    reservation = Reservation(
        hotel_id=current_hotel_id(session),
        confirmation_number=_new_confirmation_number(),
        guest_id=data.guest_id,
        room_type_id=room_type.id,
        check_in_date=data.check_in_date,
        check_out_date=data.check_out_date,
        adults=data.adults,
        children=data.children,
        rate_per_night=(
            data.rate_per_night if data.rate_per_night is not None else room_type.base_rate
        ),
        status=ReservationStatus.CONFIRMED,
        source=data.source,
        external_reference=data.external_reference,
        notes=data.notes,
    )
    if data.room_id is not None:
        await _check_room_assignable(session, reservation, data.room_id)
        reservation.room_id = data.room_id

    session.add(reservation)
    await flush_or_conflict(session, _ROOM_TAKEN)
    await _push_availability(session, reservation)
    return reservation


async def update_reservation(
    session: AsyncSession, reservation_id: UUID, changes: dict[str, Any]
) -> Reservation:
    reservation = await get_or_404(session, Reservation, reservation_id)
    if reservation.status != ReservationStatus.CONFIRMED:
        raise ConflictError(f"A {reservation.status} reservation cannot be modified")

    inventory_fields = {"room_type_id", "check_in_date", "check_out_date"}
    inventory_changed = any(
        field in changes and changes[field] != getattr(reservation, field)
        for field in inventory_fields
    )
    room_type_changed = (
        "room_type_id" in changes and changes["room_type_id"] != reservation.room_type_id
    )

    if "guest_id" in changes:
        await get_or_404(session, Guest, changes["guest_id"])
    previous = (reservation.room_type_id, reservation.check_in_date, reservation.check_out_date)
    apply_changes(reservation, changes)

    try:
        validate_stay(reservation.check_in_date, reservation.check_out_date)
    except ValueError as exc:
        raise UnprocessableError(str(exc)) from exc

    room_type = await _lock_room_type(session, reservation.room_type_id)
    _check_occupancy(room_type, reservation.adults, reservation.children)

    if inventory_changed:
        await ensure_available(
            session,
            room_type.id,
            reservation.check_in_date,
            reservation.check_out_date,
            exclude_reservation_id=reservation.id,
        )
        if room_type_changed:
            # The assigned room belongs to the old type; it must be re-assigned.
            reservation.room_id = None
        elif reservation.room_id is not None:
            await _check_room_assignable(session, reservation, reservation.room_id)

    await flush_or_conflict(session, _ROOM_TAKEN)
    if inventory_changed:
        # The nights it used to hold are free again; the nights it holds now are not.
        await request_availability_push(session, *previous)
        await _push_availability(session, reservation)
    return reservation


async def assign_room(session: AsyncSession, reservation_id: UUID, room_id: UUID) -> Reservation:
    reservation = await get_or_404(session, Reservation, reservation_id)
    if reservation.status not in INVENTORY_HOLDING_STATUSES:
        raise ConflictError(f"Cannot assign a room to a {reservation.status} reservation")
    await _check_room_assignable(session, reservation, room_id)
    reservation.room_id = room_id
    await flush_or_conflict(session, _ROOM_TAKEN)
    return reservation


async def _transition(
    session: AsyncSession,
    reservation_id: UUID,
    *,
    expected: ReservationStatus,
    target: ReservationStatus,
) -> Reservation:
    reservation = await get_or_404(session, Reservation, reservation_id)
    if reservation.status != expected:
        raise ConflictError(
            f"Reservation is {reservation.status}; it must be {expected} to become {target}"
        )
    if target == ReservationStatus.CHECKED_IN and reservation.room_id is None:
        raise ConflictError("Assign a room before check-in")
    was_holding = reservation.status in INVENTORY_HOLDING_STATUSES
    reservation.status = target
    await session.flush()
    if was_holding != (target in INVENTORY_HOLDING_STATUSES):
        await _push_availability(session, reservation)
    return reservation


async def cancel_reservation(session: AsyncSession, reservation_id: UUID) -> Reservation:
    """Cancel, releasing inventory. The record itself is kept."""
    return await _transition(
        session,
        reservation_id,
        expected=ReservationStatus.CONFIRMED,
        target=ReservationStatus.CANCELLED,
    )


async def check_in(session: AsyncSession, reservation_id: UUID) -> Reservation:
    reservation = await _transition(
        session,
        reservation_id,
        expected=ReservationStatus.CONFIRMED,
        target=ReservationStatus.CHECKED_IN,
    )
    # The stay starts accruing charges, so it needs its folio.
    await ensure_folio(session, reservation)
    return reservation


async def check_out(session: AsyncSession, reservation_id: UUID) -> Reservation:
    """Check out. The folio must be settled; it is closed as part of check-out."""
    reservation = await get_or_404(session, Reservation, reservation_id)
    if reservation.status == ReservationStatus.CHECKED_IN:
        folio = await ensure_folio(session, reservation)
        if folio.status == FolioStatus.OPEN:
            await close_folio(session, folio.id)
    return await _transition(
        session,
        reservation_id,
        expected=ReservationStatus.CHECKED_IN,
        target=ReservationStatus.CHECKED_OUT,
    )
