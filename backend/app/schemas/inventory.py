from datetime import date
from decimal import Decimal
from typing import Annotated, ClassVar, Self
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from app.schemas.base import CreateSchema, PatchSchema, ReadSchema

Money = Annotated[Decimal, Field(ge=0, max_digits=12, decimal_places=2)]


class RoomTypeCreate(CreateSchema):
    name: str = Field(min_length=1, max_length=100)
    code: str = Field(min_length=1, max_length=20)
    description: str | None = None
    base_occupancy: int = Field(default=2, ge=1)
    max_occupancy: int = Field(default=2, ge=1)
    base_rate: Money

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
    is_active: bool | None = None


class RoomTypeRead(ReadSchema):
    name: str
    code: str
    description: str | None
    base_occupancy: int
    max_occupancy: int
    base_rate: Decimal
    is_active: bool


class RoomCreate(CreateSchema):
    room_type_id: UUID
    room_number: str = Field(min_length=1, max_length=20)
    floor: str | None = Field(default=None, max_length=20)


class RoomUpdate(PatchSchema):
    nullable_fields: ClassVar[frozenset[str]] = frozenset({"floor"})

    room_type_id: UUID | None = None
    room_number: str | None = Field(default=None, min_length=1, max_length=20)
    floor: str | None = Field(default=None, max_length=20)
    is_active: bool | None = None


class RoomRead(ReadSchema):
    room_type_id: UUID
    room_number: str
    floor: str | None
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
