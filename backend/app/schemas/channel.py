from datetime import date, datetime
from typing import Annotated, Any, ClassVar, Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

from app.config import get_settings
from app.core.outbound import MAX_URL_LENGTH, validate_outbound_url
from app.models import BookingSource, ChannelProvider, ReservationStatus, WebhookEventStatus
from app.schemas.base import CreateSchema, PatchSchema, ReadSchema
from app.schemas.inventory import Money
from app.schemas.reservation import validate_stay

# --- webhook payloads ---------------------------------------------------------


class _ChannelEvent(BaseModel):
    # Unknown fields are ignored: channel managers add fields without notice.
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    # The OTA the booking was made on.
    channel: BookingSource
    # The booking's id on that OTA; identifies it across redeliveries.
    booking_id: str = Field(min_length=1, max_length=100)


class ChannelGuest(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=32)


class BookingCreatedEvent(_ChannelEvent):
    event: Literal["booking.created"]
    # The hotel's own room type code (RoomType.code).
    room_type_code: str = Field(min_length=1, max_length=20)
    check_in_date: date
    check_out_date: date
    adults: int = Field(default=1, ge=1)
    children: int = Field(default=0, ge=0)
    # Per night, before tax. Defaults to the room type's base rate.
    rate_per_night: Money | None = None
    guest: ChannelGuest
    notes: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def _dates_valid(self) -> Self:
        validate_stay(self.check_in_date, self.check_out_date)
        return self


class BookingCancelledEvent(_ChannelEvent):
    event: Literal["booking.cancelled"]


ChannelEvent = Annotated[BookingCreatedEvent | BookingCancelledEvent, Field(discriminator="event")]


class WebhookResult(BaseModel):
    result: Literal["created", "cancelled", "duplicate"]
    reservation_id: UUID
    confirmation_number: str
    reservation_status: ReservationStatus


# --- connection management ----------------------------------------------------


# The hotel's id on the provider: a Channex property id is a UUID.
PropertyId = Annotated[str, Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9-]+$")]


class ChannelConnectionCreate(CreateSchema):
    name: str = Field(min_length=1, max_length=100)
    provider: ChannelProvider = ChannelProvider.GENERIC
    # Required for Channex: the property id Channex shows for this hotel.
    external_property_id: PropertyId | None = None

    @model_validator(mode="after")
    def _property_id_matches_provider(self) -> Self:
        if self.provider == ChannelProvider.CHANNEX and self.external_property_id is None:
            raise ValueError("external_property_id is required for a Channex connection")
        if self.provider == ChannelProvider.GENERIC and self.external_property_id is not None:
            raise ValueError("external_property_id is only used by Channex connections")
        return self


class ChannelConnectionUpdate(PatchSchema):
    nullable_fields: ClassVar[frozenset[str]] = frozenset({"outbound_url"})

    name: str | None = Field(default=None, min_length=1, max_length=100)
    is_active: bool | None = None
    # Where availability updates are pushed. Null (or blank) turns pushing off.
    outbound_url: str | None = Field(default=None, max_length=MAX_URL_LENGTH)
    # Channex only: for when the property id changes (for example going live).
    external_property_id: PropertyId | None = None

    @field_validator("outbound_url")
    @classmethod
    def _outbound_url_is_safe(cls, value: str | None) -> str | None:
        if value is None or value == "":
            return None
        # OutboundUrlError is a ValueError, so its message becomes the 422 detail.
        return validate_outbound_url(
            value, allow_private=get_settings().channel_outbound_allow_private_hosts
        )


class ChannelConnectionRead(ReadSchema):
    name: str
    provider: ChannelProvider
    external_property_id: str | None
    key_id: str
    is_active: bool
    outbound_url: str | None
    last_push_at: datetime | None
    last_push_ok: bool | None
    last_push_detail: str | None


class OutboundTestResult(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    ok: bool
    # Null when the endpoint could not be reached at all.
    status_code: int | None
    detail: str
    duration_ms: int


class SyncQueued(BaseModel):
    room_types_queued: int


class ChannelConnectionCreated(ChannelConnectionRead):
    # Returned once, when the connection is created.
    signing_secret: str


class ChannelWebhookEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    connection_id: UUID
    event_type: str
    channel: str
    external_booking_id: str
    status: WebhookEventStatus
    detail: str | None
    reservation_id: UUID | None
    payload: dict[str, Any]
    received_at: datetime
