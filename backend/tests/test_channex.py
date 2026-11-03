"""Channex.io integration: inbound booking revisions, outbound ARI, and the clients."""

import json
from collections.abc import Iterator
from datetime import date, timedelta
from typing import Any
from uuid import UUID

import httpx
import pytest
from httpx import AsyncClient, Response
from pydantic import ValidationError

from app.config import Settings, get_settings
from app.models import UserRole
from app.services import channel_sync
from app.services.channel_sync import DeliveryFailed
from app.services.channex import bookings
from app.services.channex.ari import availability_values, push_ari
from app.services.channex.client import HttpChannexClient, MockChannexClient, interpret
from tests.conftest import Inventory, Tenant, TenantFactory, create_inventory
from tests.test_channel_manager import (
    Connection,
    available,
    booking_event,
    connect,
    deliver,
    events,
    reservations,
)

API = "/api/v1"
WEBHOOK = f"{API}/webhooks/channex"
PROPERTY = "716e7e6b-6ab2-4c2c-9a4e-8f5d3c5b1a01"
CX_ROOM_TYPE = "b1c6a7d2-0f4e-4a51-9c0e-2d3f4a5b6c7d"
CX_RATE_PLAN = "c2d7b8e3-1a5f-4b62-8d1f-3e4a5b6c7d8e"
BOOKING = "0a1b2c3d-4e5f-4a6b-8c7d-9e0f1a2b3c4d"

ChannexPush = tuple[UUID, UUID, list[tuple[UUID, date, date]], bool]


