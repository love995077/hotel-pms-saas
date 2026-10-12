from typing import Annotated, Any

from fastapi import APIRouter, Query

from app.api.deps import LEDGER_CONTROL, CurrentUser, DbSession
from app.schemas.reports import (
    DashboardStatsRead,
    DayPerformanceRead,
    PerformanceRead,
    TodayPerformanceRead,
)
from app.services.reports import MAX_TREND_DAYS, DayPerformance, dashboard_performance, summarise

router = APIRouter(prefix="/reports", tags=["reports"])


def _figures(performance: DayPerformance, *, with_revenue: bool) -> dict[str, Any]:
    return {
        "rooms_available": performance.rooms_available,
        "rooms_sold": performance.rooms_sold,
        "occupancy_pct": performance.occupancy_pct,
        "room_revenue": performance.room_revenue if with_revenue else None,
        "other_revenue": performance.other_revenue if with_revenue else None,
        "adr": performance.adr if with_revenue else None,
        "revpar": performance.revpar if with_revenue else None,
    }


@router.get("/dashboard-stats", response_model=DashboardStatsRead)
async def dashboard_stats(
    db: DbSession,
    user: CurrentUser,
    days: Annotated[int, Query(ge=7, le=MAX_TREND_DAYS, description="Days of history")] = 30,
) -> DashboardStatsRead:
    """Occupancy, room revenue, ADR and RevPAR for today and the days before it.

    Every role sees occupancy. Revenue, ADR and RevPAR are returned only to
    owners, managers and accountants; for other roles those fields are null.
    """
    with_revenue = user.role in LEDGER_CONTROL
    today, trend = await dashboard_performance(db, days)
    return DashboardStatsRead(
        can_view_revenue=with_revenue,
        today=TodayPerformanceRead(
            date=today.day,
            is_projected=today.is_projected,
            **_figures(today, with_revenue=with_revenue),
        ),
        period=PerformanceRead(**_figures(summarise(trend), with_revenue=with_revenue)),
        trend=[
            DayPerformanceRead(date=day.day, **_figures(day, with_revenue=with_revenue))
            for day in trend
        ],
    )
