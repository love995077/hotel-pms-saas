from collections.abc import Sequence
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select

from app.api.deps import MANAGEMENT, DbSession, get_current_user, require_roles
from app.core.exceptions import UnprocessableError
from app.database import current_hotel_id
from app.models import RoomType
from app.schemas.inventory import RoomTypeCreate, RoomTypeRead, RoomTypeUpdate
from app.services.crud import apply_changes, flush_or_conflict, get_or_404

router = APIRouter(
    prefix="/room-types", tags=["room types"], dependencies=[Depends(get_current_user)]
)
_manage = Depends(require_roles(*MANAGEMENT))
_CODE_TAKEN = "A room type with this code already exists"


@router.post(
    "", response_model=RoomTypeRead, status_code=status.HTTP_201_CREATED, dependencies=[_manage]
)
async def create_room_type(data: RoomTypeCreate, db: DbSession) -> RoomType:
    room_type = RoomType(hotel_id=current_hotel_id(db), **data.model_dump())
    db.add(room_type)
    await flush_or_conflict(db, _CODE_TAKEN)
    return room_type


@router.get("", response_model=list[RoomTypeRead])
async def list_room_types(
    db: DbSession,
    include_inactive: bool = False,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Sequence[RoomType]:
    statement = select(RoomType).order_by(RoomType.name).limit(limit).offset(offset)
    if not include_inactive:
        statement = statement.where(RoomType.is_active)
    return (await db.scalars(statement)).all()


@router.get("/{room_type_id}", response_model=RoomTypeRead)
async def get_room_type(room_type_id: UUID, db: DbSession) -> RoomType:
    return await get_or_404(db, RoomType, room_type_id)


@router.patch("/{room_type_id}", response_model=RoomTypeRead, dependencies=[_manage])
async def update_room_type(room_type_id: UUID, data: RoomTypeUpdate, db: DbSession) -> RoomType:
    room_type = await get_or_404(db, RoomType, room_type_id)
    apply_changes(room_type, data.model_dump(exclude_unset=True))
    if room_type.max_occupancy < room_type.base_occupancy:
        raise UnprocessableError("max_occupancy must be at least base_occupancy")
    await flush_or_conflict(db, _CODE_TAKEN)
    return room_type


@router.delete("/{room_type_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[_manage])
async def delete_room_type(room_type_id: UUID, db: DbSession) -> None:
    room_type = await get_or_404(db, RoomType, room_type_id)
    await db.delete(room_type)
    await flush_or_conflict(
        db, "Room type has rooms or reservations; deactivate it instead of deleting"
    )
