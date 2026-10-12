"""GST invoices: content, numbering, the PDF itself, and the hotel profile printed on it."""

import asyncio
from datetime import date, timedelta
from decimal import Decimal
from io import BytesIO
from typing import Any

import pytest
from httpx import AsyncClient, Response
from pypdf import PdfReader

from app.models import UserRole
from app.services.invoices import (
    MAX_INVOICE_NUMBER_LENGTH,
    financial_year,
    format_inr,
    format_invoice_number,
    rupees_in_words,
)
from tests.conftest import Inventory, Tenant, TenantFactory, create_inventory

API = "/api/v1"
PROFILE = {
    "name": "Aravalli Heritage Hotel",
    "gstin": "08AAACH7409R1ZZ",
    "address": "14 Lake Palace Road",
    "city": "Udaipur",
    "state": "Rajasthan",
    "postal_code": "313001",
    "phone": "+91 294 242 0000",
    "email": "accounts@aravalli.example.com",
}


async def post(client: AsyncClient, tenant: Tenant, path: str, **body: Any) -> Any:
    response = await client.post(f"{API}{path}", headers=tenant.headers, json=body or None)
    assert response.status_code < 300, (path, response.status_code, response.text)
    return response.json()


async def in_house_folio(
    client: AsyncClient, tenant: Tenant, inventory: Inventory, room: int = 0
) -> tuple[str, str]:
    """Check a guest in tonight and post the night's room charge. Returns (reservation, folio)."""
    today = date.today()
    reservation = await post(
        client,
        tenant,
        "/reservations",
        guest_id=inventory.guest_id,
        room_type_id=inventory.room_type_id,
        room_id=inventory.room_ids[room],
        check_in_date=today.isoformat(),
        check_out_date=(today + timedelta(days=1)).isoformat(),
    )
    await post(client, tenant, f"/reservations/{reservation['id']}/check-in")
    await post(client, tenant, "/night-audit/run", business_date=today.isoformat())
    folio = await client.get(
        f"{API}/folios", headers=tenant.headers, params={"reservation_id": reservation["id"]}
    )
    return reservation["id"], folio.json()["id"]


async def settle_and_check_out(
    client: AsyncClient, tenant: Tenant, reservation_id: str, folio_id: str
) -> None:
    folio = (await client.get(f"{API}/folios/{folio_id}", headers=tenant.headers)).json()
    await post(
        client,
        tenant,
        f"/folios/{folio_id}/payments",
        amount=folio["balance"],
        payment_method="card",
    )
    await post(client, tenant, f"/reservations/{reservation_id}/check-out")


async def invoice(client: AsyncClient, tenant: Tenant, folio_id: str) -> Response:
    return await client.get(f"{API}/folios/{folio_id}/invoice", headers=tenant.headers)


def text_of(response: Response) -> str:
    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "application/pdf"
    assert response.content.startswith(b"%PDF-")
    reader = PdfReader(BytesIO(response.content))
    return "\n".join(page.extract_text() for page in reader.pages)


async def folio_state(client: AsyncClient, tenant: Tenant, folio_id: str) -> dict[str, Any]:
    body: dict[str, Any] = (
        await client.get(f"{API}/folios/{folio_id}", headers=tenant.headers)
    ).json()
    return body


# --- the document ---------------------------------------------------------------------


