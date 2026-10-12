import asyncio
from typing import Any

from httpx import AsyncClient, Response

from tests.conftest import Inventory, Tenant, TenantFactory, create_inventory

RESERVATIONS = "/api/v1/reservations"


def booking(inventory: Inventory, check_in: str, check_out: str, **extra: Any) -> dict[str, Any]:
    return {
        "guest_id": inventory.guest_id,
        "room_type_id": inventory.room_type_id,
        "check_in_date": check_in,
        "check_out_date": check_out,
        **extra,
    }


async def book(
    client: AsyncClient,
    tenant: Tenant,
    inventory: Inventory,
    check_in: str,
    check_out: str,
    **extra: Any,
) -> Response:
    return await client.post(
        RESERVATIONS, headers=tenant.headers, json=booking(inventory, check_in, check_out, **extra)
    )


async def available(client: AsyncClient, tenant: Tenant, start: str, end: str) -> list[int]:
    response = await client.get(
        "/api/v1/availability", headers=tenant.headers, params={"start": start, "end": end}
    )
    assert response.status_code == 200, response.text
    (room_type,) = response.json()
    return [day["available"] for day in room_type["days"]]


async def test_create_reservation(
    client: AsyncClient, tenant: Tenant, inventory: Inventory
) -> None:
    response = await book(client, tenant, inventory, "2027-03-10", "2027-03-13", adults=2)

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "confirmed"
    assert body["source"] == "direct"
    assert body["room_type_id"] == inventory.room_type_id
    # Booked against the room type; no physical room yet.
    assert body["room_id"] is None
    # Rate defaults to the room type's base rate.
    assert body["rate_per_night"] == "4500.00"
    assert len(body["confirmation_number"]) == 10

    fetched = await client.get(f"{RESERVATIONS}/{body['id']}", headers=tenant.headers)
    assert fetched.status_code == 200
    assert fetched.json() == body


