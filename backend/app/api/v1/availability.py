from datetime import date
from itertools import groupby
from uuid import UUID

from fastapi import APIRouter, Depends

from app.api.deps import DbSession, get_current_user
from app.schemas.inventory import DayAvailabilityRead, RoomTypeAvailabilityRead
from app.services.availability import get_availability

router = APIRouter(
    prefix="/availability", tags=["availability"], dependencies=[Depends(get_current_user)]
)


@router.get("", response_model=list[RoomTypeAvailabilityRead])
async def read_availability(
    db: DbSession, start: date, end: date, room_type_id: UUID | None = None
) -> list[RoomTypeAvailabilityRead]:
    """Rooms left per room type for each night from `start` up to, not including, `end`."""
    nights = await get_availability(db, start, end, room_type_id=room_type_id)
    response = []
    for type_id, group in groupby(nights, key=lambda night: night.room_type_id):
        days = [
            DayAvailabilityRead(
                date=n.night, total_rooms=n.total_rooms, booked=n.booked, available=n.available
            )
            for n in group
        ]
        response.append(
            RoomTypeAvailabilityRead(
                room_type_id=type_id,
                available_for_stay=max(0, min(day.available for day in days)),
                days=days,
            )
        )
    return response
