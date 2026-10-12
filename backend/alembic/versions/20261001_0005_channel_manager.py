"""channel manager connections and webhook event log

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-01
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.engine import make_url

from alembic import op
from app.config import get_settings

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Unset or empty setting -> NULL -> no row matches (fails closed).
CURRENT_HOTEL = "NULLIF(current_setting('app.current_hotel_id', true), '')::uuid"


def _enable_rls(table: str) -> None:
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY tenant_isolation ON {table} "
        f"USING (hotel_id = {CURRENT_HOTEL}) "
        f"WITH CHECK (hotel_id = {CURRENT_HOTEL})"
    )


def upgrade() -> None:
    # One reservation per channel booking, so a redelivered webhook can never
    # take inventory twice.
    op.create_index(
        "uq_reservations_external_reference",
        "reservations",
        ["hotel_id", "source", "external_reference"],
        unique=True,
        postgresql_where=sa.text("external_reference IS NOT NULL"),
    )

    op.create_table(
        "channel_connections",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("hotel_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("key_id", sa.String(40), nullable=False),
        sa.Column("signing_secret", sa.String(128), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name="pk_channel_connections"),
        sa.ForeignKeyConstraint(
            ["hotel_id"],
            ["hotels.id"],
            name="fk_channel_connections_hotel_id_hotels",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("hotel_id", "id", name="uq_channel_connections_hotel_id_id"),
        sa.UniqueConstraint("key_id", name="uq_channel_connections_key_id"),
    )
    op.create_index("ix_channel_connections_hotel_id", "channel_connections", ["hotel_id"])
    _enable_rls("channel_connections")

    op.create_table(
        "channel_webhook_events",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("hotel_id", sa.Uuid(), nullable=False),
        sa.Column("connection_id", sa.Uuid(), nullable=False),
        sa.Column("event_type", sa.String(40), nullable=False),
        sa.Column("channel", sa.String(20), nullable=False),
        sa.Column("external_booking_id", sa.String(100), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column("reservation_id", sa.Uuid(), nullable=True),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column(
            "received_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name="pk_channel_webhook_events"),
        sa.ForeignKeyConstraint(
            ["hotel_id"],
            ["hotels.id"],
            name="fk_channel_webhook_events_hotel_id_hotels",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["hotel_id", "connection_id"],
            ["channel_connections.hotel_id", "channel_connections.id"],
            name="fk_channel_webhook_events_connection_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["hotel_id", "reservation_id"],
            ["reservations.hotel_id", "reservations.id"],
            name="fk_channel_webhook_events_reservation_id",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "status IN ('processed', 'duplicate', 'rejected')",
            name="ck_channel_webhook_events_status_valid",
        ),
    )
    op.create_index("ix_channel_webhook_events_hotel_id", "channel_webhook_events", ["hotel_id"])
    op.create_index(
        "ix_channel_webhook_events_received", "channel_webhook_events", ["hotel_id", "received_at"]
    )
    _enable_rls("channel_webhook_events")

    # A webhook arrives with no tenant context, only a key id. Like
    # auth_lookup_user, this runs as the migration role (which must be able to
    # bypass RLS) and returns the one active connection matching the key.
    op.execute(
        """
        CREATE FUNCTION channel_lookup_connection(p_key_id text)
        RETURNS TABLE (connection_id uuid, hotel_id uuid, signing_secret text)
        LANGUAGE sql
        STABLE
        SECURITY DEFINER
        SET search_path = public, pg_temp
        AS $$
            SELECT c.id, c.hotel_id, c.signing_secret::text
            FROM channel_connections AS c
            JOIN hotels AS h ON h.id = c.hotel_id
            WHERE c.key_id = p_key_id AND c.is_active AND h.is_active
        $$
        """
    )
    app_role = make_url(get_settings().database_url).username or ""
    quoted_role = op.get_bind().dialect.identifier_preparer.quote(app_role)
    op.execute("REVOKE ALL ON FUNCTION channel_lookup_connection(text) FROM PUBLIC")
    op.execute(f"GRANT EXECUTE ON FUNCTION channel_lookup_connection(text) TO {quoted_role}")


def downgrade() -> None:
    op.execute("DROP FUNCTION channel_lookup_connection(text)")
    op.drop_table("channel_webhook_events")
    op.drop_table("channel_connections")
    op.drop_index("uq_reservations_external_reference", table_name="reservations")
