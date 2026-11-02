"""channex.io integration: provider on connections, room type mappings

Revision ID: 0008
Revises: 0007
Create Date: 2026-11-02
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.engine import make_url

from alembic import op
from app.config import get_settings

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CURRENT_HOTEL = "NULLIF(current_setting('app.current_hotel_id', true), '')::uuid"


def _enable_rls(table: str) -> None:
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY tenant_isolation ON {table} "
        f"USING (hotel_id = {CURRENT_HOTEL}) "
        f"WITH CHECK (hotel_id = {CURRENT_HOTEL})"
    )


def _grant_to_app_role(signature: str) -> None:
    app_role = make_url(get_settings().database_url).username or ""
    quoted_role = op.get_bind().dialect.identifier_preparer.quote(app_role)
    op.execute(f"REVOKE ALL ON FUNCTION {signature} FROM PUBLIC")
    op.execute(f"GRANT EXECUTE ON FUNCTION {signature} TO {quoted_role}")


def upgrade() -> None:
    # Existing table: its RLS policy and (hotel_id, id) key already cover these.
    op.add_column(
        "channel_connections",
        sa.Column("provider", sa.String(20), server_default=sa.text("'generic'"), nullable=False),
    )
    op.add_column(
        "channel_connections", sa.Column("external_property_id", sa.String(100), nullable=True)
    )
    op.create_check_constraint(
        op.f("ck_channel_connections_provider_valid"),
        "channel_connections",
        "provider IN ('generic', 'channex')",
    )
    op.create_check_constraint(
        op.f("ck_channel_connections_channex_property_required"),
        "channel_connections",
        "provider <> 'channex' OR external_property_id IS NOT NULL",
    )
    op.create_index(
        "uq_channel_connections_one_channex",
        "channel_connections",
        ["hotel_id"],
        unique=True,
        postgresql_where=sa.text("provider = 'channex'"),
    )

    op.create_table(
        "channex_room_mappings",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("hotel_id", sa.Uuid(), nullable=False),
        sa.Column("connection_id", sa.Uuid(), nullable=False),
        sa.Column("room_type_id", sa.Uuid(), nullable=False),
        sa.Column("channex_room_type_id", sa.String(100), nullable=False),
        sa.Column("channex_rate_plan_id", sa.String(100), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name="pk_channex_room_mappings"),
        sa.ForeignKeyConstraint(
            ["hotel_id"],
            ["hotels.id"],
            name="fk_channex_room_mappings_hotel_id_hotels",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["hotel_id", "connection_id"],
            ["channel_connections.hotel_id", "channel_connections.id"],
            name="fk_channex_room_mappings_connection_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["hotel_id", "room_type_id"],
            ["room_types.hotel_id", "room_types.id"],
            name="fk_channex_room_mappings_room_type_id",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("hotel_id", "id", name="uq_channex_room_mappings_hotel_id_id"),
        sa.UniqueConstraint(
            "hotel_id",
            "connection_id",
            "room_type_id",
            name="uq_channex_room_mappings_room_type",
        ),
        sa.UniqueConstraint(
            "hotel_id",
            "connection_id",
            "channex_room_type_id",
            name="uq_channex_room_mappings_channex_room_type",
        ),
    )
    op.create_index("ix_channex_room_mappings_hotel_id", "channex_room_mappings", ["hotel_id"])
    _enable_rls("channex_room_mappings")

    # The generic endpoint must not accept a Channex connection's key: Channex
    # sends its token as a plain header, which is weaker than our HMAC.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION channel_lookup_connection(p_key_id text)
        RETURNS TABLE (connection_id uuid, hotel_id uuid, signing_secret text)
        LANGUAGE sql
        STABLE
        SECURITY DEFINER
        SET search_path = public, pg_temp
        AS $$
            SELECT c.id, c.hotel_id, c.signing_secret::text
            FROM channel_connections AS c
            JOIN hotels AS h ON h.id = c.hotel_id
            WHERE c.key_id = p_key_id AND c.provider = 'generic' AND c.is_active AND h.is_active
        $$
        """
    )
    # Like channel_lookup_connection (migration 0005): runs with the migration
    # role's rights, as a webhook arrives with only a key id and no tenant context.
    op.execute(
        """
        CREATE FUNCTION channex_lookup_connection(p_key_id text)
        RETURNS TABLE (
            connection_id uuid, hotel_id uuid, signing_secret text, property_id text
        )
        LANGUAGE sql
        STABLE
        SECURITY DEFINER
        SET search_path = public, pg_temp
        AS $$
            SELECT c.id, c.hotel_id, c.signing_secret::text, c.external_property_id::text
            FROM channel_connections AS c
            JOIN hotels AS h ON h.id = c.hotel_id
            WHERE c.key_id = p_key_id AND c.provider = 'channex' AND c.is_active AND h.is_active
        $$
        """
    )
    _grant_to_app_role("channex_lookup_connection(text)")


def downgrade() -> None:
    op.execute("DROP FUNCTION channex_lookup_connection(text)")
    op.execute(
        """
        CREATE OR REPLACE FUNCTION channel_lookup_connection(p_key_id text)
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
    op.drop_table("channex_room_mappings")
    op.drop_index("uq_channel_connections_one_channex", table_name="channel_connections")
    op.drop_constraint(
        op.f("ck_channel_connections_channex_property_required"),
        "channel_connections",
        type_="check",
    )
    op.drop_constraint(
        op.f("ck_channel_connections_provider_valid"), "channel_connections", type_="check"
    )
    op.drop_column("channel_connections", "external_property_id")
    op.drop_column("channel_connections", "provider")
