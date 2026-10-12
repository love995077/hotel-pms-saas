"""Outbound channel manager sync: push availability to connected channels.

When a reservation is created, changed, cancelled, checked out or marked a
no-show, the availability of its room type changes. Services call
`request_availability_push` inside their transaction; once that transaction
commits, one Celery task per outbound connection is queued. Each task reads the
availability afresh when it runs, so a retried delivery never sends numbers
that have since gone stale.

Nothing is queued for a transaction that rolls back.
"""

import asyncio
import json
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from functools import partial
from typing import Any
from uuid import UUID

import httpx
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.celery_app import celery_app
from app.config import get_settings
from app.core.outbound import OutboundUrlError, resolve_public_address, validate_outbound_url
from app.core.security import sign_webhook
from app.database import TenantSession, tenant_session
from app.models import ChannelConnection, RoomType
from app.services.availability import MAX_RANGE_NIGHTS, get_availability
from app.services.folios import hotel_today

logger = logging.getLogger(__name__)

DELIVER_TASK = "channel_sync.deliver"
EVENT_AVAILABILITY = "availability.updated"
EVENT_PING = "ping"
USER_AGENT = "HotelPMS-ChannelSync/1.0"

_PENDING_KEY = "channel_sync_pending"
_ORIGIN_KEY = "channel_sync_origin_connection_id"
_DETAIL_LIMIT = 300


class DeliveryFailed(Exception):
    """A push did not get through and is worth trying again."""


@dataclass(frozen=True, slots=True)
class DeliveryResult:
    ok: bool
    # None when no HTTP response was received at all.
    status_code: int | None
    detail: str
    # False for outcomes that trying again cannot change (a 4xx, a blocked URL).
    retryable: bool
    duration_ms: int


@dataclass(frozen=True, slots=True)
class _PendingPush:
    connection_id: UUID
    room_type_id: UUID
    start: date
    end: date


# --- queueing -------------------------------------------------------------------


def set_push_origin(session: AsyncSession, connection_id: UUID) -> None:
    """Mark the connection whose own booking this transaction is applying.

    It is left out of the pushes the transaction causes, so a channel is not
    told about a change it has just told us about.
    """
    session.info[_ORIGIN_KEY] = connection_id


async def request_availability_push(
    session: AsyncSession, room_type_id: UUID, start: date, end: date
) -> None:
    """Ask for `room_type_id`'s availability on nights [start, end) to be pushed.

    Call this from the transaction that changes the inventory. Nothing leaves
    the process until that transaction has committed.
    """
    if end <= start:
        return
    origin = session.info.get(_ORIGIN_KEY)
    connection_ids = await session.scalars(
        select(ChannelConnection.id).where(
            ChannelConnection.is_active, ChannelConnection.outbound_url.is_not(None)
        )
    )
    pending: list[_PendingPush] = session.info.setdefault(_PENDING_KEY, [])
    pending.extend(
        _PendingPush(connection_id, room_type_id, start, end)
        for connection_id in connection_ids
        if connection_id != origin
    )


def _merge(pending: list[_PendingPush]) -> list[_PendingPush]:
    """One push per connection and room type, spanning every requested night.

    A night audit can release dozens of no-shows of one room type at once;
    the channel needs one update for that, not dozens.
    """
    merged: dict[tuple[UUID, UUID], _PendingPush] = {}
    for push in pending:
        key = (push.connection_id, push.room_type_id)
        current = merged.get(key)
        merged[key] = (
            push
            if current is None
            else _PendingPush(
                push.connection_id,
                push.room_type_id,
                min(current.start, push.start),
                max(current.end, push.end),
            )
        )
    return list(merged.values())


def enqueue_delivery(
    hotel_id: UUID, connection_id: UUID, room_type_id: UUID, start: date, end: date
) -> None:
    """Queue one availability push. Never raises: the booking is already committed."""
    try:
        celery_app.send_task(
            DELIVER_TASK,
            args=[
                str(hotel_id),
                str(connection_id),
                str(room_type_id),
                start.isoformat(),
                end.isoformat(),
            ],
            retry=True,
            retry_policy={"max_retries": 2, "interval_start": 0.2, "interval_step": 0.5},
        )
    except Exception:
        # The broker is unreachable. The change itself is safe in the database;
        # "Sync now" on the connection re-sends the current availability.
        logger.exception(
            "Could not queue availability push for connection %s (room type %s, %s to %s)",
            connection_id,
            room_type_id,
            start,
            end,
        )


