"""room types, rooms, guests, reservations

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-01
"""

from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Unset or empty setting -> NULL -> no row matches (fails closed).
CURRENT_HOTEL = "NULLIF(current_setting('app.current_hotel_id', true), '')::uuid"
HOLDING = "status IN ('confirmed', 'checked_in')"


def _enable_rls(table: str) -> None:
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY tenant_isolation ON {table} "
        f"USING (hotel_id = {CURRENT_HOTEL}) "
        f"WITH CHECK (hotel_id = {CURRENT_HOTEL})"
    )


def _base_columns(table: str) -> list[sa.Column[Any] | sa.Constraint]:
    return [
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("hotel_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name=f"pk_{table}"),
        sa.ForeignKeyConstraint(
            ["hotel_id"], ["hotels.id"], name=f"fk_{table}_hotel_id_hotels", ondelete="RESTRICT"
        ),
    ]


def upgrade() -> None:
    # Needed for the room double-allocation exclusion constraint (uuid in GiST).
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")

    op.create_table(
        "room_types",
        *_base_columns("room_types"),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("code", sa.String(20), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("base_occupancy", sa.Integer(), server_default=sa.text("2"), nullable=False),
        sa.Column("max_occupancy", sa.Integer(), server_default=sa.text("2"), nullable=False),
        sa.Column("base_rate", sa.Numeric(12, 2), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.UniqueConstraint("hotel_id", "code", name="uq_room_types_hotel_id_code"),
        sa.UniqueConstraint("hotel_id", "id", name="uq_room_types_hotel_id_id"),
        sa.CheckConstraint("base_occupancy >= 1", name="ck_room_types_base_occupancy_positive"),
        sa.CheckConstraint(
            "max_occupancy >= base_occupancy", name="ck_room_types_max_occupancy_valid"
        ),
        sa.CheckConstraint("base_rate >= 0", name="ck_room_types_base_rate_non_negative"),
    )
    op.create_index("ix_room_types_hotel_id", "room_types", ["hotel_id"])
    _enable_rls("room_types")

    op.create_table(
        "rooms",
        *_base_columns("rooms"),
        sa.Column("room_type_id", sa.Uuid(), nullable=False),
        sa.Column("room_number", sa.String(20), nullable=False),
        sa.Column("floor", sa.String(20), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.UniqueConstraint("hotel_id", "room_number", name="uq_rooms_hotel_id_room_number"),
        sa.UniqueConstraint("hotel_id", "id", name="uq_rooms_hotel_id_id"),
        sa.ForeignKeyConstraint(
            ["hotel_id", "room_type_id"],
            ["room_types.hotel_id", "room_types.id"],
            name="fk_rooms_room_type_id_room_types",
            ondelete="RESTRICT",
        ),
    )
    op.create_index("ix_rooms_hotel_id", "rooms", ["hotel_id"])
    op.create_index("ix_rooms_room_type_id", "rooms", ["room_type_id"])
    _enable_rls("rooms")

    op.create_table(
        "guests",
        *_base_columns("guests"),
        sa.Column("first_name", sa.String(100), nullable=False),
        sa.Column("last_name", sa.String(100), nullable=False),
        sa.Column("email", sa.String(320), nullable=True),
        sa.Column("phone", sa.String(32), nullable=True),
        sa.Column("id_document_type", sa.String(50), nullable=True),
        sa.Column("id_document_number", sa.String(100), nullable=True),
        sa.Column("nationality", sa.String(100), nullable=True),
        sa.Column("address", sa.Text(), nullable=True),
        sa.Column("city", sa.String(100), nullable=True),
        sa.Column("state", sa.String(100), nullable=True),
        sa.Column("country", sa.String(100), nullable=True),
        sa.Column("company_name", sa.String(200), nullable=True),
        sa.Column("gstin", sa.String(15), nullable=True),
        sa.UniqueConstraint("hotel_id", "id", name="uq_guests_hotel_id_id"),
    )
    op.create_index("ix_guests_hotel_id", "guests", ["hotel_id"])
    _enable_rls("guests")

    op.create_table(
        "reservations",
        *_base_columns("reservations"),
        sa.Column("confirmation_number", sa.String(20), nullable=False),
        sa.Column("guest_id", sa.Uuid(), nullable=False),
        sa.Column("room_type_id", sa.Uuid(), nullable=False),
        sa.Column("room_id", sa.Uuid(), nullable=True),
        sa.Column("check_in_date", sa.Date(), nullable=False),
        sa.Column("check_out_date", sa.Date(), nullable=False),
        sa.Column("adults", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("children", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("rate_per_night", sa.Numeric(12, 2), nullable=False),
        sa.Column("status", sa.String(20), server_default=sa.text("'confirmed'"), nullable=False),
        sa.Column("source", sa.String(20), server_default=sa.text("'direct'"), nullable=False),
        sa.Column("external_reference", sa.String(100), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.UniqueConstraint(
            "hotel_id", "confirmation_number", name="uq_reservations_hotel_id_confirmation_number"
        ),
        sa.ForeignKeyConstraint(
            ["hotel_id", "guest_id"],
            ["guests.hotel_id", "guests.id"],
            name="fk_reservations_guest_id_guests",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["hotel_id", "room_type_id"],
            ["room_types.hotel_id", "room_types.id"],
            name="fk_reservations_room_type_id_room_types",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["hotel_id", "room_id"],
            ["rooms.hotel_id", "rooms.id"],
            name="fk_reservations_room_id_rooms",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint("check_out_date > check_in_date", name="ck_reservations_dates_valid"),
        sa.CheckConstraint("adults >= 1", name="ck_reservations_adults_positive"),
        sa.CheckConstraint("children >= 0", name="ck_reservations_children_non_negative"),
        sa.CheckConstraint("rate_per_night >= 0", name="ck_reservations_rate_non_negative"),
        sa.CheckConstraint(
            "status IN ('confirmed', 'checked_in', 'checked_out', 'cancelled', 'no_show')",
            name="ck_reservations_status_valid",
        ),
        sa.CheckConstraint(
            "source IN ('direct', 'walk_in', 'phone', 'website', 'booking_com', 'makemytrip', "
            "'goibibo', 'agoda', 'expedia', 'airbnb', 'corporate', 'travel_agent', 'other')",
            name="ck_reservations_source_valid",
        ),
    )
    op.create_index("ix_reservations_hotel_id", "reservations", ["hotel_id"])
    op.create_index("ix_reservations_guest_id", "reservations", ["guest_id"])
    op.create_index(
        "ix_reservations_inventory",
        "reservations",
        ["hotel_id", "room_type_id", "check_in_date", "check_out_date"],
        postgresql_where=sa.text(HOLDING),
    )
    # A physical room cannot be allocated to two overlapping live stays.
    op.execute(
        "ALTER TABLE reservations ADD CONSTRAINT ex_reservations_room_no_overlap "
        "EXCLUDE USING gist (room_id WITH =, daterange(check_in_date, check_out_date) WITH &&) "
        f"WHERE (room_id IS NOT NULL AND {HOLDING})"
    )
    _enable_rls("reservations")


def downgrade() -> None:
    op.drop_table("reservations")
    op.drop_table("guests")
    op.drop_table("rooms")
    op.drop_table("room_types")
    op.execute("DROP EXTENSION IF EXISTS btree_gist")
