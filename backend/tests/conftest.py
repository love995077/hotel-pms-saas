"""Shared fixtures. Tests run against the migrated docker-compose database."""

from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from typing import Any
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.config import get_settings
from app.core.security import hash_password
from app.database import engine, tenant_session
from app.main import app
from app.models import Hotel, User, UserRole

PASSWORD = "correct-horse-battery"  # noqa: S105
_TENANT_TABLES = (
    "channel_webhook_events",
    "channel_connections",
    "night_audit_runs",
    "invoice_sequences",
    "folio_transactions",
    "folios",
    "reservations",
    "guests",
    "rooms",
    "room_types",
    "users",
)


@dataclass(frozen=True)
class Tenant:
    hotel_id: UUID
    slug: str
    email: str
    headers: dict[str, str]


@dataclass(frozen=True)
class Inventory:
    room_type_id: str
    room_ids: list[str]
    guest_id: str


TenantFactory = Callable[..., Awaitable[Tenant]]


@pytest.fixture(scope="session", autouse=True)
async def _dispose_engine() -> AsyncIterator[None]:
    yield
    await engine.dispose()


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


async def login(client: AsyncClient, slug: str, email: str, password: str = PASSWORD) -> Any:
    return await client.post(
        "/api/v1/auth/login", json={"hotel_slug": slug, "email": email, "password": password}
    )


@pytest.fixture
async def make_tenant(client: AsyncClient) -> AsyncIterator[TenantFactory]:
    """Create a hotel with one logged-in user; everything is removed afterwards."""
    hotel_ids: list[UUID] = []

    async def factory(role: UserRole = UserRole.OWNER) -> Tenant:
        hotel_id = uuid4()
        slug = f"test-{hotel_id}"
        email = "staff@example.com"
        async with tenant_session(hotel_id) as session:
            session.add(Hotel(id=hotel_id, name="Test Hotel", slug=slug))
            await session.flush()
            session.add(
                User(
                    hotel_id=hotel_id,
                    email=email,
                    hashed_password=hash_password(PASSWORD),
                    full_name="Test Staff",
                    role=role,
                )
            )
        hotel_ids.append(hotel_id)
        response = await login(client, slug, email)
        assert response.status_code == 200, response.text
        token = response.json()["access_token"]
        return Tenant(hotel_id, slug, email, {"Authorization": f"Bearer {token}"})

    yield factory

    # Clean up as the owner role, which is not subject to RLS.
    owner_engine = create_async_engine(get_settings().migration_database_url)
    async with owner_engine.begin() as connection:
        # The ledger is append-only even for the owner. Only a superuser can
        # switch its triggers off, and only for this transaction.
        await connection.execute(text("SET LOCAL session_replication_role = replica"))
        for table in _TENANT_TABLES:
            await connection.execute(
                text(f"DELETE FROM {table} WHERE hotel_id = ANY(:ids)"),  # noqa: S608
                {"ids": hotel_ids},
            )
        await connection.execute(
            text("DELETE FROM hotels WHERE id = ANY(:ids)"), {"ids": hotel_ids}
        )
    await owner_engine.dispose()


@pytest.fixture
async def tenant(make_tenant: TenantFactory) -> Tenant:
    return await make_tenant()


async def create_inventory(client: AsyncClient, tenant: Tenant, *, rooms: int = 2) -> Inventory:
    """A room type with `rooms` physical rooms, plus one guest."""
    response = await client.post(
        "/api/v1/room-types",
        headers=tenant.headers,
        json={"name": "Deluxe", "code": "DLX", "max_occupancy": 3, "base_rate": "4500.00"},
    )
    assert response.status_code == 201, response.text
    room_type_id = response.json()["id"]

    room_ids = []
    for number in range(rooms):
        response = await client.post(
            "/api/v1/rooms",
            headers=tenant.headers,
            json={"room_type_id": room_type_id, "room_number": str(101 + number)},
        )
        assert response.status_code == 201, response.text
        room_ids.append(response.json()["id"])

    response = await client.post(
        "/api/v1/guests",
        headers=tenant.headers,
        json={"first_name": "Asha", "last_name": "Rao", "email": "asha@example.com"},
    )
    assert response.status_code == 201, response.text
    return Inventory(room_type_id, room_ids, response.json()["id"])


@pytest.fixture
async def inventory(client: AsyncClient, tenant: Tenant) -> Inventory:
    return await create_inventory(client, tenant)
