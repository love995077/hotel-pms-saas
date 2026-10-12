"""Celery worker and scheduled jobs.

    uv run celery -A app.worker worker --loglevel=info      (add --pool=solo on Windows)
    uv run celery -A app.worker beat --loglevel=info

The worker also delivers outbound availability pushes (`channel_sync.deliver`),
which the API queues whenever a reservation changes what can be sold.

Every hour, `night_audit.dispatch` looks at each hotel's local clock. Once it is
past the audit hour there, it queues the audit for the day that has just ended.
The audit task does nothing if that day has already been audited, so a missed
hour (worker or scheduler down) is caught up automatically on the next tick.
"""

import asyncio
import logging
from collections.abc import Coroutine
from datetime import date, datetime, timedelta
from typing import Any, TypeVar
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import select, text

from app.celery_app import celery_app
from app.config import get_settings
from app.database import engine, tenant_session
from app.models import NightAuditRun
from app.services.channel_sync import DELIVER_TASK, DeliveryFailed, deliver_availability
from app.services.night_audit import run_night_audit

logger = logging.getLogger(__name__)
settings = get_settings()
T = TypeVar("T")

__all__ = ["celery_app"]


def run_async(coroutine: Coroutine[Any, Any, T]) -> T:
    """Run a coroutine to completion from a synchronous Celery task.

    Pooled connections belong to the event loop that opened them, and each call
    gets a new loop, so the pool is emptied before the loop goes away.
    """

    async def runner() -> T:
        try:
            return await coroutine
        finally:
            await engine.dispose()

    return asyncio.run(runner())


async def _audit_hotel(hotel_id: UUID, business_date: date) -> dict[str, Any]:
    async with tenant_session(hotel_id) as session:
        already_run = await session.scalar(
            select(NightAuditRun.id).where(NightAuditRun.business_date == business_date)
        )
        if already_run is not None:
            return {
                "hotel_id": str(hotel_id),
                "business_date": business_date.isoformat(),
                "skipped": True,
            }
        run = await run_night_audit(session, business_date)
        return {
            "hotel_id": str(hotel_id),
            "business_date": business_date.isoformat(),
            "skipped": False,
            "room_charges_posted": run.room_charges_posted,
            "no_shows_marked": run.no_shows_marked,
            "room_revenue": str(run.room_revenue),
            "tax_amount": str(run.tax_amount),
        }


async def _hotels_due(now: datetime) -> list[tuple[UUID, date]]:
    """Hotels whose local time is past the audit hour, with the date to close."""
    async with engine.connect() as connection:
        rows = await connection.execute(text("SELECT hotel_id, timezone FROM list_active_hotels()"))
        hotels = rows.all()

    due = []
    for hotel_id, timezone in hotels:
        local = now.astimezone(ZoneInfo(timezone))
        if local.hour >= settings.night_audit_hour:
            due.append((hotel_id, local.date() - timedelta(days=1)))
    return due


@celery_app.task(
    name="night_audit.run_for_hotel",
    autoretry_for=(OSError,),
    retry_backoff=True,
    max_retries=3,
)
def run_night_audit_for_hotel(hotel_id: str, business_date: str) -> dict[str, Any]:
    result = run_async(_audit_hotel(UUID(hotel_id), date.fromisoformat(business_date)))
    logger.info("Night audit %s", result)
    return result


@celery_app.task(name="night_audit.dispatch")
def dispatch_night_audits() -> int:
    """Queue one audit task per hotel that is due. Returns how many were queued."""
    due = run_async(_hotels_due(datetime.now(ZoneInfo("UTC"))))
    for hotel_id, business_date in due:
        run_night_audit_for_hotel.delay(str(hotel_id), business_date.isoformat())
    return len(due)


@celery_app.task(
    name=DELIVER_TASK,
    # Network trouble and 5xx answers are retried for about two hours, with the
    # wait doubling from 30 seconds up to an hour between attempts.
    autoretry_for=(DeliveryFailed, OSError),
    retry_backoff=30,
    retry_backoff_max=3600,
    retry_jitter=True,
    max_retries=8,
)
def deliver_availability_task(
    hotel_id: str, connection_id: str, room_type_id: str, start: str, end: str
) -> dict[str, Any]:
    """Push one room type's availability to one channel connection."""
    result = run_async(
        deliver_availability(
            UUID(hotel_id),
            UUID(connection_id),
            UUID(room_type_id),
            date.fromisoformat(start),
            date.fromisoformat(end),
        )
    )
    outcome = {
        "connection_id": connection_id,
        "room_type_id": room_type_id,
        "start": start,
        "end": end,
        "skipped": result is None,
        "ok": result.ok if result else None,
        "detail": result.detail if result else None,
    }
    logger.info("Availability push %s", outcome)
    return outcome
