"""Inbound Channex bookings: apply booking revisions as reservations.

A Channex booking revision is the whole current state of a booking, not a
diff. Applying one makes our reservations match it, so a redelivery changes
nothing and a "modified" revision for a booking we never saw simply creates it.

Each room in the booking is one reservation, with external reference
"<channex booking id>/<n>" (n counting from 1), source taken from the OTA name.
Everything goes through the reservation service: same room type lock, same
availability check, same availability push to every connected channel
(including Channex itself, which needs the new count for its other OTAs).

Once a revision is applied and committed, it is acknowledged to Channex
(`channex.ack_revision`), which takes it out of the unacknowledged feed. A
revision that is rejected is not acknowledged, so it can be applied later.
"""

import asyncio
import hmac
import logging
import re
from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.celery_app import celery_app
from app.core.exceptions import (
    ConflictError,
    DomainError,
    UnprocessableError,
    UpstreamUnavailableError,
)
from app.database import engine, tenant_session
from app.models import (
    BookingSource,
    ChannelWebhookEvent,
    ChannexRoomMapping,
    Hotel,
    Reservation,
    ReservationStatus,
    WebhookEventStatus,
)
from app.schemas.channel import ChannelGuest
from app.schemas.channex import (
    BOOKING_EVENTS,
    ChannexBookingRevision,
    ChannexRevisionRoom,
    ChannexWebhook,
)
from app.schemas.reservation import ReservationCreate
from app.services.channel_manager import find_or_create_guest
from app.services.channel_sync import DeliveryFailed
from app.services.channex.client import get_channex_client
from app.services.reservations import cancel_reservation, create_reservation, update_reservation

logger = logging.getLogger(__name__)

ACK_TASK = "channex.ack_revision"

# Used when the key id is unknown, so the comparison is made either way.
_UNKNOWN_KEY_TOKEN = "unknown-key"  # noqa: S105
_CENT = Decimal("0.01")

# Channex's ota_name, lower-cased with everything but letters and digits removed.
_OTA_SOURCES = {
    "bookingcom": BookingSource.BOOKING_COM,
    "booking": BookingSource.BOOKING_COM,
    "expedia": BookingSource.EXPEDIA,
    "airbnb": BookingSource.AIRBNB,
    "agoda": BookingSource.AGODA,
    "makemytrip": BookingSource.MAKEMYTRIP,
    "mmt": BookingSource.MAKEMYTRIP,
    "goibibo": BookingSource.GOIBIBO,
}

Result = Literal["created", "modified", "cancelled", "unchanged", "ignored"]


@dataclass(frozen=True, slots=True)
class ChannexContext:
    """The verified sender of a Channex webhook."""

    hotel_id: UUID
    connection_id: UUID
    property_id: str


@dataclass(slots=True)
class ChannexOutcome:
    result: Result
    revision: ChannexBookingRevision | None = None
    reservations: list[Reservation] = field(default_factory=list)


async def authenticate_channex_webhook(key_id: str, token: str) -> ChannexContext | None:
    """Check the key and token Channex sends as webhook headers; None to refuse.

    Channex does not sign webhooks. Instead the webhook is configured in
    Channex with two custom headers carrying the connection's key id and its
    secret, which are compared in constant time.
    """
    async with engine.connect() as connection:
        row = (
            await connection.execute(
                text(
                    "SELECT connection_id, hotel_id, signing_secret, property_id "
                    "FROM channex_lookup_connection(:key_id)"
                ),
                {"key_id": key_id},
            )
        ).one_or_none()
    expected = row.signing_secret if row else _UNKNOWN_KEY_TOKEN
    if not hmac.compare_digest(expected.encode(), token.encode()) or row is None:
        return None
    return ChannexContext(row.hotel_id, row.connection_id, row.property_id)


def booking_source(ota_name: str | None) -> BookingSource:
    key = re.sub(r"[^a-z0-9]", "", (ota_name or "").lower())
    return _OTA_SOURCES.get(key, BookingSource.OTHER)


def external_reference(booking_id: str, room_index: int) -> str:
    return f"{booking_id}/{room_index + 1}"