async def test_create_reservation_with_explicit_rate_and_source(
    client: AsyncClient, tenant: Tenant, inventory: Inventory
) -> None:
    response = await book(
        client,
        tenant,
        inventory,
        "2027-03-10",
        "2027-03-11",
        rate_per_night="8200.50",
        source="booking_com",
        external_reference="BDC-991",
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["rate_per_night"] == "8200.50"
    assert body["source"] == "booking_com"
    assert body["external_reference"] == "BDC-991"


async def test_reservation_decrements_availability_for_its_nights_only(
    client: AsyncClient, tenant: Tenant, inventory: Inventory
) -> None:
    assert await available(client, tenant, "2027-03-09", "2027-03-14") == [2, 2, 2, 2, 2]

    await book(client, tenant, inventory, "2027-03-10", "2027-03-13")

    # 9th free, 10th-12th held, 13th is the departure day and free again.
    assert await available(client, tenant, "2027-03-09", "2027-03-14") == [2, 1, 1, 1, 2]


async def test_create_reservation_rejected_when_sold_out(
    client: AsyncClient, tenant: Tenant, inventory: Inventory
) -> None:
    for _ in range(2):
        assert (
            await book(client, tenant, inventory, "2027-03-10", "2027-03-13")
        ).status_code == 201

    # Overlaps a single sold-out night (the 12th).
    response = await book(client, tenant, inventory, "2027-03-12", "2027-03-15")

    assert response.status_code == 409
    assert "2027-03-12" in response.json()["detail"]


async def test_back_to_back_stays_share_the_changeover_day(
    client: AsyncClient, tenant: Tenant
) -> None:
    inventory = await create_inventory(client, tenant, rooms=1)
    assert (await book(client, tenant, inventory, "2027-03-10", "2027-03-12")).status_code == 201
    assert (await book(client, tenant, inventory, "2027-03-12", "2027-03-14")).status_code == 201
    assert (await book(client, tenant, inventory, "2027-03-08", "2027-03-10")).status_code == 201


async def test_concurrent_bookings_for_the_last_room_cannot_both_succeed(
    client: AsyncClient, tenant: Tenant
) -> None:
    inventory = await create_inventory(client, tenant, rooms=1)

    responses = await asyncio.gather(
        *(book(client, tenant, inventory, "2027-03-10", "2027-03-12") for _ in range(6))
    )

    assert sorted(r.status_code for r in responses) == [201, 409, 409, 409, 409, 409]
    assert await available(client, tenant, "2027-03-10", "2027-03-12") == [0, 0]


async def test_cancelling_releases_inventory(client: AsyncClient, tenant: Tenant) -> None:
    inventory = await create_inventory(client, tenant, rooms=1)
    first = await book(client, tenant, inventory, "2027-03-10", "2027-03-12")
    assert (await book(client, tenant, inventory, "2027-03-10", "2027-03-12")).status_code == 409

    cancelled = await client.post(
        f"{RESERVATIONS}/{first.json()['id']}/cancel", headers=tenant.headers
    )
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"

    assert (await book(client, tenant, inventory, "2027-03-10", "2027-03-12")).status_code == 201


async def test_inactive_rooms_do_not_count_as_inventory(
    client: AsyncClient, tenant: Tenant, inventory: Inventory
) -> None:
    response = await client.patch(
        f"/api/v1/rooms/{inventory.room_ids[0]}", headers=tenant.headers, json={"is_active": False}
    )
    assert response.status_code == 200
    assert await available(client, tenant, "2027-03-10", "2027-03-11") == [1]


async def test_create_reservation_validates_input(
    client: AsyncClient, tenant: Tenant, inventory: Inventory
) -> None:
    same_day = await book(client, tenant, inventory, "2027-03-10", "2027-03-10")
    reversed_dates = await book(client, tenant, inventory, "2027-03-12", "2027-03-10")
    no_adults = await book(client, tenant, inventory, "2027-03-10", "2027-03-11", adults=0)
    too_many = await book(
        client, tenant, inventory, "2027-03-10", "2027-03-11", adults=3, children=1
    )
    unknown_field = await book(
        client, tenant, inventory, "2027-03-10", "2027-03-11", status="checked_in"
    )

    for response in (same_day, reversed_dates, no_adults, too_many, unknown_field):
        assert response.status_code == 422, response.text
    assert await available(client, tenant, "2027-03-10", "2027-03-11") == [2]


async def test_create_reservation_with_unknown_references_is_404(
    client: AsyncClient, tenant: Tenant, inventory: Inventory
) -> None:
    missing = "00000000-0000-0000-0000-000000000000"
    payload = booking(inventory, "2027-03-10", "2027-03-11")

    for field in ("room_type_id", "guest_id"):
        response = await client.post(
            RESERVATIONS, headers=tenant.headers, json={**payload, field: missing}
        )
        assert response.status_code == 404, response.text


async def test_cannot_book_against_another_hotels_inventory(
    client: AsyncClient, make_tenant: TenantFactory
) -> None:
    hotel_a = await make_tenant()
    hotel_b = await make_tenant()
    inventory_a = await create_inventory(client, hotel_a)
    inventory_b = await create_inventory(client, hotel_b)

    # Hotel B's user, hotel A's room type.
    stolen_type = {
        **booking(inventory_b, "2027-03-10", "2027-03-11"),
        "room_type_id": inventory_a.room_type_id,
    }
    stolen_guest = {
        **booking(inventory_b, "2027-03-10", "2027-03-11"),
        "guest_id": inventory_a.guest_id,
    }
    for payload in (stolen_type, stolen_guest):
        response = await client.post(RESERVATIONS, headers=hotel_b.headers, json=payload)
        assert response.status_code == 404, response.text

    # And hotel A's reservations are invisible to hotel B.
    made = await book(client, hotel_a, inventory_a, "2027-03-10", "2027-03-11")
    assert made.status_code == 201
    seen = await client.get(f"{RESERVATIONS}/{made.json()['id']}", headers=hotel_b.headers)
    assert seen.status_code == 404
    assert (await client.get(RESERVATIONS, headers=hotel_b.headers)).json() == []
    assert await available(client, hotel_b, "2027-03-10", "2027-03-11") == [2]


async def test_room_assignment_and_check_in(
    client: AsyncClient, tenant: Tenant, inventory: Inventory
) -> None:
    first = (await book(client, tenant, inventory, "2027-03-10", "2027-03-12")).json()
    second = (await book(client, tenant, inventory, "2027-03-11", "2027-03-13")).json()
    room = inventory.room_ids[0]

    # A room must be assigned before check-in.
    early = await client.post(f"{RESERVATIONS}/{first['id']}/check-in", headers=tenant.headers)
    assert early.status_code == 409

    assigned = await client.post(
        f"{RESERVATIONS}/{first['id']}/assign-room", headers=tenant.headers, json={"room_id": room}
    )
    assert assigned.status_code == 200
    assert assigned.json()["room_id"] == room

    # The same physical room cannot host an overlapping stay.
    clash = await client.post(
        f"{RESERVATIONS}/{second['id']}/assign-room", headers=tenant.headers, json={"room_id": room}
    )
    assert clash.status_code == 409

    checked_in = await client.post(f"{RESERVATIONS}/{first['id']}/check-in", headers=tenant.headers)
    assert checked_in.status_code == 200
    assert checked_in.json()["status"] == "checked_in"

    checked_out = await client.post(
        f"{RESERVATIONS}/{first['id']}/check-out", headers=tenant.headers
    )
    assert checked_out.json()["status"] == "checked_out"
    # Checked-out stays no longer hold inventory or the room.
    assert await available(client, tenant, "2027-03-10", "2027-03-11") == [2]


async def test_room_of_another_type_cannot_be_assigned(
    client: AsyncClient, tenant: Tenant, inventory: Inventory
) -> None:
    suite = await client.post(
        "/api/v1/room-types",
        headers=tenant.headers,
        json={"name": "Suite", "code": "STE", "base_rate": "9000.00"},
    )
    suite_room = await client.post(
        "/api/v1/rooms",
        headers=tenant.headers,
        json={"room_type_id": suite.json()["id"], "room_number": "501"},
    )
    reservation = (await book(client, tenant, inventory, "2027-03-10", "2027-03-12")).json()

    response = await client.post(
        f"{RESERVATIONS}/{reservation['id']}/assign-room",
        headers=tenant.headers,
        json={"room_id": suite_room.json()["id"]},
    )
    assert response.status_code == 422


async def test_extending_a_stay_rechecks_availability(client: AsyncClient, tenant: Tenant) -> None:
    inventory = await create_inventory(client, tenant, rooms=1)
    first = (await book(client, tenant, inventory, "2027-03-10", "2027-03-12")).json()
    await book(client, tenant, inventory, "2027-03-13", "2027-03-15")

    # Extending by one night is fine: the 12th is free.
    ok = await client.patch(
        f"{RESERVATIONS}/{first['id']}",
        headers=tenant.headers,
        json={"check_out_date": "2027-03-13"},
    )
    assert ok.status_code == 200, ok.text
    assert ok.json()["check_out_date"] == "2027-03-13"

    # Extending into the next booking is not.
    blocked = await client.patch(
        f"{RESERVATIONS}/{first['id']}",
        headers=tenant.headers,
        json={"check_out_date": "2027-03-14"},
    )
    assert blocked.status_code == 409
    current = await client.get(f"{RESERVATIONS}/{first['id']}", headers=tenant.headers)
    assert current.json()["check_out_date"] == "2027-03-13"


async def test_list_reservations_filters_by_date_window(
    client: AsyncClient, tenant: Tenant, inventory: Inventory
) -> None:
    march = (await book(client, tenant, inventory, "2027-03-10", "2027-03-12")).json()
    await book(client, tenant, inventory, "2027-04-01", "2027-04-03")

    response = await client.get(
        RESERVATIONS,
        headers=tenant.headers,
        params={"from_date": "2027-03-01", "to_date": "2027-03-31"},
    )
    assert [r["id"] for r in response.json()] == [march["id"]]
