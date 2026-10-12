"""Outbound availability sync: what triggers a push, what is sent, and where it may go."""

import json
from collections.abc import Callable
from datetime import date, timedelta
from ipaddress import ip_address
from typing import Any
from uuid import UUID

import httpx
import pytest
from httpx import AsyncClient
from pydantic import ValidationError

from app.config import Settings, get_settings
from app.core.outbound import OutboundUrlError, is_public_address, resolve_public_address
from app.core.security import sign_webhook
from app.models import UserRole
from app.services import channel_sync
from app.services.channel_sync import DeliveryFailed, deliver_availability
from tests.conftest import Inventory, Tenant, TenantFactory, create_inventory
from tests.test_channel_manager import Connection, booking_event, connect, deliver

API = "/api/v1"
OUTBOUND_URL = "https://ota.example.com/hooks/ari?hotel=42"

Push = tuple[UUID, UUID, UUID, date, date]


@pytest.fixture(autouse=True)
def _public_hosts_only(monkeypatch: pytest.MonkeyPatch) -> None:
    """Run with the production rule, whatever the developer's .env says."""
    monkeypatch.setattr(get_settings(), "channel_outbound_allow_private_hosts", False)


@pytest.fixture
def pushes(monkeypatch: pytest.MonkeyPatch) -> list[Push]:
    """Capture what would be queued on Celery, synchronously."""
    queued: list[Push] = []
    monkeypatch.setattr(channel_sync, "enqueue_delivery", lambda *args: queued.append(args))
    monkeypatch.setattr(channel_sync, "_run_in_background", lambda job: job())
    return queued


async def set_outbound_url(
    client: AsyncClient, tenant: Tenant, connection: Connection, url: str | None = OUTBOUND_URL
) -> httpx.Response:
    return await client.patch(
        f"{API}/channel-connections/{connection.id}",
        headers=tenant.headers,
        json={"outbound_url": url},
    )


@pytest.fixture
async def outbound(client: AsyncClient, tenant: Tenant) -> Connection:
    """A connection that availability is pushed to."""
    connection = await connect(client, tenant)
    assert (await set_outbound_url(client, tenant, connection)).status_code == 200
    return connection


async def book(
    client: AsyncClient,
    tenant: Tenant,
    inventory: Inventory,
    check_in: str = "2027-05-10",
    check_out: str = "2027-05-12",
) -> httpx.Response:
    return await client.post(
        f"{API}/reservations",
        headers=tenant.headers,
        json={
            "guest_id": inventory.guest_id,
            "room_type_id": inventory.room_type_id,
            "check_in_date": check_in,
            "check_out_date": check_out,
        },
    )


def targets(pushes: list[Push]) -> list[tuple[str, str, str, str]]:
    """(connection, room type, start, end) of each queued push."""
    return [(str(c), str(r), s.isoformat(), e.isoformat()) for _, c, r, s, e in pushes]


# --- what triggers a push -----------------------------------------------------------


async def test_creating_a_reservation_queues_a_push_for_its_nights(
    client: AsyncClient,
    tenant: Tenant,
    inventory: Inventory,
    outbound: Connection,
    pushes: list[Push],
) -> None:
    assert (await book(client, tenant, inventory)).status_code == 201

    assert targets(pushes) == [(outbound.id, inventory.room_type_id, "2027-05-10", "2027-05-12")]
    assert pushes[0][0] == tenant.hotel_id


async def test_nothing_is_queued_without_an_active_outbound_connection(
    client: AsyncClient, tenant: Tenant, inventory: Inventory, pushes: list[Push]
) -> None:
    inbound_only = await connect(client, tenant)
    disabled = await connect(client, tenant)
    await set_outbound_url(client, tenant, disabled)
    await client.patch(
        f"{API}/channel-connections/{disabled.id}",
        headers=tenant.headers,
        json={"is_active": False},
    )

    assert (await book(client, tenant, inventory)).status_code == 201

    assert pushes == []
    assert inbound_only.id != disabled.id


