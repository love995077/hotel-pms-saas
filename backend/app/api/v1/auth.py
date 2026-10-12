from fastapi import APIRouter, HTTPException, status

from app.api.deps import CurrentUser
from app.config import get_settings
from app.core.security import create_access_token
from app.schemas.auth import CurrentUserResponse, LoginRequest, TokenResponse
from app.services.auth import authenticate

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
async def login(credentials: LoginRequest) -> TokenResponse:
    principal = await authenticate(credentials.hotel_slug, credentials.email, credentials.password)
    if principal is None:
        # One message for every failure, so the response does not reveal which
        # hotels or accounts exist.
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Incorrect hotel, email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return TokenResponse(
        access_token=create_access_token(principal),
        expires_in=get_settings().access_token_expire_minutes * 60,
    )


@router.get("/me", response_model=CurrentUserResponse)
async def me(user: CurrentUser) -> CurrentUserResponse:
    return CurrentUserResponse.model_validate(user)
