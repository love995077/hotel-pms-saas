from datetime import date
from decimal import Decimal
from typing import ClassVar, Self
from uuid import UUID

from pydantic import Field, model_validator

from app.models import BookingSource, ReservationStatus
from app.schemas.base import CreateSchema, PatchSchema, ReadSchema
from app.schemas.inventory import Money

MAX_STAY_NIGHTS = 365


def validate_stay(check_in: date, check_out: date) -> None:
    if check_out <= check_in:
        raise ValueError("check_out_date must be after check_in_date")
    if (check_out - check_in).days > MAX_STAY_NIGHTS:
        raise ValueError(f"A stay cannot exceed {MAX_STAY_NIGHTS} nights")


class ReservationCreate(CreateSchema):
    guest_id: UUID
    room_type_id: UUID
    # Optional: a physical room may be assigned any time up to check-in.
    room_id: UUID | None = None
    check_in_date: date
    check_out_date: date
    adults: int = Field(default=1, ge=1)
    children: int = Field(default=0, ge=0)
    # Defaults to the room type's base rate.
    rate_per_night: Money | None = None
    source: BookingSource = BookingSource.DIRECT
    external_reference: str | None = Field(default=None, max_length=100)
    notes: str | None = None

    @model_validator(mode="after")
    def _dates_valid(self) -> Self:
        validate_stay(self.check_in_date, self.check_out_date)
        return self


class ReservationUpdate(PatchSchema):
    nullable_fields: ClassVar[frozenset[str]] = frozenset({"external_reference", "notes"})

    guest_id: UUID | None = None
    room_type_id: UUID | None = None
    check_in_date: date | None = None
    check_out_date: date | None = None
    adults: int | None = Field(default=None, ge=1)
    children: int | None = Field(default=None, ge=0)
    rate_per_night: Money | None = None
    source: BookingSource | None = None
    external_reference: str | None = Field(default=None, max_length=100)
    notes: str | None = None


class RoomAssignment(CreateSchema):
    room_id: UUID


class ReservationRead(ReadSchema):
    confirmation_number: str
    guest_id: UUID
    room_type_id: UUID
    room_id: UUID | None
    check_in_date: date
    check_out_date: date
    adults: int
    children: int
    rate_per_night: Decimal
    status: ReservationStatus
    source: BookingSource
    external_reference: str | None
    notes: str | None
