"""Async SQLAlchemy engine and tenant-scoped sessions.

Tenant isolation is enforced by PostgreSQL Row-Level Security. Every policy
compares a row's hotel id with the transaction-local setting
``app.current_hotel_id``. A session obtained from :func:`tenant_session` sets
that value at the start of every transaction it opens; a session without it
sees no tenant rows at all (the policies fail closed).
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import UUID

from sqlalchemy import Connection, event, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session, SessionTransaction

from app.config import get_settings

_HOTEL_ID_KEY = "hotel_id"

settings = get_settings()

engine = create_async_engine(
    settings.database_url,
    echo=settings.db_echo,
    pool_size=settings.db_pool_size,
    max_overflow=settings.db_max_overflow,
    pool_pre_ping=True,
)


class TenantSession(Session):
    """Sync session class behind every AsyncSession; target of the RLS hook."""


@event.listens_for(TenantSession, "after_begin")
def _apply_tenant_context(
    session: Session, transaction: SessionTransaction, connection: Connection
) -> None:
    """Scope each new transaction to the session's hotel.

    ``set_config(..., is_local => true)`` is the parameterisable form of
    ``SET LOCAL app.current_hotel_id = ...`` (SET cannot take bind parameters).
    Being transaction-local, the value is discarded on commit/rollback, so it
    can never leak to another request through the connection pool. Hooking
    ``after_begin`` re-applies it if a request commits and keeps working.
    """
    hotel_id = session.info.get(_HOTEL_ID_KEY)
    if hotel_id is not None:
        connection.execute(
            text("SELECT set_config('app.current_hotel_id', :hotel_id, true)"),
            {"hotel_id": str(hotel_id)},
        )


SessionFactory = async_sessionmaker(
    engine,
    sync_session_class=TenantSession,
    expire_on_commit=False,
    autoflush=False,
)


@asynccontextmanager
async def tenant_session(hotel_id: UUID) -> AsyncIterator[AsyncSession]:
    """Yield a session restricted to one hotel; commits on success."""
    async with SessionFactory(info={_HOTEL_ID_KEY: hotel_id}) as session:
        async with session.begin():
            yield session


def current_hotel_id(session: AsyncSession) -> UUID:
    """Hotel a tenant session is scoped to."""
    hotel_id = session.info.get(_HOTEL_ID_KEY)
    if not isinstance(hotel_id, UUID):
        raise RuntimeError("Session is not tenant-scoped")
    return hotel_id
