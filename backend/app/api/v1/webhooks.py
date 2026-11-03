import json
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response, status

from app.schemas.channel import ChannelEvent, WebhookResult
from app.schemas.channex import ChannexReservationRef, ChannexWebhook, ChannexWebhookResult
from app.services.channel_manager import ChannelContext, authenticate_webhook, handle_event
from app.services.channex.bookings import (
    ChannexContext,
    authenticate_channex_webhook,
    handle_webhook,
)

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


async def verify_channel_signature(
    request: Request,
    x_channel_key: Annotated[str | None, Header()] = None,
    x_channel_timestamp: Annotated[str | None, Header()] = None,
    x_channel_signature: Annotated[str | None, Header()] = None,
) -> ChannelContext:
    """Authenticate the sender before anything in the body is trusted.

    The hotel is taken from the connection the key belongs to, never from the
    payload, so a sender can only ever create bookings in its own hotel.
    """
    context = None
    if x_channel_key and x_channel_timestamp and x_channel_signature:
        context = await authenticate_webhook(
            x_channel_key, x_channel_timestamp, x_channel_signature, await request.body()
        )
    if context is None:
        # One answer for every failure: no hint about which part was wrong.
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid webhook signature")
    return context


@router.post(
    "/channel-manager",
    response_model=WebhookResult,
    status_code=status.HTTP_201_CREATED,
    responses={
        200: {"model": WebhookResult, "description": "Cancelled, or already applied earlier"},
        401: {"description": "Missing, invalid or expired signature"},
        404: {"description": "Cancellation for a booking that does not exist"},
        409: {"description": "No availability for the requested stay"},
        422: {"description": "Malformed payload or unknown room type code"},
    },
)
async def channel_manager_webhook(
    event: ChannelEvent,
    response: Response,
    context: Annotated[ChannelContext, Depends(verify_channel_signature)],
) -> WebhookResult:
    """Receive a booking event from a channel manager.

    Send three headers with the JSON body:

    - `X-Channel-Key`: the connection's key id
    - `X-Channel-Timestamp`: Unix time in seconds
    - `X-Channel-Signature`: `sha256=` + hex HMAC-SHA256 of `<timestamp>.<raw body>`
      using the connection's signing secret

    Deliveries are idempotent on `channel` + `booking_id`: resending an event
    returns 200 with the original reservation and changes nothing. Retry on 5xx;
    do not retry 4xx.
    """
    outcome = await handle_event(context, event)
    if outcome.result != "created":
        response.status_code = status.HTTP_200_OK
    return WebhookResult(
        result=outcome.result,
        reservation_id=outcome.reservation.id,
        confirmation_number=outcome.reservation.confirmation_number,
        reservation_status=outcome.reservation.status,
    )


async def verify_channex_token(
    x_channex_key: Annotated[str | None, Header()] = None,
    x_channex_token: Annotated[str | None, Header()] = None,
) -> ChannexContext:
    """The Channex webhook is configured with two custom headers: the
    connection's key id and its secret."""
    context = None
    if x_channex_key and x_channex_token:
        context = await authenticate_channex_webhook(x_channex_key, x_channex_token)
    if context is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid webhook credentials")
    return context


@router.post(
    "/channex",
    response_model=ChannexWebhookResult,
    # The body is read by hand, after authentication, so that a delivery in a
    # shape we did not expect is logged instead of vanishing as a bare 422.
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {"application/json": {"schema": ChannexWebhook.model_json_schema()}},
        }
    },
    responses={
        401: {"description": "Missing or wrong X-Channex-Key / X-Channex-Token"},
        409: {"description": "No availability, or the booking is already in house"},
        422: {
            "description": "Not a webhook body, malformed revision, unmapped room type "
            "or another property"
        },
        503: {"description": "The revision had to be fetched and Channex was unreachable"},
    },
)
async def channex_webhook(
    request: Request,
    context: Annotated[ChannexContext, Depends(verify_channex_token)],
) -> ChannexWebhookResult:
    """Receive a Channex.io webhook and apply booking revisions as reservations.

    Configure the webhook in Channex with this URL, event mask `booking`, "send
    data" on, and two custom headers from the Channex connection in Settings:

    - `X-Channex-Key`: the connection's key id
    - `X-Channex-Token`: the connection's secret

    A revision is applied as the booking's whole state, so redeliveries are
    harmless. Each room becomes one reservation. Non-booking events (such as
    Channex's test message) are answered 200 with `result: "ignored"`. Every
    authenticated delivery is listed under Settings > Channex. Applied
    revisions are acknowledged to Channex in the background.
    """
    raw = await request.body()
    try:
        body: Any = json.loads(raw)
    except ValueError:
        body = raw.decode("utf-8", errors="replace")[:2000]
    outcome = await handle_webhook(context, body)
    return ChannexWebhookResult(
        result=outcome.result,
        booking_id=outcome.revision.booking_id if outcome.revision else None,
        revision_id=outcome.revision.id if outcome.revision else None,
        reservations=[
            ChannexReservationRef(
                reservation_id=r.id, confirmation_number=r.confirmation_number, status=r.status
            )
            for r in outcome.reservations
        ],
    )
