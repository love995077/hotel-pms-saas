import secrets
from collections.abc import Sequence
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select

from app.api.deps import FRONT_OFFICE, MANAGEMENT, DbSession, get_current_user, require_roles
from app.core.exceptions import ConflictError
from app.database import current_hotel_id
from app.models import ChannelConnection, ChannelWebhookEvent, WebhookEventStatus
from app.schemas.channel import (
    ChannelConnectionCreate,
    ChannelConnectionCreated,
    ChannelConnectionRead,
    ChannelConnectionUpdate,
    ChannelWebhookEventRead,
    OutboundTestResult,
    SyncQueued,
)
from app.services.channel_sync import DeliveryResult, request_full_sync, send_test_ping
from app.services.crud import apply_changes, get_or_404

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
    """Issue webhook credentials. The signing secret is shown only in this response."""
    connection = ChannelConnection(
        hotel_id=current_hotel_id(db),
        name=data.name,
        key_id="ck_" + secrets.token_hex(16),
        signing_secret=secrets.token_urlsafe(48),
    )
    db.add(connection)
    await db.flush()
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
    if "outbound_url" in changes and changes["outbound_url"] != connection.outbound_url:
        # The last result describes the old URL; it says nothing about the new one.
        connection.last_push_at = None
        connection.last_push_ok = None
        connection.last_push_detail = None
    apply_changes(connection, changes)
    await db.flush()
    return connection


async def _outbound_connection(db: DbSession, connection_id: UUID) -> ChannelConnection:
    connection = await get_or_404(db, ChannelConnection, connection_id)
    if connection.outbound_url is None:
        raise ConflictError("Set an outbound URL on this connection first")
    return connection


@router.post(
    "/{connection_id}/test-outbound", response_model=OutboundTestResult, dependencies=[_manage]
)
async def test_outbound(connection_id: UUID, db: DbSession) -> DeliveryResult:
    """Send a signed `ping` to the outbound URL now and report what came back.

    Always answers 200; `ok` says whether the endpoint accepted the ping.
    """
    return await send_test_ping(await _outbound_connection(db, connection_id))


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