def _run_in_background(job: Callable[[], None]) -> None:
    """Run a blocking job off the event loop, or inline when there is no loop."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        job()
        return
    loop.run_in_executor(None, job)


@event.listens_for(TenantSession, "after_commit")
def _queue_pending_pushes(session: Session) -> None:
    pending: list[_PendingPush] = session.info.pop(_PENDING_KEY, [])
    hotel_id = session.info.get("hotel_id")
    if not pending or not isinstance(hotel_id, UUID):
        return
    for push in _merge(pending):
        # Publishing to the broker is blocking network I/O.
        _run_in_background(
            partial(
                enqueue_delivery,
                hotel_id,
                push.connection_id,
                push.room_type_id,
                push.start,
                push.end,
            )
        )


@event.listens_for(TenantSession, "after_rollback")
def _discard_pending_pushes(session: Session) -> None:
    session.info.pop(_PENDING_KEY, None)


# --- sending --------------------------------------------------------------------


def _http_client() -> httpx.AsyncClient:
    # Redirects are not followed: a redirect target has not been through the
    # address check, and a webhook endpoint has no reason to redirect.
    return httpx.AsyncClient(
        timeout=get_settings().channel_outbound_timeout_seconds, follow_redirects=False
    )


def _clip(detail: str) -> str:
    return detail if len(detail) <= _DETAIL_LIMIT else detail[: _DETAIL_LIMIT - 1] + "…"


async def send_signed(
    url: str, key_id: str, signing_secret: str, payload: dict[str, Any]
) -> DeliveryResult:
    """POST `payload` to `url`, signed the same way inbound webhooks are.

    The receiver verifies `X-Channel-Signature` = "sha256=" + hex HMAC-SHA256 of
    "<X-Channel-Timestamp>.<raw body>" using the connection's signing secret.
    """
    started = time.monotonic()

    def result(ok: bool, status_code: int | None, detail: str, retryable: bool) -> DeliveryResult:
        return DeliveryResult(
            ok, status_code, _clip(detail), retryable, int((time.monotonic() - started) * 1000)
        )

    allow_private = get_settings().channel_outbound_allow_private_hosts
    try:
        target = httpx.URL(validate_outbound_url(url, allow_private=allow_private))
        port = target.port or (443 if target.scheme == "https" else 80)
        address = await resolve_public_address(target.host, port, allow_private=allow_private)
    except OutboundUrlError as exc:
        return result(False, None, str(exc), retryable=False)

    body = json.dumps(payload, separators=(",", ":")).encode()
    timestamp = str(int(time.time()))
    headers = {
        "Content-Type": "application/json",
        "User-Agent": USER_AGENT,
        # We connect to the checked address, so the name travels in Host and SNI.
        "Host": target.netloc.decode("ascii"),
        "X-Channel-Key": key_id,
        "X-Channel-Timestamp": timestamp,
        "X-Channel-Signature": sign_webhook(signing_secret, timestamp, body),
        "X-Channel-Event": str(payload.get("event", "")),
    }
    try:
        async with _http_client() as client:
            response = await client.post(
                target.copy_with(host=address),
                content=body,
                headers=headers,
                extensions={"sni_hostname": target.host},
            )
    except httpx.TimeoutException:
        return result(False, None, "The endpoint did not respond in time", retryable=True)
    except httpx.HTTPError as exc:
        return result(False, None, f"Could not connect: {type(exc).__name__}", retryable=True)

    status = response.status_code
    if 200 <= status < 300:
        return result(True, status, f"Delivered (HTTP {status})", retryable=False)
    # 5xx and "slow down" are the receiver's temporary trouble; any other
    # status means it rejected the request and will reject it again.
    retryable = status >= 500 or status in (408, 425, 429)
    return result(False, status, f"The endpoint answered HTTP {status}", retryable=retryable)


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


async def send_test_ping(connection: ChannelConnection) -> DeliveryResult:
    """Send a signed `ping` so staff can check a URL before relying on it."""
    if connection.outbound_url is None:
        return DeliveryResult(False, None, "No outbound URL is set", False, 0)
    return await send_signed(
        connection.outbound_url,
        connection.key_id,
        connection.signing_secret,
        {"event": EVENT_PING, "generated_at": _now()},
    )


async def deliver_availability(
    hotel_id: UUID, connection_id: UUID, room_type_id: UUID, start: date, end: date
) -> DeliveryResult | None:
    """Push current availability for one room type to one connection.

    Returns None when there is nothing to send (connection disabled or its URL
    removed since the push was queued, room type gone, or every night already
    in the past). Raises DeliveryFailed for failures worth retrying.
    """
    async with tenant_session(hotel_id) as session:
        connection = await session.get(ChannelConnection, connection_id)
        room_type = await session.get(RoomType, room_type_id)
        if (
            connection is None
            or not connection.is_active
            or connection.outbound_url is None
            or room_type is None
        ):
            return None
        # Past nights cannot be sold; channels only care about today onwards.
        start = max(start, await hotel_today(session))
        end = min(end, start + timedelta(days=MAX_RANGE_NIGHTS))
        if end <= start:
            return None
        nights = await get_availability(session, start, end, room_type_id=room_type_id)
        url, key_id, secret = connection.outbound_url, connection.key_id, connection.signing_secret
        payload = {
            "event": EVENT_AVAILABILITY,
            "generated_at": _now(),
            "room_type": {"code": room_type.code, "name": room_type.name},
            "start": start.isoformat(),
            "end": end.isoformat(),
            # An inactive room type reports no nights: it is closed for sale.
            "nights": [
                {
                    "date": night.night.isoformat(),
                    "total_rooms": night.total_rooms,
                    "booked": night.booked,
                    "available": max(night.available, 0),
                }
                for night in nights
            ],
        }

    # The HTTP call is made with no database transaction open.
    result = await send_signed(url, key_id, secret, payload)

    async with tenant_session(hotel_id) as session:
        connection = await session.get(ChannelConnection, connection_id)
        if connection is not None:
            connection.last_push_at = datetime.now(UTC)
            connection.last_push_ok = result.ok
            connection.last_push_detail = result.detail

    if not result.ok and result.retryable:
        raise DeliveryFailed(result.detail)
    return result


async def request_full_sync(session: AsyncSession, connection: ChannelConnection) -> int:
    """Queue a push of every active room type for the coming weeks to one connection.

    For bringing a newly connected channel up to date, or recovering after its
    endpoint was down. Returns the number of room types queued.
    """
    start = await hotel_today(session)
    end = start + timedelta(days=get_settings().channel_outbound_sync_days)
    room_type_ids = (await session.scalars(select(RoomType.id).where(RoomType.is_active))).all()
    pending: list[_PendingPush] = session.info.setdefault(_PENDING_KEY, [])
    pending.extend(
        _PendingPush(connection.id, room_type_id, start, end) for room_type_id in room_type_ids
    )
    return len(room_type_ids)
