from sqlalchemy import Boolean, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Hotel(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """The tenant. RLS restricts a session to the row whose id it is scoped to."""

    __tablename__ = "hotels"

    name: Mapped[str] = mapped_column(String(200))
    slug: Mapped[str] = mapped_column(String(63), unique=True)
    gstin: Mapped[str | None] = mapped_column(String(15))
    # Printed on invoices: a GST invoice must carry the supplier's address.
    address: Mapped[str | None] = mapped_column(Text)
    city: Mapped[str | None] = mapped_column(String(100))
    state: Mapped[str | None] = mapped_column(String(100))
    postal_code: Mapped[str | None] = mapped_column(String(10))
    phone: Mapped[str | None] = mapped_column(String(32))
    email: Mapped[str | None] = mapped_column(String(320))
    timezone: Mapped[str] = mapped_column(String(64), server_default=text("'Asia/Kolkata'"))
    currency: Mapped[str] = mapped_column(String(3), server_default=text("'INR'"))
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
