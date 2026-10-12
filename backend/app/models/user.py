from enum import StrEnum

from sqlalchemy import Boolean, CheckConstraint, Index, String, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TenantMixin, TimestampMixin, UUIDPrimaryKeyMixin


class UserRole(StrEnum):
    OWNER = "owner"
    MANAGER = "manager"
    FRONT_DESK = "front_desk"
    HOUSEKEEPING = "housekeeping"
    ACCOUNTANT = "accountant"


class User(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("hotel_id", "id"),
        # Emails are unique per hotel, case-insensitively.
        Index("uq_users_hotel_id_email_lower", "hotel_id", text("lower(email)"), unique=True),
        CheckConstraint(
            "role IN ('owner', 'manager', 'front_desk', 'housekeeping', 'accountant')",
            name="role_valid",
        ),
    )

    email: Mapped[str] = mapped_column(String(320))
    hashed_password: Mapped[str] = mapped_column(String(255))
    full_name: Mapped[str] = mapped_column(String(200))
    role: Mapped[UserRole] = mapped_column(String(32))
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
