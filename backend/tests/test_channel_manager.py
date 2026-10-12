import asyncio
import json
import time
from dataclasses import dataclass
from typing import Any

import pytest
from httpx import AsyncClient, Response

from app.core.security import sign_webhook
from app.models import UserRole
from tests.conftest import Inventory, Tenant, TenantFactory, create_inventory

API = "/api/v1"
WEBHOOK = f"{API}/webhooks/channel-manager"


@dataclass(frozen=True)
class Connection:
    id: str
    key_id: str
    secret: str


async def connect(client: AsyncClient, tenant: Tenant) -> Connection:
    response = await client.post(
        f"{API}/channel-connections", headers=tenant.headers, json={"name": "Test channel manager"}
    )
    assert response.status_code == 201, response.text
    body = response.json()
    return Connection(body["id"], body["key_id"], body["signing_secret"])


@pytest.fixture
async def connection(client: AsyncClient, tenant: Tenant) -> Connection:
    return await connect(client, tenant)


def booking_event(booking_id: str = "BDC-1001", **overrides: Any) -> dict[str, Any]:
    return {
        "event": "booking.created",
        "channel": "booking_com",
        "booking_id": booking_id,
        "room_type_code": "DLX",
        "check_in_date": "2027-05-10",
        "check_out_date": "2027-05-12",
        "adults": 2,
        "rate_per_night": "5200.00",
        "guest": {
            "first_name": "Meera",
            "last_name": "Nair",
            "email": f"{booking_id.lower()}@example.com",
            "phone": "+91 98765 43210",
        },
        **overrides,
    }


async def deliver(
    client: AsyncClient,
    connection: Connection,
    payload: dict[str, Any],
    *,
    secret: str | None = None,
    timestamp: int | None = None,
    key_id: str | None = None,
    sent_body: bytes | None = None,
) -> Response:
    """POST a signed webhook. `sent_body` lets a test send bytes other than the signed ones."""
    body = json.dumps(payload).encode()
    stamp = str(timestamp if timestamp is not None else int(time.time()))
    return await client.post(
        WEBHOOK,
        content=sent_body if sent_body is not None else body,
        headers={
            "Content-Type": "application/json",
            "X-Channel-Key": key_id or connection.key_id,
            "X-Channel-Timestamp": stamp,
            "X-Channel-Signature": sign_webhook(secret or connection.secret, stamp, body),
        },
    )


async def available(
    client: AsyncClient, tenant: Tenant, start: str = "2027-05-09", end: str = "2027-05-13"
) -> list[int]:
    response = await client.get(
        f"{API}/availability", headers=tenant.headers, params={"start": start, "end": end}
    )
    assert response.status_code == 200, response.text
    (room_type,) = response.json()
    return [d["available"] for d in room_type["days"]]


async def reservations(client: AsyncClient, tenant: Tenant) -> list[dict[str, Any]]:
    body: list[dict[str, Any]] = (
        await client.get(f"{API}/reservations", headers=tenant.headers)
    ).json()
    return body


async def events(client: AsyncClient, tenant: Tenant) -> list[dict[str, Any]]:
    body: list[dict[str, Any]] = (
        await client.get(f"{API}/channel-connections/events", headers=tenant.headers)
    ).json()
    return body


# --- booking creation and inventory ------------------------------------------


async def test_webhook_creates_reservation_and_decrements_inventory(
    client: AsyncClient, tenant: Tenant, inventory: Inventory, connection: Connection
) -> None:
    assert await available(client, tenant) == [2, 2, 2, 2]

    response = await deliver(client, connection, booking_event())

    assert response.status_code == 201, response.text
    result = response.json()
    assert result["result"] == "created"
    assert result["reservation_status"] == "confirmed"

    # Inventory is down by one for the nights of the stay (10th, 11th) only.
    assert await available(client, tenant) == [2, 1, 1, 2]

    (reservation,) = await reservations(client, tenant)
    assert reservation["id"] == result["reservation_id"]
    assert reservation["confirmation_number"] == result["confirmation_number"]
    assert reservation["source"] == "booking_com"
    assert reservation["external_reference"] == "BDC-1001"
    assert reservation["room_type_id"] == inventory.room_type_id
    assert reservation["room_id"] is None  # assigned later, at or before check-in
    assert reservation["check_in_date"] == "2027-05-10"
    assert reservation["check_out_date"] == "2027-05-12"
    assert reservation["adults"] == 2
    assert reservation["rate_per_night"] == "5200.00"

    guest = (
        await client.get(f"{API}/guests/{reservation['guest_id']}", headers=tenant.headers)
    ).json()
    assert (guest["first_name"], guest["last_name"]) == ("Meera", "Nair")
    assert guest["email"] == "bdc-1001@example.com"