@pytest.fixture(autouse=True)
def _mock_channex(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Mock mode with a clean record of requests, whatever the developer's .env says."""
    monkeypatch.setattr(get_settings(), "channex_mode", "mock")
    MockChannexClient.requests.clear()
    MockChannexClient.revisions.clear()
    yield
    MockChannexClient.requests.clear()
    MockChannexClient.revisions.clear()


@pytest.fixture
def acks(monkeypatch: pytest.MonkeyPatch) -> list[tuple[UUID, UUID, str]]:
    """Acknowledgements that would be queued on Celery."""
    queued: list[tuple[UUID, UUID, str]] = []
    monkeypatch.setattr(bookings, "enqueue_ack", lambda *args: queued.append(args))
    return queued


@pytest.fixture
def channex_pushes(monkeypatch: pytest.MonkeyPatch) -> list[ChannexPush]:
    """Channex ARI pushes that would be queued on Celery, captured synchronously."""
    queued: list[ChannexPush] = []
    monkeypatch.setattr(channel_sync, "enqueue_channex_push", lambda *args: queued.append(args))
    monkeypatch.setattr(channel_sync, "_run_in_background", lambda job: job())
    return queued


class Channex:
    def __init__(self, body: dict[str, Any]) -> None:
        self.id: str = body["id"]
        self.key_id: str = body["key_id"]
        self.secret: str = body["signing_secret"]


async def connect_channex(
    client: AsyncClient, tenant: Tenant, property_id: str = PROPERTY
) -> Response:
    return await client.post(
        f"{API}/channel-connections",
        headers=tenant.headers,
        json={"name": "Channex", "provider": "channex", "external_property_id": property_id},
    )


async def second_room_type(client: AsyncClient, tenant: Tenant) -> str:
    response = await client.post(
        f"{API}/room-types",
        headers=tenant.headers,
        json={"name": "Standard", "code": "STD", "max_occupancy": 2, "base_rate": "3000.00"},
    )
    assert response.status_code == 201, response.text
    room_type_id: str = response.json()["id"]
    return room_type_id


async def map_rooms(
    client: AsyncClient, tenant: Tenant, connection: Channex, mappings: list[dict[str, Any]]
) -> Response:
    return await client.put(
        f"{API}/channel-connections/{connection.id}/channex-mappings",
        headers=tenant.headers,
        json=mappings,
    )


@pytest.fixture
async def channex(client: AsyncClient, tenant: Tenant, inventory: Inventory) -> Channex:
    """A Channex connection with the inventory's room type mapped."""
    response = await connect_channex(client, tenant)
    assert response.status_code == 201, response.text
    connection = Channex(response.json())
    response = await map_rooms(
        client,
        tenant,
        connection,
        [
            {
                "room_type_id": inventory.room_type_id,
                "channex_room_type_id": CX_ROOM_TYPE,
                "channex_rate_plan_id": CX_RATE_PLAN,
            }
        ],
    )
    assert response.status_code == 200, response.text
    return connection


def room(**overrides: Any) -> dict[str, Any]:
    return {
        "room_type_id": CX_ROOM_TYPE,
        "rate_plan_id": CX_RATE_PLAN,
        "amount": "10400.00",
        "occupancy": {"adults": 2, "children": 1, "infants": 0},
        **overrides,
    }


def revision(
    status: str = "new", revision_id: str = "11111111-0000-4000-8000-000000000001", **overrides: Any
) -> dict[str, Any]:
    """A Channex booking revision, flat, as a webhook with "send data" carries it."""
    return {
        "id": revision_id,
        "booking_id": BOOKING,
        "property_id": PROPERTY,
        "status": status,
        "ota_name": "Booking.com",
        "ota_reservation_code": "4012345678",
        "arrival_date": "2027-05-10",
        "departure_date": "2027-05-12",
        "currency": "INR",
        "amount": "10400.00",
        "customer": {
            "name": "Meera",
            "surname": "Nair",
            "mail": "meera@example.com",
            "phone": "+91 98765 43210",
        },
        "rooms": [room()],
        "notes": "Late arrival",
        **overrides,
    }


def webhook(data: dict[str, Any] | None = None, event: str = "booking_new") -> dict[str, Any]:
    data = data if data is not None else revision()
    return {
        "event": event,
        "property_id": PROPERTY,
        "timestamp": "2026-11-02T10:00:00Z",
        "payload": {"booking_id": data["booking_id"], "revision_id": data["id"], **data},
    }


async def send(
    client: AsyncClient,
    connection: Channex,
    payload: dict[str, Any],
    *,
    key_id: str | None = None,
    token: str | None = None,
) -> Response:
    return await client.post(
        WEBHOOK,
        json=payload,
        headers={
            "X-Channex-Key": key_id or connection.key_id,
            "X-Channex-Token": token if token is not None else connection.secret,
        },
    )


# --- connections and mappings ------------------------------------------------------


async def test_channex_connection_needs_a_property_and_is_one_per_hotel(
    client: AsyncClient, tenant: Tenant
) -> None:
    missing = await client.post(
        f"{API}/channel-connections",
        headers=tenant.headers,
        json={"name": "Channex", "provider": "channex"},
    )
    assert missing.status_code == 422

    created = await connect_channex(client, tenant)
    assert created.status_code == 201, created.text
    body = created.json()
    assert (body["provider"], body["external_property_id"]) == ("channex", PROPERTY)
    assert body["signing_secret"]

    assert (await connect_channex(client, tenant)).status_code == 409


async def test_channex_connection_has_no_outbound_url_but_can_change_property(
    client: AsyncClient, tenant: Tenant, channex: Channex
) -> None:
    url = f"{API}/channel-connections/{channex.id}"
    refused = await client.patch(
        url, headers=tenant.headers, json={"outbound_url": "https://example.com/hook"}
    )
    assert refused.status_code == 422

    new_property = "99999999-6ab2-4c2c-9a4e-8f5d3c5b1a01"
    changed = await client.patch(
        url, headers=tenant.headers, json={"external_property_id": new_property}
    )
    assert changed.status_code == 200, changed.text
    assert changed.json()["external_property_id"] == new_property


async def test_mappings_are_replaced_whole_and_validated(
    client: AsyncClient, tenant: Tenant, inventory: Inventory, channex: Channex
) -> None:
    url = f"{API}/channel-connections/{channex.id}/channex-mappings"
    (mapping,) = (await client.get(url, headers=tenant.headers)).json()
    assert mapping["channex_room_type_id"] == CX_ROOM_TYPE

    other = await second_room_type(client, tenant)
    clash = [
        {"room_type_id": inventory.room_type_id, "channex_room_type_id": CX_ROOM_TYPE},
        {"room_type_id": other, "channex_room_type_id": CX_ROOM_TYPE},
    ]
    assert (await map_rooms(client, tenant, channex, clash)).status_code == 409
    # The failed replacement changed nothing.
    assert len((await client.get(url, headers=tenant.headers)).json()) == 1

    unknown = [
        {
            "room_type_id": "00000000-0000-4000-8000-000000000000",
            "channex_room_type_id": CX_ROOM_TYPE,
        }
    ]
    assert (await map_rooms(client, tenant, channex, unknown)).status_code == 404

    assert (await map_rooms(client, tenant, channex, [])).status_code == 200
    assert (await client.get(url, headers=tenant.headers)).json() == []


async def test_mappings_are_for_channex_connections_and_management_only(
    client: AsyncClient, tenant: Tenant, make_tenant: TenantFactory
) -> None:
    generic = await connect(client, tenant)
    response = await client.get(
        f"{API}/channel-connections/{generic.id}/channex-mappings", headers=tenant.headers
    )
    assert response.status_code == 409

    clerk = await make_tenant(UserRole.FRONT_DESK)
    response = await client.get(
        f"{API}/channel-connections/{generic.id}/channex-mappings", headers=clerk.headers
    )
    assert response.status_code == 403


async def test_test_endpoint_checks_the_property_through_the_api(
    client: AsyncClient, tenant: Tenant, channex: Channex
) -> None:
    response = await client.post(
        f"{API}/channel-connections/{channex.id}/test-outbound", headers=tenant.headers
    )
    assert response.status_code == 200, response.text
    assert response.json()["ok"] is True
    assert response.json()["detail"].startswith("Mock, not sent")
    assert MockChannexClient.requests[-1] == ("GET", f"/properties/{PROPERTY}", None)


# --- inbound bookings -----------------------------------------------------------------


async def test_new_booking_creates_a_reservation_and_is_acknowledged(
    client: AsyncClient,
    tenant: Tenant,
    inventory: Inventory,
    channex: Channex,
    acks: list[tuple[UUID, UUID, str]],
) -> None:
    response = await send(client, channex, webhook())

    assert response.status_code == 200, response.text
    result = response.json()
    assert result["result"] == "created"
    assert (result["booking_id"], result["revision_id"]) == (BOOKING, revision()["id"])
    assert await available(client, tenant) == [2, 1, 1, 2]

    (reservation,) = await reservations(client, tenant)
    assert reservation["id"] == result["reservations"][0]["reservation_id"]
    assert reservation["source"] == "booking_com"
    assert reservation["external_reference"] == f"{BOOKING}/1"
    assert reservation["room_type_id"] == inventory.room_type_id
    assert (reservation["adults"], reservation["children"]) == (2, 1)
    # 10,400 for two nights.
    assert reservation["rate_per_night"] == "5200.00"
    assert "4012345678" in reservation["notes"]
    assert "Late arrival" in reservation["notes"]

    guest = (
        await client.get(f"{API}/guests/{reservation['guest_id']}", headers=tenant.headers)
    ).json()
    assert (guest["first_name"], guest["last_name"], guest["email"]) == (
        "Meera",
        "Nair",
        "meera@example.com",
    )

    assert acks == [(tenant.hotel_id, UUID(channex.id), revision()["id"])]
    (event,) = await events(client, tenant)
    assert (event["status"], event["event_type"], event["channel"]) == (
        "processed",
        "booking_new",
        "booking_com",
    )


async def test_redelivered_revision_changes_nothing(
    client: AsyncClient, tenant: Tenant, channex: Channex, acks: list[Any]
) -> None:
    assert (await send(client, channex, webhook())).json()["result"] == "created"
    again = await send(client, channex, webhook())

    assert again.status_code == 200
    assert again.json()["result"] == "unchanged"
    assert len(await reservations(client, tenant)) == 1
    assert await available(client, tenant) == [2, 1, 1, 2]
    # Still acknowledged: Channex must stop redelivering it.
    assert len(acks) == 2
    assert [e["status"] for e in await events(client, tenant)] == ["duplicate", "processed"]


async def test_modification_moves_the_stay(
    client: AsyncClient, tenant: Tenant, channex: Channex, acks: list[Any]
) -> None:
    created = (await send(client, channex, webhook())).json()

    modified = revision(
        "modified",
        revision_id="11111111-0000-4000-8000-000000000002",
        arrival_date="2027-05-11",
        departure_date="2027-05-13",
        rooms=[room(amount="12000.00")],
    )
    response = await send(client, channex, webhook(modified, event="booking_modification"))

    assert response.status_code == 200, response.text
    assert response.json()["result"] == "modified"
    (reservation,) = await reservations(client, tenant)
    assert reservation["id"] == created["reservations"][0]["reservation_id"]
    assert (reservation["check_in_date"], reservation["check_out_date"]) == (
        "2027-05-11",
        "2027-05-13",
    )
    assert reservation["rate_per_night"] == "6000.00"
    assert await available(client, tenant) == [2, 2, 1, 1]


async def test_modification_for_an_unseen_booking_creates_it(
    client: AsyncClient, tenant: Tenant, channex: Channex, acks: list[Any]
) -> None:
    response = await send(
        client, channex, webhook(revision("modified"), event="booking_modification")
    )
    assert response.json()["result"] == "created"
    assert len(await reservations(client, tenant)) == 1


async def test_cancellation_releases_inventory_and_is_idempotent(
    client: AsyncClient, tenant: Tenant, channex: Channex, acks: list[Any]
) -> None:
    await send(client, channex, webhook())
    cancelled = revision("cancelled", revision_id="11111111-0000-4000-8000-000000000003")

    first = await send(client, channex, webhook(cancelled, event="booking_cancellation"))
    second = await send(client, channex, webhook(cancelled, event="booking_cancellation"))

    assert first.json()["result"] == "cancelled"
    assert second.json()["result"] == "unchanged"
    (reservation,) = await reservations(client, tenant)
    assert reservation["status"] == "cancelled"
    assert await available(client, tenant) == [2, 2, 2, 2]


async def test_cancellation_of_an_unknown_booking_is_acknowledged(
    client: AsyncClient, tenant: Tenant, channex: Channex, acks: list[Any]
) -> None:
    response = await send(
        client, channex, webhook(revision("cancelled"), event="booking_cancellation")
    )
    assert response.status_code == 200
    assert response.json()["result"] == "unchanged"
    assert len(acks) == 1


async def test_multi_room_booking_and_a_room_removed_later(
    client: AsyncClient, tenant: Tenant, channex: Channex, acks: list[Any]
) -> None:
    two_rooms = revision(rooms=[room(), room(occupancy={"adults": 1})])
    created = await send(client, channex, webhook(two_rooms))
    assert created.json()["result"] == "created"
    assert len(created.json()["reservations"]) == 2
    assert await available(client, tenant) == [2, 0, 0, 2]

    one_room = revision("modified", revision_id="11111111-0000-4000-8000-000000000004")
    response = await send(client, channex, webhook(one_room, event="booking_modification"))

    assert response.json()["result"] == "modified"
    statuses = {r["external_reference"]: r["status"] for r in await reservations(client, tenant)}
    assert statuses == {f"{BOOKING}/1": "confirmed", f"{BOOKING}/2": "cancelled"}
    assert await available(client, tenant) == [2, 1, 1, 2]


async def test_other_currency_keeps_the_base_rate(
    client: AsyncClient, tenant: Tenant, channex: Channex, acks: list[Any]
) -> None:
    await send(client, channex, webhook(revision(currency="USD", amount="125.00")))
    (reservation,) = await reservations(client, tenant)
    assert reservation["rate_per_night"] == "4500.00"  # the room type's base rate
    assert "125.00 USD" in reservation["notes"]


async def test_unmapped_room_type_is_rejected_logged_and_not_acknowledged(
    client: AsyncClient, tenant: Tenant, channex: Channex, acks: list[Any]
) -> None:
    unmapped = revision(rooms=[room(room_type_id="ffffffff-0000-4000-8000-000000000000")])
    response = await send(client, channex, webhook(unmapped))

    assert response.status_code == 422
    assert "not mapped" in response.json()["detail"]
    assert await reservations(client, tenant) == []
    assert acks == []
    (event,) = await events(client, tenant)
    assert event["status"] == "rejected"


async def test_no_availability_is_a_conflict(
    client: AsyncClient, tenant: Tenant, inventory: Inventory, channex: Channex, acks: list[Any]
) -> None:
    three_rooms = revision(rooms=[room(), room(), room()])  # the hotel has two
    response = await send(client, channex, webhook(three_rooms))

    assert response.status_code == 409
    # All or nothing: the first two rooms were rolled back with the third.
    assert await reservations(client, tenant) == []
    assert acks == []


async def test_booking_for_another_property_is_refused(
    client: AsyncClient, tenant: Tenant, channex: Channex, acks: list[Any]
) -> None:
    foreign = revision(property_id="22222222-0000-4000-8000-000000000000")
    response = await send(client, channex, webhook(foreign))
    assert response.status_code == 422
    assert await reservations(client, tenant) == []


async def test_revision_is_fetched_when_the_webhook_carries_only_ids(
    client: AsyncClient, tenant: Tenant, channex: Channex, acks: list[Any]
) -> None:
    data = revision()
    MockChannexClient.revisions[data["id"]] = {k: v for k, v in data.items() if k != "id"}
    ids_only = {
        "event": "booking",
        "property_id": PROPERTY,
        "payload": {"booking_id": BOOKING, "revision_id": data["id"], "property_id": PROPERTY},
    }

    response = await send(client, channex, ids_only)

    assert response.status_code == 200, response.text
    assert response.json()["result"] == "created"
    assert ("GET", f"/booking_revisions/{data['id']}", None) in MockChannexClient.requests


async def test_unknown_revision_id_is_rejected(
    client: AsyncClient, tenant: Tenant, channex: Channex, acks: list[Any]
) -> None:
    ids_only = {"event": "booking_new", "payload": {"revision_id": "deadbeef"}}
    response = await send(client, channex, ids_only)
    assert response.status_code == 422
    assert acks == []


async def test_non_booking_events_are_ignored(
    client: AsyncClient, tenant: Tenant, channex: Channex, acks: list[Any]
) -> None:
    response = await send(client, channex, {"event": "message", "payload": {"text": "hi"}})
    assert response.status_code == 200
    assert response.json() == {
        "result": "ignored",
        "booking_id": None,
        "revision_id": None,
        "reservations": [],
    }
    (event,) = await events(client, tenant)
    assert (event["status"], event["event_type"]) == ("ignored", "message")
    assert event["payload"] == {"event": "message", "payload": {"text": "hi"}}
    assert acks == []


@pytest.mark.parametrize(
    "body",
    [
        {"event": "test", "timestamp": 1793700000, "payload": None},
        {"event": "test", "property_id": 12345, "payload": ["not", "an", "object"]},
        {"message": "Test webhook"},
    ],
    ids=["numeric-timestamp-null-payload", "odd-types", "no-event"],
)
async def test_test_messages_in_any_shape_are_answered_and_logged(
    client: AsyncClient, tenant: Tenant, channex: Channex, acks: list[Any], body: dict[str, Any]
) -> None:
    """Channex's "Send test message" must show up as a delivery, not vanish as a 422."""
    response = await send(client, channex, body)

    assert response.status_code == 200, response.text
    assert response.json()["result"] == "ignored"
    (event,) = await events(client, tenant)
    assert event["status"] == "ignored"
    assert event["payload"] == body  # kept exactly as received
    assert await reservations(client, tenant) == []


async def test_a_body_that_is_not_a_webhook_is_rejected_and_logged(
    client: AsyncClient, tenant: Tenant, channex: Channex
) -> None:
    as_list = await send(client, channex, [{"event": "booking_new"}])  # type: ignore[arg-type]
    not_json = await client.post(
        WEBHOOK,
        content=b"<xml>nope</xml>",
        headers={
            "Content-Type": "application/xml",
            "X-Channex-Key": channex.key_id,
            "X-Channex-Token": channex.secret,
        },
    )

    assert (as_list.status_code, not_json.status_code) == (422, 422)
    assert "Unexpected webhook body" in as_list.json()["detail"]
    logged = await events(client, tenant)
    assert [(e["status"], e["event_type"]) for e in logged] == [
        ("rejected", "invalid"),
        ("rejected", "invalid"),
    ]
    assert {"body": "<xml>nope</xml>"} in [e["payload"] for e in logged]


# --- inbound security ----------------------------------------------------------------


async def test_webhook_refuses_wrong_missing_or_disabled_credentials(
    client: AsyncClient, tenant: Tenant, channex: Channex
) -> None:
    assert (await send(client, channex, webhook(), token="wrong")).status_code == 401
    assert (await send(client, channex, webhook(), key_id="ck_unknown")).status_code == 401
    assert (await client.post(WEBHOOK, json=webhook())).status_code == 401
    # An invalid body tells an unauthenticated caller nothing.
    assert (await send(client, channex, {"nonsense": 1}, token="wrong")).status_code == 401

    await client.patch(
        f"{API}/channel-connections/{channex.id}", headers=tenant.headers, json={"is_active": False}
    )
    assert (await send(client, channex, webhook())).status_code == 401
    assert await reservations(client, tenant) == []


async def test_keys_only_work_on_their_own_endpoint(
    client: AsyncClient, tenant: Tenant, inventory: Inventory, channex: Channex
) -> None:
    generic = await connect(client, tenant)
    as_channex = await client.post(
        WEBHOOK,
        json=webhook(),
        headers={"X-Channex-Key": generic.key_id, "X-Channex-Token": generic.secret},
    )
    assert as_channex.status_code == 401

    impostor = Connection(channex.id, channex.key_id, channex.secret)
    assert (await deliver(client, impostor, booking_event())).status_code == 401


async def test_connection_books_only_into_its_own_hotel(
    client: AsyncClient,
    make_tenant: TenantFactory,
    tenant: Tenant,
    channex: Channex,
    acks: list[Any],
) -> None:
    other = await make_tenant()
    await create_inventory(client, other)

    assert (await send(client, channex, webhook())).status_code == 200

    assert len(await reservations(client, tenant)) == 1
    assert await reservations(client, other) == []


# --- outbound ARI ------------------------------------------------------------------------


async def test_local_reservation_queues_one_channex_push(
    client: AsyncClient,
    tenant: Tenant,
    inventory: Inventory,
    channex: Channex,
    channex_pushes: list[ChannexPush],
) -> None:
    response = await client.post(
        f"{API}/reservations",
        headers=tenant.headers,
        json={
            "guest_id": inventory.guest_id,
            "room_type_id": inventory.room_type_id,
            "check_in_date": "2027-05-10",
            "check_out_date": "2027-05-12",
        },
    )
    assert response.status_code == 201, response.text

    assert channex_pushes == [
        (
            tenant.hotel_id,
            UUID(channex.id),
            [(UUID(inventory.room_type_id), date(2027, 5, 10), date(2027, 5, 12))],
            False,
        )
    ]


async def test_channex_booking_is_pushed_back_to_channex(
    client: AsyncClient,
    tenant: Tenant,
    channex: Channex,
    channex_pushes: list[ChannexPush],
    acks: list[Any],
) -> None:
    """Channex relays the new count to its other OTAs, so its own bookings are pushed too."""
    await send(client, channex, webhook())
    assert len(channex_pushes) == 1


async def test_sync_now_includes_rates(
    client: AsyncClient,
    tenant: Tenant,
    inventory: Inventory,
    channex: Channex,
    channex_pushes: list[ChannexPush],
) -> None:
    response = await client.post(
        f"{API}/channel-connections/{channex.id}/sync", headers=tenant.headers
    )
    assert response.status_code == 202, response.text
    ((_, _, ranges, include_rates),) = channex_pushes
    assert include_rates is True
    assert [r for r, _, _ in ranges] == [UUID(inventory.room_type_id)]


def test_availability_values_compress_runs_with_inclusive_end() -> None:
    nights = [(date(2027, 5, 10) + timedelta(days=i), n) for i, n in enumerate([2, 2, 1, 1, 2])]
    values = availability_values("P", "R", nights)
    assert [(v["date_from"], v["date_to"], v["availability"]) for v in values] == [
        ("2027-05-10", "2027-05-11", 2),
        ("2027-05-12", "2027-05-13", 1),
        ("2027-05-14", "2027-05-14", 2),
    ]


async def test_push_sends_current_availability_and_records_the_result(
    client: AsyncClient, tenant: Tenant, inventory: Inventory, channex: Channex, acks: list[Any]
) -> None:
    await send(client, channex, webhook())  # takes one room on the 10th and 11th
    MockChannexClient.requests.clear()

    result = await push_ari(
        tenant.hotel_id,
        UUID(channex.id),
        [(UUID(inventory.room_type_id), date(2027, 5, 9), date(2027, 5, 13))],
        include_rates=True,
    )

    assert result is not None and result.ok
    (availability, restrictions) = MockChannexClient.requests
    assert availability[:2] == ("POST", "/availability")
    assert availability[2] == {
        "values": [
            {
                "property_id": PROPERTY,
                "room_type_id": CX_ROOM_TYPE,
                "date_from": "2027-05-09",
                "date_to": "2027-05-09",
                "availability": 2,
            },
            {
                "property_id": PROPERTY,
                "room_type_id": CX_ROOM_TYPE,
                "date_from": "2027-05-10",
                "date_to": "2027-05-11",
                "availability": 1,
            },
            {
                "property_id": PROPERTY,
                "room_type_id": CX_ROOM_TYPE,
                "date_from": "2027-05-12",
                "date_to": "2027-05-12",
                "availability": 2,
            },
        ]
    }
    assert restrictions == (
        "POST",
        "/restrictions",
        {
            "values": [
                {
                    "property_id": PROPERTY,
                    "rate_plan_id": CX_RATE_PLAN,
                    "date_from": "2027-05-09",
                    "date_to": "2027-05-12",
                    "rate": "4500.00",
                }
            ]
        },
    )

    (connection,) = [
        c
        for c in (await client.get(f"{API}/channel-connections", headers=tenant.headers)).json()
        if c["id"] == channex.id
    ]
    assert connection["last_push_ok"] is True
    assert connection["last_push_detail"].startswith("Mock, not sent")


async def test_push_skips_unmapped_room_types_and_disabled_connections(
    client: AsyncClient, tenant: Tenant, inventory: Inventory, channex: Channex
) -> None:
    unmapped = [(UUID(await second_room_type(client, tenant)), date(2027, 5, 9), date(2027, 5, 13))]
    assert await push_ari(tenant.hotel_id, UUID(channex.id), unmapped, False) is None

    await client.patch(
        f"{API}/channel-connections/{channex.id}", headers=tenant.headers, json={"is_active": False}
    )
    mapped = [(UUID(inventory.room_type_id), date(2027, 5, 9), date(2027, 5, 13))]
    assert await push_ari(tenant.hotel_id, UUID(channex.id), mapped, False) is None
    assert list(MockChannexClient.requests) == []


async def test_rate_limited_push_is_retried(
    monkeypatch: pytest.MonkeyPatch,
    tenant: Tenant,
    inventory: Inventory,
    channex: Channex,
) -> None:
    async def too_many(self: MockChannexClient, method: str, path: str, json: Any = None) -> Any:
        return interpret(429, {"errors": {"title": "Too Many Requests"}}, 0)

    monkeypatch.setattr(MockChannexClient, "_send", too_many)
    mapped = [(UUID(inventory.room_type_id), date(2027, 5, 9), date(2027, 5, 13))]
    with pytest.raises(DeliveryFailed, match="429"):
        await push_ari(tenant.hotel_id, UUID(channex.id), mapped, False)


# --- the live client ---------------------------------------------------------------------


async def test_http_client_sends_the_api_key_and_classifies_answers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[httpx.Request] = []
    answers = iter(
        [
            httpx.Response(200, json={"data": [{"id": "t", "type": "task"}], "meta": {}}),
            httpx.Response(
                200, json={"meta": {"message": "Success", "warnings": ["unknown room type"]}}
            ),
            httpx.Response(422, json={"errors": {"code": "validation_error", "title": "Bad"}}),
            httpx.Response(503, text="down"),
        ]
    )

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return next(answers)

    real_client = httpx.AsyncClient

    def fake_client(**kwargs: Any) -> httpx.AsyncClient:
        return real_client(transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", fake_client)
    client = HttpChannexClient("https://staging.channex.io/api/v1/", "secret-key", 5)

    ok = await client.update_availability([{"availability": 1}])
    warned = await client.update_availability([])
    invalid = await client.update_restrictions([])
    down = await client.ack_booking_revision("rev-1")

    assert (ok.ok, warned.ok, invalid.ok, down.ok) == (True, False, False, False)
    assert (warned.retryable, invalid.retryable, down.retryable) == (False, False, True)
    assert "Bad" in invalid.detail
    assert str(seen[0].url) == "https://staging.channex.io/api/v1/availability"
    assert seen[0].headers["user-api-key"] == "secret-key"
    assert json.loads(seen[0].content) == {"values": [{"availability": 1}]}
    assert str(seen[3].url) == "https://staging.channex.io/api/v1/booking_revisions/rev-1/ack"


def test_live_mode_requires_a_key_and_https() -> None:
    base = {**get_settings().model_dump(), "channex_mode": "live"}
    with pytest.raises(ValidationError, match="CHANNEX_API_KEY"):
        Settings(**{**base, "channex_api_key": None})
    with pytest.raises(ValidationError, match="https"):
        Settings(**{**base, "channex_api_key": "k", "channex_base_url": "http://channex.example"})
