"""GST invoices for folios: what goes on one, its number, and the PDF.

A closed folio gets a tax invoice. Its number is taken from the hotel's
consecutive series for the financial year the first time the invoice is
produced, stored on the folio, and never changes. An open folio gets a pro
forma invoice, which has no number and is not a tax document.

A charge that was reversed, and the line that reversed it, are both left off:
the invoice shows what the guest was actually billed.
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from io import BytesIO
from typing import Any
from uuid import UUID
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import (
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError
from app.database import current_hotel_id
from app.models import (
    EntryType,
    Folio,
    FolioStatus,
    FolioTransaction,
    Guest,
    Hotel,
    InvoiceSequence,
    Reservation,
    Room,
    TransactionCategory,
)
from app.services.crud import get_or_404
from app.services.folios import hotel_today, list_transactions

# Rule 46 of the CGST Rules caps an invoice number at 16 characters.
MAX_INVOICE_NUMBER_LENGTH = 16
_MAX_SERIAL = 999_999
_ZERO = Decimal("0.00")


# --- numbering ------------------------------------------------------------------


def financial_year(on: date) -> int:
    """First calendar year of the April-to-March financial year `on` falls in."""
    return on.year if on.month >= 4 else on.year - 1


def format_invoice_number(year: int, serial: int) -> str:
    """INV/26-27/000123: prefix, financial year, serial. Exactly 16 characters."""
    return f"INV/{year % 100:02d}-{(year + 1) % 100:02d}/{serial:06d}"


async def _next_invoice_number(session: AsyncSession, issued_on: date) -> str:
    """Take the next number in the hotel's series for the financial year.

    The upsert locks the series row until the transaction ends, so concurrent
    invoices queue up, and a rollback returns the number: no gaps, no repeats.
    """
    year = financial_year(issued_on)
    statement = (
        insert(InvoiceSequence)
        .values(hotel_id=current_hotel_id(session), financial_year=year, last_number=1)
        .on_conflict_do_update(
            index_elements=[InvoiceSequence.hotel_id, InvoiceSequence.financial_year],
            set_={"last_number": InvoiceSequence.last_number + 1},
        )
        .returning(InvoiceSequence.last_number)
    )
    serial = (await session.execute(statement)).scalar_one()
    if serial > _MAX_SERIAL:
        raise ConflictError("The invoice series for this financial year is exhausted")
    return format_invoice_number(year, serial)


# --- content --------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class TaxRow:
    """Charges sharing one SAC code and GST rate, added up."""

    sac_code: str | None
    gst_rate: Decimal
    taxable: Decimal
    cgst: Decimal
    sgst: Decimal

    @property
    def tax(self) -> Decimal:
        return self.cgst + self.sgst


@dataclass(frozen=True, slots=True)
class Invoice:
    hotel: Hotel
    guest: Guest
    reservation: Reservation
    folio: Folio
    room_number: str | None
    # None for a pro forma invoice.
    number: str | None
    issued_on: date
    charges: list[FolioTransaction]
    payments: list[FolioTransaction]
    tax_rows: list[TaxRow]

    @property
    def is_pro_forma(self) -> bool:
        return self.number is None

    @property
    def title(self) -> str:
        if self.is_pro_forma:
            return "PRO FORMA INVOICE"
        # Only a GST-registered supplier can issue a tax invoice.
        return "TAX INVOICE" if self.hotel.gstin else "INVOICE"

    @property
    def taxable_total(self) -> Decimal:
        return sum((row.taxable for row in self.tax_rows), _ZERO)

    @property
    def cgst_total(self) -> Decimal:
        return sum((row.cgst for row in self.tax_rows), _ZERO)

    @property
    def sgst_total(self) -> Decimal:
        return sum((row.sgst for row in self.tax_rows), _ZERO)

    @property
    def grand_total(self) -> Decimal:
        return self.taxable_total + self.cgst_total + self.sgst_total

    @property
    def paid_total(self) -> Decimal:
        return sum((payment.total_amount for payment in self.payments), _ZERO)

    @property
    def balance_due(self) -> Decimal:
        return self.grand_total - self.paid_total

    @property
    def filename(self) -> str:
        if self.number is None:
            return f"Proforma-{self.folio.folio_number}.pdf"
        return f"Invoice-{self.number.replace('/', '-')}.pdf"


def _tax_rows(charges: list[FolioTransaction]) -> list[TaxRow]:
    grouped: dict[tuple[str, Decimal], list[FolioTransaction]] = {}
    for charge in charges:
        grouped.setdefault((charge.sac_code or "", charge.gst_rate), []).append(charge)
    return [
        TaxRow(
            sac_code=sac_code or None,
            gst_rate=rate,
            taxable=sum((line.amount for line in lines), _ZERO),
            cgst=sum((line.cgst_amount for line in lines), _ZERO),
            sgst=sum((line.sgst_amount for line in lines), _ZERO),
        )
        for (sac_code, rate), lines in sorted(grouped.items())
    ]


async def prepare_invoice(session: AsyncSession, folio_id: UUID) -> Invoice:
    """Gather an invoice's content, issuing its number if it is due one."""
    # Locked so that two first downloads of the same invoice cannot both take a number.
    folio = await session.scalar(
        select(Folio)
        .where(Folio.id == folio_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if folio is None:
        raise NotFoundError("Folio not found")

    transactions = await list_transactions(session, folio.id)
    reversed_ids = {t.reverses_transaction_id for t in transactions if t.reverses_transaction_id}
    standing = [
        t for t in transactions if t.reverses_transaction_id is None and t.id not in reversed_ids
    ]
    charges = [
        t
        for t in standing
        if t.category != TransactionCategory.PAYMENT and t.entry_type == EntryType.DEBIT
    ]
    payments = [
        t
        for t in standing
        if t.category == TransactionCategory.PAYMENT and t.entry_type == EntryType.CREDIT
    ]
    if not charges:
        raise ConflictError(
            "Nothing has been charged to this folio, so there is nothing to invoice"
        )

    today = await hotel_today(session)
    if folio.status == FolioStatus.CLOSED and folio.invoice_number is None:
        folio.invoice_number = await _next_invoice_number(session, today)
        folio.invoice_date = today
        await session.flush()

    reservation = await get_or_404(session, Reservation, folio.reservation_id)
    room = await session.get(Room, reservation.room_id) if reservation.room_id else None
    return Invoice(
        hotel=await get_or_404(session, Hotel, current_hotel_id(session)),
        guest=await get_or_404(session, Guest, reservation.guest_id),
        reservation=reservation,
        folio=folio,
        room_number=room.room_number if room else None,
        number=folio.invoice_number,
        issued_on=folio.invoice_date or today,
        charges=charges,
        payments=payments,
        tax_rows=_tax_rows(charges),
    )


# --- words and numbers ------------------------------------------------------------

_ONES = (
    "Zero One Two Three Four Five Six Seven Eight Nine Ten Eleven Twelve Thirteen Fourteen "
    "Fifteen Sixteen Seventeen Eighteen Nineteen"
).split()
_TENS = "_ _ Twenty Thirty Forty Fifty Sixty Seventy Eighty Ninety".split()


def _below_thousand(number: int) -> str:
    parts = []
    if number >= 100:
        parts.append(f"{_ONES[number // 100]} Hundred")
        number %= 100
    if number >= 20:
        tens = _TENS[number // 10]
        parts.append(f"{tens}-{_ONES[number % 10]}" if number % 10 else tens)
    elif number > 0:
        parts.append(_ONES[number])
    return " ".join(parts)


def _in_words(number: int) -> str:
    """Whole number in words, in the Indian system (thousand, lakh, crore)."""
    if number == 0:
        return "Zero"
    crore, number = divmod(number, 10_000_000)
    lakh, number = divmod(number, 100_000)
    thousand, number = divmod(number, 1000)
    parts = []
    if crore:
        parts.append(f"{_in_words(crore)} Crore")
    if lakh:
        parts.append(f"{_below_thousand(lakh)} Lakh")
    if thousand:
        parts.append(f"{_below_thousand(thousand)} Thousand")
    if number:
        parts.append(_below_thousand(number))
    return " ".join(parts)


def rupees_in_words(amount: Decimal) -> str:
    """1234.50 -> 'Rupees One Thousand Two Hundred Thirty-Four and Fifty Paise Only'."""
    rupees, paise = divmod(int((abs(amount) * 100).to_integral_value()), 100)
    words = f"Rupees {_in_words(rupees)}"
    if paise:
        words += f" and {_in_words(paise)} Paise"
    return f"{words} Only"


def format_inr(amount: Decimal) -> str:
    """Indian digit grouping: 1234567.5 -> '12,34,567.50'."""
    sign = "-" if amount < 0 else ""
    whole, _, fraction = f"{abs(amount):.2f}".partition(".")
    head, tail = whole[:-3], whole[-3:]
    groups: list[str] = []
    while len(head) > 2:
        groups.insert(0, head[-2:])
        head = head[:-2]
    if head:
        groups.insert(0, head)
    return f"{sign}{','.join([*groups, tail])}.{fraction}"


def _rate(rate: Decimal) -> str:
    """5.00 -> '5%', 2.50 -> '2.5%'."""
    return f"{rate.normalize():f}%"


# --- PDF ------------------------------------------------------------------------

_INK = colors.HexColor("#0B1220")
_MUTED = colors.HexColor("#5B6478")
_PRIMARY = colors.HexColor("#19398D")
_RULE = colors.HexColor("#D6DCE9")
_BAND = colors.HexColor("#F3F5FB")

_BASE = ParagraphStyle("base", fontName="Helvetica", fontSize=8.5, leading=11.5, textColor=_INK)
_SMALL = ParagraphStyle("small", parent=_BASE, fontSize=7.5, leading=10, textColor=_MUTED)
_LABEL = ParagraphStyle(
    "label", parent=_SMALL, fontName="Helvetica-Bold", fontSize=6.8, leading=10, spaceAfter=2
)
_HOTEL = ParagraphStyle(
    "hotel", parent=_BASE, fontName="Helvetica-Bold", fontSize=15, leading=18, spaceAfter=3
)
_TITLE = ParagraphStyle(
    "title",
    parent=_BASE,
    fontName="Helvetica-Bold",
    fontSize=12.5,
    leading=15,
    textColor=_PRIMARY,
    alignment=TA_RIGHT,
    spaceAfter=4,
)
_RIGHT = ParagraphStyle("right", parent=_BASE, alignment=TA_RIGHT)
_BOLD = ParagraphStyle("bold", parent=_BASE, fontName="Helvetica-Bold")
_HEAD = ParagraphStyle(
    "head", parent=_BASE, fontName="Helvetica-Bold", fontSize=7.2, leading=9, textColor=_MUTED
)
_HEAD_RIGHT = ParagraphStyle("head-right", parent=_HEAD, alignment=TA_RIGHT)
_NUMBER = ParagraphStyle("number", parent=_BASE, alignment=TA_RIGHT)
_NUMBER_BOLD = ParagraphStyle("number-bold", parent=_NUMBER, fontName="Helvetica-Bold")

_PAGE_WIDTH = A4[0] - 32 * mm


def _p(text: str, style: ParagraphStyle = _BASE) -> Paragraph:
    """A paragraph of plain text (anything that looks like markup is escaped)."""
    return Paragraph(escape(text), style)


def _lines(*lines: str | None) -> str:
    return "<br/>".join(escape(line) for line in lines if line)


def _labelled(label: str, value: str | None) -> str:
    return f'<font color="#5B6478">{escape(label)}</font>&nbsp;&nbsp;{escape(value or "—")}'


def _header(invoice: Invoice) -> Table:
    hotel = invoice.hotel
    locality = ", ".join(part for part in (hotel.city, hotel.state) if part)
    if hotel.postal_code:
        locality = f"{locality} {hotel.postal_code}".strip()
    contact = "  ·  ".join(part for part in (hotel.phone, hotel.email) if part)
    supplier = [
        _p(hotel.name, _HOTEL),
        Paragraph(_lines(hotel.address, locality, contact), _SMALL),
    ]
    if hotel.gstin:
        supplier.append(Paragraph(f"<b>GSTIN</b>&nbsp;&nbsp;{escape(hotel.gstin)}", _BASE))

    meta = [
        _p(invoice.title, _TITLE),
        Paragraph(
            "<br/>".join(
                [
                    _labelled("Invoice no.", invoice.number or "Not yet issued"),
                    _labelled("Date", invoice.issued_on.strftime("%d %b %Y")),
                    _labelled("Place of supply", hotel.state),
                ]
            ),
            _RIGHT,
        ),
    ]
    table = Table([[supplier, meta]], colWidths=[_PAGE_WIDTH * 0.58, _PAGE_WIDTH * 0.42])
    table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
                ("LINEBELOW", (0, 0), (-1, -1), 1.2, _PRIMARY),
            ]
        )
    )
    return table


