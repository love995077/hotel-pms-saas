"""Indian GST for hotel accommodation (SAC 996311).

The rate is chosen by the tariff of one room for one night:

    up to Rs 1,000            0%  (exempt)
    above Rs 1,000 to 7,500   5%  (no input tax credit)
    above Rs 7,500           18%  (with input tax credit)

The place of supply for accommodation is the hotel itself, so the tax is always
intra-state: half CGST and half SGST, never IGST.

To change the rules, edit ROOM_TARIFF_SLABS; nothing else encodes them.
"""

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

SAC_ACCOMMODATION = "996311"
_PAISA = Decimal("0.01")


@dataclass(frozen=True, slots=True)
class GstSlab:
    # Highest tariff (inclusive) the slab applies to; None means no upper limit.
    upper_limit: Decimal | None
    rate: Decimal
    itc_eligible: bool


ROOM_TARIFF_SLABS: tuple[GstSlab, ...] = (
    GstSlab(upper_limit=Decimal("1000"), rate=Decimal("0"), itc_eligible=False),
    GstSlab(upper_limit=Decimal("7500"), rate=Decimal("5"), itc_eligible=False),
    GstSlab(upper_limit=None, rate=Decimal("18"), itc_eligible=True),
)


@dataclass(frozen=True, slots=True)
class GstBreakdown:
    taxable_amount: Decimal
    gst_rate: Decimal
    cgst_amount: Decimal
    sgst_amount: Decimal
    itc_eligible: bool

    @property
    def total_tax(self) -> Decimal:
        return self.cgst_amount + self.sgst_amount

    @property
    def total_amount(self) -> Decimal:
        return self.taxable_amount + self.total_tax


def round_money(value: Decimal) -> Decimal:
    return value.quantize(_PAISA, rounding=ROUND_HALF_UP)


def room_tariff_slab(tariff_per_night: Decimal) -> GstSlab:
    if tariff_per_night < 0:
        raise ValueError("Tariff cannot be negative")
    for slab in ROOM_TARIFF_SLABS:
        if slab.upper_limit is None or tariff_per_night <= slab.upper_limit:
            return slab
    raise AssertionError("ROOM_TARIFF_SLABS must end with an open-ended slab")


def calculate_gst(
    taxable_amount: Decimal, rate: Decimal, *, itc_eligible: bool = True
) -> GstBreakdown:
    """Split GST at `rate` percent into equal CGST and SGST, each rounded to the paisa."""
    if taxable_amount < 0:
        raise ValueError("Taxable amount cannot be negative")
    if rate < 0:
        raise ValueError("GST rate cannot be negative")
    taxable = round_money(taxable_amount)
    half = round_money(taxable * rate / Decimal(200))
    return GstBreakdown(
        taxable_amount=taxable,
        gst_rate=rate,
        cgst_amount=half,
        sgst_amount=half,
        itc_eligible=itc_eligible,
    )


def calculate_room_gst(tariff_per_night: Decimal) -> GstBreakdown:
    """GST on one room-night, with the rate chosen by the tariff slab."""
    slab = room_tariff_slab(tariff_per_night)
    return calculate_gst(tariff_per_night, slab.rate, itc_eligible=slab.itc_eligible)
