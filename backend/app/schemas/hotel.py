from typing import Annotated, ClassVar

from pydantic import AfterValidator, EmailStr, Field

from app.schemas.base import PatchSchema, ReadSchema

# Two-digit state code, ten-character PAN, entity number, "Z", check character.
GSTIN_PATTERN = r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$"


def _blank_to_none(value: str | None) -> str | None:
    return value or None


# Optional text: a blank value clears the field.
Optional = Annotated[str | None, AfterValidator(_blank_to_none)]


class HotelUpdate(PatchSchema):
    nullable_fields: ClassVar[frozenset[str]] = frozenset(
        {"gstin", "address", "city", "state", "postal_code", "phone", "email"}
    )

    name: str | None = Field(default=None, min_length=2, max_length=200)
    gstin: str | None = Field(default=None, pattern=GSTIN_PATTERN)
    address: Optional = Field(default=None, max_length=500)
    city: Optional = Field(default=None, max_length=100)
    state: Optional = Field(default=None, max_length=100)
    postal_code: Optional = Field(default=None, max_length=10)
    phone: Optional = Field(default=None, max_length=32)
    email: EmailStr | None = None


class HotelRead(ReadSchema):
    name: str
    slug: str
    gstin: str | None
    address: str | None
    city: str | None
    state: str | None
    postal_code: str | None
    phone: str | None
    email: str | None
    timezone: str
    currency: str
