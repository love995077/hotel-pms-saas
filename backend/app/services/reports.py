"""Hotel performance figures for the dashboard.

Definitions, for one night:

    rooms available  active rooms of active room types (as they stand today:
                     the history of the room count is not recorded)
    rooms sold       stays occupying the night
    occupancy        rooms sold / rooms available
    room revenue     room charges before GST
    ADR              room revenue / rooms sold        (average daily rate)
    RevPAR           room revenue / rooms available   (revenue per available room)

Past nights are counted from what happened: stays that were in house, and the
room charges the night audit posted. Tonight is counted from what is on the
books: confirmed and in-house stays at their booked rates, until the audit for
today has run and there are posted charges to use instead.
"""

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sqlalchemy import Date, Integer, and_, case, column, func, literal, or_, select, true
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.models import (
    EntryType,
    FolioTransaction,
    NightAuditRun,
    Reservation,
    ReservationStatus,
    Room,
    RoomType,
    TransactionCategory,
)
from app.services.folios import hotel_today

MAX_TREND_DAYS = 90
_ZERO = Decimal("0.00")
_PAISA = Decimal("0.01")
_TENTH = Decimal("0.1")

# A past night was occupied by stays that actually arrived.
_STAYED = (ReservationStatus.CHECKED_IN, ReservationStatus.CHECKED_OUT)
# Tonight also counts guests still expected to arrive.
_ON_THE_BOOKS = (ReservationStatus.CONFIRMED, ReservationStatus.CHECKED_IN)


@dataclass(frozen=True, slots=True)
class DayPerformance:
    day: date
    rooms_available: int
    rooms_sold: int
    room_revenue: Decimal
    other_revenue: Decimal
    # True when the revenue is what is booked, not yet what has been charged.
    is_projected: bool = False

    @property
    def occupancy_pct(self) -> Decimal:
        return _ratio(Decimal(self.rooms_sold) * 100, self.rooms_available, _TENTH)

    @property
    def adr(self) -> Decimal:
        return _ratio(self.room_revenue, self.rooms_sold, _PAISA)

    @property
    def revpar(self) -> Decimal:
        return _ratio(self.room_revenue, self.rooms_available, _PAISA)


def _ratio(numerator: Decimal, denominator: int, quantum: Decimal) -> Decimal:
    if denominator <= 0:
        return Decimal(0).quantize(quantum)
    return (numerator / denominator).quantize(quantum, rounding=ROUND_HALF_UP)


def summarise(days: list[DayPerformance]) -> DayPerformance:
    """Roll several days into one: totals, so its ratios are properly weighted."""
    return DayPerformance(
        day=days[-1].day,
        rooms_available=sum(day.rooms_available for day in days),
        rooms_sold=sum(day.rooms_sold for day in days),
        room_revenue=sum((day.room_revenue for day in days), _ZERO),
        other_revenue=sum((day.other_revenue for day in days), _ZERO),
    )


async def _rooms_available(session: AsyncSession) -> int:
    count = await session.scalar(
        select(func.count())
        .select_from(Room)
        .join(RoomType, RoomType.id == Room.room_type_id)
        .where(Room.is_active, RoomType.is_active)
    )
    return count or 0


async def _rooms_sold(session: AsyncSession, start: date, today: date) -> dict[date, int]:
    """Stays occupying each night from `start` to today, in one query."""
    nights = (today - start).days + 1
    offsets = (
        func.generate_series(0, nights - 1)
        .table_valued(column("n", Integer), name="offsets")
        .render_derived()
    )
    night = literal(start, Date) + offsets.c.n
    occupies = and_(
        Reservation.check_in_date <= night,
        Reservation.check_out_date > night,
        or_(
            and_(night < today, Reservation.status.in_(_STAYED)),
            and_(night == today, Reservation.status.in_(_ON_THE_BOOKS)),
        ),
    )
    rows = await session.execute(
        select(offsets.c.n, func.count(Reservation.id))
        .select_from(offsets)
        .outerjoin(Reservation, occupies)
        .group_by(offsets.c.n)
    )
    return {start + timedelta(days=offset): sold for offset, sold in rows}


async def _posted_revenue(
    session: AsyncSession, start: date, today: date
) -> dict[date, dict[str, Decimal]]:
    """Charges before GST per business date, split into room and other.

    A reversal is taken off the day of the charge it reverses, not the day the
    reversal was entered, so a correction made later still fixes the right day.
    """
    original = aliased(FolioTransaction)
    day = func.coalesce(original.business_date, FolioTransaction.business_date)
    signed = case(
        (FolioTransaction.entry_type == EntryType.DEBIT, FolioTransaction.amount),
        else_=-FolioTransaction.amount,
    )
    rows = await session.execute(
        select(day, FolioTransaction.category, func.sum(signed))
        .outerjoin(original, original.id == FolioTransaction.reverses_transaction_id)
        .where(
            FolioTransaction.category != TransactionCategory.PAYMENT,
            day >= start,
            day <= today,
        )
        .group_by(day, FolioTransaction.category)
    )
    revenue: dict[date, dict[str, Decimal]] = {}
    for business_date, category, amount in rows:
        revenue.setdefault(business_date, {})[category] = Decimal(amount)
    return revenue


async def _booked_tonight(session: AsyncSession, today: date) -> Decimal:
    """What tonight's occupied rooms will be charged, at their booked rates."""
    total = await session.scalar(
        select(func.coalesce(func.sum(Reservation.rate_per_night), 0)).where(
            Reservation.check_in_date <= today,
            Reservation.check_out_date > today,
            Reservation.status.in_(_ON_THE_BOOKS),
        )
    )
    return Decimal(total or 0).quantize(_PAISA)


async def dashboard_performance(
    session: AsyncSession, days: int
) -> tuple[DayPerformance, list[DayPerformance]]:
    """Today's figures, and one entry for each of the `days` days before today."""
    today = await hotel_today(session)
    start = today - timedelta(days=days)

    rooms = await _rooms_available(session)
    sold = await _rooms_sold(session, start, today)
    revenue = await _posted_revenue(session, start, today)

    def performance(day: date, **overrides: Any) -> DayPerformance:
        posted = revenue.get(day, {})
        values: dict[str, Any] = {
            "day": day,
            "rooms_available": rooms,
            "rooms_sold": sold.get(day, 0),
            "room_revenue": posted.get(TransactionCategory.ROOM_CHARGE, _ZERO),
            "other_revenue": posted.get(TransactionCategory.EXTRA_CHARGE, _ZERO),
        }
        return DayPerformance(**{**values, **overrides})

    trend = [performance(start + timedelta(days=offset)) for offset in range(days)]

    audited_today = await session.scalar(
        select(true()).where(NightAuditRun.business_date == today).limit(1)
    )
    if audited_today:
        current = performance(today)
    else:
        current = performance(
            today, room_revenue=await _booked_tonight(session, today), is_projected=True
        )
    return current, trend
