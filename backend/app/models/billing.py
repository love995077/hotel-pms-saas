from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import (
    Base,
    TenantMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
    enum_values_sql,
)


class FolioStatus(StrEnum):
    OPEN = "open"
    CLOSED = "closed"


class EntryType(StrEnum):
    # Debit: the guest owes more. Credit: the guest owes less.
    DEBIT = "debit"
    CREDIT = "credit"


class TransactionCategory(StrEnum):
    ROOM_CHARGE = "room_charge"
    EXTRA_CHARGE = "extra_charge"
    PAYMENT = "payment"


class PaymentMethod(StrEnum):
    CASH = "cash"
    CARD = "card"
    UPI = "upi"
    BANK_TRANSFER = "bank_transfer"
    CHEQUE = "cheque"
    OTHER = "other"


class Folio(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    """A guest's running account for one reservation."""

    __tablename__ = "folios"
    __table_args__ = (
        UniqueConstraint("hotel_id", "id"),
        UniqueConstraint("hotel_id", "reservation_id"),
        UniqueConstraint("hotel_id", "folio_number"),
        UniqueConstraint("hotel_id", "invoice_number"),
        ForeignKeyConstraint(
            ["hotel_id", "reservation_id"],
            ["reservations.hotel_id", "reservations.id"],
            name="fk_folios_reservation_id_reservations",
            ondelete="RESTRICT",
        ),
        CheckConstraint(f"status IN ({enum_values_sql(FolioStatus)})", name="status_valid"),
    )

    reservation_id: Mapped[UUID] = mapped_column(Uuid)
    folio_number: Mapped[str] = mapped_column(String(20))
    status: Mapped[FolioStatus] = mapped_column(String(10), server_default=text("'open'"))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Set once, when the tax invoice for the closed folio is first issued, and
    # never changed afterwards. Null until then.
    invoice_number: Mapped[str | None] = mapped_column(String(16))
    invoice_date: Mapped[date | None] = mapped_column(Date)


class InvoiceSequence(UUIDPrimaryKeyMixin, TenantMixin, Base):
    """The last invoice serial a hotel has issued in one financial year.

    GST invoices must be numbered consecutively within a financial year. The
    row is locked while a number is taken, and a rolled-back transaction gives
    its number back, so the series has no gaps.
    """

    __tablename__ = "invoice_sequences"
    __table_args__ = (
        UniqueConstraint("hotel_id", "id"),
        UniqueConstraint("hotel_id", "financial_year"),
        CheckConstraint("last_number >= 0", name="last_number_non_negative"),
    )

    # First calendar year of the April-to-March year, e.g. 2026 for FY 2026-27.
    financial_year: Mapped[int] = mapped_column(Integer)
    last_number: Mapped[int] = mapped_column(Integer, server_default=text("0"))


class FolioTransaction(UUIDPrimaryKeyMixin, TenantMixin, Base):
    """One immutable ledger line.

    Rows are insert-only: the database rejects UPDATE, DELETE and TRUNCATE on
    this table for every role. A mistake is corrected by posting a reversing
    line (`reverses_transaction_id`), never by changing what was posted.
    """

    __tablename__ = "folio_transactions"
    __table_args__ = (
        UniqueConstraint("hotel_id", "id"),
        ForeignKeyConstraint(
            ["hotel_id", "folio_id"],
            ["folios.hotel_id", "folios.id"],
            name="fk_folio_transactions_folio_id_folios",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["hotel_id", "reverses_transaction_id"],
            ["folio_transactions.hotel_id", "folio_transactions.id"],
            name="fk_folio_transactions_reverses_transaction_id",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["hotel_id", "created_by"],
            ["users.hotel_id", "users.id"],
            name="fk_folio_transactions_created_by_users",
            ondelete="RESTRICT",
        ),
        CheckConstraint(f"entry_type IN ({enum_values_sql(EntryType)})", name="entry_type_valid"),
        CheckConstraint(
            f"category IN ({enum_values_sql(TransactionCategory)})", name="category_valid"
        ),
        CheckConstraint(
            f"payment_method IS NULL OR payment_method IN ({enum_values_sql(PaymentMethod)})",
            name="payment_method_valid",
        ),
        CheckConstraint(
            "amount >= 0 AND cgst_amount >= 0 AND sgst_amount >= 0", name="amounts_non_negative"
        ),
        CheckConstraint(
            "total_amount = amount + cgst_amount + sgst_amount", name="total_consistent"
        ),
        # A line can be reversed at most once.
        Index(
            "uq_folio_transactions_reverses_transaction_id",
            "reverses_transaction_id",
            unique=True,
            postgresql_where=text("reverses_transaction_id IS NOT NULL"),
        ),
        # At most one room charge per folio per night: makes night audit re-runnable.
        Index(
            "uq_folio_transactions_room_charge_per_night",
            "folio_id",
            "business_date",
            unique=True,
            postgresql_where=text("category = 'room_charge' AND reverses_transaction_id IS NULL"),
        ),
    )

    folio_id: Mapped[UUID] = mapped_column(Uuid, index=True)
    # The hotel day the line belongs to, which is not always the calendar day.
    business_date: Mapped[date] = mapped_column(Date)
    entry_type: Mapped[EntryType] = mapped_column(String(10))
    category: Mapped[TransactionCategory] = mapped_column(String(20))
    description: Mapped[str] = mapped_column(Text)
    # Taxable value for charges; the amount received for payments.
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    gst_rate: Mapped[Decimal] = mapped_column(Numeric(5, 2), server_default=text("0"))
    cgst_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), server_default=text("0"))
    sgst_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), server_default=text("0"))
    total_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    sac_code: Mapped[str | None] = mapped_column(String(8))
    payment_method: Mapped[PaymentMethod | None] = mapped_column(String(20))
    reference: Mapped[str | None] = mapped_column(String(100))
    reverses_transaction_id: Mapped[UUID | None] = mapped_column(Uuid)
    # Null when posted by the system (night audit).
    created_by: Mapped[UUID | None] = mapped_column(Uuid)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class NightAuditRun(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    """Record of the night audit for one business date. Totals are cumulative
    across re-runs of the same date."""

    __tablename__ = "night_audit_runs"
    __table_args__ = (UniqueConstraint("hotel_id", "business_date"),)

    business_date: Mapped[date] = mapped_column(Date)
    room_charges_posted: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    no_shows_marked: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    room_revenue: Mapped[Decimal] = mapped_column(Numeric(14, 2), server_default=text("0"))
    tax_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), server_default=text("0"))
    run_by: Mapped[UUID | None] = mapped_column(Uuid)
