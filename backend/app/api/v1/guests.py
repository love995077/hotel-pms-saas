from collections.abc import Sequence
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import or_, select

from app.api.deps import FRONT_OFFICE, DbSession, get_current_user, require_roles
from app.database import current_hotel_id
from app.models import Guest
from app.schemas.guest import GuestCreate, GuestRead, GuestUpdate
from app.services.crud import apply_changes, flush_or_conflict, get_or_404

router = APIRouter(prefix="/guests", tags=["guests"], dependencies=[Depends(get_current_user)])
_front_office = Depends(require_roles(*FRONT_OFFICE))


@router.post(
    "", response_model=GuestRead, status_code=status.HTTP_201_CREATED, dependencies=[_front_office]
)
async def create_guest(data: GuestCreate, db: DbSession) -> Guest:
    guest = Guest(hotel_id=current_hotel_id(db), **data.model_dump())
    db.add(guest)
    await db.flush()
    return guest


@router.get("", response_model=list[GuestRead])
async def list_guests(
    db: DbSession,
    q: Annotated[
        str | None, Query(min_length=2, max_length=100, description="Name, email or phone")
    ] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Sequence[Guest]:
    statement = (
        select(Guest).order_by(Guest.last_name, Guest.first_name).limit(limit).offset(offset)
    )
    if q:
        pattern = f"%{q}%"
        statement = statement.where(
            or_(
                Guest.first_name.ilike(pattern, escape="\\"),
                Guest.last_name.ilike(pattern, escape="\\"),
                Guest.email.ilike(pattern, escape="\\"),
                Guest.phone.ilike(pattern, escape="\\"),
            )
        )
    return (await db.scalars(statement)).all()


@router.get("/{guest_id}", response_model=GuestRead)
async def get_guest(guest_id: UUID, db: DbSession) -> Guest:
    return await get_or_404(db, Guest, guest_id)


@router.patch("/{guest_id}", response_model=GuestRead, dependencies=[_front_office])
async def update_guest(guest_id: UUID, data: GuestUpdate, db: DbSession) -> Guest:
    guest = await get_or_404(db, Guest, guest_id)
    apply_changes(guest, data.model_dump(exclude_unset=True))
    await db.flush()
    return guest


@router.delete("/{guest_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[_front_office])
async def delete_guest(guest_id: UUID, db: DbSession) -> None:
    guest = await get_or_404(db, Guest, guest_id)
    await db.delete(guest)
    await flush_or_conflict(db, "Guest has reservations and cannot be deleted")
