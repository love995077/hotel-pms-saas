"""room_types.unit_kind: what one unit of the category is (room, dorm bed, villa, flat)

Revision ID: 0011
Revises: 0010
Create Date: 2026-11-19

A property can mix kinds (a hostel with dormitory beds and private rooms), so
the label and icon of a unit come from its room type, not from the property.
Existing categories are backfilled from the property type where that is
unambiguous (resort and villa properties: villas; serviced apartments: flats);
everything else, hostels included, starts as a room and the owner can change it.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "room_types",
        sa.Column("unit_kind", sa.String(20), server_default=sa.text("'room'"), nullable=False),
    )
    op.create_check_constraint(
        op.f("ck_room_types_unit_kind_valid"),
        "room_types",
        "unit_kind IN ('room', 'dorm_bed', 'villa', 'flat')",
    )
    # Runs as the owner role, which is not subject to RLS: every hotel at once.
    op.execute(
        """
        UPDATE room_types AS rt
        SET unit_kind = CASE h.property_type
            WHEN 'resort' THEN 'villa'
            WHEN 'villa' THEN 'villa'
            WHEN 'apartment' THEN 'flat'
        END
        FROM hotels AS h
        WHERE h.id = rt.hotel_id AND h.property_type IN ('resort', 'villa', 'apartment')
        """
    )


def downgrade() -> None:
    op.drop_constraint(op.f("ck_room_types_unit_kind_valid"), "room_types", type_="check")
    op.drop_column("room_types", "unit_kind")