async def test_closed_folio_gets_a_numbered_tax_invoice_with_gst_details(
    client: AsyncClient, tenant: Tenant, inventory: Inventory
) -> None:
    saved = await client.patch(f"{API}/hotel", headers=tenant.headers, json=PROFILE)
    assert saved.status_code == 200, saved.text
    await client.patch(
        f"{API}/guests/{inventory.guest_id}",
        headers=tenant.headers,
        json={"company_name": "Rao Exports Pvt Ltd", "gstin": "29AAGFN1234C1Z5"},
    )
    reservation_id, folio_id = await in_house_folio(client, tenant, inventory)
    await post(
        client,
        tenant,
        f"/folios/{folio_id}/charges",
        description="Laundry",
        amount="400.00",
        gst_rate="18",
        sac_code="999712",
    )
    mistake = await post(
        client, tenant, f"/folios/{folio_id}/charges", description="Minibar", amount="900.00"
    )
    await post(
        client,
        tenant,
        f"/folios/{folio_id}/transactions/{mistake['id']}/reverse",
        reason="Wrong room",
    )
    await settle_and_check_out(client, tenant, reservation_id, folio_id)

    response = await invoice(client, tenant, folio_id)
    text = text_of(response)

    year = financial_year(date.today())
    number = format_invoice_number(year, 1)
    assert response.headers["content-disposition"] == (
        f'attachment; filename="Invoice-{number.replace("/", "-")}.pdf"'
    )
    assert "TAX INVOICE" in text and "PRO FORMA" not in text
    assert number in text
    # Supplier and recipient.
    for expected in (
        "Aravalli Heritage Hotel",
        "14 Lake Palace Road",
        "Udaipur, Rajasthan 313001",
        "08AAACH7409R1ZZ",
        "Rao Exports Pvt Ltd",
        "Guest: Asha Rao",
        "29AAGFN1234C1Z5",
    ):
        assert expected in text, expected
    # Room night at Rs 4,500 falls in the 5% slab: 112.50 CGST + 112.50 SGST.
    assert "996311" in text and "4,500.00" in text and "112.50" in text and "4,725.00" in text
    assert "Laundry" in text and "999712" in text and "472.00" in text
    # Totals: 4,900 taxable, 148.50 each of CGST and SGST, 5,197 in all.
    assert "4,900.00" in text and "148.50" in text and "5,197.00" in text
    assert "Rupees Five Thousand One Hundred Ninety-Seven Only" in text
    # The reversed charge and its reversal are not on the invoice.
    assert "Minibar" not in text and "Reversal" not in text

    state = await folio_state(client, tenant, folio_id)
    assert state["invoice_number"] == number
    assert state["invoice_date"] == date.today().isoformat()


async def test_open_folio_gets_a_pro_forma_invoice_without_a_number(
    client: AsyncClient, tenant: Tenant, inventory: Inventory
) -> None:
    _, folio_id = await in_house_folio(client, tenant, inventory)

    response = await invoice(client, tenant, folio_id)
    text = text_of(response)

    assert "PRO FORMA INVOICE" in text and "TAX INVOICE" not in text
    assert "Not yet issued" in text and "not a tax invoice" in text
    assert "Balance due" in text and "4,725.00" in text
    assert response.headers["content-disposition"].startswith('attachment; filename="Proforma-F-')
    state = await folio_state(client, tenant, folio_id)
    assert state["invoice_number"] is None and state["invoice_date"] is None


async def test_hotel_without_gstin_issues_a_plain_invoice(
    client: AsyncClient, tenant: Tenant, inventory: Inventory
) -> None:
    reservation_id, folio_id = await in_house_folio(client, tenant, inventory)
    await settle_and_check_out(client, tenant, reservation_id, folio_id)

    text = text_of(await invoice(client, tenant, folio_id))
    assert "INVOICE" in text and "TAX INVOICE" not in text and "GSTIN" not in text


async def test_a_long_stay_flows_onto_further_pages(
    client: AsyncClient, tenant: Tenant, inventory: Inventory
) -> None:
    _, folio_id = await in_house_folio(client, tenant, inventory)
    for number in range(60):
        await post(
            client,
            tenant,
            f"/folios/{folio_id}/charges",
            description=f"Restaurant order {number + 1} <b>&</b> service",
            amount="100.00",
            gst_rate="5",
        )

    response = await invoice(client, tenant, folio_id)
    reader = PdfReader(BytesIO(response.content))
    assert len(reader.pages) >= 2
    text = " ".join(text_of(response).split())  # a long description wraps inside its cell
    assert "Restaurant order 60 <b>&</b> service" in text  # printed literally, not as markup
    assert "Page 2" in text