async def test_a_rejected_booking_queues_nothing(
    client: AsyncClient, tenant: Tenant, outbound: Connection, pushes: list[Push]
) -> None:
    inventory = await create_inventory(client, tenant, rooms=1)
    assert (await book(client, tenant, inventory)).status_code == 201
    pushes.clear()

    assert (await book(client, tenant, inventory)).status_code == 409  # sold out
    assert pushes == []


async def test_moving_a_stay_pushes_the_nights_freed_and_the_nights_taken(
    client: AsyncClient,
    tenant: Tenant,
    inventory: Inventory,
    outbound: Connection,
    pushes: list[Push],
) -> None:
    reservation = (await book(client, tenant, inventory)).json()
    pushes.clear()

    moved = await client.patch(
        f"{API}/reservations/{reservation['id']}",
        headers=tenant.headers,
        json={"check_in_date": "2027-05-14", "check_out_date": "2027-05-16"},
    )
    assert moved.status_code == 200, moved.text
    # One push per connection and room type, spanning the old and the new nights.
    assert targets(pushes) == [(outbound.id, inventory.room_type_id, "2027-05-10", "2027-05-16")]

    pushes.clear()
    renamed = await client.patch(
        f"{API}/reservations/{reservation['id']}", headers=tenant.headers, json={"notes": "Late"}
    )
    assert renamed.status_code == 200
    assert pushes == []  # availability did not change


async def test_cancel_and_check_out_push_but_check_in_does_not(
    client: AsyncClient,
    tenant: Tenant,
    inventory: Inventory,
    outbound: Connection,
    pushes: list[Push],
) -> None:
    cancelled = (await book(client, tenant, inventory)).json()
    staying = (await book(client, tenant, inventory, "2027-06-01", "2027-06-03")).json()
    await client.post(
        f"{API}/reservations/{staying['id']}/assign-room",
        headers=tenant.headers,
        json={"room_id": inventory.room_ids[0]},
    )
    pushes.clear()

    await client.post(f"{API}/reservations/{cancelled['id']}/cancel", headers=tenant.headers)
    assert targets(pushes) == [(outbound.id, inventory.room_type_id, "2027-05-10", "2027-05-12")]

    pushes.clear()
    checked_in = await client.post(
        f"{API}/reservations/{staying['id']}/check-in", headers=tenant.headers
    )
    assert checked_in.status_code == 200, checked_in.text
    assert pushes == []  # a checked-in stay holds the same nights as a confirmed one

    checked_out = await client.post(
        f"{API}/reservations/{staying['id']}/check-out", headers=tenant.headers
    )
    assert checked_out.status_code == 200, checked_out.text
    assert targets(pushes) == [(outbound.id, inventory.room_type_id, "2027-06-01", "2027-06-03")]


async def test_inbound_booking_is_pushed_to_other_connections_but_not_echoed_to_its_sender(
    client: AsyncClient, tenant: Tenant, inventory: Inventory, pushes: list[Push]
) -> None:
    sender = await connect(client, tenant)
    other = await connect(client, tenant)
    await set_outbound_url(client, tenant, sender)
    await set_outbound_url(client, tenant, other, "https://second.example.com/ari")

    assert (await deliver(client, sender, booking_event())).status_code == 201
    assert targets(pushes) == [(other.id, inventory.room_type_id, "2027-05-10", "2027-05-12")]

    pushes.clear()
    assert (await deliver(client, sender, booking_event())).status_code == 200  # duplicate
    assert pushes == []

    cancel = {"event": "booking.cancelled", "channel": "booking_com", "booking_id": "BDC-1001"}
    assert (await deliver(client, sender, cancel)).status_code == 200
    assert targets(pushes) == [(other.id, inventory.room_type_id, "2027-05-10", "2027-05-12")]


