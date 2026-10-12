from typing import ClassVar

from pydantic import EmailStr, Field

from app.schemas.base import CreateSchema, PatchSchema, ReadSchema


class GuestCreate(CreateSchema):
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=32)
    id_document_type: str | None = Field(default=None, max_length=50)
    id_document_number: str | None = Field(default=None, max_length=100)
    nationality: str | None = Field(default=None, max_length=100)
    address: str | None = None
    city: str | None = Field(default=None, max_length=100)
    state: str | None = Field(default=None, max_length=100)
    country: str | None = Field(default=None, max_length=100)
    company_name: str | None = Field(default=None, max_length=200)
    gstin: str | None = Field(default=None, min_length=15, max_length=15)


class GuestUpdate(PatchSchema):
    nullable_fields: ClassVar[frozenset[str]] = frozenset(
        set(GuestCreate.model_fields) - {"first_name", "last_name"}
    )

    first_name: str | None = Field(default=None, min_length=1, max_length=100)
    last_name: str | None = Field(default=None, min_length=1, max_length=100)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=32)
    id_document_type: str | None = Field(default=None, max_length=50)
    id_document_number: str | None = Field(default=None, max_length=100)
    nationality: str | None = Field(default=None, max_length=100)
    address: str | None = None
    city: str | None = Field(default=None, max_length=100)
    state: str | None = Field(default=None, max_length=100)
    country: str | None = Field(default=None, max_length=100)
    company_name: str | None = Field(default=None, max_length=200)
    gstin: str | None = Field(default=None, min_length=15, max_length=15)


class GuestRead(ReadSchema):
    first_name: str
    last_name: str
    email: str | None
    phone: str | None
    id_document_type: str | None
    id_document_number: str | None
    nationality: str | None
    address: str | None
    city: str | None
    state: str | None
    country: str | None
    company_name: str | None
    gstin: str | None