def _parties(invoice: Invoice) -> Table:
    guest, reservation = invoice.guest, invoice.reservation
    guest_name = f"{guest.first_name} {guest.last_name}"
    locality = ", ".join(part for part in (guest.city, guest.state, guest.country) if part)
    bill_to = [
        _p("BILLED TO", _LABEL),
        _p(guest.company_name or guest_name, _BOLD),
        Paragraph(
            _lines(
                f"Guest: {guest_name}" if guest.company_name else None,
                guest.address,
                locality,
                guest.phone,
            ),
            _SMALL,
        ),
    ]
    if guest.gstin:
        bill_to.append(Paragraph(f"<b>GSTIN</b>&nbsp;&nbsp;{escape(guest.gstin)}", _BASE))

    nights = (reservation.check_out_date - reservation.check_in_date).days
    stay = [
        _p("STAY", _LABEL),
        Paragraph(
            "<br/>".join(
                [
                    _labelled("Confirmation", reservation.confirmation_number),
                    _labelled("Folio", invoice.folio.folio_number),
                    _labelled("Room", invoice.room_number),
                    _labelled("Check-in", reservation.check_in_date.strftime("%d %b %Y")),
                    _labelled("Check-out", reservation.check_out_date.strftime("%d %b %Y")),
                    _labelled("Nights", str(nights)),
                ]
            ),
            _BASE,
        ),
    ]
    table = Table([[bill_to, stay]], colWidths=[_PAGE_WIDTH * 0.58, _PAGE_WIDTH * 0.42])
    table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 10),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
            ]
        )
    )
    return table