async def test_night_audit_no_shows_push_the_released_nights(
    client: AsyncClient,
    tenant: Tenant,
    inventory: Inventory,
    outbound: Connection,
    pushes: list[Push],
) -> None:
    yesterday = date.today() - timedelta(days=1)
    leaves = yesterday + timedelta(days=3)
    for _ in range(2):  # two no-shows of the same room type: still one push
        booked = await book(client, tenant, inventory, yesterday.isoformat(), leaves.isoformat())
        assert booked.status_code == 201, booked.text
    pushes.clear()

    audit = await client.post(
        f"{API}/night-audit/run",
        headers=tenant.headers,
        json={"business_date": yesterday.isoformat()},
    )
    assert audit.status_code == 200, audit.text
    assert audit.json()["no_shows_marked"] == 2
    assert targets(pushes) == [
        (outbound.id, inventory.room_type_id, yesterday.isoformat(), leaves.isoformat())
    ]


async def test_pushes_stay_inside_the_hotel(
    client: AsyncClient, make_tenant: TenantFactory, pushes: list[Push]
) -> None:
    hotel_a = await make_tenant()
    hotel_b = await make_tenant()
    inventory_a = await create_inventory(client, hotel_a)
    connection_b = await connect(client, hotel_b)
    await set_outbound_url(client, hotel_b, connection_b)

    assert (await book(client, hotel_a, inventory_a)).status_code == 201
    assert pushes == []  # hotel B's connection never hears about hotel A


async def test_sync_now_queues_every_room_type_for_the_coming_weeks(
    client: AsyncClient,
    tenant: Tenant,
    inventory: Inventory,
    outbound: Connection,
    pushes: list[Push],
) -> None:
    response = await client.post(
        f"{API}/channel-connections/{outbound.id}/sync", headers=tenant.headers
    )
    assert response.status_code == 202, response.text
    assert response.json() == {"room_types_queued": 1}

    ((_, connection_id, room_type_id, start, end),) = pushes
    assert (str(connection_id), str(room_type_id)) == (outbound.id, inventory.room_type_id)
    assert (end - start).days == get_settings().channel_outbound_sync_days

    inbound_only = await connect(client, tenant)
    no_url = await client.post(
        f"{API}/channel-connections/{inbound_only.id}/sync", headers=tenant.headers
    )
    assert no_url.status_code == 409


# --- what is sent -------------------------------------------------------------------


@pytest.fixture
def endpoint(monkeypatch: pytest.MonkeyPatch) -> Callable[[int], list[httpx.Request]]:
    """Stand in for the channel's endpoint; returns the requests it received."""

    def install(status_code: int) -> list[httpx.Request]:
        received: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            received.append(request)
            return httpx.Response(status_code)

        async def resolve(host: str, port: int, *, allow_private: bool) -> str:
            return "93.184.216.34"

        monkeypatch.setattr(
            channel_sync,
            "_http_client",
            lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        )
        monkeypatch.setattr(channel_sync, "resolve_public_address", resolve)
        return received

    return install


async def push_now(tenant: Tenant, connection: Connection, inventory: Inventory) -> Any:
    return await deliver_availability(
        tenant.hotel_id,
        UUID(connection.id),
        UUID(inventory.room_type_id),
        date(2027, 5, 9),
        date(2027, 5, 13),
    )


async def listed(client: AsyncClient, tenant: Tenant, connection: Connection) -> dict[str, Any]:
    rows = (await client.get(f"{API}/channel-connections", headers=tenant.headers)).json()
    found: dict[str, Any] = next(row for row in rows if row["id"] == connection.id)
    return found