# --- numbering ------------------------------------------------------------------------


async def test_invoice_numbers_are_consecutive_and_never_change(
    client: AsyncClient, tenant: Tenant, inventory: Inventory
) -> None:
    year = financial_year(date.today())
    folios = []
    for room in (0, 1):
        reservation_id, folio_id = await in_house_folio(client, tenant, inventory, room)
        await settle_and_check_out(client, tenant, reservation_id, folio_id)
        folios.append(folio_id)

    # Issued in the order the invoices are first produced, not the order of the stays.
    second_stay, first_stay = folios[1], folios[0]
    assert (await invoice(client, tenant, second_stay)).status_code == 200
    assert (await invoice(client, tenant, first_stay)).status_code == 200
    assert (await invoice(client, tenant, second_stay)).status_code == 200  # a re-download

    assert (await folio_state(client, tenant, second_stay))["invoice_number"] == (
        format_invoice_number(year, 1)
    )
    assert (await folio_state(client, tenant, first_stay))["invoice_number"] == (
        format_invoice_number(year, 2)
    )


async def test_concurrent_first_downloads_issue_one_number(
    client: AsyncClient, tenant: Tenant, inventory: Inventory
) -> None:
    reservation_id, folio_id = await in_house_folio(client, tenant, inventory)
    await settle_and_check_out(client, tenant, reservation_id, folio_id)

    responses = await asyncio.gather(*(invoice(client, tenant, folio_id) for _ in range(5)))

    assert {r.status_code for r in responses} == {200}
    assert len({r.headers["content-disposition"] for r in responses}) == 1
    number = (await folio_state(client, tenant, folio_id))["invoice_number"]
    assert number == format_invoice_number(financial_year(date.today()), 1)


async def test_each_hotel_has_its_own_series(
    client: AsyncClient, make_tenant: TenantFactory
) -> None:
    numbers = []
    for _ in range(2):
        hotel = await make_tenant()
        inventory = await create_inventory(client, hotel)
        reservation_id, folio_id = await in_house_folio(client, hotel, inventory)
        await settle_and_check_out(client, hotel, reservation_id, folio_id)
        assert (await invoice(client, hotel, folio_id)).status_code == 200
        numbers.append((await folio_state(client, hotel, folio_id))["invoice_number"])
        other = hotel

    assert numbers[0] == numbers[1] == format_invoice_number(financial_year(date.today()), 1)
    # A folio id from one hotel means nothing in another.
    first_hotel = await make_tenant()
    assert (await invoice(client, first_hotel, folio_id)).status_code == 404
    assert other.hotel_id != first_hotel.hotel_id


def test_invoice_number_format_and_financial_year() -> None:
    assert format_invoice_number(2026, 123) == "INV/26-27/000123"
    assert format_invoice_number(2099, 999_999) == "INV/99-00/999999"
    assert len(format_invoice_number(2026, 999_999)) == MAX_INVOICE_NUMBER_LENGTH
    # The Indian financial year runs from 1 April to 31 March.
    assert financial_year(date(2026, 4, 1)) == 2026
    assert financial_year(date(2027, 3, 31)) == 2026
    assert financial_year(date(2027, 4, 1)) == 2027
    assert financial_year(date(2026, 1, 15)) == 2025


# --- access and edge cases --------------------------------------------------------------


async def test_nothing_to_invoice_and_who_may_download(
    client: AsyncClient, tenant: Tenant, inventory: Inventory, make_tenant: TenantFactory
) -> None:
    reservation = await post(
        client,
        tenant,
        "/reservations",
        guest_id=inventory.guest_id,
        room_type_id=inventory.room_type_id,
        check_in_date="2027-05-10",
        check_out_date="2027-05-12",
    )
    folio = await post(client, tenant, "/folios", reservation_id=reservation["id"])

    empty = await invoice(client, tenant, folio["id"])
    assert empty.status_code == 409
    assert "nothing to invoice" in empty.json()["detail"]

    assert (await client.get(f"{API}/folios/{folio['id']}/invoice")).status_code == 401
    housekeeping = await make_tenant(UserRole.HOUSEKEEPING)
    forbidden = await client.get(
        f"{API}/folios/{folio['id']}/invoice", headers=housekeeping.headers
    )
    assert forbidden.status_code == 403


