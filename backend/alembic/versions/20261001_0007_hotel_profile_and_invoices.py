"""hotel profile for invoices, and consecutive GST invoice numbers

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-01
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Unset or empty setting -> NULL -> no row matches (fails closed).
CURRENT_HOTEL = "NULLIF(current_setting('app.current_hotel_id', true), '')::uuid"


def upgrade() -> None:
    # What a GST invoice must say about the supplier, beyond name and GSTIN.
    op.add_column("hotels", sa.Column("address", sa.Text(), nullable=True))
    op.add_column("hotels", sa.Column("city", sa.String(100), nullable=True))
    op.add_column("hotels", sa.Column("state", sa.String(100), nullable=True))
    op.add_column("hotels", sa.Column("postal_code", sa.String(10), nullable=True))
    op.add_column("hotels", sa.Column("phone", sa.String(32), nullable=True))
    op.add_column("hotels", sa.Column("email", sa.String(320), nullable=True))

    # 16 characters is the longest invoice number the GST rules allow.
    op.add_column("folios", sa.Column("invoice_number", sa.String(16), nullable=True))
    op.add_column("folios", sa.Column("invoice_date", sa.Date(), nullable=True))
    op.create_unique_constraint(
        "uq_folios_hotel_id_invoice_number", "folios", ["hotel_id", "invoice_number"]
    )

    op.create_table(
        "invoice_sequences",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("hotel_id", sa.Uuid(), nullable=False),
        sa.Column("financial_year", sa.Integer(), nullable=False),
        sa.Column("last_number", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_invoice_sequences"),
        sa.ForeignKeyConstraint(
            ["hotel_id"],
            ["hotels.id"],
            name="fk_invoice_sequences_hotel_id_hotels",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("hotel_id", "id", name="uq_invoice_sequences_hotel_id_id"),
        sa.UniqueConstraint(
            "hotel_id", "financial_year", name="uq_invoice_sequences_hotel_id_financial_year"
        ),
        sa.CheckConstraint(
            "last_number >= 0", name="ck_invoice_sequences_last_number_non_negative"
        ),
    )
    op.create_index("ix_invoice_sequences_hotel_id", "invoice_sequences", ["hotel_id"])
    op.execute("ALTER TABLE invoice_sequences ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE invoice_sequences FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY tenant_isolation ON invoice_sequences "
        f"USING (hotel_id = {CURRENT_HOTEL}) "
        f"WITH CHECK (hotel_id = {CURRENT_HOTEL})"
    )


def downgrade() -> None:
    op.drop_table("invoice_sequences")
    op.drop_constraint("uq_folios_hotel_id_invoice_number", "folios", type_="unique")
    op.drop_column("folios", "invoice_date")
    op.drop_column("folios", "invoice_number")
    for column in ("email", "phone", "postal_code", "state", "city", "address"):
        op.drop_column("hotels", column)
