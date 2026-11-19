from datetime import date
from decimal import Decimal
from typing import Annotated, ClassVar, Self
from uuid import UUID

from pydantic import AfterValidator, BaseModel, Field, model_validator

from app.models import UnitKind
from app.schemas.base import CreateSchema, PatchSchema, ReadSchema

Money = Annotated[Decimal, Field(ge=0, max_digits=12, decimal_places=2)]


def _trimmed_or_none(value: str | None) -> str | None:
    value = value.strip() if value is not None else None
    return value or None


# A floor, zone, dormitory or block. Blank means "derive one from the room number".
GroupName = Annotated[str | None, Field(max_length=50), AfterValidator(_trimmed_or_none)]


class RoomTypeCreate(CreateSchema):
    name: str = Field(min_length=1, max_length=100)
    code: str = Field(min_length=1, max_length=20)
    description: str | None = None
    base_occupancy: int = Field(default=2, ge=1)
    max_occupancy: int = Field(default=2, ge=1)
    base_rate: Money
    # Left out: derived from the property type (villa, flat, otherwise room).
    unit_kind: UnitKind | None = None

    @model_validator(mode="after")
    def _occupancy_consistent(self) -> Self:
        if self.max_occupancy < self.base_occupancy:
            raise ValueError("max_occupancy must be at least base_occupancy")
        return self


class RoomTypeUpdate(PatchSchema):
    nullable_fields: ClassVar[frozenset[str]] = frozenset({"description"})

    name: str | None = Field(default=None, min_length=1, max_length=100)
    code: str | None = Field(default=None, min_length=1, max_length=20)
    description: str | None = None
    base_occupancy: int | None = Field(default=None, ge=1)
    max_occupancy: int | None = Field(default=None, ge=1)
    base_rate: Money | None = None
    unit_kind: UnitKind | None = None
    is_active: bool | None = None


class RoomTypeRead(ReadSchema):
    name: str
    code: str
    description: str | None
    base_occupancy: int
    max_occupancy: int
    base_rate: Decimal
    unit_kind: UnitKind
    is_active: bool


class RoomCreate(CreateSchema):
    room_type_id: UUID
    room_number: str = Field(min_length=1, max_length=20)
    floor_or_zone: GroupName = None


class RoomUpdate(PatchSchema):
    nullable_fields: ClassVar[frozenset[str]] = frozenset({"floor_or_zone"})

    room_type_id: UUID | None = None
    room_number: str | None = Field(default=None, min_length=1, max_length=20)
    floor_or_zone: GroupName = None
    is_active: bool | None = None


class RoomRead(ReadSchema):
    room_type_id: UUID
    room_number: str
    floor_or_zone: str | None
    is_active: bool


class DayAvailabilityRead(BaseModel):
    date: date
    total_rooms: int
    booked: int
    available: int


class RoomTypeAvailabilityRead(BaseModel):
    room_type_id: UUID
    # Rooms bookable for the whole requested stay: the minimum over its nights.
    available_for_stay: int
    days: list[DayAvailabilityRead]
