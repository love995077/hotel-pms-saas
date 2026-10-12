"""Password hashing, JWT access tokens and webhook signatures."""

import hashlib
import hmac
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

from app.config import get_settings
from app.models.user import UserRole

_TOKEN_TYPE = "access"  # noqa: S105

_hasher = PasswordHasher()
# Verified against when the account does not exist, so that a failed login
# costs the same whether or not the email is registered.
DUMMY_PASSWORD_HASH = _hasher.hash("not-a-real-password")


class InvalidTokenError(Exception):
    """The token is malformed, expired, or was not signed by us."""


@dataclass(frozen=True, slots=True)
class Principal:
    """Identity carried by a verified access token."""

    user_id: UUID
    hotel_id: UUID
    role: UserRole


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, hashed_password: str) -> bool:
    try:
        return _hasher.verify(hashed_password, password)
    except (VerificationError, InvalidHashError):
        return False


def sign_webhook(secret: str, timestamp: str, body: bytes) -> str:
    """Signature a sender must put in X-Channel-Signature.

    HMAC-SHA256 over "<timestamp>.<raw body>". Binding the timestamp into the
    signature is what lets the receiver refuse replays of old deliveries.
    """
    mac = hmac.new(secret.encode(), timestamp.encode() + b"." + body, hashlib.sha256)
    return "sha256=" + mac.hexdigest()


def webhook_signature_valid(secret: str, timestamp: str, body: bytes, signature: str) -> bool:
    # Compared as bytes: compare_digest refuses non-ASCII str input.
    return hmac.compare_digest(sign_webhook(secret, timestamp, body).encode(), signature.encode())


def create_access_token(principal: Principal, *, now: datetime | None = None) -> str:
    settings = get_settings()
    issued_at = now or datetime.now(UTC)
    claims = {
        "sub": str(principal.user_id),
        "hotel_id": str(principal.hotel_id),
        "role": principal.role.value,
        "type": _TOKEN_TYPE,
        "iat": issued_at,
        "exp": issued_at + timedelta(minutes=settings.access_token_expire_minutes),
    }
    return jwt.encode(
        claims, settings.jwt_secret_key.get_secret_value(), algorithm=settings.jwt_algorithm
    )


def decode_access_token(token: str) -> Principal:
    settings = get_settings()
    try:
        claims = jwt.decode(
            token,
            settings.jwt_secret_key.get_secret_value(),
            algorithms=[settings.jwt_algorithm],
            options={"require": ["exp", "iat", "sub"]},
        )
        if claims.get("type") != _TOKEN_TYPE:
            raise InvalidTokenError("Wrong token type")
        return Principal(
            user_id=UUID(claims["sub"]),
            hotel_id=UUID(claims["hotel_id"]),
            role=UserRole(claims["role"]),
        )
    except (jwt.PyJWTError, KeyError, ValueError, TypeError) as exc:
        raise InvalidTokenError("Invalid access token") from exc
