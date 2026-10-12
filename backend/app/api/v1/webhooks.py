from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response, status

from app.schemas.channel import ChannelEvent, WebhookResult
from app.services.channel_manager import ChannelContext, authenticate_webhook, handle_event

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
