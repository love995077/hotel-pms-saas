from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKeyConstraint,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TenantMixin, TimestampMixin, UUIDPrimaryKeyMixin


class RoomType(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    """A sellable category of rooms. Inventory is counted at this level."""

    __tablename__ = "room_types"
    __table_args__ = (
        UniqueConstraint("hotel_id", "code"),
        # Target for composite foreign keys, which pin children to the same hotel.
        UniqueConstraint("hotel_id", "id"),
        CheckConstraint("base_occupancy >= 1", name="base_occupancy_positive"),
        CheckConstraint("max_occupancy >= base_occupancy", name="max_occupancy_valid"),
        CheckConstraint("base_rate >= 0", name="base_rate_non_negative"),
    )

    name: Mapped[str] = mapped_column(String(100))
    code: Mapped[str] = mapped_column(String(20))
    description: Mapped[str | None] = mapped_column(Text)
    base_occupancy: Mapped[int] = mapped_column(Integer, server_default=text("2"))
    max_occupancy: Mapped[int] = mapped_column(Integer, server_default=text("2"))
    # Tariff per night, before tax.
    base_rate: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))


class Room(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    """A physical room. Only active rooms count towards sellable inventory."""

    __tablename__ = "rooms"
    __table_args__ = (
        UniqueConstraint("hotel_id", "room_number"),
        UniqueConstraint("hotel_id", "id"),
        # Foreign-key checks bypass RLS, so the hotel is part of the key.
        ForeignKeyConstraint(
            ["hotel_id", "room_type_id"],
            ["room_types.hotel_id", "room_types.id"],
            name="fk_rooms_room_type_id_room_types",
            ondelete="RESTRICT",
        ),
    )

    room_type_id: Mapped[UUID] = mapped_column(Uuid, index=True)
    room_number: Mapped[str] = mapped_column(String(20))
    floor: Mapped[str | None] = mapped_column(String(20))
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