async def test_delivery_sends_current_availability_signed_with_the_connection_secret(
    client: AsyncClient,
    tenant: Tenant,
    inventory: Inventory,
    outbound: Connection,
    pushes: list[Push],
    endpoint: Callable[[int], list[httpx.Request]],
) -> None:
    received = endpoint(200)
    assert (await book(client, tenant, inventory)).status_code == 201

    result = await push_now(tenant, outbound, inventory)

    assert result.ok and result.status_code == 200
    (request,) = received
    # Connected to the address that passed the check; the name travels in Host.
    assert request.url.host == "93.184.216.34"
    assert request.url.raw_path == b"/hooks/ari?hotel=42"
    assert request.headers["host"] == "ota.example.com"
    assert request.headers["x-channel-key"] == outbound.key_id
    assert request.headers["x-channel-event"] == "availability.updated"
    assert request.headers["x-channel-signature"] == sign_webhook(
        outbound.secret, request.headers["x-channel-timestamp"], request.content
    )

    payload = json.loads(request.content)
    assert payload["event"] == "availability.updated"
    assert payload["room_type"] == {"code": "DLX", "name": "Deluxe"}
    assert (payload["start"], payload["end"]) == ("2027-05-09", "2027-05-13")
    assert [
        (n["date"], n["total_rooms"], n["booked"], n["available"]) for n in payload["nights"]
    ] == [
        ("2027-05-09", 2, 0, 2),
        ("2027-05-10", 2, 1, 1),
        ("2027-05-11", 2, 1, 1),
        ("2027-05-12", 2, 0, 2),
    ]

    status = await listed(client, tenant, outbound)
    assert status["last_push_ok"] is True
    assert status["last_push_at"] is not None
    assert "signing_secret" not in status


async def test_server_errors_are_retried_and_client_errors_are_not(
    client: AsyncClient,
    tenant: Tenant,
    inventory: Inventory,
    outbound: Connection,
    endpoint: Callable[[int], list[httpx.Request]],
) -> None:
    endpoint(503)
    with pytest.raises(DeliveryFailed, match="HTTP 503"):
        await push_now(tenant, outbound, inventory)
    status = await listed(client, tenant, outbound)
    assert status["last_push_ok"] is False
    assert "503" in status["last_push_detail"]

    endpoint(400)
    rejected = await push_now(tenant, outbound, inventory)  # no exception: retrying cannot help
    assert not rejected.ok and not rejected.retryable and rejected.status_code == 400


async def test_delivery_is_skipped_when_the_connection_no_longer_wants_it(
    client: AsyncClient,
    tenant: Tenant,
    inventory: Inventory,
    outbound: Connection,
    endpoint: Callable[[int], list[httpx.Request]],
) -> None:
    received = endpoint(200)
    assert (await set_outbound_url(client, tenant, outbound, None)).status_code == 200

    assert await push_now(tenant, outbound, inventory) is None
    # Nights entirely in the past are not sent either.
    await set_outbound_url(client, tenant, outbound)
    past = await deliver_availability(
        tenant.hotel_id,
        UUID(outbound.id),
        UUID(inventory.room_type_id),
        date(2020, 1, 1),
        date(2020, 1, 3),
    )
    assert past is None
    assert received == []


async def test_test_endpoint_sends_a_signed_ping_and_reports_the_answer(
    client: AsyncClient,
    tenant: Tenant,
    outbound: Connection,
    endpoint: Callable[[int], list[httpx.Request]],
) -> None:
    received = endpoint(204)
    url = f"{API}/channel-connections/{outbound.id}/test-outbound"

    ok = await client.post(url, headers=tenant.headers)
    assert ok.status_code == 200, ok.text
    assert ok.json()["ok"] is True and ok.json()["status_code"] == 204
    (request,) = received
    assert json.loads(request.content)["event"] == "ping"
    assert request.headers["x-channel-signature"] == sign_webhook(
        outbound.secret, request.headers["x-channel-timestamp"], request.content
    )

    endpoint(401)
    refused = await client.post(url, headers=tenant.headers)
    assert refused.status_code == 200
    assert refused.json()["ok"] is False and refused.json()["status_code"] == 401

    inbound_only = await connect(client, tenant)
    no_url = await client.post(
        f"{API}/channel-connections/{inbound_only.id}/test-outbound", headers=tenant.headers
    )
    assert no_url.status_code == 409