async def test_each_booking_decrements_inventory_until_sold_out(
    client: AsyncClient, tenant: Tenant, inventory: Inventory, connection: Connection
) -> None:
    assert (await deliver(client, connection, booking_event("BDC-1"))).status_code == 201
    assert await available(client, tenant) == [2, 1, 1, 2]

    assert (await deliver(client, connection, booking_event("BDC-2"))).status_code == 201
    assert await available(client, tenant) == [2, 0, 0, 2]

    sold_out = await deliver(client, connection, booking_event("BDC-3"))
    assert sold_out.status_code == 409
    assert "2027-05-10" in sold_out.json()["detail"]

    # The rejected booking left nothing behind: no reservation, no guest, no inventory change.
    assert await available(client, tenant) == [2, 0, 0, 2]
    assert len(await reservations(client, tenant)) == 2
    guests = (
        await client.get(f"{API}/guests", headers=tenant.headers, params={"q": "bdc-3@"})
    ).json()
    assert guests == []


async def test_rate_defaults_to_room_type_base_rate(
    client: AsyncClient, tenant: Tenant, inventory: Inventory, connection: Connection
) -> None:
    payload = booking_event()
    del payload["rate_per_night"]
    assert (await deliver(client, connection, payload)).status_code == 201
    (reservation,) = await reservations(client, tenant)
    assert reservation["rate_per_night"] == "4500.00"


async def test_returning_guest_is_matched_by_email(
    client: AsyncClient, tenant: Tenant, inventory: Inventory, connection: Connection
) -> None:
    guest = {"first_name": "Asha", "last_name": "Rao", "email": "ASHA@example.com"}
    await deliver(client, connection, booking_event("BDC-1", guest=guest))

    (reservation,) = await reservations(client, tenant)
    # `inventory` already created a guest with this email (in lower case).
    assert reservation["guest_id"] == inventory.guest_id


# --- idempotency --------------------------------------------------------------


async def test_redelivered_booking_does_not_decrement_inventory_twice(
    client: AsyncClient, tenant: Tenant, inventory: Inventory, connection: Connection
) -> None:
    first = await deliver(client, connection, booking_event())
    second = await deliver(client, connection, booking_event())

    assert first.status_code == 201
    assert second.status_code == 200
    assert second.json()["result"] == "duplicate"
    assert second.json()["reservation_id"] == first.json()["reservation_id"]
    assert await available(client, tenant) == [2, 1, 1, 2]
    assert len(await reservations(client, tenant)) == 1


async def test_same_booking_id_on_another_channel_is_a_different_booking(
    client: AsyncClient, tenant: Tenant, inventory: Inventory, connection: Connection
) -> None:
    assert (await deliver(client, connection, booking_event("X-1"))).status_code == 201
    other = await deliver(client, connection, booking_event("X-1", channel="agoda"))
    assert other.status_code == 201
    assert await available(client, tenant) == [2, 0, 0, 2]


# --- concurrency --------------------------------------------------------------


async def test_concurrent_bookings_for_the_last_room_cannot_oversell(
    client: AsyncClient, tenant: Tenant, connection: Connection
) -> None:
    await create_inventory(client, tenant, rooms=1)

    responses = await asyncio.gather(
        *(deliver(client, connection, booking_event(f"BDC-{n}")) for n in range(6))
    )

    assert sorted(r.status_code for r in responses) == [201, 409, 409, 409, 409, 409]
    assert await available(client, tenant) == [1, 0, 0, 1]
    assert len(await reservations(client, tenant)) == 1


