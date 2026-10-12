from datetime import datetime
from enum import StrEnum
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, MetaData, Uuid, func, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# Deterministic constraint names so Alembic can always address them.
NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)
    # Fetch server-generated values (ids, timestamps) via RETURNING on INSERT
    # and UPDATE, so attributes never need a lazy load under asyncio.
    __mapper_args__ = {"eager_defaults": True}  # noqa: RUF012


def enum_values_sql(enum: type[StrEnum]) -> str:
    """Render enum values as a SQL list for CHECK constraints: 'a', 'b'."""
    return ", ".join(f"'{member.value}'" for member in enum)


class UUIDPrimaryKeyMixin:
    id: Mapped[UUID] = mapped_column(
        Uuid, primary_key=True, server_default=text("gen_random_uuid()")
    )


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class TenantMixin:
    """Every operational table carries hotel_id and gets an RLS policy on it."""

    hotel_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("hotels.id", ondelete="RESTRICT"), index=True
    )
