from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models import UserRole


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    hotel_slug: str = Field(min_length=1, max_length=63)
    email: EmailStr
    password: str = Field(min_length=1, max_length=1024)


class TokenResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"  # noqa: S105
    expires_in: int = Field(description="Lifetime of the access token in seconds")


class CurrentUserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    hotel_id: UUID
    email: EmailStr
    full_name: str
    role: UserRole
