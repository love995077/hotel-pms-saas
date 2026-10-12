from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.schemas.base import CreateSchema

MIN_PASSWORD_LENGTH = 12


class RegisterRequest(CreateSchema):
    hotel_name: str = Field(min_length=2, max_length=200)
    # Lowercase letters, digits and single hyphens: safe in a URL and a DNS label.
    slug: str = Field(min_length=3, max_length=63, pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$")
    email: EmailStr
    full_name: str = Field(min_length=2, max_length=200)
    password: str = Field(min_length=MIN_PASSWORD_LENGTH, max_length=1024)


class RegisterResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    hotel_id: UUID = Field(validation_alias="id")
    name: str
    slug: str
