import asyncio
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import create_async_engine

from app.config import get_settings
from app.database import engine, tenant_session
from app.models import UserRole
from app.worker import dispatch_night_audits, run_night_audit_for_hotel
from tests.conftest import Inventory, Tenant, TenantFactory, create_inventory

API = "/api/v1"
TODAY = datetime.now(ZoneInfo("Asia/Kolkata")).date()


def day(offset: int) -> str:
    return (TODAY + timedelta(days=offset)).isoformat()


async def book(
    client: AsyncClient,
    tenant: Tenant,
    inventory: Inventory,
    check_in: str,
    check_out: str,
    **extra: Any,
) -> dict[str, Any]:
    response = await client.post(
        f"{API}/reservations",
        headers=tenant.headers,
        json={
            "guest_id": inventory.guest_id,
            "room_type_id": inventory.room_type_id,
            "check_in_date": check_in,
            "check_out_date": check_out,
            **extra,
        },
    )
    assert response.status_code == 201, response.text
    body: dict[str, Any] = response.json()
    return body


async def check_in(client: AsyncClient, tenant: Tenant, reservation_id: str, room_id: str) -> None:
    for path, payload in (("assign-room", {"room_id": room_id}), ("check-in", None)):
        response = await client.post(
            f"{API}/reservations/{reservation_id}/{path}", headers=tenant.headers, json=payload
        )
        assert response.status_code == 200, response.text


async def in_house_stay(
    client: AsyncClient, tenant: Tenant, inventory: Inventory, **extra: Any
) -> dict[str, Any]:
    """A stay that arrived two days ago, leaves in two days, and is checked in."""
    reservation = await book(client, tenant, inventory, day(-2), day(2), **extra)
    await check_in(client, tenant, reservation["id"], inventory.room_ids[0])
    return reservation


async def folio_of(client: AsyncClient, tenant: Tenant, reservation_id: str) -> dict[str, Any]:
    response = await client.get(
        f"{API}/folios", headers=tenant.headers, params={"reservation_id": reservation_id}
    )
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


async def audit(client: AsyncClient, tenant: Tenant, business_date: str) -> dict[str, Any]:
    response = await client.post(
        f"{API}/night-audit/run", headers=tenant.headers, json={"business_date": business_date}
    )
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


async def pay(client: AsyncClient, tenant: Tenant, folio_id: str, amount: str) -> dict[str, Any]:
    response = await client.post(
        f"{API}/folios/{folio_id}/payments",
        headers=tenant.headers,
        json={"amount": amount, "payment_method": "upi", "reference": "UPI-123"},
    )
    assert response.status_code == 201, response.text
    body: dict[str, Any] = response.json()
    return body


# --- folios -----------------------------------------------------------------


async def test_check_in_opens_an_empty_folio(
    client: AsyncClient, tenant: Tenant, inventory: Inventory
) -> None:
    reservation = await book(client, tenant, inventory, day(-2), day(2))
    missing = await client.get(
        f"{API}/folios", headers=tenant.headers, params={"reservation_id": reservation["id"]}
    )
    assert missing.status_code == 404

    await check_in(client, tenant, reservation["id"], inventory.room_ids[0])

    folio = await folio_of(client, tenant, reservation["id"])
    assert folio["status"] == "open"
    assert folio["balance"] == "0.00"
    assert folio["transactions"] == []


async def test_charges_and_payments_move_the_balance(
    client: AsyncClient, tenant: Tenant, inventory: Inventory
) -> None:
    reservation = await in_house_stay(client, tenant, inventory)
    folio = await folio_of(client, tenant, reservation["id"])

    charge = await client.post(
        f"{API}/folios/{folio['id']}/charges",
        headers=tenant.headers,
        json={"description": "Dinner", "amount": "1200.00", "gst_rate": "5", "sac_code": "996331"},
    )
    assert charge.status_code == 201, charge.text
    assert charge.json()["cgst_amount"] == "30.00"
    assert charge.json()["sgst_amount"] == "30.00"
    assert charge.json()["total_amount"] == "1260.00"
    assert charge.json()["entry_type"] == "debit"

    payment = await pay(client, tenant, folio["id"], "1000.00")
    assert payment["entry_type"] == "credit"
    assert payment["payment_method"] == "upi"

    folio = await folio_of(client, tenant, reservation["id"])
    assert folio["total_debits"] == "1260.00"
    assert folio["total_credits"] == "1000.00"
    assert folio["balance"] == "260.00"
    assert len(folio["transactions"]) == 2