async def test_concurrent_deliveries_of_one_booking_create_one_reservation(
    client: AsyncClient, tenant: Tenant, connection: Connection
) -> None:
    await create_inventory(client, tenant, rooms=5)

    responses = await asyncio.gather(
        *(deliver(client, connection, booking_event("BDC-SAME")) for _ in range(6))
    )

    assert sorted(r.status_code for r in responses) == [200, 200, 200, 200, 200, 201]
    assert len({r.json()["reservation_id"] for r in responses}) == 1
    assert await available(client, tenant) == [5, 4, 4, 5]
    assert len(await reservations(client, tenant)) == 1
    # The losing deliveries did not leave duplicate guest profiles behind.
    guests = (
        await client.get(f"{API}/guests", headers=tenant.headers, params={"q": "bdc-same@"})
    ).json()
    assert len(guests) == 1


# --- cancellation ---------------------------------------------------------------


async def test_cancellation_releases_inventory(
    client: AsyncClient, tenant: Tenant, inventory: Inventory, connection: Connection
) -> None:
    created = await deliver(client, connection, booking_event())
    cancel = {"event": "booking.cancelled", "channel": "booking_com", "booking_id": "BDC-1001"}

    cancelled = await deliver(client, connection, cancel)

    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["result"] == "cancelled"
    assert cancelled.json()["reservation_id"] == created.json()["reservation_id"]
    assert cancelled.json()["reservation_status"] == "cancelled"
    assert await available(client, tenant) == [2, 2, 2, 2]

    # Redelivery is harmless.
    again = await deliver(client, connection, cancel)
    assert again.status_code == 200
    assert again.json()["result"] == "duplicate"


async def test_cancellation_of_unknown_booking_is_404(
    client: AsyncClient, tenant: Tenant, inventory: Inventory, connection: Connection
) -> None:
    cancel = {"event": "booking.cancelled", "channel": "booking_com", "booking_id": "NOPE"}
    assert (await deliver(client, connection, cancel)).status_code == 404


# --- validation ---------------------------------------------------------------


async def test_invalid_payloads_are_rejected_without_touching_inventory(
    client: AsyncClient, tenant: Tenant, inventory: Inventory, connection: Connection
) -> None:
    unknown_room_type = await deliver(client, connection, booking_event(room_type_code="NOPE"))
    reversed_dates = await deliver(
        client, connection, booking_event(check_in_date="2027-05-12", check_out_date="2027-05-10")
    )
    unknown_event = await deliver(client, connection, booking_event(event="booking.exploded"))
    unknown_channel = await deliver(client, connection, booking_event(channel="myspace"))
    too_many_guests = await deliver(client, connection, booking_event(adults=9))
    no_guest = booking_event()
    del no_guest["guest"]
    missing_guest = await deliver(client, connection, no_guest)

    for response in (
        unknown_room_type,
        reversed_dates,
        unknown_event,
        unknown_channel,
        too_many_guests,
        missing_guest,
    ):
        assert response.status_code == 422, response.text
    assert "NOPE" in unknown_room_type.json()["detail"]
    assert await available(client, tenant) == [2, 2, 2, 2]
    assert await reservations(client, tenant) == []


# --- authentication -----------------------------------------------------------


async def test_webhook_rejects_unauthenticated_deliveries(
    client: AsyncClient, tenant: Tenant, inventory: Inventory, connection: Connection
) -> None:
    payload = booking_event()
    now = int(time.time())
    tampered = json.dumps({**payload, "rate_per_night": "1.00"}).encode()

    attempts = {
        "no headers": await client.post(WEBHOOK, json=payload),
        "wrong secret": await deliver(client, connection, payload, secret="not-the-secret"),
        "unknown key": await deliver(client, connection, payload, key_id="ck_unknown"),
        "tampered body": await deliver(client, connection, payload, sent_body=tampered),
        "stale timestamp": await deliver(client, connection, payload, timestamp=now - 3600),
        "future timestamp": await deliver(client, connection, payload, timestamp=now + 3600),
    }

    for name, response in attempts.items():
        assert response.status_code == 401, name
        assert response.json() == {"detail": "Invalid webhook signature"}, name
    assert await available(client, tenant) == [2, 2, 2, 2]
    assert await reservations(client, tenant) == []


