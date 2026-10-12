"""Small persistence helpers shared by routes and services."""

from typing import Any, TypeVar
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError
from app.models import Base

ModelT = TypeVar("ModelT", bound=Base)


async def get_or_404(session: AsyncSession, model: type[ModelT], id_: UUID) -> ModelT:
    """Fetch by primary key. RLS makes other hotels' rows simply not exist."""
    instance = await session.get(model, id_)
    if instance is None:
        raise NotFoundError(f"{model.__name__} not found")
    return instance


async def flush_or_conflict(session: AsyncSession, detail: str) -> None:
    """Flush pending changes, turning a constraint violation into a 409."""
    try:
        await session.flush()
    except IntegrityError as exc:
        raise ConflictError(detail) from exc


def apply_changes(instance: Base, changes: dict[str, Any]) -> None:
    for field, value in changes.items():
        setattr(instance, field, value)
