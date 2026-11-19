"""property type on the hotel profile; rooms.floor becomes the wider floor_or_zone

Revision ID: 0010
Revises: 0009
Create Date: 2026-11-19

`property_type` is nullable on purpose: NULL means the owner has not been asked
yet, and the app treats it as a hotel until they answer. New sign-ups choose it
on the registration form.

`floor` is renamed rather than duplicated, so existing values are kept; it is
widened because a zone ("Poolside cottages") is longer than a floor number.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_PROPERTY_TYPES = "'hotel', 'resort', 'hostel', 'apartment', 'villa'"


def upgrade() -> None:
    op.add_column("hotels", sa.Column("property_type", sa.String(20), nullable=True))
    op.create_check_constraint(
        op.f("ck_hotels_property_type_valid"),
        "hotels",
        f"property_type IS NULL OR property_type IN ({_PROPERTY_TYPES})",
    )
    op.alter_column(
        "rooms",
        "floor",
        new_column_name="floor_or_zone",
        type_=sa.String(50),
        existing_type=sa.String(20),
        existing_nullable=True,
    )


def downgrade() -> None:
    # Values longer than the old column are cut rather than blocking the downgrade.
    op.alter_column(
        "rooms",
        "floor_or_zone",
        new_column_name="floor",
        type_=sa.String(20),
        existing_type=sa.String(50),
        existing_nullable=True,
        postgresql_using="left(floor_or_zone, 20)",
    )
    op.drop_constraint(op.f("ck_hotels_property_type_valid"), "hotels", type_="check")
    op.drop_column("hotels", "property_type")
