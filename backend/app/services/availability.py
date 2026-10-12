"""Inventory availability engine.

Inventory is counted per room type, not per physical room: on any night,

    available = active rooms of the type - reservations holding inventory

A reservation holds the nights from check_in_date up to, but not including,
check_out_date, so a departure and an arrival can share a calendar day.
"""

from dataclasses import dataclass
from datetime import date, timedelta
from uuid import UUID

from sqlalchemy import Date, Integer, and_, column, func, literal, select, true
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, UnprocessableError
from app.models import INVENTORY_HOLDING_STATUSES, Reservation, Room, RoomType

MAX_RANGE_NIGHTS = 366


@dataclass(frozen=True, slots=True)
class NightAvailability:
    room_type_id: UUID
    night: date
    total_rooms: int
    booked: int

    @property
    def available(self) -> int:
        return self.total_rooms - self.booked


async def get_availability(
    session: AsyncSession,
    start: date,
    end: date,
    *,
    room_type_id: UUID | None = None,
    exclude_reservation_id: UUID | None = None,
) -> list[NightAvailability]:
    """Availability for every night in [start, end), for every active room type.

    One SQL statement regardless of how many room types or nights are involved:
    a generated series of nights is joined to the room types and the overlapping
    reservations are counted per (room type, night).
    """
    nights = (end - start).days
    if nights < 1:
        raise UnprocessableError("end date must be after start date")
    if nights > MAX_RANGE_NIGHTS:
        raise UnprocessableError(f"Date range cannot exceed {MAX_RANGE_NIGHTS} nights")

    offsets = (
        func.generate_series(0, nights - 1)
        .table_valued(column("n", Integer), name="offsets")
        .render_derived()
    )
    night = literal(start, Date) + offsets.c.n

    room_totals = (
        select(Room.room_type_id, func.count().label("total"))
        .where(Room.is_active)
        .group_by(Room.room_type_id)
        .subquery()
    )

    holds_night = and_(
        Reservation.room_type_id == RoomType.id,
        Reservation.status.in_(INVENTORY_HOLDING_STATUSES),
        Reservation.check_in_date <= night,
        Reservation.check_out_date > night,
    )
    if exclude_reservation_id is not None:
        holds_night = and_(holds_night, Reservation.id != exclude_reservation_id)

    statement = (
        select(
            RoomType.id,
            offsets.c.n,
            func.coalesce(room_totals.c.total, 0),
            func.count(Reservation.id),
        )
        .select_from(RoomType)
        .join(offsets, true())
        .outerjoin(room_totals, room_totals.c.room_type_id == RoomType.id)
        .outerjoin(Reservation, holds_night)
        .where(RoomType.is_active)
        .group_by(RoomType.id, offsets.c.n, room_totals.c.total)
        .order_by(RoomType.id, offsets.c.n)
    )
    if room_type_id is not None:
        statement = statement.where(RoomType.id == room_type_id)

    result = await session.execute(statement)
    return [
        NightAvailability(
            room_type_id=type_id,
            night=start + timedelta(days=offset),
            total_rooms=total,
            booked=booked,
        )
        for type_id, offset, total, booked in result
    ]


async def ensure_available(
    session: AsyncSession,
    room_type_id: UUID,
    check_in: date,
    check_out: date,
    *,
    exclude_reservation_id: UUID | None = None,
) -> None:
    """Raise ConflictError unless one more stay fits on every night.

    The caller must hold the room type's row lock, otherwise two concurrent
    bookings can both pass this check for the last room.
    """
    nights = await get_availability(
        session,
        check_in,
        check_out,
        room_type_id=room_type_id,
        exclude_reservation_id=exclude_reservation_id,
    )
    sold_out = next((n for n in nights if n.available < 1), None)
    if not nights or sold_out is not None:
        when = f" on {sold_out.night.isoformat()}" if sold_out else ""
        raise ConflictError(f"No availability for this room type{when}")
