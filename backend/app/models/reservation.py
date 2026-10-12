from datetime import date
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    Date,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    column,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ExcludeConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import (
    Base,
    TenantMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
    enum_values_sql,
)


class ReservationStatus(StrEnum):
    CONFIRMED = "confirmed"
    CHECKED_IN = "checked_in"
    CHECKED_OUT = "checked_out"
    CANCELLED = "cancelled"
    NO_SHOW = "no_show"


class BookingSource(StrEnum):
    DIRECT = "direct"
    WALK_IN = "walk_in"
    PHONE = "phone"
    WEBSITE = "website"
    BOOKING_COM = "booking_com"
    MAKEMYTRIP = "makemytrip"
    GOIBIBO = "goibibo"
    AGODA = "agoda"
    EXPEDIA = "expedia"
    AIRBNB = "airbnb"
    CORPORATE = "corporate"
    TRAVEL_AGENT = "travel_agent"
    OTHER = "other"


# Statuses that hold inventory. Anything else frees the room type for resale.
INVENTORY_HOLDING_STATUSES = (ReservationStatus.CONFIRMED, ReservationStatus.CHECKED_IN)
_HOLDING_SQL = "status IN ('confirmed', 'checked_in')"


class Reservation(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    """A booking against a room type. A physical room is assigned by check-in.

    A stay occupies the nights from check_in_date up to, but not including,
    check_out_date.
    """

    __tablename__ = "reservations"
    __table_args__ = (
        UniqueConstraint("hotel_id", "confirmation_number"),
        UniqueConstraint("hotel_id", "id"),
        # Foreign-key checks bypass RLS, so the hotel is part of every key.
        ForeignKeyConstraint(
            ["hotel_id", "guest_id"],
            ["guests.hotel_id", "guests.id"],
            name="fk_reservations_guest_id_guests",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["hotel_id", "room_type_id"],
            ["room_types.hotel_id", "room_types.id"],
            name="fk_reservations_room_type_id_room_types",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["hotel_id", "room_id"],
            ["rooms.hotel_id", "rooms.id"],
            name="fk_reservations_room_id_rooms",
            ondelete="RESTRICT",
        ),
        CheckConstraint("check_out_date > check_in_date", name="dates_valid"),
        CheckConstraint("adults >= 1", name="adults_positive"),
        CheckConstraint("children >= 0", name="children_non_negative"),
        CheckConstraint("rate_per_night >= 0", name="rate_non_negative"),
        CheckConstraint(f"status IN ({enum_values_sql(ReservationStatus)})", name="status_valid"),
        CheckConstraint(f"source IN ({enum_values_sql(BookingSource)})", name="source_valid"),
        # Last line of defence against double-allocating a physical room.
        ExcludeConstraint(
            (column("room_id"), "="),
            (func.daterange(column("check_in_date"), column("check_out_date")), "&&"),
            where=text(f"room_id IS NOT NULL AND {_HOLDING_SQL}"),
            using="gist",
            name="ex_reservations_room_no_overlap",
        ),
        # Serves the availability engine's date-range scan.
        Index(
            "ix_reservations_inventory",
            "hotel_id",
            "room_type_id",
            "check_in_date",
            "check_out_date",
            postgresql_where=text(_HOLDING_SQL),
        ),
        # One reservation per channel booking: makes webhook redelivery harmless.
        Index(
            "uq_reservations_external_reference",
            "hotel_id",
            "source",
            "external_reference",
            unique=True,
            postgresql_where=text("external_reference IS NOT NULL"),
        ),
    )

    confirmation_number: Mapped[str] = mapped_column(String(20))
    guest_id: Mapped[UUID] = mapped_column(Uuid, index=True)
    room_type_id: Mapped[UUID] = mapped_column(Uuid)
    room_id: Mapped[UUID | None] = mapped_column(Uuid)
    check_in_date: Mapped[date] = mapped_column(Date)
    check_out_date: Mapped[date] = mapped_column(Date)
    adults: Mapped[int] = mapped_column(Integer, server_default=text("1"))
    children: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    # Tariff per night, before tax, agreed at booking time.
    rate_per_night: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    status: Mapped[ReservationStatus] = mapped_column(
        String(20), server_default=text("'confirmed'")
    )
    source: Mapped[BookingSource] = mapped_column(String(20), server_default=text("'direct'"))
    # Booking id on the originating channel (OTA), when there is one.
    external_reference: Mapped[str | None] = mapped_column(String(100))
    notes: Mapped[str | None] = mapped_column(Text)
