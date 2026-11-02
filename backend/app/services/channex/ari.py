"""Outbound ARI (availability, rates, inventory) to Channex.

Queued by app.services.channel_sync after any transaction that changes what can
be sold, and by "Sync now". Like the generic push, it reads availability when it
runs, so a retry never sends numbers that have gone stale.

Every push sends availability. Rates are sent only by a full sync, and only for
room types whose mapping names a Channex rate plan: many hotels manage rates in
Channex itself, and a booking must not overwrite them with our base rate.
"""

import logging
from collections.abc import Iterable
from datetime import UTC, date, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import select

from app.database import tenant_session
from app.models import ChannelConnection, ChannelProvider, ChannexRoomMapping, RoomType
from app.services.availability import MAX_RANGE_NIGHTS, get_availability
from app.services.channel_sync import DeliveryFailed
from app.services.channex.client import ChannexResponse, get_channex_client
from app.services.folios import hotel_today

logger = logging.getLogger(__name__)


def availability_values(
    property_id: str, channex_room_type_id: str, nights: Iterable[tuple[date, int]]
) -> list[dict[str, Any]]:
    """One Channex value per run of consecutive nights with the same count.

    Channex date ranges are inclusive of `date_to`; ours exclude the end.
    """
    values: list[dict[str, Any]] = []
    for night, count in sorted(nights):
        last = values[-1] if values else None
        if (
            last is not None
            and last["availability"] == count
            and date.fromisoformat(last["date_to"]) + timedelta(days=1) == night
        ):
            last["date_to"] = night.isoformat()
            continue
        values.append(
            {
                "property_id": property_id,
                "room_type_id": channex_room_type_id,
                "date_from": night.isoformat(),
                "date_to": night.isoformat(),
                "availability": count,
            }
        )
    return values


async def push_ari(
    hotel_id: UUID,
    connection_id: UUID,
    ranges: list[tuple[UUID, date, date]],
    include_rates: bool,
) -> ChannexResponse | None:
    """Send current availability (and, if asked, rates) for the given nights.

    Returns None when there is nothing to send: the connection is gone or
    disabled, no requested room type is mapped, or every night is in the past.
    Raises DeliveryFailed when Channex could not be reached or asked us to
    slow down, so the task retries.
    """
    availability: list[dict[str, Any]] = []
    restrictions: list[dict[str, Any]] = []
    async with tenant_session(hotel_id) as session:
        connection = await session.get(ChannelConnection, connection_id)
        if (
            connection is None
            or not connection.is_active
            or connection.provider != ChannelProvider.CHANNEX
            or connection.external_property_id is None
        ):
            return None
        property_id = connection.external_property_id
        mappings = {
            mapping.room_type_id: mapping
            for mapping in await session.scalars(
                select(ChannexRoomMapping).where(
                    ChannexRoomMapping.connection_id == connection_id,
                    ChannexRoomMapping.room_type_id.in_({r for r, _, _ in ranges}),
                )
            )
        }
        today = await hotel_today(session)
        for room_type_id, requested_start, requested_end in ranges:
            mapping = mappings.get(room_type_id)
            room_type = await session.get(RoomType, room_type_id)
            if mapping is None or room_type is None:
                logger.warning(
                    "Room type %s has no Channex mapping on connection %s; not pushed",
                    room_type_id,
                    connection_id,
                )
                continue
            # Past nights cannot be sold.
            start = max(requested_start, today)
            end = min(requested_end, start + timedelta(days=MAX_RANGE_NIGHTS))
            if end <= start:
                continue
            if room_type.is_active:
                nights = await get_availability(session, start, end, room_type_id=room_type_id)
                counts = [(night.night, max(night.available, 0)) for night in nights]
            else:
                # A deactivated room type is closed for sale on every channel.
                counts = [(start + timedelta(days=i), 0) for i in range((end - start).days)]
            availability += availability_values(property_id, mapping.channex_room_type_id, counts)
            if include_rates and mapping.channex_rate_plan_id is not None:
                restrictions.append(
                    {
                        "property_id": property_id,
                        "rate_plan_id": mapping.channex_rate_plan_id,
                        "date_from": start.isoformat(),
                        "date_to": (end - timedelta(days=1)).isoformat(),
                        "rate": f"{room_type.base_rate:.2f}",
                    }
                )

    if not availability and not restrictions:
        return None

    # The HTTP calls are made with no database transaction open.
    client = get_channex_client()
    if availability:
        result = await client.update_availability(availability)
        if result.ok and restrictions:
            result = await client.update_restrictions(restrictions)
    else:
        result = await client.update_restrictions(restrictions)

    async with tenant_session(hotel_id) as session:
        connection = await session.get(ChannelConnection, connection_id)
        if connection is not None:
            connection.last_push_at = datetime.now(UTC)
            connection.last_push_ok = result.ok
            connection.last_push_detail = result.detail

    if not result.ok and result.retryable:
        raise DeliveryFailed(result.detail)
    return result
