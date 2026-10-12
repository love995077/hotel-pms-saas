from datetime import date
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel

from app.models import BookingSource, ReservationStatus
from app.schemas.inventory import DayAvailabilityRead


class TapeChartRoom(BaseModel):
    id: UUID
    room_number: str
    floor: str | None


class TapeChartRoomType(BaseModel):
    id: UUID
    name: str
    code: str
    rooms: list[TapeChartRoom]
    # One entry per night in the requested window.
    availability: list[DayAvailabilityRead]


class TapeChartReservation(BaseModel):
    id: UUID
    confirmation_number: str
    guest_id: UUID
    guest_name: str
    room_type_id: UUID
    # Null until a physical room is assigned.
    room_id: UUID | None
    check_in_date: date
    check_out_date: date
    adults: int
    children: int
    rate_per_night: Decimal
    status: ReservationStatus
    source: BookingSource


class TapeChartRead(BaseModel):
    start: date
    end: date
    room_types: list[TapeChartRoomType]
    reservations: list[TapeChartReservation]
