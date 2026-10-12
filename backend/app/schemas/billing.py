from datetime import date, datetime
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models import EntryType, FolioStatus, PaymentMethod, TransactionCategory
from app.schemas.base import CreateSchema, ReadSchema

PositiveMoney = Annotated[Decimal, Field(gt=0, max_digits=12, decimal_places=2)]
GstRate = Annotated[Decimal, Field(ge=0, le=40, max_digits=5, decimal_places=2)]


class FolioOpen(CreateSchema):
    reservation_id: UUID


class ChargeCreate(CreateSchema):
    description: str = Field(min_length=1, max_length=500)
    # Taxable value, before GST.
    amount: PositiveMoney
    gst_rate: GstRate = Decimal("0")
    sac_code: str | None = Field(default=None, min_length=4, max_length=8, pattern=r"^\d+$")
    # Defaults to today at the hotel.
    business_date: date | None = None


class PaymentCreate(CreateSchema):
    amount: PositiveMoney
    payment_method: PaymentMethod
    reference: str | None = Field(default=None, max_length=100)


class ReversalCreate(CreateSchema):
    reason: str = Field(min_length=3, max_length=300)


class FolioTransactionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    folio_id: UUID
    business_date: date
    entry_type: EntryType
    category: TransactionCategory
    description: str
    amount: Decimal
    gst_rate: Decimal
    cgst_amount: Decimal
    sgst_amount: Decimal
    total_amount: Decimal
    sac_code: str | None
    payment_method: PaymentMethod | None
    reference: str | None
    reverses_transaction_id: UUID | None
    created_by: UUID | None
    created_at: datetime


class FolioRead(ReadSchema):
    reservation_id: UUID
    folio_number: str
    status: FolioStatus
    closed_at: datetime | None
    # Set when the tax invoice for the closed folio is first issued.
    invoice_number: str | None
    invoice_date: date | None


class FolioDetailRead(FolioRead):
    total_debits: Decimal
    total_credits: Decimal
    # What the guest still owes.
    balance: Decimal
    transactions: list[FolioTransactionRead]


class GstQuoteRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    sac_code: str
    nights: int
    tariff_per_night: Decimal
    gst_rate: Decimal
    itc_eligible: bool
    taxable_amount: Decimal
    cgst_amount: Decimal
    sgst_amount: Decimal
    total_tax: Decimal
    total_amount: Decimal


class NightAuditRequest(CreateSchema):
    # Defaults to yesterday at the hotel: the day that has just ended.
    business_date: date | None = None


class NightAuditRunRead(ReadSchema):
    business_date: date
    room_charges_posted: int
    no_shows_marked: int
    room_revenue: Decimal
    tax_amount: Decimal
    run_by: UUID | None