def _grid(rows: list[list[Any]], widths: list[float], *, total_row: bool = False) -> Table:
    """A ruled table with a header band; the header repeats on every page."""
    table = Table(rows, colWidths=widths, repeatRows=1)
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), _BAND),
        ("LINEBELOW", (0, 0), (-1, 0), 0.6, _RULE),
        ("LINEABOVE", (0, 0), (-1, 0), 0.6, _RULE),
        ("LINEBELOW", (0, 1), (-1, -1), 0.4, _RULE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 4.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4.5),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
    ]
    if total_row:
        style.append(("LINEABOVE", (0, -1), (-1, -1), 0.8, _INK))
    table.setStyle(TableStyle(style))
    return table


def _charges(invoice: Invoice) -> Table:
    head = [
        _p("DATE", _HEAD),
        _p("DESCRIPTION", _HEAD),
        _p("HSN/SAC", _HEAD),
        _p("TAXABLE VALUE", _HEAD_RIGHT),
        _p("GST", _HEAD_RIGHT),
        _p("CGST", _HEAD_RIGHT),
        _p("SGST", _HEAD_RIGHT),
        _p("AMOUNT (INR)", _HEAD_RIGHT),
    ]
    rows: list[list[Any]] = [head]
    for line in invoice.charges:
        rows.append(
            [
                _p(line.business_date.strftime("%d %b %Y")),
                _p(line.description),
                _p(line.sac_code or "—"),
                _p(format_inr(line.amount), _NUMBER),
                _p(_rate(line.gst_rate), _NUMBER),
                _p(format_inr(line.cgst_amount), _NUMBER),
                _p(format_inr(line.sgst_amount), _NUMBER),
                _p(format_inr(line.total_amount), _NUMBER),
            ]
        )
    widths = [22 * mm, 0, 16 * mm, 25 * mm, 11 * mm, 18 * mm, 18 * mm, 25 * mm]
    widths[1] = _PAGE_WIDTH - sum(widths)
    return _grid(rows, widths)


