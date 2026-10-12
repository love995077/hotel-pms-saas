"""Inbound channel manager integration: turn OTA booking events into reservations.

Bookings are created through the same reservation service the front desk uses,
so they take the room type lock, pass the same availability check and decrement
inventory in exactly the same way. Nothing here writes reservations directly.
"""

import time
from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.exceptions import (
    ConflictError,
    DomainError,
    DuplicateBookingError,
    NotFoundError,
    UnprocessableError,
)
from app.core.security import webhook_signature_valid
from app.database import engine, tenant_session
from app.models import (
    BookingSource,
    ChannelWebhookEvent,
    Guest,
    Reservation,
    ReservationStatus,
    RoomType,
    WebhookEventStatus,
)
from app.schemas.channel import BookingCancelledEvent, BookingCreatedEvent, ChannelGuest
from app.schemas.reservation import ReservationCreate
from app.services.channel_sync import set_push_origin
from app.services.reservations import cancel_reservation, create_reservation

# Used when the key id is unknown, so the HMAC is computed either way.
_UNKNOWN_KEY_SECRET = "unknown-key"  # noqa: S105

Result = Literal["created", "cancelled", "duplicate"]


@dataclass(frozen=True, slots=True)
class ChannelContext:
    """The verified sender of a webhook."""

    hotel_id: UUID
    connection_id: UUID


@dataclass(frozen=True, slots=True)
class Outcome:
    result: Result
    reservation: Reservation


async def authenticate_webhook(
    key_id: str, timestamp: str, signature: str, body: bytes
) -> ChannelContext | None:
    """Verify a delivery's signature and freshness; None if it must be refused."""
    async with engine.connect() as connection:
        row = (
            await connection.execute(
                text(
                    "SELECT connection_id, hotel_id, signing_secret "
                    "FROM channel_lookup_connection(:key_id)"
                ),
                {"key_id": key_id},
            )
        ).one_or_none()

    secret = row.signing_secret if row else _UNKNOWN_KEY_SECRET
    if not webhook_signature_valid(secret, timestamp, body, signature) or row is None:
        return None

    tolerance = get_settings().webhook_timestamp_tolerance_seconds
    if not timestamp.isascii() or not timestamp.isdigit():
        return None
    if abs(time.time() - int(timestamp)) > tolerance:
        return None
    return ChannelContext(hotel_id=row.hotel_id, connection_id=row.connection_id)


async def _find_booking(
    session: AsyncSession, channel: BookingSource, booking_id: str
) -> Reservation | None:
    return await session.scalar(
        select(Reservation).where(
            Reservation.source == channel, Reservation.external_reference == booking_id
        )
    )


async def _find_or_create_guest(
    session: AsyncSession, hotel_id: UUID, guest: ChannelGuest
) -> tuple[Guest, bool]:
    """Reuse the hotel's existing guest profile when the email matches.

    Returns the guest and whether it was created by this call.
    """
    if guest.email is not None:
        existing = await session.scalar(
            select(Guest)
            .where(func.lower(Guest.email) == guest.email.lower())
            .order_by(Guest.created_at)
            .limit(1)
        )
        if existing is not None:
            return existing, False
    created = Guest(hotel_id=hotel_id, **guest.model_dump())
    session.add(created)
    await session.flush()
    return created, True


async def _create_booking(
    session: AsyncSession, hotel_id: UUID, event: BookingCreatedEvent
) -> Outcome:
    existing = await _find_booking(session, event.channel, event.booking_id)
    if existing is not None:
        return Outcome("duplicate", existing)

    room_type_id = await session.scalar(
        select(RoomType.id).where(RoomType.code == event.room_type_code)
    )
    if room_type_id is None:
        raise UnprocessableError(f"Unknown room type code '{event.room_type_code}'")

    guest, guest_created = await _find_or_create_guest(session, hotel_id, event.guest)
    try:
        reservation = await create_reservation(
            session,
            ReservationCreate(
                guest_id=guest.id,
                room_type_id=room_type_id,
                check_in_date=event.check_in_date,
                check_out_date=event.check_out_date,
                adults=event.adults,
                children=event.children,
                rate_per_night=event.rate_per_night,
                source=event.channel,
                external_reference=event.booking_id,
                notes=event.notes,
            ),
        )
    except DuplicateBookingError:
        # A concurrent delivery of the same booking committed first.
        existing = await _find_booking(session, event.channel, event.booking_id)
        if existing is None:
            raise
        if guest_created:
            # This transaction still commits; do not leave a second profile behind.
            await session.delete(guest)
            await session.flush()
        return Outcome("duplicate", existing)
    return Outcome("created", reservation)


async def _cancel_booking(session: AsyncSession, event: BookingCancelledEvent) -> Outcome:
    reservation = await _find_booking(session, event.channel, event.booking_id)
    if reservation is None:
        raise NotFoundError("No reservation exists for this booking")
    if reservation.status == ReservationStatus.CANCELLED:
        return Outcome("duplicate", reservation)
    if reservation.status != ReservationStatus.CONFIRMED:
        raise ConflictError(f"A {reservation.status} reservation cannot be cancelled")
    return Outcome("cancelled", await cancel_reservation(session, reservation.id))


def _log_entry(
    context: ChannelContext,
    event: BookingCreatedEvent | BookingCancelledEvent,
    status: WebhookEventStatus,
    *,
    reservation_id: UUID | None = None,
    detail: str | None = None,
) -> ChannelWebhookEvent:
    return ChannelWebhookEvent(
        hotel_id=context.hotel_id,
        connection_id=context.connection_id,
        event_type=event.event,
        channel=event.channel.value,
        external_booking_id=event.booking_id,
        status=status,
        detail=detail,
        reservation_id=reservation_id,
        payload=event.model_dump(mode="json"),
    )


async def handle_event(
    context: ChannelContext, event: BookingCreatedEvent | BookingCancelledEvent
) -> Outcome:
    """Apply one verified event in a single transaction and record what happened.

    A rejected event rolls back completely; its log entry is then written in a
    transaction of its own so that the rejection (for example an OTA booking
    the hotel had no room for) is still visible to staff.
    """
    try:
        async with tenant_session(context.hotel_id) as session:
            # Every other outbound connection hears about the change; the sender already knows.
            set_push_origin(session, context.connection_id)
            if isinstance(event, BookingCreatedEvent):
                outcome = await _create_booking(session, context.hotel_id, event)
            else:
                outcome = await _cancel_booking(session, event)
            session.add(
                _log_entry(
                    context,
                    event,
                    WebhookEventStatus.DUPLICATE
                    if outcome.result == "duplicate"
                    else WebhookEventStatus.PROCESSED,
                    reservation_id=outcome.reservation.id,
                )
            )
            return outcome
    except DomainError as exc:
        async with tenant_session(context.hotel_id) as session:
            session.add(_log_entry(context, event, WebhookEventStatus.REJECTED, detail=exc.detail))
        raise
