from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Index,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import (
    Base,
    TenantMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
    enum_values_sql,
)


class WebhookEventStatus(StrEnum):
    PROCESSED = "processed"
    # A redelivery of something already applied; nothing changed.
    DUPLICATE = "duplicate"
    REJECTED = "rejected"


class ChannelProvider(StrEnum):
    # Our own signed webhook protocol (see app/api/v1/webhooks.py).
    GENERIC = "generic"
    # Channex.io: Channex's booking webhooks in, Channex ARI API calls out.
    CHANNEX = "channex"


class ChannelConnection(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    """Credentials a channel manager uses to deliver webhooks for one hotel."""

    __tablename__ = "channel_connections"
    __table_args__ = (
        UniqueConstraint("hotel_id", "id"),
        CheckConstraint(f"provider IN ({enum_values_sql(ChannelProvider)})", name="provider_valid"),
        CheckConstraint(
            "provider <> 'channex' OR external_property_id IS NOT NULL",
            name="channex_property_required",
        ),
        # A hotel is one Channex property, so it has at most one Channex connection.
        Index(
            "uq_channel_connections_one_channex",
            "hotel_id",
            unique=True,
            postgresql_where=text("provider = 'channex'"),
        ),
    )

    name: Mapped[str] = mapped_column(String(100))
    provider: Mapped[ChannelProvider] = mapped_column(String(20), server_default=text("'generic'"))
    # The hotel's id on the provider (the Channex property id).
    external_property_id: Mapped[str | None] = mapped_column(String(100))
    # Public identifier sent with every webhook; unique across all hotels.
    key_id: Mapped[str] = mapped_column(String(40), unique=True)
    # Shared HMAC secret. Kept readable because verifying a signature needs it.
    signing_secret: Mapped[str] = mapped_column(String(128))
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    # Where availability updates are pushed to. Null: this connection is inbound only.
    outbound_url: Mapped[str | None] = mapped_column(String(2048))
    # Outcome of the most recent availability push, for staff to see at a glance.
    last_push_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_push_ok: Mapped[bool | None] = mapped_column(Boolean)
    last_push_detail: Mapped[str | None] = mapped_column(String(300))


class ChannelWebhookEvent(UUIDPrimaryKeyMixin, TenantMixin, Base):
    """Every authenticated webhook delivery and what was done with it."""

    __tablename__ = "channel_webhook_events"
    __table_args__ = (
        ForeignKeyConstraint(
            ["hotel_id", "connection_id"],
            ["channel_connections.hotel_id", "channel_connections.id"],
            name="fk_channel_webhook_events_connection_id",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["hotel_id", "reservation_id"],
            ["reservations.hotel_id", "reservations.id"],
            name="fk_channel_webhook_events_reservation_id",
            ondelete="RESTRICT",
        ),
        CheckConstraint(f"status IN ({enum_values_sql(WebhookEventStatus)})", name="status_valid"),
        Index("ix_channel_webhook_events_received", "hotel_id", "received_at"),
    )

    connection_id: Mapped[UUID] = mapped_column(Uuid)
    event_type: Mapped[str] = mapped_column(String(40))
    channel: Mapped[str] = mapped_column(String(20))
    external_booking_id: Mapped[str] = mapped_column(String(100))
    status: Mapped[WebhookEventStatus] = mapped_column(String(20))
    # Why it was rejected, when it was.
    detail: Mapped[str | None] = mapped_column(Text)
    reservation_id: Mapped[UUID | None] = mapped_column(Uuid)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class ChannexRoomMapping(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    """Which Channex room type (and rate plan) one of our room types is sold as."""

    __tablename__ = "channex_room_mappings"
    __table_args__ = (
        UniqueConstraint("hotel_id", "id"),
        UniqueConstraint(
            "hotel_id", "connection_id", "room_type_id", name="uq_channex_room_mappings_room_type"
        ),
        UniqueConstraint(
            "hotel_id",
            "connection_id",
            "channex_room_type_id",
            name="uq_channex_room_mappings_channex_room_type",
        ),
        ForeignKeyConstraint(
            ["hotel_id", "connection_id"],
            ["channel_connections.hotel_id", "channel_connections.id"],
            name="fk_channex_room_mappings_connection_id",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["hotel_id", "room_type_id"],
            ["room_types.hotel_id", "room_types.id"],
            name="fk_channex_room_mappings_room_type_id",
            ondelete="CASCADE",
        ),
    )

    connection_id: Mapped[UUID] = mapped_column(Uuid)
    room_type_id: Mapped[UUID] = mapped_column(Uuid)
    channex_room_type_id: Mapped[str] = mapped_column(String(100))
    # Rates are pushed to this plan by a full sync. Null: rates are managed in Channex.
    channex_rate_plan_id: Mapped[str | None] = mapped_column(String(100))
