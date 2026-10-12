from collections import defaultdict
from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import select

from app.api.deps import DbSession, get_current_user
from app.models import Guest, Reservation, ReservationStatus, Room, RoomType
from app.schemas.inventory import DayAvailabilityRead
from app.schemas.tape_chart import (
    TapeChartRead,
    TapeChartReservation,
    TapeChartRoom,
    TapeChartRoomType,
)
from app.services.availability import get_availability

router = APIRouter(
    prefix="/tape-chart", tags=["tape chart"], dependencies=[Depends(get_current_user)]
)

_RELEASED = (ReservationStatus.CANCELLED, ReservationStatus.NO_SHOW)


@router.get("", response_model=TapeChartRead)
async def tape_chart(
    db: DbSession, start: date, end: date, include_released: bool = False
) -> TapeChartRead:
    """Everything the tape chart needs for nights from `start` up to, not including, `end`.

    Four queries in total, however many rooms and reservations there are.
    Cancelled and no-show reservations are left out unless `include_released`.
    """
    nights = await get_availability(db, start, end)
    availability: dict[UUID, list[DayAvailabilityRead]] = defaultdict(list)
    for night in nights:
        availability[night.room_type_id].append(
            DayAvailabilityRead(
                date=night.night,
                total_rooms=night.total_rooms,
                booked=night.booked,
                available=night.available,
            )
        )

    rooms: dict[UUID, list[TapeChartRoom]] = defaultdict(list)
    for room in await db.scalars(select(Room).where(Room.is_active).order_by(Room.room_number)):
        rooms[room.room_type_id].append(
            TapeChartRoom(id=room.id, room_number=room.room_number, floor=room.floor)
        )

    room_types = await db.scalars(
        select(RoomType).where(RoomType.is_active).order_by(RoomType.name)
    )

    statement = (
        select(Reservation, Guest.first_name, Guest.last_name)
        .join(Guest, Guest.id == Reservation.guest_id)
        .where(Reservation.check_in_date < end, Reservation.check_out_date > start)
        .order_by(Reservation.check_in_date, Reservation.id)
    )
    if not include_released:
        statement = statement.where(Reservation.status.not_in(_RELEASED))

    return TapeChartRead(
        start=start,
        end=end,
        room_types=[
            TapeChartRoomType(
                id=room_type.id,
                name=room_type.name,
                code=room_type.code,
                rooms=rooms[room_type.id],
                availability=availability[room_type.id],
            )
            for room_type in room_types
        ],
        reservations=[
            TapeChartReservation(
                id=reservation.id,
                confirmation_number=reservation.confirmation_number,
                guest_id=reservation.guest_id,
                guest_name=f"{first_name} {last_name}",
                room_type_id=reservation.room_type_id,
                room_id=reservation.room_id,
                check_in_date=reservation.check_in_date,
                check_out_date=reservation.check_out_date,
                adults=reservation.adults,
                children=reservation.children,
                rate_per_night=reservation.rate_per_night,
                status=ReservationStatus(reservation.status),
                source=reservation.source,
            )
            for reservation, first_name, last_name in await db.execute(statement)
        ],
    )
