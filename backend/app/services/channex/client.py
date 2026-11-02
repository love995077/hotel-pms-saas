"""HTTP client for the Channex.io API, with a mock for use until keys are issued.

Both clients build exactly the same requests (`ChannexClient`); they differ only
in `_send`. `HttpChannexClient` calls Channex with the `user-api-key` header.
`MockChannexClient` sends nothing: it records each request and answers the way
Channex documents a success. `get_channex_client()` picks one from settings, so
going live is configuration only:

    CHANNEX_MODE=live
    CHANNEX_BASE_URL=https://app.channex.io/api/v1   (staging: https://staging.channex.io/api/v1)
    CHANNEX_API_KEY=...
"""

import logging
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, ClassVar
from uuid import uuid4

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)

USER_AGENT = "HotelPMS-Channex/1.0"
_DETAIL_LIMIT = 300


@dataclass(frozen=True, slots=True)
class ChannexResponse:
    ok: bool
    # None when no HTTP response was received at all.
    status_code: int | None
    detail: str
    # False for outcomes that trying again cannot change (validation errors, warnings).
    retryable: bool
    duration_ms: int
    body: dict[str, Any] = field(default_factory=dict)


def _clip(detail: str) -> str:
    return detail if len(detail) <= _DETAIL_LIMIT else detail[: _DETAIL_LIMIT - 1] + "…"


def _error_title(body: dict[str, Any]) -> str | None:
    errors = body.get("errors")
    if isinstance(errors, dict):
        title = errors.get("title") or errors.get("code")
        return str(title) if title else None
    return None


def interpret(
    status: int, body: dict[str, Any], duration_ms: int, prefix: str = ""
) -> ChannexResponse:
    """Turn a Channex answer into a result. Shared by the real and the mock client."""

    def result(ok: bool, detail: str, retryable: bool) -> ChannexResponse:
        return ChannexResponse(ok, status, _clip(prefix + detail), retryable, duration_ms, body)

    if 200 <= status < 300:
        # Channex answers 200 but lists values it skipped (an unknown room type,
        # a date in the past) as warnings. Sending them again will not help.
        meta = body.get("meta")
        warnings = meta.get("warnings") if isinstance(meta, dict) else None
        if warnings:
            return result(False, f"Channex accepted with warnings: {warnings}", retryable=False)
        return result(True, f"Accepted by Channex (HTTP {status})", retryable=False)
    title = _error_title(body)
    detail = f"Channex answered HTTP {status}" + (f": {title}" if title else "")
    # Channex rate-limits ARI per property; 429 and 5xx clear up by themselves.
    return result(False, detail, retryable=status >= 500 or status in (408, 425, 429))


class ChannexClient:
    """The Channex calls this PMS makes. Subclasses supply the transport."""

    async def _send(
        self, method: str, path: str, json: dict[str, Any] | None = None
    ) -> ChannexResponse:
        raise NotImplementedError

    async def update_availability(self, values: list[dict[str, Any]]) -> ChannexResponse:
        """`values`: {property_id, room_type_id, date_from, date_to (inclusive), availability}."""
        return await self._send("POST", "/availability", {"values": values})

    async def update_restrictions(self, values: list[dict[str, Any]]) -> ChannexResponse:
        """`values`: {property_id, rate_plan_id, date_from, date_to (inclusive), rate}."""
        return await self._send("POST", "/restrictions", {"values": values})

    async def get_booking_revision(self, revision_id: str) -> ChannexResponse:
        return await self._send("GET", f"/booking_revisions/{revision_id}")

    async def ack_booking_revision(self, revision_id: str) -> ChannexResponse:
        """Tell Channex a revision is applied, so it leaves the unacknowledged feed."""
        return await self._send("POST", f"/booking_revisions/{revision_id}/ack")

    async def get_property(self, property_id: str) -> ChannexResponse:
        """Cheapest call that proves the key works and can see the property."""
        return await self._send("GET", f"/properties/{property_id}")


class HttpChannexClient(ChannexClient):
    def __init__(self, base_url: str, api_key: str, timeout: float) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._timeout = timeout

    async def _send(
        self, method: str, path: str, json: dict[str, Any] | None = None
    ) -> ChannexResponse:
        started = time.monotonic()

        def elapsed() -> int:
            return int((time.monotonic() - started) * 1000)

        headers = {
            "user-api-key": self._api_key,
            "Accept": "application/json",
            "User-Agent": USER_AGENT,
        }
        try:
            async with httpx.AsyncClient(timeout=self._timeout, follow_redirects=False) as client:
                response = await client.request(
                    method, self._base_url + path, json=json, headers=headers
                )
        except httpx.TimeoutException:
            return ChannexResponse(False, None, "Channex did not respond in time", True, elapsed())
        except httpx.HTTPError as exc:
            detail = f"Could not reach Channex: {type(exc).__name__}"
            return ChannexResponse(False, None, detail, True, elapsed())

        try:
            body = response.json()
        except ValueError:
            body = {}
        return interpret(response.status_code, body if isinstance(body, dict) else {}, elapsed())


class MockChannexClient(ChannexClient):
    """Stands in for Channex until API keys are issued. Sends nothing anywhere.

    Every request is kept in `requests` (most recent last) so tests and
    developers can see exactly what would have been sent. Booking revisions
    put in `revisions` are served by `get_booking_revision`; any other id is a 404.
    """

    requests: ClassVar[deque[tuple[str, str, dict[str, Any] | None]]] = deque(maxlen=500)
    revisions: ClassVar[dict[str, dict[str, Any]]] = {}

    async def _send(
        self, method: str, path: str, json: dict[str, Any] | None = None
    ) -> ChannexResponse:
        self.requests.append((method, path, json))
        logger.info("Channex mock: %s %s %s", method, path, json)
        status, body = self._answer(method, path, json)
        return interpret(status, body, duration_ms=0, prefix="Mock, not sent: ")

    def _answer(
        self, method: str, path: str, json: dict[str, Any] | None
    ) -> tuple[int, dict[str, Any]]:
        parts = path.strip("/").split("/")
        if method == "POST" and parts[0] in ("availability", "restrictions"):
            return 200, {
                "data": [{"id": str(uuid4()), "type": "task"}],
                "meta": {"message": "Success", "warnings": []},
            }
        if method == "POST" and parts[0] == "booking_revisions" and parts[-1] == "ack":
            return 200, {"meta": {"message": "Success"}}
        if method == "GET" and parts[0] == "booking_revisions" and parts[1] in self.revisions:
            attributes = self.revisions[parts[1]]
            return 200, {
                "data": {"type": "booking_revision", "id": parts[1], "attributes": attributes}
            }
        if method == "GET" and parts[0] == "properties":
            return 200, {
                "data": {
                    "type": "property",
                    "id": parts[1],
                    "attributes": {"id": parts[1], "title": "Mock property", "currency": "INR"},
                }
            }
        return 404, {"errors": {"code": "resource_not_found", "title": "Resource Not Found"}}


def get_channex_client() -> ChannexClient:
    settings = get_settings()
    if settings.channex_mode == "mock":
        return MockChannexClient()
    if settings.channex_api_key is None:
        # Unreachable: the settings validator requires a key in live mode.
        raise RuntimeError("CHANNEX_API_KEY is not set")
    return HttpChannexClient(
        settings.channex_base_url,
        settings.channex_api_key.get_secret_value(),
        settings.channex_timeout_seconds,
    )
