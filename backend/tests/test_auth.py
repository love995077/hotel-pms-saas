from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import update

from app.core.security import (
    InvalidTokenError,
    Principal,
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)
from app.database import tenant_session
from app.models import User, UserRole
from tests.conftest import Tenant, TenantFactory, login


def _principal() -> Principal:
    return Principal(user_id=uuid4(), hotel_id=uuid4(), role=UserRole.FRONT_DESK)


def test_password_hash_round_trip() -> None:
    hashed = hash_password("s3cret-password")
    assert hashed != "s3cret-password"
    assert verify_password("s3cret-password", hashed)
    assert not verify_password("wrong", hashed)
    assert not verify_password("s3cret-password", "not-a-hash")


def test_token_round_trip() -> None:
    principal = _principal()
    assert decode_access_token(create_access_token(principal)) == principal


def test_expired_token_is_rejected() -> None:
    token = create_access_token(_principal(), now=datetime.now(UTC) - timedelta(days=1))
    with pytest.raises(InvalidTokenError):
        decode_access_token(token)


def test_tampered_token_is_rejected() -> None:
    token = create_access_token(_principal())
    with pytest.raises(InvalidTokenError):
        decode_access_token(token[:-4] + "AAAA")
    with pytest.raises(InvalidTokenError):
        decode_access_token("not.a.token")


async def test_login_returns_token_for_the_users_hotel(client: AsyncClient, tenant: Tenant) -> None:
    response = await client.get("/api/v1/auth/me", headers=tenant.headers)
    assert response.status_code == 200
    body = response.json()
    assert body["hotel_id"] == str(tenant.hotel_id)
    assert body["email"] == tenant.email
    assert body["role"] == "owner"


async def test_login_is_case_insensitive_on_email(client: AsyncClient, tenant: Tenant) -> None:
    response = await login(client, tenant.slug, tenant.email.upper())
    assert response.status_code == 200


@pytest.mark.parametrize(
    ("slug_ok", "email", "password"),
    [
        (True, "staff@example.com", "wrong-password"),
        (True, "nobody@example.com", "correct-horse-battery"),
        (False, "staff@example.com", "correct-horse-battery"),
    ],
)
async def test_login_rejects_bad_credentials(
    client: AsyncClient, tenant: Tenant, slug_ok: bool, email: str, password: str
) -> None:
    response = await login(client, tenant.slug if slug_ok else "no-such-hotel", email, password)
    assert response.status_code == 401
    assert response.json()["detail"] == "Incorrect hotel, email or password"


async def test_same_email_in_two_hotels_resolves_by_slug(
    client: AsyncClient, make_tenant: TenantFactory
) -> None:
    # Both hotels have a user with the same email and password.
    for hotel in (await make_tenant(), await make_tenant()):
        me = await client.get("/api/v1/auth/me", headers=hotel.headers)
        assert me.json()["hotel_id"] == str(hotel.hotel_id)


async def test_protected_routes_require_a_valid_token(client: AsyncClient) -> None:
    assert (await client.get("/api/v1/room-types")).status_code == 401
    bad = {"Authorization": "Bearer garbage"}
    assert (await client.get("/api/v1/room-types", headers=bad)).status_code == 401


async def test_deactivated_user_is_locked_out_immediately(
    client: AsyncClient, tenant: Tenant
) -> None:
    async with tenant_session(tenant.hotel_id) as session:
        await session.execute(update(User).values(is_active=False))

    assert (await client.get("/api/v1/auth/me", headers=tenant.headers)).status_code == 401
    assert (await login(client, tenant.slug, tenant.email)).status_code == 401


async def test_role_without_permission_gets_403(
    client: AsyncClient, make_tenant: TenantFactory
) -> None:
    housekeeper = await make_tenant(UserRole.HOUSEKEEPING)
    response = await client.post(
        "/api/v1/room-types",
        headers=housekeeper.headers,
        json={"name": "Suite", "code": "STE", "base_rate": "9000.00"},
    )
    assert response.status_code == 403
    # Reading is still allowed.
    assert (await client.get("/api/v1/room-types", headers=housekeeper.headers)).status_code == 200