def _tax_summary(invoice: Invoice) -> Table:
    rows: list[list[Any]] = [
        [
            _p("HSN/SAC", _HEAD),
            _p("GST", _HEAD_RIGHT),
            _p("TAXABLE", _HEAD_RIGHT),
            _p("CGST", _HEAD_RIGHT),
            _p("SGST", _HEAD_RIGHT),
            _p("TAX", _HEAD_RIGHT),
        ]
    ]
    for row in invoice.tax_rows:
        half = f'<font size="6.8" color="#5B6478">@ {_rate(row.gst_rate / 2)}</font>'
        rows.append(
            [
                _p(row.sac_code or "—"),
                _p(_rate(row.gst_rate), _NUMBER),
                _p(format_inr(row.taxable), _NUMBER),
                Paragraph(f"{format_inr(row.cgst)} {half}", _NUMBER),
                Paragraph(f"{format_inr(row.sgst)} {half}", _NUMBER),
                _p(format_inr(row.tax), _NUMBER),
            ]
        )
    rows.append(
        [
            _p("Total", _BOLD),
            _p(""),
            _p(format_inr(invoice.taxable_total), _NUMBER_BOLD),
            _p(format_inr(invoice.cgst_total), _NUMBER_BOLD),
            _p(format_inr(invoice.sgst_total), _NUMBER_BOLD),
            _p(format_inr(invoice.cgst_total + invoice.sgst_total), _NUMBER_BOLD),
        ]
    )
    width = _PAGE_WIDTH * 0.59
    widths = [width * f for f in (0.15, 0.1, 0.18, 0.21, 0.21, 0.15)]
    return _grid(rows, widths, total_row=True)


