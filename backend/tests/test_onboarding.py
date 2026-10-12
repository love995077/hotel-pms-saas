from collections.abc import AsyncIterator
from typing import Any
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.config import get_settings
from tests.conftest import PASSWORD, login

REGISTER_URL = "/api/v1/onboarding/register"


@pytest.fixture
async def slug() -> AsyncIterator[str]:
    """A unique hotel code; whatever was registered under it is removed afterwards."""
    value = f"signup-{uuid4()}"
    yield value

    # Clean up as the owner role, which is not subject to RLS.
    owner_engine = create_async_engine(get_settings().migration_database_url)
    async with owner_engine.begin() as connection:
        await connection.execute(
            text("DELETE FROM users WHERE hotel_id IN (SELECT id FROM hotels WHERE slug = :slug)"),
            {"slug": value},
        )
        await connection.execute(text("DELETE FROM hotels WHERE slug = :slug"), {"slug": value})
    await owner_engine.dispose()


def _payload(slug: str, **overrides: Any) -> dict[str, Any]:
    return {
        "hotel_name": "Sea View Residency",
        "slug": slug,
        "email": "Owner@Example.com",
        "full_name": "Asha Rao",
        "password": PASSWORD,
        **overrides,
    }


async def test_register_creates_hotel_and_owner_who_can_log_in(
    client: AsyncClient, slug: str
) -> None:
    response = await client.post(REGISTER_URL, json=_payload(slug))
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["slug"] == slug
    assert body["name"] == "Sea View Residency"
    assert "password" not in response.text

    token = (await login(client, slug, "owner@example.com")).json()["access_token"]
    me = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["hotel_id"] == body["hotel_id"]
    assert me.json()["role"] == "owner"
    assert me.json()["email"] == "owner@example.com"


async def test_register_rejects_a_taken_hotel_code(client: AsyncClient, slug: str) -> None:
    assert (await client.post(REGISTER_URL, json=_payload(slug))).status_code == 201

    response = await client.post(
        REGISTER_URL, json=_payload(slug, email="intruder@example.com", password="x" * 12)
    )
    assert response.status_code == 409
    assert response.json()["detail"] == "That hotel code is already taken"
    # The first owner is untouched and no second account was attached to the hotel.
    assert (await login(client, slug, "owner@example.com")).status_code == 200
    assert (await login(client, slug, "intruder@example.com", "x" * 12)).status_code == 401


@pytest.mark.parametrize(
    "overrides",
    [
        {"password": "too-short"},
        {"slug": "Has Spaces"},
        {"slug": "-leading-hyphen"},
        {"slug": "ab"},
        {"email": "not-an-email"},
        {"hotel_name": " "},
        {"hotel_id": "00000000-0000-0000-0000-000000000000"},
        {"role": "owner"},
    ],
)
async def test_register_validates_input(
    client: AsyncClient, slug: str, overrides: dict[str, str]
) -> None:
    response = await client.post(REGISTER_URL, json={**_payload(slug), **overrides})
    assert response.status_code == 422
