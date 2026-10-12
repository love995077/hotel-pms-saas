"""Tenant isolation tests. Require the docker-compose database, migrated."""

from collections.abc import AsyncIterator
from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete, select
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.config import get_settings
from app.database import SessionFactory, tenant_session
from app.models import Hotel, User, UserRole


@pytest.fixture
async def two_hotels() -> AsyncIterator[tuple[UUID, UUID]]:
    ids = (uuid4(), uuid4())
    for hotel_id in ids:
        async with tenant_session(hotel_id) as session:
            session.add(Hotel(id=hotel_id, name="Test Hotel", slug=f"test-{hotel_id}"))
            await session.flush()
            session.add(
                User(
                    hotel_id=hotel_id,
                    email="frontdesk@example.com",
                    hashed_password="x",
                    full_name="Front Desk",
                    role=UserRole.FRONT_DESK,
                )
            )
    yield ids

    # Clean up as the owner role, which is not subject to RLS.
    owner_engine = create_async_engine(get_settings().migration_database_url)
    async with AsyncSession(owner_engine) as session, session.begin():
        await session.execute(delete(User).where(User.hotel_id.in_(ids)))
        await session.execute(delete(Hotel).where(Hotel.id.in_(ids)))
    await owner_engine.dispose()


async def test_session_only_sees_its_own_hotel(two_hotels: tuple[UUID, UUID]) -> None:
    hotel_a, hotel_b = two_hotels
    async with tenant_session(hotel_a) as session:
        hotels = (await session.scalars(select(Hotel))).all()
        users = (await session.scalars(select(User))).all()
        other = await session.get(Hotel, hotel_b)

    assert [h.id for h in hotels] == [hotel_a]
    assert [u.hotel_id for u in users] == [hotel_a]
    assert other is None


async def test_unscoped_session_sees_nothing(two_hotels: tuple[UUID, UUID]) -> None:
    async with SessionFactory() as session:
        assert (await session.scalars(select(Hotel))).all() == []
        assert (await session.scalars(select(User))).all() == []


async def test_cannot_write_into_another_hotel(two_hotels: tuple[UUID, UUID]) -> None:
    hotel_a, hotel_b = two_hotels
    with pytest.raises(DBAPIError, match="row-level security"):
        async with tenant_session(hotel_a) as session:
            session.add(
                User(
                    hotel_id=hotel_b,
                    email="intruder@example.com",
                    hashed_password="x",
                    full_name="Intruder",
                    role=UserRole.MANAGER,
                )
            )


async def test_tenant_context_survives_commit(two_hotels: tuple[UUID, UUID]) -> None:
    hotel_a, _ = two_hotels
    async with SessionFactory(info={"hotel_id": hotel_a}) as session:
        await session.commit()
        users = (await session.scalars(select(User))).all()
    assert [u.hotel_id for u in users] == [hotel_a]


async def test_tenant_context_does_not_leak_through_pool(two_hotels: tuple[UUID, UUID]) -> None:
    hotel_a, _ = two_hotels
    async with tenant_session(hotel_a) as session:
        await session.scalars(select(User))
    # Pool hands the same connection back; the setting must be gone.
    async with SessionFactory() as session:
        assert (await session.scalars(select(User))).all() == []
