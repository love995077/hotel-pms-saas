"""Dashboard KPIs: occupancy, room revenue, ADR and RevPAR for today and the days before."""

from datetime import date, timedelta
from typing import Any

from httpx import AsyncClient

from app.models import UserRole
from tests.conftest import Inventory, Tenant, TenantFactory, create_inventory

API = "/api/v1"
TODAY = date.today()


def day(offset: int) -> str:
    return (TODAY + timedelta(days=offset)).isoformat()


async def post(client: AsyncClient, tenant: Tenant, path: str, **body: Any) -> Any:
    response = await client.post(f"{API}{path}", headers=tenant.headers, json=body or None)
    assert response.status_code < 300, (path, response.status_code, response.text)
    return response.json()


async def stats(client: AsyncClient, tenant: Tenant, **params: Any) -> dict[str, Any]:
    response = await client.get(
        f"{API}/reports/dashboard-stats", headers=tenant.headers, params=params
    )
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


async def stay(
    client: AsyncClient,
    tenant: Tenant,
    inventory: Inventory,
    arrive: int,
    leave: int,
    *,
    room: int | None = 0,
    rate: str | None = None,
) -> dict[str, Any]:
    """Book a stay from `arrive` to `leave` days from today; check it in if given a room."""
    reservation: dict[str, Any] = await post(
        client,
        tenant,
        "/reservations",
        guest_id=inventory.guest_id,
        room_type_id=inventory.room_type_id,
        room_id=inventory.room_ids[room] if room is not None else None,
        check_in_date=day(arrive),
        check_out_date=day(leave),
        **({"rate_per_night": rate} if rate else {}),
    )
    if room is not None:
        await post(client, tenant, f"/reservations/{reservation['id']}/check-in")
    return reservation


async def audit(client: AsyncClient, tenant: Tenant, *offsets: int) -> None:
    for offset in offsets:
        await post(client, tenant, "/night-audit/run", business_date=day(offset))


