"""Property Map: one date's view of every room, plus property type and unit groups."""

from typing import Any

from httpx import AsyncClient

from tests.conftest import Inventory, Tenant, TenantFactory, create_inventory

API = "/api/v1"


async def book(
    client: AsyncClient,
    tenant: Tenant,
    inventory: Inventory,
    check_in: str,
    check_out: str,
    room_id: str | None = None,
) -> str:
    response = await client.post(
        f"{API}/reservations",
        headers=tenant.headers,
        json={
            "guest_id": inventory.guest_id,
            "room_type_id": inventory.room_type_id,
            "room_id": room_id,
            "check_in_date": check_in,
            "check_out_date": check_out,
            "source": "booking_com",
        },
    )
    assert response.status_code == 201, response.text
    reservation_id: str = response.json()["id"]
    return reservation_id


async def property_map(client: AsyncClient, tenant: Tenant, day: str) -> dict[str, Any]:
    response = await client.get(f"{API}/property-map", headers=tenant.headers, params={"date": day})
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


async def test_each_room_gets_its_status_for_the_date(
    client: AsyncClient, make_tenant: TenantFactory
) -> None:
    tenant = await make_tenant()
    inventory = await create_inventory(client, tenant, rooms=4)
    in_house_room, reserved_room, broken_room, free_room = inventory.room_ids
    response = await client.patch(
        f"{API}/rooms/{broken_room}", headers=tenant.headers, json={"is_active": False}
    )
    assert response.status_code == 200, response.text

    in_house = await book(client, tenant, inventory, "2027-06-10", "2027-06-12", in_house_room)
    response = await client.post(f"{API}/reservations/{in_house}/check-in", headers=tenant.headers)
    assert response.status_code == 200, response.text
    reserved = await book(client, tenant, inventory, "2027-06-11", "2027-06-13", reserved_room)
    unassigned = await book(client, tenant, inventory, "2027-06-11", "2027-06-12")

    body = await property_map(client, tenant, "2027-06-11")
    units = {unit["id"]: unit for unit in body["units"]}
    assert body["date"] == "2027-06-11"
    assert units[in_house_room]["status"] == "occupied"
    assert units[in_house_room]["reservation"]["id"] == in_house
    assert units[reserved_room]["status"] == "reserved"
    assert units[reserved_room]["reservation"]["id"] == reserved
    assert units[reserved_room]["reservation"]["source"] == "booking_com"
    assert units[broken_room]["status"] == "out_of_order"
    assert units[free_room]["reservation"] is None
    assert units[free_room]["status"] == "available"
    assert [stay["id"] for stay in body["unassigned"]] == [unassigned]
    (room_type,) = body["room_types"]
    assert (room_type["total_rooms"], room_type["available"]) == (3, 0)
    assert room_type["base_rate"] == "4500.00"

    # On the day they are due out, a checked-in guest is still in the room.
    due_out = await property_map(client, tenant, "2027-06-12")
    units = {unit["id"]: unit for unit in due_out["units"]}
    assert units[in_house_room]["status"] == "occupied"
    assert units[reserved_room]["status"] == "reserved"
    assert due_out["unassigned"] == []


async def test_property_map_is_tenant_scoped(
    client: AsyncClient, make_tenant: TenantFactory
) -> None:
    owner, other = await make_tenant(), await make_tenant()
    await create_inventory(client, owner)

    body = await property_map(client, other, "2027-06-11")
    assert (body["units"], body["room_types"], body["unassigned"]) == ([], [], [])


async def test_property_type_starts_unset_and_can_be_chosen(
    client: AsyncClient, tenant: Tenant
) -> None:
    hotel = await client.get(f"{API}/hotel", headers=tenant.headers)
    assert hotel.json()["property_type"] is None

    chosen = await client.patch(
        f"{API}/hotel", headers=tenant.headers, json={"property_type": "hostel"}
    )
    assert chosen.status_code == 200, chosen.text
    assert chosen.json()["property_type"] == "hostel"

    for bad in ("castle", None):
        response = await client.patch(
            f"{API}/hotel", headers=tenant.headers, json={"property_type": bad}
        )
        assert response.status_code == 422, response.text
    assert (await client.get(f"{API}/hotel", headers=tenant.headers)).json()[
        "property_type"
    ] == "hostel"


async def test_room_group_is_trimmed_and_blank_means_none(
    client: AsyncClient, tenant: Tenant, inventory: Inventory
) -> None:
    created = await client.post(
        f"{API}/rooms",
        headers=tenant.headers,
        json={
            "room_type_id": inventory.room_type_id,
            "room_number": "D1",
            "floor_or_zone": "  Poolside cottages ",
        },
    )
    assert created.status_code == 201, created.text
    assert created.json()["floor_or_zone"] == "Poolside cottages"

    cleared = await client.patch(
        f"{API}/rooms/{created.json()['id']}", headers=tenant.headers, json={"floor_or_zone": "  "}
    )
    assert cleared.status_code == 200, cleared.text
    assert cleared.json()["floor_or_zone"] is None

    too_long = await client.patch(
        f"{API}/rooms/{created.json()['id']}",
        headers=tenant.headers,
        json={"floor_or_zone": "x" * 51},
    )
    assert too_long.status_code == 422


async def test_unit_kind_defaults_from_the_property_and_can_be_mixed(
    client: AsyncClient, tenant: Tenant
) -> None:
    async def create(code: str, **extra: Any) -> dict[str, Any]:
        response = await client.post(
            f"{API}/room-types",
            headers=tenant.headers,
            json={"name": code, "code": code, "base_rate": "1000.00", **extra},
        )
        assert response.status_code == 201, response.text
        body: dict[str, Any] = response.json()
        return body

    # Not chosen yet (a hotel), and a hostel, both default to rooms: hostels mix.
    assert (await create("DBL"))["unit_kind"] == "room"
    await client.patch(f"{API}/hotel", headers=tenant.headers, json={"property_type": "hostel"})
    assert (await create("PRV"))["unit_kind"] == "room"
    dorm = await create("DRM", unit_kind="dorm_bed")
    assert dorm["unit_kind"] == "dorm_bed"

    await client.patch(f"{API}/hotel", headers=tenant.headers, json={"property_type": "apartment"})
    assert (await create("1BHK"))["unit_kind"] == "flat"
    await client.patch(f"{API}/hotel", headers=tenant.headers, json={"property_type": "resort"})
    assert (await create("COT"))["unit_kind"] == "villa"

    changed = await client.patch(
        f"{API}/room-types/{dorm['id']}", headers=tenant.headers, json={"unit_kind": "room"}
    )
    assert changed.json()["unit_kind"] == "room"
    for bad in ({"unit_kind": "castle"}, {"unit_kind": None}):
        response = await client.patch(
            f"{API}/room-types/{dorm['id']}", headers=tenant.headers, json=bad
        )
        assert response.status_code == 422, response.text

    chart = await client.get(
        f"{API}/tape-chart",
        headers=tenant.headers,
        params={"start": "2027-06-10", "end": "2027-06-11"},
    )
    kinds = {room_type["code"]: room_type["unit_kind"] for room_type in chart.json()["room_types"]}
    assert kinds == {"DBL": "room", "PRV": "room", "DRM": "room", "1BHK": "flat", "COT": "villa"}
    body = await property_map(client, tenant, "2027-06-10")
    assert {room_type["unit_kind"] for room_type in body["room_types"]} == {"room", "flat", "villa"}
