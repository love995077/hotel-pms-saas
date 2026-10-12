from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.deps import get_current_user
from app.schemas.billing import GstQuoteRead
from app.services.gst import SAC_ACCOMMODATION, calculate_room_gst

router = APIRouter(prefix="/gst", tags=["gst"], dependencies=[Depends(get_current_user)])


@router.get("/room-quote", response_model=GstQuoteRead)
async def room_quote(
    tariff_per_night: Annotated[Decimal, Query(ge=0, max_digits=12, decimal_places=2)],
    nights: Annotated[int, Query(ge=1, le=365)] = 1,
) -> GstQuoteRead:
    """GST on a stay. The slab is chosen per night, then multiplied by the nights."""
    per_night = calculate_room_gst(tariff_per_night)
    return GstQuoteRead(
        sac_code=SAC_ACCOMMODATION,
        nights=nights,
        tariff_per_night=per_night.taxable_amount,
        gst_rate=per_night.gst_rate,
        itc_eligible=per_night.itc_eligible,
        taxable_amount=per_night.taxable_amount * nights,
        cgst_amount=per_night.cgst_amount * nights,
        sgst_amount=per_night.sgst_amount * nights,
        total_tax=per_night.total_tax * nights,
        total_amount=per_night.total_amount * nights,
    )
