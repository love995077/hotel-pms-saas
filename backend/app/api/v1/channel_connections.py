import secrets
from collections.abc import Sequence
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import delete, select

from app.api.deps import FRONT_OFFICE, MANAGEMENT, DbSession, get_current_user, require_roles
from app.core.exceptions import ConflictError, UnprocessableError
from app.database import current_hotel_id
from app.models import (
    ChannelConnection,
    ChannelProvider,
    ChannelWebhookEvent,
    ChannexRoomMapping,
    RoomType,
    WebhookEventStatus,
)
from app.schemas.channel import (
    ChannelConnectionCreate,
    ChannelConnectionCreated,
    ChannelConnectionRead,
    ChannelConnectionUpdate,
    ChannelWebhookEventRead,
    OutboundTestResult,
    SyncQueued,
)
from app.schemas.channex import ChannexMappingItem, ChannexMappingRead
from app.services.channel_sync import DeliveryResult, request_full_sync, send_test_ping
from app.services.channex.client import ChannexResponse, get_channex_client
from app.services.crud import apply_changes, flush_or_conflict, get_or_404

router = APIRouter(
    prefix="/channel-connections",
    tags=["channel manager"],
    dependencies=[Depends(get_current_user)],
)
_manage = Depends(require_roles(*MANAGEMENT))


@router.post(
    "",
    response_model=ChannelConnectionCreated,
    status_code=status.HTTP_201_CREATED,
    dependencies=[_manage],
)
async def create_connection(data: ChannelConnectionCreate, db: DbSession) -> ChannelConnection:
    """Issue webhook credentials. The signing secret is shown only in this response.

    For `provider: "channex"`, pass the hotel's Channex property id; the key id
    and secret go into the Channex webhook's `X-Channex-Key` / `X-Channex-Token`
    headers. A hotel has at most one Channex connection.
    """
    connection = ChannelConnection(
        hotel_id=current_hotel_id(db),
        name=data.name,
        provider=data.provider,
        external_property_id=data.external_property_id,
        key_id="ck_" + secrets.token_hex(16),
        signing_secret=secrets.token_urlsafe(48),
    )
    db.add(connection)
    await flush_or_conflict(db, "This hotel already has a Channex connection")
    return connection


@router.get("", response_model=list[ChannelConnectionRead], dependencies=[_manage])
async def list_connections(db: DbSession) -> Sequence[ChannelConnection]:
    return (await db.scalars(select(ChannelConnection).order_by(ChannelConnection.name))).all()


@router.patch("/{connection_id}", response_model=ChannelConnectionRead, dependencies=[_manage])
async def update_connection(
    connection_id: UUID, data: ChannelConnectionUpdate, db: DbSession
) -> ChannelConnection:
    """Rename a connection, set its outbound URL, or deactivate it.

    A deactivated connection's webhooks are refused and it is sent no pushes.
    """
    connection = await get_or_404(db, ChannelConnection, connection_id)
    changes = data.model_dump(exclude_unset=True)
    is_channex = connection.provider == ChannelProvider.CHANNEX
    if is_channex and changes.get("outbound_url") is not None:
        raise UnprocessableError("A Channex connection pushes to the Channex API, not a URL")
    if not is_channex and "external_property_id" in changes:
        raise UnprocessableError("external_property_id is only used by Channex connections")
    if any(
        name in changes and changes[name] != getattr(connection, name)
        for name in ("outbound_url", "external_property_id")
    ):
        # The last result describes the old URL; it says nothing about the new one.
        connection.last_push_at = None
        connection.last_push_ok = None
        connection.last_push_detail = None
    apply_changes(connection, changes)
    await db.flush()
    return connection


async def _outbound_connection(db: DbSession, connection_id: UUID) -> ChannelConnection:
    connection = await get_or_404(db, ChannelConnection, connection_id)
    if connection.provider == ChannelProvider.GENERIC and connection.outbound_url is None:
        raise ConflictError("Set an outbound URL on this connection first")
    return connection


