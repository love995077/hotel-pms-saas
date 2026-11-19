from datetime import date
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel

from app.schemas.tape_chart import TapeChartReservation


class UnitStatus(StrEnum):
    AVAILABLE = "available"
    # A guest is checked in (including one due to leave that day).
    OCCUPIED = "occupied"
    # A confirmed stay is assigned to the room for that night.
    RESERVED = "reserved"
    # The room is deactivated in Settings, so it is not sold.
    OUT_OF_ORDER = "out_of_order"


class PropertyMapUnit(BaseModel):
    id: UUID
    room_number: str
    floor_or_zone: str | None
    room_type_id: UUID
    is_active: bool
    status: UnitStatus
    reservation: TapeChartReservation | None


class PropertyMapRoomType(BaseModel):
    id: UUID
    name: str
    code: str
    base_rate: Decimal
    max_occupancy: int
    # Sellable on the night of `date`, counted per room type like everywhere else.
    total_rooms: int
    available: int


class PropertyMapRead(BaseModel):
    date: date
    room_types: list[PropertyMapRoomType]
    units: list[PropertyMapUnit]
    # Confirmed stays covering `date` that still need a room.
    unassigned: list[TapeChartReservation]
