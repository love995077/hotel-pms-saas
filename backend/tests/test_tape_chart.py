from httpx import AsyncClient

from tests.conftest import Inventory, Tenant, TenantFactory, create_inventory

API = "/api/v1"
WINDOW = {"start": "2027-06-10", "end": "2027-06-14"}


async def book(
    client: AsyncClient, tenant: Tenant, inventory: Inventory, check_in: str, check_out: str
) -> str:
    response = await client.post(
        f"{API}/reservations",
        headers=tenant.headers,
        json={
            "guest_id": inventory.guest_id,
            "room_type_id": inventory.room_type_id,
            "check_in_date": check_in,
            "check_out_date": check_out,
            "source": "makemytrip",
        },
    )
    assert response.status_code == 201, response.text
    reservation_id: str = response.json()["id"]
    return reservation_id


async def test_tape_chart_returns_rooms_availability_and_reservations(
    client: AsyncClient, tenant: Tenant, inventory: Inventory
) -> None:
    inside = await book(client, tenant, inventory, "2027-06-11", "2027-06-13")
    await book(client, tenant, inventory, "2027-06-14", "2027-06-16")  # starts after the window
    await client.post(
        f"{API}/reservations/{inside}/assign-room",
        headers=tenant.headers,
        json={"room_id": inventory.room_ids[0]},
    )

    response = await client.get(f"{API}/tape-chart", headers=tenant.headers, params=WINDOW)

    assert response.status_code == 200, response.text
    chart = response.json()
    (room_type,) = chart["room_types"]
    assert room_type["code"] == "DLX"
    assert [r["room_number"] for r in room_type["rooms"]] == ["101", "102"]
    assert [d["date"] for d in room_type["availability"]] == [
        "2027-06-10",
        "2027-06-11",
        "2027-06-12",
        "2027-06-13",
    ]
    assert [d["available"] for d in room_type["availability"]] == [2, 1, 1, 2]

    (reservation,) = chart["reservations"]
    assert reservation["id"] == inside
    assert reservation["guest_name"] == "Asha Rao"
    assert reservation["room_id"] == inventory.room_ids[0]
    assert reservation["source"] == "makemytrip"
    assert reservation["status"] == "confirmed"


async def test_tape_chart_hides_cancelled_reservations_unless_asked(
    client: AsyncClient, tenant: Tenant, inventory: Inventory
) -> None:
    cancelled = await book(client, tenant, inventory, "2027-06-11", "2027-06-13")
    await client.post(f"{API}/reservations/{cancelled}/cancel", headers=tenant.headers)

    default = await client.get(f"{API}/tape-chart", headers=tenant.headers, params=WINDOW)
    everything = await client.get(
        f"{API}/tape-chart", headers=tenant.headers, params={**WINDOW, "include_released": True}
    )

    assert default.json()["reservations"] == []
    assert [r["status"] for r in everything.json()["reservations"]] == ["cancelled"]


async def test_tape_chart_is_scoped_to_the_callers_hotel(
    client: AsyncClient, make_tenant: TenantFactory
) -> None:
    hotel_a = await make_tenant()
    hotel_b = await make_tenant()
    inventory_a = await create_inventory(client, hotel_a)
    await book(client, hotel_a, inventory_a, "2027-06-11", "2027-06-13")

    chart_b = (await client.get(f"{API}/tape-chart", headers=hotel_b.headers, params=WINDOW)).json()

    assert chart_b["room_types"] == []
    assert chart_b["reservations"] == []
    assert (await client.get(f"{API}/tape-chart", params=WINDOW)).status_code == 401