async def test_reversal_adds_a_compensating_line_and_keeps_the_original(
    client: AsyncClient, tenant: Tenant, inventory: Inventory
) -> None:
    reservation = await in_house_stay(client, tenant, inventory)
    folio = await folio_of(client, tenant, reservation["id"])
    charge = (
        await client.post(
            f"{API}/folios/{folio['id']}/charges",
            headers=tenant.headers,
            json={"description": "Minibar", "amount": "500.00", "gst_rate": "18"},
        )
    ).json()
    reverse_url = f"{API}/folios/{folio['id']}/transactions/{charge['id']}/reverse"

    reversal = await client.post(
        reverse_url, headers=tenant.headers, json={"reason": "Posted to wrong room"}
    )
    assert reversal.status_code == 201, reversal.text
    body = reversal.json()
    assert body["entry_type"] == "credit"
    assert body["total_amount"] == charge["total_amount"]
    assert body["reverses_transaction_id"] == charge["id"]

    folio = await folio_of(client, tenant, reservation["id"])
    assert folio["balance"] == "0.00"
    original, mirror = folio["transactions"]
    assert original == charge  # untouched
    assert mirror["id"] == body["id"]

    # Not twice, and a reversal cannot itself be reversed.
    again = await client.post(reverse_url, headers=tenant.headers, json={"reason": "Again"})
    assert again.status_code == 409
    of_reversal = await client.post(
        f"{API}/folios/{folio['id']}/transactions/{body['id']}/reverse",
        headers=tenant.headers,
        json={"reason": "Undo the undo"},
    )
    assert of_reversal.status_code == 409


async def test_front_desk_cannot_reverse_ledger_lines(
    client: AsyncClient, make_tenant: TenantFactory
) -> None:
    front_desk = await make_tenant(UserRole.FRONT_DESK)
    response = await client.post(
        f"{API}/folios/00000000-0000-0000-0000-000000000000"
        "/transactions/00000000-0000-0000-0000-000000000000/reverse",
        headers=front_desk.headers,
        json={"reason": "Not allowed"},
    )
    assert response.status_code == 403


async def test_folio_is_invisible_to_another_hotel(
    client: AsyncClient, make_tenant: TenantFactory
) -> None:
    hotel_a = await make_tenant()
    hotel_b = await make_tenant()
    reservation = await in_house_stay(client, hotel_a, await create_inventory(client, hotel_a))
    folio = await folio_of(client, hotel_a, reservation["id"])

    assert (
        await client.get(f"{API}/folios/{folio['id']}", headers=hotel_b.headers)
    ).status_code == 404
    stolen = await client.post(
        f"{API}/folios/{folio['id']}/payments",
        headers=hotel_b.headers,
        json={"amount": "1.00", "payment_method": "cash"},
    )
    assert stolen.status_code == 404


# --- immutability -----------------------------------------------------------


async def test_ledger_lines_cannot_be_updated_or_deleted_by_the_application(
    client: AsyncClient, tenant: Tenant, inventory: Inventory
) -> None:
    reservation = await in_house_stay(client, tenant, inventory)
    folio = await folio_of(client, tenant, reservation["id"])
    await pay(client, tenant, folio["id"], "100.00")

    for statement in (
        "UPDATE folio_transactions SET amount = 1, total_amount = 1",
        "DELETE FROM folio_transactions",
        "TRUNCATE folio_transactions",
    ):
        with pytest.raises(DBAPIError, match="permission denied"):
            async with tenant_session(tenant.hotel_id) as session:
                await session.execute(text(statement))

    assert (await folio_of(client, tenant, reservation["id"]))["total_credits"] == "100.00"


async def test_ledger_lines_cannot_be_changed_even_by_the_database_owner(
    client: AsyncClient, tenant: Tenant, inventory: Inventory
) -> None:
    reservation = await in_house_stay(client, tenant, inventory)
    folio = await folio_of(client, tenant, reservation["id"])
    await pay(client, tenant, folio["id"], "100.00")

    owner_engine = create_async_engine(get_settings().migration_database_url)
    try:
        for statement in (
            "UPDATE folio_transactions SET amount = 1, total_amount = 1 WHERE hotel_id = :id",
            "DELETE FROM folio_transactions WHERE hotel_id = :id",
        ):
            with pytest.raises(DBAPIError, match="append-only"):
                async with owner_engine.begin() as connection:
                    await connection.execute(text(statement), {"id": tenant.hotel_id})
        with pytest.raises(DBAPIError, match="append-only"):
            async with owner_engine.begin() as connection:
                await connection.execute(text("TRUNCATE folio_transactions"))
    finally:
        await owner_engine.dispose()

    assert (await folio_of(client, tenant, reservation["id"]))["total_credits"] == "100.00"