# --- words and digits -------------------------------------------------------------------


@pytest.mark.parametrize(
    ("amount", "words"),
    [
        ("0", "Rupees Zero Only"),
        ("1", "Rupees One Only"),
        ("19.05", "Rupees Nineteen and Five Paise Only"),
        ("100", "Rupees One Hundred Only"),
        ("4725.00", "Rupees Four Thousand Seven Hundred Twenty-Five Only"),
        ("100000", "Rupees One Lakh Only"),
        (
            "1234567.50",
            "Rupees Twelve Lakh Thirty-Four Thousand Five Hundred Sixty-Seven and Fifty Paise Only",
        ),
        ("250000000", "Rupees Twenty-Five Crore Only"),
    ],
)
def test_rupees_in_words_uses_the_indian_system(amount: str, words: str) -> None:
    assert rupees_in_words(Decimal(amount)) == words


@pytest.mark.parametrize(
    ("amount", "formatted"),
    [
        ("0", "0.00"),
        ("999", "999.00"),
        ("1000", "1,000.00"),
        ("123456.7", "1,23,456.70"),
        ("12345678.91", "1,23,45,678.91"),
        ("-4500", "-4,500.00"),
    ],
)
def test_amounts_use_indian_digit_grouping(amount: str, formatted: str) -> None:
    assert format_inr(Decimal(amount)) == formatted


# --- hotel profile ----------------------------------------------------------------------


async def test_hotel_profile_can_be_read_by_staff_and_edited_by_management(
    client: AsyncClient, tenant: Tenant, make_tenant: TenantFactory
) -> None:
    before = await client.get(f"{API}/hotel", headers=tenant.headers)
    assert before.status_code == 200
    assert before.json()["id"] == str(tenant.hotel_id)
    assert before.json()["address"] is None

    saved = await client.patch(f"{API}/hotel", headers=tenant.headers, json=PROFILE)
    assert saved.status_code == 200, saved.text
    assert {key: saved.json()[key] for key in PROFILE} == PROFILE

    cleared = await client.patch(
        f"{API}/hotel", headers=tenant.headers, json={"phone": "", "gstin": None}
    )
    assert cleared.status_code == 200
    assert cleared.json()["phone"] is None and cleared.json()["gstin"] is None
    assert cleared.json()["city"] == "Udaipur"  # untouched

    front_desk = await make_tenant(UserRole.FRONT_DESK)
    assert (await client.get(f"{API}/hotel", headers=front_desk.headers)).status_code == 200
    forbidden = await client.patch(
        f"{API}/hotel", headers=front_desk.headers, json={"city": "Jaipur"}
    )
    assert forbidden.status_code == 403
    # Another hotel's profile is untouched by any of this.
    assert (await client.get(f"{API}/hotel", headers=front_desk.headers)).json()["city"] is None


@pytest.mark.parametrize(
    "changes",
    [
        {"gstin": "08AAACH7409R1Z"},  # 14 characters
        {"gstin": "08aaach7409r1zz"},  # lower case
        {"gstin": "XXAAACH7409R1ZZ"},  # no state code
        {"name": ""},
        {"name": None},
        {"email": "not-an-email"},
        {"slug": "another-hotel"},
        {"is_active": False},
    ],
)
async def test_hotel_profile_rejects_invalid_changes(
    client: AsyncClient, tenant: Tenant, changes: dict[str, Any]
) -> None:
    response = await client.patch(f"{API}/hotel", headers=tenant.headers, json=changes)
    assert response.status_code == 422, response.text