def _totals(invoice: Invoice) -> Table:
    rows: list[list[Any]] = [
        [_p("Taxable value"), _p(format_inr(invoice.taxable_total), _NUMBER)],
        [_p("CGST"), _p(format_inr(invoice.cgst_total), _NUMBER)],
        [_p("SGST"), _p(format_inr(invoice.sgst_total), _NUMBER)],
        [_p("Invoice total (INR)", _BOLD), _p(format_inr(invoice.grand_total), _NUMBER_BOLD)],
        [_p("Payments received"), _p(format_inr(invoice.paid_total), _NUMBER)],
        [
            _p("Refund due" if invoice.balance_due < 0 else "Balance due", _BOLD),
            _p(format_inr(abs(invoice.balance_due)), _NUMBER_BOLD),
        ],
    ]
    width = _PAGE_WIDTH * 0.37
    table = Table(rows, colWidths=[width * 0.55, width * 0.45])
    table.setStyle(
        TableStyle(
            [
                ("TOPPADDING", (0, 0), (-1, -1), 3.5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("BACKGROUND", (0, 3), (-1, 3), _BAND),
                ("LINEABOVE", (0, 3), (-1, 3), 0.8, _INK),
                ("LINEBELOW", (0, 3), (-1, 3), 0.4, _RULE),
                ("LINEABOVE", (0, 5), (-1, 5), 0.4, _RULE),
            ]
        )
    )
    return table


def _payments(invoice: Invoice) -> Table:
    rows: list[list[Any]] = [
        [
            _p("DATE", _HEAD),
            _p("PAYMENT METHOD", _HEAD),
            _p("REFERENCE", _HEAD),
            _p("AMOUNT (INR)", _HEAD_RIGHT),
        ]
    ]
    for payment in invoice.payments:
        method = (payment.payment_method or "other").replace("_", " ")
        rows.append(
            [
                _p(payment.business_date.strftime("%d %b %Y")),
                _p("UPI" if method == "upi" else method.capitalize()),
                _p(payment.reference or "—"),
                _p(format_inr(payment.total_amount), _NUMBER),
            ]
        )
    widths = [24 * mm, 40 * mm, 0, 30 * mm]
    widths[2] = _PAGE_WIDTH - sum(widths)
    return _grid(rows, widths)


def render_invoice_pdf(invoice: Invoice) -> bytes:
    """Lay the invoice out on A4 and return the PDF."""
    buffer = BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=16 * mm,
        rightMargin=16 * mm,
        topMargin=16 * mm,
        bottomMargin=18 * mm,
        title=f"{invoice.title.title()} {invoice.number or invoice.folio.folio_number}",
        author=invoice.hotel.name,
    )

    summary = Table(
        [[_tax_summary(invoice), _totals(invoice)]],
        colWidths=[_PAGE_WIDTH * 0.62, _PAGE_WIDTH * 0.38],
    )
    summary.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("ALIGN", (1, 0), (1, 0), "RIGHT"),
            ]
        )
    )

    closing: list[Any] = [
        Spacer(1, 10),
        _p("TAX SUMMARY", _LABEL),
        summary,
        Spacer(1, 8),
        Paragraph(
            f'<font color="#5B6478">Amount in words</font>&nbsp;&nbsp;'
            f"<b>{escape(rupees_in_words(invoice.grand_total))}</b>",
            _BASE,
        ),
    ]
    story: list[Any] = [
        _header(invoice),
        _parties(invoice),
        _charges(invoice),
        KeepTogether(closing),
    ]
    if invoice.payments:
        story += [Spacer(1, 12), KeepTogether([_p("PAYMENTS", _LABEL), _payments(invoice)])]

    notes = []
    if invoice.is_pro_forma:
        notes.append(
            "This is a pro forma invoice for an open folio. It is not a tax invoice; the tax "
            "invoice is issued when the folio is settled and closed."
        )
    notes.append("Tax is charged as CGST and SGST: the place of supply is the hotel.")
    story += [
        Spacer(1, 14),
        KeepTogether(
            [
                Paragraph(_lines(*notes), _SMALL),
                Spacer(1, 22),
                Paragraph(f"For <b>{escape(invoice.hotel.name)}</b>", _RIGHT),
                Spacer(1, 20),
                _p(
                    "Authorised signatory",
                    ParagraphStyle("sign", parent=_SMALL, alignment=TA_RIGHT),
                ),
            ]
        ),
    ]

    footer = (
        f"{invoice.hotel.name}  ·  {invoice.number or 'Pro forma ' + invoice.folio.folio_number}"
    )

    def draw_footer(canvas: Canvas, _document: Any) -> None:
        canvas.saveState()
        canvas.setStrokeColor(_RULE)
        canvas.setLineWidth(0.5)
        canvas.line(16 * mm, 13 * mm, A4[0] - 16 * mm, 13 * mm)
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(_MUTED)
        canvas.drawString(16 * mm, 9 * mm, footer)
        canvas.drawRightString(A4[0] - 16 * mm, 9 * mm, f"Page {canvas.getPageNumber()}")
        canvas.restoreState()

    document.build(story, onFirstPage=draw_footer, onLaterPages=draw_footer)
    return buffer.getvalue()