# --- night audit ------------------------------------------------------------


async def test_night_audit_posts_room_charge_with_gst(
    client: AsyncClient, tenant: Tenant, inventory: Inventory
) -> None:
    reservation = await in_house_stay(client, tenant, inventory)  # Rs 4,500 -> 5% slab

    run = await audit(client, tenant, day(-1))

    assert run["business_date"] == day(-1)
    assert run["room_charges_posted"] == 1
    assert run["room_revenue"] == "4500.00"
    assert run["tax_amount"] == "225.00"

    folio = await folio_of(client, tenant, reservation["id"])
    (charge,) = folio["transactions"]
    assert charge["category"] == "room_charge"
    assert charge["entry_type"] == "debit"
    assert charge["business_date"] == day(-1)
    assert charge["amount"] == "4500.00"
    assert charge["gst_rate"] == "5.00"
    assert charge["cgst_amount"] == "112.50"
    assert charge["sgst_amount"] == "112.50"
    assert charge["total_amount"] == "4725.00"
    assert charge["sac_code"] == "996311"
    assert charge["created_by"] is not None
    assert folio["balance"] == "4725.00"


@pytest.mark.parametrize(
    ("rate", "gst_rate", "total"),
    [
        ("900.00", "0.00", "900.00"),
        ("7500.00", "5.00", "7875.00"),
        ("9000.00", "18.00", "10620.00"),
    ],
)
async def test_night_audit_applies_the_slab_of_the_reservation_rate(
    client: AsyncClient, tenant: Tenant, inventory: Inventory, rate: str, gst_rate: str, total: str
) -> None:
    reservation = await in_house_stay(client, tenant, inventory, rate_per_night=rate)
    await audit(client, tenant, day(-1))
    (charge,) = (await folio_of(client, tenant, reservation["id"]))["transactions"]
    assert charge["gst_rate"] == gst_rate
    assert charge["total_amount"] == total


async def test_night_audit_is_idempotent(
    client: AsyncClient, tenant: Tenant, inventory: Inventory
) -> None:
    reservation = await in_house_stay(client, tenant, inventory)

    first = await audit(client, tenant, day(-1))
    second = await audit(client, tenant, day(-1))

    assert first["room_charges_posted"] == 1
    # Same run record, nothing new posted.
    assert second["id"] == first["id"]
    assert second["room_charges_posted"] == 1
    assert len((await folio_of(client, tenant, reservation["id"]))["transactions"]) == 1

    # A different night is a separate charge.
    await audit(client, tenant, day(-2))
    assert len((await folio_of(client, tenant, reservation["id"]))["transactions"]) == 2


async def test_night_audit_only_charges_stays_in_house_that_night(
    client: AsyncClient, tenant: Tenant
) -> None:
    inventory = await create_inventory(client, tenant, rooms=3)
    # Leaves on the audit date: that night is not theirs.
    departing = await book(client, tenant, inventory, day(-3), day(-1))
    await check_in(client, tenant, departing["id"], inventory.room_ids[0])
    # Arrives tomorrow.
    await book(client, tenant, inventory, day(1), day(3))

    run = await audit(client, tenant, day(-1))

    assert run["room_charges_posted"] == 0
    assert (await folio_of(client, tenant, departing["id"]))["transactions"] == []


async def test_night_audit_marks_no_shows_and_releases_inventory(
    client: AsyncClient, tenant: Tenant
) -> None:
    inventory = await create_inventory(client, tenant, rooms=1)
    missed = await book(client, tenant, inventory, day(-1), day(2))
    future = await book(client, tenant, inventory, day(5), day(6))

    run = await audit(client, tenant, day(-1))

    assert run["no_shows_marked"] == 1
    assert run["room_charges_posted"] == 0
    statuses = {
        r["id"]: r["status"]
        for r in (await client.get(f"{API}/reservations", headers=tenant.headers)).json()
    }
    assert statuses == {missed["id"]: "no_show", future["id"]: "confirmed"}

    # The only room is sellable again for those nights.
    rebooked = await client.post(
        f"{API}/reservations",
        headers=tenant.headers,
        json={
            "guest_id": inventory.guest_id,
            "room_type_id": inventory.room_type_id,
            "check_in_date": day(0),
            "check_out_date": day(2),
        },
    )
    assert rebooked.status_code == 201, rebooked.text


