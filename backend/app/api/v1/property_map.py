from datetime import date, timedelta
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import and_, or_, select

from app.api.deps import DbSession, get_current_user
from app.models import Guest, Reservation, ReservationStatus, Room, RoomType
from app.schemas.property_map import (
    PropertyMapRead,
    PropertyMapRoomType,
    PropertyMapUnit,
    UnitStatus,
)
from app.schemas.tape_chart import TapeChartReservation
from app.services.availability import get_availability

router = APIRouter(
    prefix="/property-map", tags=["property map"], dependencies=[Depends(get_current_user)]
)


def _reservation(reservation: Reservation, guest_name: str) -> TapeChartReservation:
    return TapeChartReservation(
        id=reservation.id,
        confirmation_number=reservation.confirmation_number,
        guest_id=reservation.guest_id,
        guest_name=guest_name,
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


@router.get("", response_model=PropertyMapRead)
async def property_map(db: DbSession, day: Annotated[date, Query(alias="date")]) -> PropertyMapRead:
    """Every room and what is in it on one day, for the Property Map. Four queries.

    A room is occupied while a checked-in guest holds it, including on the day
    they are due to leave; reserved when a confirmed stay is assigned to it for
    that night; out of order when it is deactivated.
    """
    nights = {
        night.room_type_id: night
        for night in await get_availability(db, day, day + timedelta(days=1))
    }
    room_types = list(
        await db.scalars(select(RoomType).where(RoomType.is_active).order_by(RoomType.name))
    )
    active_type_ids = {room_type.id for room_type in room_types}

    statement = (
        select(Reservation, Guest.first_name, Guest.last_name)
        .join(Guest, Guest.id == Reservation.guest_id)
        .where(
            or_(
                and_(
                    Reservation.status == ReservationStatus.CONFIRMED,
                    Reservation.check_in_date <= day,
                    Reservation.check_out_date > day,
                ),
                and_(
                    Reservation.status == ReservationStatus.CHECKED_IN,
                    Reservation.check_in_date <= day,
                    Reservation.check_out_date >= day,
                ),
            )
        )
        .order_by(Reservation.check_in_date, Reservation.id)
    )
    in_rooms: dict[UUID, TapeChartReservation] = {}
    unassigned: list[TapeChartReservation] = []
    for reservation, first_name, last_name in await db.execute(statement):
        stay = _reservation(reservation, f"{first_name} {last_name}")
        if reservation.room_id is None:
            if reservation.status == ReservationStatus.CONFIRMED:
                unassigned.append(stay)
            continue
        current = in_rooms.get(reservation.room_id)
        # A guest still in the room outranks the next arrival assigned to it.
        if current is None or stay.status == ReservationStatus.CHECKED_IN:
            in_rooms[reservation.room_id] = stay

    units: list[PropertyMapUnit] = []
    for room in await db.scalars(select(Room).order_by(Room.room_number)):
        if room.room_type_id not in active_type_ids:
            continue
        held = in_rooms.get(room.id)
        if not room.is_active:
            status = UnitStatus.OUT_OF_ORDER
        elif held is None:
            status = UnitStatus.AVAILABLE
        elif held.status == ReservationStatus.CHECKED_IN:
            status = UnitStatus.OCCUPIED
        else:
            status = UnitStatus.RESERVED
        units.append(
            PropertyMapUnit(
                id=room.id,
                room_number=room.room_number,
                floor_or_zone=room.floor_or_zone,
                room_type_id=room.room_type_id,
                is_active=room.is_active,
                status=status,
                reservation=held,
            )
        )

    return PropertyMapRead(
        date=day,
        room_types=[
            PropertyMapRoomType(
                id=room_type.id,
                name=room_type.name,
                code=room_type.code,
                base_rate=room_type.base_rate,
                max_occupancy=room_type.max_occupancy,
                total_rooms=nights[room_type.id].total_rooms if room_type.id in nights else 0,
                available=nights[room_type.id].available if room_type.id in nights else 0,
            )
            for room_type in room_types
        ],
        units=units,
        unassigned=unassigned,
    )