@router.post(
    "/{connection_id}/test-outbound", response_model=OutboundTestResult, dependencies=[_manage]
)
async def test_outbound(connection_id: UUID, db: DbSession) -> DeliveryResult | ChannexResponse:
    """Send a signed `ping` to the outbound URL now and report what came back.

    For a Channex connection, fetch the property from the Channex API instead,
    which proves the API key works and can see the property.

    Always answers 200; `ok` says whether the endpoint accepted the ping.
    """
    connection = await _outbound_connection(db, connection_id)
    if connection.provider == ChannelProvider.CHANNEX and connection.external_property_id:
        return await get_channex_client().get_property(connection.external_property_id)
    return await send_test_ping(connection)


@router.post(
    "/{connection_id}/sync",
    response_model=SyncQueued,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[_manage],
)
async def sync_now(connection_id: UUID, db: DbSession) -> SyncQueued:
    """Queue a push of every room type's availability for the coming weeks."""
    connection = await _outbound_connection(db, connection_id)
    if not connection.is_active:
        raise ConflictError("This connection is disabled")
    return SyncQueued(room_types_queued=await request_full_sync(db, connection))


async def _channex_connection(db: DbSession, connection_id: UUID) -> ChannelConnection:
    connection = await get_or_404(db, ChannelConnection, connection_id)
    if connection.provider != ChannelProvider.CHANNEX:
        raise ConflictError("Room type mappings apply to Channex connections only")
    return connection


@router.get(
    "/{connection_id}/channex-mappings",
    response_model=list[ChannexMappingRead],
    dependencies=[_manage],
)
async def list_channex_mappings(connection_id: UUID, db: DbSession) -> Sequence[ChannexRoomMapping]:
    await _channex_connection(db, connection_id)
    return (
        await db.scalars(
            select(ChannexRoomMapping)
            .where(ChannexRoomMapping.connection_id == connection_id)
            .order_by(ChannexRoomMapping.created_at, ChannexRoomMapping.id)
        )
    ).all()


@router.put(
    "/{connection_id}/channex-mappings",
    response_model=list[ChannexMappingRead],
    dependencies=[_manage],
)
async def replace_channex_mappings(
    connection_id: UUID, data: list[ChannexMappingItem], db: DbSession
) -> list[ChannexRoomMapping]:
    """Set which Channex room type (and rate plan) each room type is sold as.

    Replaces the whole list. Room types left out are not pushed to Channex,
    and Channex bookings for an unmapped Channex room type are refused. Use
    "Sync now" afterwards to send Channex the current availability.
    """
    connection = await _channex_connection(db, connection_id)
    for item in data:
        await get_or_404(db, RoomType, item.room_type_id)
    # Executed now, so the inserts below never collide with the rows they replace.
    await db.execute(
        delete(ChannexRoomMapping).where(ChannexRoomMapping.connection_id == connection.id)
    )
    mappings = [
        ChannexRoomMapping(
            hotel_id=connection.hotel_id, connection_id=connection.id, **item.model_dump()
        )
        for item in data
    ]
    db.add_all(mappings)
    await flush_or_conflict(db, "Each room type and each Channex room type can be mapped only once")
    return mappings


@router.get(
    "/events",
    response_model=list[ChannelWebhookEventRead],
    dependencies=[Depends(require_roles(*FRONT_OFFICE))],
)
async def list_events(
    db: DbSession,
    status_: Annotated[WebhookEventStatus | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Sequence[ChannelWebhookEvent]:
    """Webhook deliveries, newest first. Filter by `rejected` to find bookings that failed."""
    statement = (
        select(ChannelWebhookEvent)
        .order_by(ChannelWebhookEvent.received_at.desc(), ChannelWebhookEvent.id)
        .limit(limit)
        .offset(offset)
    )
    if status_ is not None:
        statement = statement.where(ChannelWebhookEvent.status == status_)
    return (await db.scalars(statement)).all()