async def test_night_audit_rejects_future_dates_and_unauthorised_roles(
    client: AsyncClient, make_tenant: TenantFactory
) -> None:
    owner = await make_tenant()
    front_desk = await make_tenant(UserRole.FRONT_DESK)

    future = await client.post(
        f"{API}/night-audit/run", headers=owner.headers, json={"business_date": day(1)}
    )
    forbidden = await client.post(f"{API}/night-audit/run", headers=front_desk.headers, json={})

    assert future.status_code == 422
    assert forbidden.status_code == 403


async def test_night_audit_does_not_touch_other_hotels(
    client: AsyncClient, make_tenant: TenantFactory
) -> None:
    hotel_a = await make_tenant()
    hotel_b = await make_tenant()
    stay_a = await in_house_stay(client, hotel_a, await create_inventory(client, hotel_a))
    stay_b = await in_house_stay(client, hotel_b, await create_inventory(client, hotel_b))

    await audit(client, hotel_a, day(-1))

    assert len((await folio_of(client, hotel_a, stay_a["id"]))["transactions"]) == 1
    assert (await folio_of(client, hotel_b, stay_b["id"]))["transactions"] == []
    assert (await client.get(f"{API}/night-audit/runs", headers=hotel_b.headers)).json() == []


# --- check-out --------------------------------------------------------------


async def test_check_out_requires_a_settled_folio_and_closes_it(
    client: AsyncClient, tenant: Tenant, inventory: Inventory
) -> None:
    reservation = await in_house_stay(client, tenant, inventory)
    await audit(client, tenant, day(-1))
    folio = await folio_of(client, tenant, reservation["id"])
    check_out_url = f"{API}/reservations/{reservation['id']}/check-out"

    unpaid = await client.post(check_out_url, headers=tenant.headers)
    assert unpaid.status_code == 409
    assert "4725.00" in unpaid.json()["detail"]

    await pay(client, tenant, folio["id"], "4725.00")
    paid = await client.post(check_out_url, headers=tenant.headers)
    assert paid.status_code == 200, paid.text
    assert paid.json()["status"] == "checked_out"

    folio = await folio_of(client, tenant, reservation["id"])
    assert folio["status"] == "closed"
    assert folio["closed_at"] is not None

    late = await client.post(
        f"{API}/folios/{folio['id']}/charges",
        headers=tenant.headers,
        json={"description": "Late minibar", "amount": "100.00"},
    )
    assert late.status_code == 409


# --- celery -----------------------------------------------------------------


async def test_celery_task_runs_the_audit_and_skips_when_already_done(
    client: AsyncClient, tenant: Tenant, inventory: Inventory
) -> None:
    reservation = await in_house_stay(client, tenant, inventory)
    # The task runs on its own event loop; do not hand it this loop's connections.
    await engine.dispose()

    def run_task() -> dict[str, Any]:
        result: dict[str, Any] = run_night_audit_for_hotel.apply(
            args=(str(tenant.hotel_id), day(-1))
        ).get()
        return result

    first = await asyncio.to_thread(run_task)
    second = await asyncio.to_thread(run_task)

    assert first["skipped"] is False
    assert first["room_charges_posted"] == 1
    assert first["room_revenue"] == "4500.00"
    assert second["skipped"] is True
    assert len((await folio_of(client, tenant, reservation["id"]))["transactions"]) == 1
    # System postings carry no user.
    (charge,) = (await folio_of(client, tenant, reservation["id"]))["transactions"]
    assert charge["created_by"] is None


async def test_dispatcher_queues_an_audit_for_each_hotel_past_its_audit_hour(
    tenant: Tenant, monkeypatch: pytest.MonkeyPatch
) -> None:
    queued: list[tuple[str, str]] = []
    monkeypatch.setattr(
        run_night_audit_for_hotel, "delay", lambda hotel_id, when: queued.append((hotel_id, when))
    )
    monkeypatch.setattr("app.worker.settings.night_audit_hour", 0)
    await engine.dispose()

    count = await asyncio.to_thread(dispatch_night_audits)

    assert count == len(queued) >= 1
    assert (str(tenant.hotel_id), date.fromisoformat(day(-1)).isoformat()) in queued