def _revision_from(document: dict[str, Any]) -> ChannexBookingRevision | None:
    """The booking revision in a webhook payload or an API answer, if there is one.

    Accepts the JSON:API form the API returns ({"data": {"id", "attributes"}})
    and the flat form a webhook with "send data" carries.
    """
    data = document.get("data")
    if isinstance(data, dict) and isinstance(data.get("attributes"), dict):
        document = {"id": data.get("id"), **data["attributes"]}
    for key in ("booking", "revision"):
        if isinstance(document.get(key), dict):
            document = {**document, **document[key]}
    if "arrival_date" not in document:
        return None
    if "id" not in document and "revision_id" in document:
        document = {**document, "id": document["revision_id"]}
    try:
        return ChannexBookingRevision.model_validate(document)
    except ValidationError as exc:
        raise UnprocessableError(f"Malformed Channex booking revision: {exc}") from exc


async def _fetch_revision(revision_id: str) -> ChannexBookingRevision:
    response = await get_channex_client().get_booking_revision(revision_id)
    if not response.ok:
        if response.retryable:
            raise UpstreamUnavailableError(response.detail)
        raise UnprocessableError(
            f"Could not fetch booking revision {revision_id}: {response.detail}"
        )
    revision = _revision_from(response.body)
    if revision is None:
        raise UnprocessableError(f"Channex returned no booking revision for {revision_id}")
    return revision


async def resolve_revision(webhook: ChannexWebhook) -> ChannexBookingRevision:
    """The revision a booking webhook is about: from the payload, or fetched by id."""
    inline = _revision_from(webhook.payload)
    if inline is not None:
        return inline
    revision_id = webhook.payload.get("revision_id")
    if not isinstance(revision_id, str) or not re.fullmatch(r"[A-Za-z0-9-]{1,64}", revision_id):
        raise UnprocessableError("Booking webhook has neither booking data nor a revision_id")
    return await _fetch_revision(revision_id)


# --- applying a revision ----------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _Stay:
    """What one room of a revision says the reservation should be."""

    room_type_id: UUID
    check_in_date: date
    check_out_date: date
    adults: int
    children: int
    # None: keep the current rate (or use the base rate for a new booking).
    rate_per_night: Decimal | None


async def _room_type_ids(
    session: AsyncSession, connection_id: UUID, revision: ChannexBookingRevision
) -> dict[str, UUID]:
    wanted = {room.room_type_id for room in revision.rooms}
    mapped = {
        mapping.channex_room_type_id: mapping.room_type_id
        for mapping in await session.scalars(
            select(ChannexRoomMapping).where(
                ChannexRoomMapping.connection_id == connection_id,
                ChannexRoomMapping.channex_room_type_id.in_(wanted),
            )
        )
    }
    missing = sorted(wanted - mapped.keys())
    if missing:
        raise UnprocessableError(
            f"Channex room type {', '.join(missing)} is not mapped to a room type of this hotel"
        )
    return mapped


def _stay(
    room: ChannexRevisionRoom,
    revision: ChannexBookingRevision,
    room_type_id: UUID,
    hotel_currency: str,
) -> _Stay:
    check_in = room.checkin_date or revision.arrival_date
    check_out = room.checkout_date or revision.departure_date
    nights = (check_out - check_in).days
    rate = None
    # A rate in another currency would be taxed and invoiced as if it were ours;
    # the room type's base rate is used instead and the OTA amount kept in the notes.
    same_currency = revision.currency is None or revision.currency.upper() == hotel_currency
    if room.amount is not None and nights > 0 and same_currency:
        # TODO(channex-live): confirm with real payloads whether OTA amounts
        # include tax; our rate is before GST.
        rate = (room.amount / nights).quantize(_CENT, rounding=ROUND_HALF_UP)
    return _Stay(
        room_type_id=room_type_id,
        check_in_date=check_in,
        check_out_date=check_out,
        adults=max(room.occupancy.adults, 1),
        children=room.occupancy.children,
        rate_per_night=rate,
    )


def _notes(revision: ChannexBookingRevision) -> str:
    parts = [f"Channex booking via {revision.ota_name or 'unknown channel'}"]
    if revision.ota_reservation_code:
        parts[0] += f", OTA reference {revision.ota_reservation_code}"
    if revision.currency and revision.amount is not None:
        parts.append(f"OTA total {revision.amount} {revision.currency}")
    if revision.notes:
        parts.append(revision.notes)
    return ". ".join(parts)[:2000]


async def _existing(session: AsyncSession, booking_id: str) -> dict[str, Reservation]:
    reservations = await session.scalars(
        select(Reservation).where(
            Reservation.external_reference.startswith(f"{booking_id}/", autoescape=True)
        )
    )
    return {r.external_reference: r for r in reservations if r.external_reference}


