from decimal import Decimal

import pytest
from httpx import AsyncClient

from app.services.gst import calculate_gst, calculate_room_gst, room_tariff_slab
from tests.conftest import Tenant


@pytest.mark.parametrize(
    ("tariff", "rate", "itc_eligible"),
    [
        ("0", "0", False),
        ("999.99", "0", False),
        ("1000", "0", False),  # top of the exempt slab
        ("1000.01", "5", False),
        ("1001", "5", False),
        ("4500", "5", False),
        ("7500", "5", False),  # top of the 5% slab
        ("7500.01", "18", True),
        ("7501", "18", True),
        ("25000", "18", True),
    ],
)
def test_room_tariff_slab_boundaries(tariff: str, rate: str, itc_eligible: bool) -> None:
    slab = room_tariff_slab(Decimal(tariff))
    assert slab.rate == Decimal(rate)
    assert slab.itc_eligible is itc_eligible


@pytest.mark.parametrize(
    ("tariff", "cgst", "sgst", "total"),
    [
        ("800.00", "0.00", "0.00", "800.00"),
        ("1000.00", "0.00", "0.00", "1000.00"),
        ("4500.00", "112.50", "112.50", "4725.00"),
        ("7500.00", "187.50", "187.50", "7875.00"),
        ("7500.01", "675.00", "675.00", "8850.01"),
        ("10000.00", "900.00", "900.00", "11800.00"),
    ],
)
def test_room_gst_amounts(tariff: str, cgst: str, sgst: str, total: str) -> None:
    gst = calculate_room_gst(Decimal(tariff))
    assert gst.cgst_amount == Decimal(cgst)
    assert gst.sgst_amount == Decimal(sgst)
    assert gst.total_tax == Decimal(cgst) + Decimal(sgst)
    assert gst.total_amount == Decimal(total)


def test_tax_is_rounded_half_up_to_the_paisa() -> None:
    # 2.5% of 1001.00 is 25.025, which rounds up to 25.03 for each half.
    gst = calculate_room_gst(Decimal("1001.00"))
    assert gst.cgst_amount == gst.sgst_amount == Decimal("25.03")
    assert gst.total_amount == Decimal("1051.06")


def test_cgst_and_sgst_are_always_equal() -> None:
    for paise in range(100001, 100200):
        gst = calculate_room_gst(Decimal(paise) / 100)
        assert gst.cgst_amount == gst.sgst_amount


def test_negative_values_are_rejected() -> None:
    with pytest.raises(ValueError, match="negative"):
        calculate_room_gst(Decimal("-1"))
    with pytest.raises(ValueError, match="negative"):
        calculate_gst(Decimal("100"), Decimal("-5"))


async def test_room_quote_endpoint(client: AsyncClient, tenant: Tenant) -> None:
    response = await client.get(
        "/api/v1/gst/room-quote",
        headers=tenant.headers,
        params={"tariff_per_night": "8000.00", "nights": 3},
    )
    assert response.status_code == 200, response.text
    assert response.json() == {
        "sac_code": "996311",
        "nights": 3,
        "tariff_per_night": "8000.00",
        "gst_rate": "18",
        "itc_eligible": True,
        "taxable_amount": "24000.00",
        "cgst_amount": "2160.00",
        "sgst_amount": "2160.00",
        "total_tax": "4320.00",
        "total_amount": "28320.00",
    }