async def test_unauthenticated_caller_learns_nothing_from_an_invalid_body(
    client: AsyncClient,
) -> None:
    response = await client.post(WEBHOOK, json={"nonsense": True})
    assert response.status_code == 401


async def test_deactivated_connection_is_refused(
    client: AsyncClient, tenant: Tenant, inventory: Inventory, connection: Connection
) -> None:
    disabled = await client.patch(
        f"{API}/channel-connections/{connection.id}",
        headers=tenant.headers,
        json={"is_active": False},
    )
    assert disabled.status_code == 200
    assert (await deliver(client, connection, booking_event())).status_code == 401
    assert await available(client, tenant) == [2, 2, 2, 2]


async def test_connection_books_only_into_its_own_hotel(
    client: AsyncClient, make_tenant: TenantFactory
) -> None:
    hotel_a = await make_tenant()
    hotel_b = await make_tenant()
    await create_inventory(client, hotel_a)
    await create_inventory(client, hotel_b)  # same room type code, "DLX"
    connection_a = await connect(client, hotel_a)
    connection_b = await connect(client, hotel_b)

    assert (await deliver(client, connection_a, booking_event())).status_code == 201

    assert await available(client, hotel_a) == [2, 1, 1, 2]
    assert await available(client, hotel_b) == [2, 2, 2, 2]
    assert await reservations(client, hotel_b) == []
    assert await events(client, hotel_b) == []

    # Hotel A's key signed with hotel B's secret gets nowhere.
    mixed = await deliver(client, connection_a, booking_event("BDC-2"), secret=connection_b.secret)
    assert mixed.status_code == 401
    # The same OTA booking id in hotel B is hotel B's own booking, not a duplicate.
    assert (await deliver(client, connection_b, booking_event())).status_code == 201
    assert await available(client, hotel_b) == [2, 1, 1, 2]


# --- event log and connection management ----------------------------------------


async def test_every_authenticated_delivery_is_logged(
    client: AsyncClient, tenant: Tenant, connection: Connection
) -> None:
    await create_inventory(client, tenant, rooms=1)
    created = await deliver(client, connection, booking_event("BDC-1"))
    await deliver(client, connection, booking_event("BDC-1"))
    await deliver(client, connection, booking_event("BDC-2"))  # sold out

    log = {(e["external_booking_id"], e["status"]): e for e in await events(client, tenant)}

    assert set(log) == {("BDC-1", "processed"), ("BDC-1", "duplicate"), ("BDC-2", "rejected")}
    assert log["BDC-1", "processed"]["reservation_id"] == created.json()["reservation_id"]
    rejected = log["BDC-2", "rejected"]
    assert rejected["reservation_id"] is None
    assert "No availability" in rejected["detail"]
    assert rejected["payload"]["guest"]["last_name"] == "Nair"

    only_rejected = await client.get(
        f"{API}/channel-connections/events", headers=tenant.headers, params={"status": "rejected"}
    )
    assert [e["external_booking_id"] for e in only_rejected.json()] == ["BDC-2"]


async def test_signing_secret_is_shown_once_and_only_to_management(
    client: AsyncClient, tenant: Tenant, connection: Connection, make_tenant: TenantFactory
) -> None:
    listed = await client.get(f"{API}/channel-connections", headers=tenant.headers)
    assert listed.status_code == 200
    (entry,) = listed.json()
    assert entry["key_id"] == connection.key_id
    assert "signing_secret" not in entry

    front_desk = await make_tenant(UserRole.FRONT_DESK)
    forbidden = await client.post(
        f"{API}/channel-connections", headers=front_desk.headers, json={"name": "Sneaky"}
    )
    assert forbidden.status_code == 403
    assert (
        await client.get(f"{API}/channel-connections", headers=front_desk.headers)
    ).status_code == 403
