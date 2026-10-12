from collections.abc import Sequence
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select

from app.api.deps import MANAGEMENT, DbSession, get_current_user, require_roles
from app.database import current_hotel_id
from app.models import Room, RoomType
from app.schemas.inventory import RoomCreate, RoomRead, RoomUpdate
from app.services.crud import apply_changes, flush_or_conflict, get_or_404

router = APIRouter(prefix="/rooms", tags=["rooms"], dependencies=[Depends(get_current_user)])
_manage = Depends(require_roles(*MANAGEMENT))
_NUMBER_TAKEN = "A room with this number already exists"


@router.post(
    "", response_model=RoomRead, status_code=status.HTTP_201_CREATED, dependencies=[_manage]
)
async def create_room(data: RoomCreate, db: DbSession) -> Room:
    await get_or_404(db, RoomType, data.room_type_id)
    room = Room(hotel_id=current_hotel_id(db), **data.model_dump())
    db.add(room)
    await flush_or_conflict(db, _NUMBER_TAKEN)
    return room


@router.get("", response_model=list[RoomRead])
async def list_rooms(
    db: DbSession,
    room_type_id: UUID | None = None,
    include_inactive: bool = False,
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Sequence[Room]:
    statement = select(Room).order_by(Room.room_number).limit(limit).offset(offset)
    if room_type_id is not None:
        statement = statement.where(Room.room_type_id == room_type_id)
    if not include_inactive:
        statement = statement.where(Room.is_active)
    return (await db.scalars(statement)).all()


@router.get("/{room_id}", response_model=RoomRead)
async def get_room(room_id: UUID, db: DbSession) -> Room:
    return await get_or_404(db, Room, room_id)


@router.patch("/{room_id}", response_model=RoomRead, dependencies=[_manage])
async def update_room(room_id: UUID, data: RoomUpdate, db: DbSession) -> Room:
    room = await get_or_404(db, Room, room_id)
    changes = data.model_dump(exclude_unset=True)
    if "room_type_id" in changes:
        await get_or_404(db, RoomType, changes["room_type_id"])
    apply_changes(room, changes)
    await flush_or_conflict(db, _NUMBER_TAKEN)
    return room


@router.delete("/{room_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[_manage])
async def delete_room(room_id: UUID, db: DbSession) -> None:
    room = await get_or_404(db, Room, room_id)
    await db.delete(room)
    await flush_or_conflict(db, "Room has reservations; deactivate it instead of deleting")
