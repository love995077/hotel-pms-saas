from collections.abc import Sequence
from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select

from app.api.deps import FRONT_OFFICE, DbSession, get_current_user, require_roles
from app.models import Reservation, ReservationStatus
from app.schemas.reservation import (
    ReservationCreate,
    ReservationRead,
    ReservationUpdate,
    RoomAssignment,
)
from app.services import reservations as service
from app.services.crud import get_or_404

router = APIRouter(
    prefix="/reservations", tags=["reservations"], dependencies=[Depends(get_current_user)]
)
_front_office = Depends(require_roles(*FRONT_OFFICE))


@router.post(
    "",
    response_model=ReservationRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[_front_office],
)
async def create_reservation(data: ReservationCreate, db: DbSession) -> Reservation:
    return await service.create_reservation(db, data)


@router.get("", response_model=list[ReservationRead])
async def list_reservations(
    db: DbSession,
    from_date: Annotated[
        date | None, Query(description="Only stays still in house on or after this date")
    ] = None,
    to_date: Annotated[
        date | None, Query(description="Only stays starting before this date")
    ] = None,
    status_: Annotated[ReservationStatus | None, Query(alias="status")] = None,
    room_type_id: UUID | None = None,
    guest_id: UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 200,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Sequence[Reservation]:
    statement = (
        select(Reservation)
        .order_by(Reservation.check_in_date, Reservation.id)
        .limit(limit)
        .offset(offset)
    )
    if from_date is not None:
        statement = statement.where(Reservation.check_out_date > from_date)
    if to_date is not None:
        statement = statement.where(Reservation.check_in_date < to_date)
    if status_ is not None:
        statement = statement.where(Reservation.status == status_)
    if room_type_id is not None:
        statement = statement.where(Reservation.room_type_id == room_type_id)
    if guest_id is not None:
        statement = statement.where(Reservation.guest_id == guest_id)
    return (await db.scalars(statement)).all()


@router.get("/{reservation_id}", response_model=ReservationRead)
async def get_reservation(reservation_id: UUID, db: DbSession) -> Reservation:
    return await get_or_404(db, Reservation, reservation_id)


@router.patch("/{reservation_id}", response_model=ReservationRead, dependencies=[_front_office])
async def update_reservation(
    reservation_id: UUID, data: ReservationUpdate, db: DbSession
) -> Reservation:
    return await service.update_reservation(db, reservation_id, data.model_dump(exclude_unset=True))


@router.post(
    "/{reservation_id}/assign-room", response_model=ReservationRead, dependencies=[_front_office]
)
async def assign_room(reservation_id: UUID, data: RoomAssignment, db: DbSession) -> Reservation:
    return await service.assign_room(db, reservation_id, data.room_id)


@router.post(
    "/{reservation_id}/check-in", response_model=ReservationRead, dependencies=[_front_office]
)
async def check_in(reservation_id: UUID, db: DbSession) -> Reservation:
    return await service.check_in(db, reservation_id)


@router.post(
    "/{reservation_id}/check-out", response_model=ReservationRead, dependencies=[_front_office]
)
async def check_out(reservation_id: UUID, db: DbSession) -> Reservation:
    return await service.check_out(db, reservation_id)


@router.post(
    "/{reservation_id}/cancel", response_model=ReservationRead, dependencies=[_front_office]
)
async def cancel_reservation(reservation_id: UUID, db: DbSession) -> Reservation:
    """Reservations are never deleted; cancelling releases the inventory."""
    return await service.cancel_reservation(db, reservation_id)
