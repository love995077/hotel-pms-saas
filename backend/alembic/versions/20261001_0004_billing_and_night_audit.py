"""folios, immutable folio transactions, night audit runs

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-01
"""

from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa
from sqlalchemy.engine import make_url

from alembic import op
from app.config import get_settings

revision: str = "0004"
down_revision: str | None = "0003"
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


def _id_and_hotel(table: str) -> list[sa.Column[Any] | sa.Constraint]:
    return [
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("hotel_id", sa.Uuid(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=f"pk_{table}"),
        sa.ForeignKeyConstraint(
            ["hotel_id"], ["hotels.id"], name=f"fk_{table}_hotel_id_hotels", ondelete="RESTRICT"
        ),
    ]


def _timestamps() -> list[sa.Column[Any]]:
    return [
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    ]


def _app_role() -> str:
    role = make_url(get_settings().database_url).username or ""
    return str(op.get_bind().dialect.identifier_preparer.quote(role))


def upgrade() -> None:
    # Lets ledger lines reference the posting user with the hotel in the key.
    op.create_unique_constraint("uq_users_hotel_id_id", "users", ["hotel_id", "id"])
    # Likewise for folios referencing their reservation.
    op.create_unique_constraint("uq_reservations_hotel_id_id", "reservations", ["hotel_id", "id"])

    op.create_table(
        "folios",
        *_id_and_hotel("folios"),
        *_timestamps(),
        sa.Column("reservation_id", sa.Uuid(), nullable=False),
        sa.Column("folio_number", sa.String(20), nullable=False),
        sa.Column("status", sa.String(10), server_default=sa.text("'open'"), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("hotel_id", "id", name="uq_folios_hotel_id_id"),
        sa.UniqueConstraint("hotel_id", "reservation_id", name="uq_folios_hotel_id_reservation_id"),
        sa.UniqueConstraint("hotel_id", "folio_number", name="uq_folios_hotel_id_folio_number"),
        sa.ForeignKeyConstraint(
            ["hotel_id", "reservation_id"],
            ["reservations.hotel_id", "reservations.id"],
            name="fk_folios_reservation_id_reservations",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint("status IN ('open', 'closed')", name="ck_folios_status_valid"),
    )
    op.create_index("ix_folios_hotel_id", "folios", ["hotel_id"])
    _enable_rls("folios")

    op.create_table(
        "folio_transactions",
        *_id_and_hotel("folio_transactions"),
        sa.Column("folio_id", sa.Uuid(), nullable=False),
        sa.Column("business_date", sa.Date(), nullable=False),
        sa.Column("entry_type", sa.String(10), nullable=False),
        sa.Column("category", sa.String(20), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("gst_rate", sa.Numeric(5, 2), server_default=sa.text("0"), nullable=False),
        sa.Column("cgst_amount", sa.Numeric(12, 2), server_default=sa.text("0"), nullable=False),
        sa.Column("sgst_amount", sa.Numeric(12, 2), server_default=sa.text("0"), nullable=False),
        sa.Column("total_amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("sac_code", sa.String(8), nullable=True),
        sa.Column("payment_method", sa.String(20), nullable=True),
        sa.Column("reference", sa.String(100), nullable=True),
        sa.Column("reverses_transaction_id", sa.Uuid(), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("hotel_id", "id", name="uq_folio_transactions_hotel_id_id"),
        sa.ForeignKeyConstraint(
            ["hotel_id", "folio_id"],
            ["folios.hotel_id", "folios.id"],
            name="fk_folio_transactions_folio_id_folios",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["hotel_id", "reverses_transaction_id"],
            ["folio_transactions.hotel_id", "folio_transactions.id"],
            name="fk_folio_transactions_reverses_transaction_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["hotel_id", "created_by"],
            ["users.hotel_id", "users.id"],
            name="fk_folio_transactions_created_by_users",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "entry_type IN ('debit', 'credit')", name="ck_folio_transactions_entry_type_valid"
        ),
        sa.CheckConstraint(
            "category IN ('room_charge', 'extra_charge', 'payment')",
            name="ck_folio_transactions_category_valid",
        ),
        sa.CheckConstraint(
            "payment_method IS NULL OR payment_method IN "
            "('cash', 'card', 'upi', 'bank_transfer', 'cheque', 'other')",
            name="ck_folio_transactions_payment_method_valid",
        ),
        sa.CheckConstraint(
            "amount >= 0 AND cgst_amount >= 0 AND sgst_amount >= 0",
            name="ck_folio_transactions_amounts_non_negative",
        ),
        sa.CheckConstraint(
            "total_amount = amount + cgst_amount + sgst_amount",
            name="ck_folio_transactions_total_consistent",
        ),
    )
    op.create_index("ix_folio_transactions_hotel_id", "folio_transactions", ["hotel_id"])
    op.create_index("ix_folio_transactions_folio_id", "folio_transactions", ["folio_id"])
    op.create_index(
        "uq_folio_transactions_reverses_transaction_id",
        "folio_transactions",
        ["reverses_transaction_id"],
        unique=True,
        postgresql_where=sa.text("reverses_transaction_id IS NOT NULL"),
    )
    op.create_index(
        "uq_folio_transactions_room_charge_per_night",
        "folio_transactions",
        ["folio_id", "business_date"],
        unique=True,
        postgresql_where=sa.text("category = 'room_charge' AND reverses_transaction_id IS NULL"),
    )
    _enable_rls("folio_transactions")

    # Ledger immutability, enforced by the database for every role (including
    # the owner): no UPDATE, DELETE or TRUNCATE on posted lines.
    op.execute(
        """
        CREATE FUNCTION prevent_ledger_mutation() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION
                'folio_transactions is append-only: % is not allowed; post a reversing entry',
                TG_OP
                USING ERRCODE = 'integrity_constraint_violation';
        END
        $$
        """
    )
    op.execute(
        "CREATE TRIGGER folio_transactions_immutable_row "
        "BEFORE UPDATE OR DELETE ON folio_transactions "
        "FOR EACH ROW EXECUTE FUNCTION prevent_ledger_mutation()"
    )
    op.execute(
        "CREATE TRIGGER folio_transactions_immutable_truncate "
        "BEFORE TRUNCATE ON folio_transactions "
        "FOR EACH STATEMENT EXECUTE FUNCTION prevent_ledger_mutation()"
    )
    # Second layer: the runtime role does not even hold the privileges.
    op.execute(f"REVOKE UPDATE, DELETE, TRUNCATE ON folio_transactions FROM {_app_role()}")

    op.create_table(
        "night_audit_runs",
        *_id_and_hotel("night_audit_runs"),
        *_timestamps(),
        sa.Column("business_date", sa.Date(), nullable=False),
        sa.Column("room_charges_posted", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("no_shows_marked", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("room_revenue", sa.Numeric(14, 2), server_default=sa.text("0"), nullable=False),
        sa.Column("tax_amount", sa.Numeric(14, 2), server_default=sa.text("0"), nullable=False),
        sa.Column("run_by", sa.Uuid(), nullable=True),
        sa.UniqueConstraint(
            "hotel_id", "business_date", name="uq_night_audit_runs_hotel_id_business_date"
        ),
    )
    op.create_index("ix_night_audit_runs_hotel_id", "night_audit_runs", ["hotel_id"])
    _enable_rls("night_audit_runs")

    # The scheduler has to enumerate hotels, which RLS hides from the runtime
    # role. Like auth_lookup_user, this runs as the migration role (which must
    # be able to bypass RLS) and exposes only ids and timezones.
    op.execute(
        """
        CREATE FUNCTION list_active_hotels()
        RETURNS TABLE (hotel_id uuid, timezone text)
        LANGUAGE sql
        STABLE
        SECURITY DEFINER
        SET search_path = public, pg_temp
        AS $$
            SELECT h.id, h.timezone::text FROM hotels AS h WHERE h.is_active
        $$
        """
    )
    op.execute("REVOKE ALL ON FUNCTION list_active_hotels() FROM PUBLIC")
    op.execute(f"GRANT EXECUTE ON FUNCTION list_active_hotels() TO {_app_role()}")


def downgrade() -> None:
    op.execute("DROP FUNCTION list_active_hotels()")
    op.drop_table("night_audit_runs")
    op.drop_table("folio_transactions")
    op.execute("DROP FUNCTION prevent_ledger_mutation()")
    op.drop_table("folios")
    op.drop_constraint("uq_reservations_hotel_id_id", "reservations", type_="unique")
    op.drop_constraint("uq_users_hotel_id_id", "users", type_="unique")
