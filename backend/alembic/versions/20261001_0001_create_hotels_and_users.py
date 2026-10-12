"""create hotels and users

Revision ID: 0001
Revises:
Create Date: 2026-10-01
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Unset or empty setting -> NULL -> no row matches (fails closed).
CURRENT_HOTEL = "NULLIF(current_setting('app.current_hotel_id', true), '')::uuid"


def _enable_rls(table: str, column: str) -> None:
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    # FORCE applies the policy to the table owner as well.
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY tenant_isolation ON {table} "
        f"USING ({column} = {CURRENT_HOTEL}) "
        f"WITH CHECK ({column} = {CURRENT_HOTEL})"
    )


def upgrade() -> None:
    op.create_table(
        "hotels",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("slug", sa.String(63), nullable=False),
        sa.Column("gstin", sa.String(15), nullable=True),
        sa.Column(
            "timezone", sa.String(64), server_default=sa.text("'Asia/Kolkata'"), nullable=False
        ),
        sa.Column("currency", sa.String(3), server_default=sa.text("'INR'"), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name="pk_hotels"),
        sa.UniqueConstraint("slug", name="uq_hotels_slug"),
    )
    _enable_rls("hotels", "id")

    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("hotel_id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column("full_name", sa.String(200), nullable=False),
        sa.Column("role", sa.String(32), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name="pk_users"),
        sa.ForeignKeyConstraint(
            ["hotel_id"], ["hotels.id"], name="fk_users_hotel_id_hotels", ondelete="RESTRICT"
        ),
        sa.CheckConstraint(
            "role IN ('owner', 'manager', 'front_desk', 'housekeeping', 'accountant')",
            name="ck_users_role_valid",
        ),
    )
    op.create_index("ix_users_hotel_id", "users", ["hotel_id"])
    op.create_index(
        "uq_users_hotel_id_email_lower",
        "users",
        ["hotel_id", sa.text("lower(email)")],
        unique=True,
    )
    _enable_rls("users", "hotel_id")


def downgrade() -> None:
    op.drop_table("users")
    op.drop_table("hotels")