async def _cancel(session: AsyncSession, reservation: Reservation) -> bool:
    """Cancel one room of a booking. True if anything changed."""
    if reservation.status in (ReservationStatus.CANCELLED, ReservationStatus.NO_SHOW):
        return False
    if reservation.status != ReservationStatus.CONFIRMED:
        raise ConflictError(
            f"Reservation {reservation.confirmation_number} is {reservation.status}; "
            "Channex cancelled it, so it needs attention at the front desk"
        )
    await cancel_reservation(session, reservation.id)
    return True


async def apply_revision(
    session: AsyncSession, context: ChannexContext, revision: ChannexBookingRevision
) -> ChannexOutcome:
    """Make the booking's reservations match the revision, in the caller's transaction."""
    existing = await _existing(session, revision.booking_id)
    touched: list[Reservation] = []

    if revision.status == "cancelled":
        changed = False
        for reservation in existing.values():
            changed |= await _cancel(session, reservation)
            touched.append(reservation)
        return ChannexOutcome("cancelled" if changed else "unchanged", revision, touched)

    if not revision.rooms:
        raise UnprocessableError("Channex booking revision has no rooms")
    room_type_ids = await _room_type_ids(session, context.connection_id, revision)
    hotel = await session.get(Hotel, context.hotel_id)
    hotel_currency = hotel.currency if hotel is not None else "INR"
    source = booking_source(revision.ota_name)
    created = modified = False
    guest_id: UUID | None = None

    for index, room in enumerate(revision.rooms):
        ref = external_reference(revision.booking_id, index)
        stay = _stay(room, revision, room_type_ids[room.room_type_id], hotel_currency)
        current = existing.pop(ref, None)

        if current is None:
            if guest_id is None:
                guest, _ = await find_or_create_guest(
                    session,
                    context.hotel_id,
                    ChannelGuest(
                        first_name=revision.customer.name or "Guest",
                        last_name=revision.customer.surname or revision.ota_reservation_code or "-",
                        email=revision.customer.valid_email(),
                        phone=revision.customer.phone,
                    ),
                )
                guest_id = guest.id
            touched.append(
                await create_reservation(
                    session,
                    ReservationCreate(
                        guest_id=guest_id,
                        room_type_id=stay.room_type_id,
                        check_in_date=stay.check_in_date,
                        check_out_date=stay.check_out_date,
                        adults=stay.adults,
                        children=stay.children,
                        rate_per_night=stay.rate_per_night,
                        source=source,
                        external_reference=ref,
                        notes=_notes(revision),
                    ),
                )
            )
            created = True
            continue

        changes = {
            name: value
            for name, value in (
                ("room_type_id", stay.room_type_id),
                ("check_in_date", stay.check_in_date),
                ("check_out_date", stay.check_out_date),
                ("adults", stay.adults),
                ("children", stay.children),
                ("rate_per_night", stay.rate_per_night),
            )
            if value is not None and getattr(current, name) != value
        }
        if changes:
            if current.status != ReservationStatus.CONFIRMED:
                raise ConflictError(
                    f"Reservation {current.confirmation_number} is {current.status}; "
                    "Channex changed it, so it needs attention at the front desk"
                )
            current = await update_reservation(session, current.id, changes)
            modified = True
        touched.append(current)

    # Rooms the booking no longer has.
    for reservation in existing.values():
        modified |= await _cancel(session, reservation)
        touched.append(reservation)

    result: Result = "created" if created else "modified" if modified else "unchanged"
    return ChannexOutcome(result, revision, touched)


# --- the webhook as a whole ---------------------------------------------------------


def enqueue_ack(hotel_id: UUID, connection_id: UUID, revision_id: str) -> None:
    """Queue the acknowledgement of an applied revision. Never raises.

    If it is lost, Channex keeps the revision in its unacknowledged feed and
    redelivers it; applying it again changes nothing.
    """
    try:
        celery_app.send_task(
            ACK_TASK,
            args=[str(hotel_id), str(connection_id), revision_id],
            retry=True,
            retry_policy={"max_retries": 2, "interval_start": 0.2, "interval_step": 0.5},
        )
    except Exception:
        logger.exception("Could not queue Channex acknowledgement of revision %s", revision_id)


