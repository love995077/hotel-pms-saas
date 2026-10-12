from fastapi import APIRouter, status

from app.schemas.onboarding import RegisterRequest, RegisterResponse
from app.services.onboarding import register_hotel

router = APIRouter(prefix="/onboarding", tags=["onboarding"])


@router.post("/register", response_model=RegisterResponse, status_code=status.HTTP_201_CREATED)
async def register(payload: RegisterRequest) -> RegisterResponse:
    """Public self-service sign-up: creates a hotel and its owner account."""
    hotel = await register_hotel(
        name=payload.hotel_name,
        slug=payload.slug,
        email=payload.email,
        full_name=payload.full_name,
        password=payload.password,
    )
    return RegisterResponse.model_validate(hotel)
