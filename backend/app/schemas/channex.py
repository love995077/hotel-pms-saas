"""Channex.io payloads (inbound) and the PMS's Channex settings.

Field names follow Channex's booking revision object. Unknown fields are
ignored: Channex adds fields without notice, and OTAs fill them unevenly.
"""

from datetime import date
from decimal import Decimal
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    TypeAdapter,
    ValidationError,
    field_validator,
)

from app.models import ReservationStatus

# Channex ids are UUIDs; anything else is refused before it reaches a query.
ChannexId = Annotated[str, Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9-]+$")]

# Webhook events that carry a booking revision; any other event is acknowledged and ignored.
BOOKING_EVENTS = frozenset(
    {"booking", "booking_new", "booking_modification", "booking_cancellation"}
)

_email = TypeAdapter(EmailStr)


class _Lenient(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)


class ChannexWebhook(_Lenient):
    """The envelope Channex POSTs to a webhook URL.

    Deliberately forgiving: Channex's "Send test message" and event types we do
    not handle come in other shapes, and refusing them would hide them from the
    delivery log. Only booking events need more, and the booking revision is
    validated strictly when it is read.
    """

    event: str = "unknown"
    property_id: str | None = None
    timestamp: Any = None
    # booking_id, revision_id and property_id; with "send data" enabled on the
    # Channex webhook, also the booking revision itself.
    payload: dict[str, Any] = Field(default_factory=dict)

    @field_validator("event", mode="before")
    @classmethod
    def _event_name(cls, value: Any) -> str:
        name = "" if value is None else str(value).strip()
        # Stored in a 40-character column.
        return name[:40] if name else "unknown"

    @field_validator("property_id", mode="before")
    @classmethod
    def _property_id(cls, value: Any) -> str | None:
        return None if value is None else str(value)

    @field_validator("payload", mode="before")
    @classmethod
    def _payload_object(cls, value: Any) -> dict[str, Any]:
        # The raw body is kept in the delivery log, so nothing is lost here.
        return value if isinstance(value, dict) else {}


class ChannexOccupancy(_Lenient):
    adults: int = Field(default=1, ge=0)
    children: int = Field(default=0, ge=0)
    infants: int = Field(default=0, ge=0)


class ChannexCustomer(_Lenient):
    name: str | None = Field(default=None, max_length=100)
    surname: str | None = Field(default=None, max_length=100)
    mail: str | None = None
    phone: str | None = Field(default=None, max_length=32)

    def valid_email(self) -> str | None:
        """OTAs sometimes send a placeholder; a bad address must not lose the booking."""
        if not self.mail:
            return None
        try:
            return str(_email.validate_python(self.mail))
        except ValidationError:
            return None


class ChannexRevisionRoom(_Lenient):
    room_type_id: ChannexId
    rate_plan_id: str | None = None
    # Per-room dates; Channex falls back to the booking's when they match.
    checkin_date: date | None = None
    checkout_date: date | None = None
    # Total for this room for the whole stay, in the booking's currency.
    amount: Decimal | None = Field(default=None, ge=0)
    occupancy: ChannexOccupancy = Field(default_factory=ChannexOccupancy)


class ChannexBookingRevision(_Lenient):
    id: ChannexId
    booking_id: ChannexId
    property_id: ChannexId
    status: Literal["new", "modified", "cancelled"]
    ota_name: str | None = Field(default=None, max_length=100)
    ota_reservation_code: str | None = Field(default=None, max_length=100)
    arrival_date: date
    departure_date: date
    currency: str | None = Field(default=None, max_length=3)
    amount: Decimal | None = None
    customer: ChannexCustomer = Field(default_factory=ChannexCustomer)
    rooms: list[ChannexRevisionRoom] = Field(default_factory=list, max_length=50)
    notes: str | None = None


class ChannexReservationRef(BaseModel):
    reservation_id: UUID
    confirmation_number: str
    status: ReservationStatus


class ChannexWebhookResult(BaseModel):
    result: Literal["created", "modified", "cancelled", "unchanged", "ignored"]
    booking_id: str | None = None
    revision_id: str | None = None
    reservations: list[ChannexReservationRef] = Field(default_factory=list)


# --- room type mapping --------------------------------------------------------


class ChannexMappingItem(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    room_type_id: UUID
    channex_room_type_id: ChannexId
    # Set to have "Sync now" push this room type's base rate to the plan.
    channex_rate_plan_id: ChannexId | None = None


class ChannexMappingRead(ChannexMappingItem):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