def _log_entry(
    context: ChannexContext,
    body: Any,
    status: WebhookEventStatus,
    *,
    webhook: ChannexWebhook | None = None,
    revision: ChannexBookingRevision | None = None,
    reservation_id: UUID | None = None,
    detail: str | None = None,
) -> ChannelWebhookEvent:
    booking_id: Any
    if revision is not None:
        booking_id = revision.booking_id
    elif webhook is not None:
        booking_id = webhook.payload.get("booking_id")
    else:
        booking_id = None
    return ChannelWebhookEvent(
        hotel_id=context.hotel_id,
        connection_id=context.connection_id,
        event_type=webhook.event if webhook else "invalid",
        channel=booking_source(revision.ota_name if revision else None).value,
        external_booking_id=str(booking_id or "-")[:100],
        status=status,
        detail=detail,
        reservation_id=reservation_id,
        # The body exactly as received, so an unexpected shape can be inspected.
        payload=body if isinstance(body, dict) else {"body": body},
    )


async def _record(context: ChannexContext, entry: ChannelWebhookEvent) -> None:
    async with tenant_session(context.hotel_id) as session:
        session.add(entry)


def _summarise(exc: ValidationError) -> str:
    """Where the body was wrong, without echoing its values."""
    problems = [
        f"{'.'.join(str(part) for part in error['loc']) or 'body'}: {error['msg']}"
        for error in exc.errors()
    ]
    return "Unexpected webhook body: " + "; ".join(problems)


async def handle_webhook(context: ChannexContext, body: Any) -> ChannexOutcome:
    """Apply one authenticated Channex webhook and record what happened.

    Every authenticated delivery is logged, whatever it contained: a body that
    is not a webhook at all as rejected, and events other than bookings
    (Channex's test message, messages, reviews) as ignored. A rejected booking
    rolls back completely; its log entry is then written in a transaction of
    its own so staff can see it.
    """
    try:
        webhook = ChannexWebhook.model_validate(body)
    except ValidationError as exc:
        detail = _summarise(exc)
        logger.warning(
            "Channex webhook for connection %s refused: %s", context.connection_id, detail
        )
        await _record(
            context, _log_entry(context, body, WebhookEventStatus.REJECTED, detail=detail)
        )
        raise UnprocessableError(detail) from exc

    if webhook.event not in BOOKING_EVENTS:
        logger.info(
            "Channex %r event for connection %s ignored", webhook.event, context.connection_id
        )
        await _record(
            context,
            _log_entry(
                context,
                body,
                WebhookEventStatus.IGNORED,
                webhook=webhook,
                detail="Not a booking event; nothing to do",
            ),
        )
        return ChannexOutcome("ignored")

    revision: ChannexBookingRevision | None = None
    try:
        revision = await resolve_revision(webhook)
        for property_id in (webhook.property_id, revision.property_id):
            if property_id is not None and property_id != context.property_id:
                raise UnprocessableError(
                    "Booking is for a Channex property not linked to this hotel"
                )
        async with tenant_session(context.hotel_id) as session:
            outcome = await apply_revision(session, context, revision)
            session.add(
                _log_entry(
                    context,
                    body,
                    WebhookEventStatus.DUPLICATE
                    if outcome.result == "unchanged"
                    else WebhookEventStatus.PROCESSED,
                    webhook=webhook,
                    revision=revision,
                    reservation_id=outcome.reservations[0].id if outcome.reservations else None,
                    detail=None if outcome.reservations else "No reservation for this booking",
                )
            )
    except DomainError as exc:
        await _record(
            context,
            _log_entry(
                context,
                body,
                WebhookEventStatus.REJECTED,
                webhook=webhook,
                revision=revision,
                detail=exc.detail,
            ),
        )
        raise

    # Committed: now Channex may forget it. Publishing is blocking network I/O.
    await asyncio.to_thread(enqueue_ack, context.hotel_id, context.connection_id, revision.id)
    return outcome


async def ack_revision(hotel_id: UUID, connection_id: UUID, revision_id: str) -> bool:
    """Acknowledge one revision to Channex. False if it could not be done; raises to retry."""
    response = await get_channex_client().ack_booking_revision(revision_id)
    if not response.ok and response.retryable:
        raise DeliveryFailed(response.detail)
    if not response.ok:
        logger.warning(
            "Channex refused acknowledgement of revision %s (hotel %s, connection %s): %s",
            revision_id,
            hotel_id,
            connection_id,
            response.detail,
        )
    return response.ok
