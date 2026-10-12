from fastapi import APIRouter, Depends

from app.api.deps import MANAGEMENT, DbSession, get_current_user, require_roles
from app.database import current_hotel_id
from app.models import Hotel
from app.schemas.hotel import HotelRead, HotelUpdate
from app.services.crud import apply_changes, get_or_404

router = APIRouter(prefix="/hotel", tags=["hotel"], dependencies=[Depends(get_current_user)])


@router.get("", response_model=HotelRead)
async def get_hotel(db: DbSession) -> Hotel:
    """The caller's own hotel. There is no way to name another one."""
    return await get_or_404(db, Hotel, current_hotel_id(db))


@router.patch("", response_model=HotelRead, dependencies=[Depends(require_roles(*MANAGEMENT))])
async def update_hotel(data: HotelUpdate, db: DbSession) -> Hotel:
    """Update the details printed on invoices: name, GSTIN, address and contacts."""
    hotel = await get_or_404(db, Hotel, current_hotel_id(db))
    apply_changes(hotel, data.model_dump(exclude_unset=True))
    await db.flush()
    return hotel