# --- where a push may go --------------------------------------------------------------


@pytest.mark.parametrize(
    "url",
    [
        "http://ota.example.com/ari",  # not https
        "https://127.0.0.1/ari",
        "https://10.0.0.8/ari",
        "https://169.254.169.254/latest/meta-data",  # cloud metadata
        "https://[::1]/ari",
        "https://user:secret@ota.example.com/ari",
        "https://ota.example.com/ari#fragment",
        "ftp://ota.example.com/ari",
        "https:///ari",
        "not a url",
    ],
)
async def test_unsafe_outbound_urls_are_refused_when_saved(
    client: AsyncClient, tenant: Tenant, connection_only: Connection, url: str
) -> None:
    response = await set_outbound_url(client, tenant, connection_only, url)
    assert response.status_code == 422, response.text
    assert (await listed(client, tenant, connection_only))["outbound_url"] is None


@pytest.fixture
async def connection_only(client: AsyncClient, tenant: Tenant) -> Connection:
    return await connect(client, tenant)


async def test_outbound_url_can_be_saved_cleared_and_is_management_only(
    client: AsyncClient, tenant: Tenant, connection_only: Connection, make_tenant: TenantFactory
) -> None:
    saved = await set_outbound_url(client, tenant, connection_only, f"  {OUTBOUND_URL} ")
    assert saved.status_code == 200
    assert saved.json()["outbound_url"] == OUTBOUND_URL

    cleared = await set_outbound_url(client, tenant, connection_only, "")
    assert cleared.status_code == 200
    assert cleared.json()["outbound_url"] is None

    front_desk = await make_tenant(UserRole.FRONT_DESK)
    theirs = f"{API}/channel-connections/{connection_only.id}"
    forbidden = await client.patch(
        theirs, headers=front_desk.headers, json={"outbound_url": OUTBOUND_URL}
    )
    assert forbidden.status_code == 403


async def test_local_development_setting_allows_http_and_localhost(
    client: AsyncClient,
    tenant: Tenant,
    connection_only: Connection,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(get_settings(), "channel_outbound_allow_private_hosts", True)
    saved = await set_outbound_url(client, tenant, connection_only, "http://localhost:9000/ari")
    assert saved.status_code == 200, saved.text


@pytest.mark.parametrize(
    ("address", "public"),
    [
        ("8.8.8.8", True),
        ("2606:4700:4700::1111", True),
        ("127.0.0.1", False),
        ("10.1.2.3", False),
        ("172.16.0.1", False),
        ("192.168.1.1", False),
        ("169.254.169.254", False),
        ("100.64.0.1", False),  # carrier-grade NAT
        ("0.0.0.0", False),  # noqa: S104
        ("::1", False),
        ("fe80::1", False),
        ("fd00::1", False),
        ("::ffff:127.0.0.1", False),  # IPv4-mapped loopback
        ("224.0.0.1", False),
    ],
)
def test_only_public_addresses_are_callable(address: str, public: bool) -> None:
    assert is_public_address(ip_address(address)) is public


async def test_a_name_that_resolves_to_a_private_address_is_refused_at_send_time() -> None:
    # "localhost" passes the shape check (it is a name, not an address) and is
    # caught when it is resolved.
    with pytest.raises(OutboundUrlError, match="public address"):
        await resolve_public_address("localhost", 443, allow_private=False)
    assert await resolve_public_address("localhost", 443, allow_private=True) in (
        "127.0.0.1",
        "::1",
    )

    blocked = await channel_sync.send_signed(
        "https://localhost/ari", "ck_test", "secret", {"event": "ping"}
    )
    assert not blocked.ok and not blocked.retryable and blocked.status_code is None


def test_private_hosts_cannot_be_allowed_in_production() -> None:
    base = get_settings().model_dump()
    with pytest.raises(ValidationError, match="production"):
        Settings(
            **{**base, "environment": "production", "channel_outbound_allow_private_hosts": True}
        )