def by_date(body: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {entry["date"]: entry for entry in body["trend"]}


async def test_empty_hotel_reports_zeros_for_every_day(client: AsyncClient, tenant: Tenant) -> None:
    body = await stats(client, tenant)

    assert body["can_view_revenue"] is True
    assert [entry["date"] for entry in body["trend"]] == [day(n) for n in range(-30, 0)]
    assert body["today"]["date"] == day(0)
    assert body["today"]["rooms_available"] == 0
    # No rooms: every ratio is zero, not a division error.
    for figures in (body["today"], body["period"], *body["trend"]):
        assert figures["occupancy_pct"] == "0.0"
        assert figures["room_revenue"] == "0.00"
        assert figures["adr"] == "0.00" and figures["revpar"] == "0.00"


async def test_past_days_come_from_posted_charges_and_actual_stays(
    client: AsyncClient, tenant: Tenant, inventory: Inventory
) -> None:
    await stay(client, tenant, inventory, -3, 1)  # in house for the last three nights and tonight
    await audit(client, tenant, -3, -2, -1)

    body = await stats(client, tenant)
    trend = by_date(body)

    for offset in (-3, -2, -1):
        night = trend[day(offset)]
        assert (night["rooms_sold"], night["rooms_available"]) == (1, 2)
        assert night["occupancy_pct"] == "50.0"
        assert night["room_revenue"] == "4500.00"  # before GST
        assert night["adr"] == "4500.00"
        assert night["revpar"] == "2250.00"
    assert trend[day(-4)]["rooms_sold"] == 0 and trend[day(-4)]["room_revenue"] == "0.00"

    # The period is the 30 days taken together: 3 room-nights sold out of 60.
    period = body["period"]
    assert (period["rooms_sold"], period["rooms_available"]) == (3, 60)
    assert period["occupancy_pct"] == "5.0"
    assert period["room_revenue"] == "13500.00"
    assert period["adr"] == "4500.00"
    assert period["revpar"] == "225.00"


async def test_today_is_projected_from_bookings_until_the_audit_runs(
    client: AsyncClient, tenant: Tenant, inventory: Inventory
) -> None:
    await stay(client, tenant, inventory, 0, 2, room=0)  # in house
    await stay(client, tenant, inventory, 0, 1, room=None, rate="6000.00")  # still to arrive

    today = (await stats(client, tenant))["today"]
    assert today["is_projected"] is True
    assert (today["rooms_sold"], today["rooms_available"]) == (2, 2)
    assert today["occupancy_pct"] == "100.0"
    assert today["room_revenue"] == "10500.00"  # 4,500 + 6,000 at booked rates
    assert today["adr"] == "5250.00"
    assert today["revpar"] == "5250.00"

    # The audit charges the in-house stay and marks the other a no-show.
    await audit(client, tenant, 0)
    today = (await stats(client, tenant))["today"]
    assert today["is_projected"] is False
    assert today["rooms_sold"] == 1
    assert today["room_revenue"] == "4500.00"
    assert today["occupancy_pct"] == "50.0"


async def test_cancelled_and_no_show_stays_do_not_count_as_sold(
    client: AsyncClient, tenant: Tenant, inventory: Inventory
) -> None:
    cancelled = await stay(client, tenant, inventory, 0, 2, room=None)
    await post(client, tenant, f"/reservations/{cancelled['id']}/cancel")
    await stay(client, tenant, inventory, -2, 0, room=None)  # never arrived
    await audit(client, tenant, -2)  # marks it a no-show

    body = await stats(client, tenant)
    assert body["today"]["rooms_sold"] == 0
    assert by_date(body)[day(-2)]["rooms_sold"] == 0
    assert by_date(body)[day(-1)]["rooms_sold"] == 0


async def test_a_checked_out_stay_still_counts_for_the_nights_it_was_in_house(
    client: AsyncClient, tenant: Tenant, inventory: Inventory
) -> None:
    reservation = await stay(client, tenant, inventory, -2, 0)
    await audit(client, tenant, -2, -1)
    folio = (
        await client.get(
            f"{API}/folios", headers=tenant.headers, params={"reservation_id": reservation["id"]}
        )
    ).json()
    await post(
        client,
        tenant,
        f"/folios/{folio['id']}/payments",
        amount=folio["balance"],
        payment_method="cash",
    )
    await post(client, tenant, f"/reservations/{reservation['id']}/check-out")

    body = await stats(client, tenant)
    assert by_date(body)[day(-2)]["rooms_sold"] == 1
    assert by_date(body)[day(-1)]["rooms_sold"] == 1
    assert body["today"]["rooms_sold"] == 0  # departed this morning


async def test_extras_are_reported_apart_and_reversals_correct_the_original_day(
    client: AsyncClient, tenant: Tenant, inventory: Inventory
) -> None:
    reservation = await stay(client, tenant, inventory, -2, 1)
    await audit(client, tenant, -2, -1)
    folio = (
        await client.get(
            f"{API}/folios", headers=tenant.headers, params={"reservation_id": reservation["id"]}
        )
    ).json()
    charges = f"/folios/{folio['id']}/charges"
    await post(
        client, tenant, charges, description="Dinner", amount="1200.00", gst_rate="5",
        business_date=day(-2),
    )  # fmt: skip
    wrong = await post(
        client, tenant, charges, description="Minibar", amount="800.00", gst_rate="18",
        business_date=day(-1),
    )  # fmt: skip
    # Entered today, but it corrects yesterday's figures.
    await post(
        client,
        tenant,
        f"/folios/{folio['id']}/transactions/{wrong['id']}/reverse",
        reason="Posted to the wrong room",
    )
    room_charge = next(t for t in folio["transactions"] if t["business_date"] == day(-1))
    await post(
        client,
        tenant,
        f"/folios/{folio['id']}/transactions/{room_charge['id']}/reverse",
        reason="Complimentary night",
    )

    body = await stats(client, tenant)
    trend = by_date(body)
    assert trend[day(-2)]["room_revenue"] == "4500.00"
    assert trend[day(-2)]["other_revenue"] == "1200.00"  # before GST, not in ADR or RevPAR
    assert trend[day(-2)]["adr"] == "4500.00"
    assert trend[day(-1)]["other_revenue"] == "0.00"
    assert trend[day(-1)]["room_revenue"] == "0.00"
    assert body["today"]["other_revenue"] == "0.00"  # the reversals did not land on today


async def test_money_is_hidden_from_roles_without_ledger_access(
    client: AsyncClient, make_tenant: TenantFactory
) -> None:
    for role, sees_money in (
        (UserRole.ACCOUNTANT, True),
        (UserRole.MANAGER, True),
        (UserRole.FRONT_DESK, False),
        (UserRole.HOUSEKEEPING, False),
    ):
        body = await stats(client, await make_tenant(role))
        assert body["can_view_revenue"] is sees_money, role
        for figures in (body["today"], body["period"], body["trend"][0]):
            assert figures["occupancy_pct"] == "0.0"  # everyone sees occupancy
            for field in ("room_revenue", "other_revenue", "adr", "revpar"):
                assert (figures[field] is not None) is sees_money, (role, field)


async def test_figures_are_per_hotel_and_the_window_is_bounded(
    client: AsyncClient, make_tenant: TenantFactory
) -> None:
    busy = await make_tenant()
    quiet = await make_tenant()
    await stay(client, busy, await create_inventory(client, busy), -1, 1)
    await audit(client, busy, -1)
    await create_inventory(client, quiet)

    assert (await stats(client, busy))["period"]["room_revenue"] == "4500.00"
    other = await stats(client, quiet)
    assert other["period"]["room_revenue"] == "0.00" and other["today"]["rooms_sold"] == 0

    assert len((await stats(client, busy, days=7))["trend"]) == 7
    for days in (6, 91):
        refused = await client.get(
            f"{API}/reports/dashboard-stats", headers=busy.headers, params={"days": days}
        )
        assert refused.status_code == 422
    assert (await client.get(f"{API}/reports/dashboard-stats")).status_code == 401
