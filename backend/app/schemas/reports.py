from datetime import date
from decimal import Decimal

from pydantic import BaseModel


class PerformanceRead(BaseModel):
    """Occupancy for everyone; money only for roles allowed to see it (else null)."""

    rooms_available: int
    rooms_sold: int
    occupancy_pct: Decimal
    # Room charges before GST.
    room_revenue: Decimal | None
    # Extras (food, laundry, ...) before GST.
    other_revenue: Decimal | None
    # Average daily rate: room revenue per room sold.
    adr: Decimal | None
    # Room revenue per available room.
    revpar: Decimal | None


class DayPerformanceRead(PerformanceRead):
    date: date


class TodayPerformanceRead(DayPerformanceRead):
    # True until tonight's audit posts the charges: revenue is then the booked
    # rate of the rooms occupied tonight, not yet a ledger figure.
    is_projected: bool


class DashboardStatsRead(BaseModel):
    can_view_revenue: bool
    today: TodayPerformanceRead
    # The days before today taken together (ratios are weighted, not averaged).
    period: PerformanceRead
    # One entry per day, oldest first, ending yesterday.
    trend: list[DayPerformanceRead]
