"""Request dependencies: authentication, tenant-scoped DB session, authorisation."""

from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import InvalidTokenError, Principal, decode_access_token
from app.database import tenant_session
from app.models import User, UserRole

_bearer = HTTPBearer(auto_error=False)

MANAGEMENT = (UserRole.OWNER, UserRole.MANAGER)
FRONT_OFFICE = (UserRole.OWNER, UserRole.MANAGER, UserRole.FRONT_DESK)
# May post charges and take payments.
BILLING = (UserRole.OWNER, UserRole.MANAGER, UserRole.FRONT_DESK, UserRole.ACCOUNTANT)
# May reverse posted ledger lines and run the night audit.
LEDGER_CONTROL = (UserRole.OWNER, UserRole.MANAGER, UserRole.ACCOUNTANT)


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status.HTTP_401_UNAUTHORIZED, detail, headers={"WWW-Authenticate": "Bearer"}
    )


def get_principal(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> Principal:
    if credentials is None:
        raise _unauthorized("Not authenticated")
    try:
        return decode_access_token(credentials.credentials)
    except InvalidTokenError as exc:
        raise _unauthorized("Invalid or expired token") from exc


async def get_db(
    principal: Annotated[Principal, Depends(get_principal)],
) -> AsyncIterator[AsyncSession]:
    """Session scoped by RLS to the hotel in the caller's verified token."""
    async with tenant_session(principal.hotel_id) as session:
        yield session


# scope="function": the transaction commits before the response is sent, so a
# failed commit surfaces as an error instead of a false success.
DbSession = Annotated[AsyncSession, Depends(get_db, scope="function")]


async def get_current_user(
    principal: Annotated[Principal, Depends(get_principal)], db: DbSession
) -> User:
    """Load the caller from the database so deactivation takes effect at once."""
    user = await db.get(User, principal.user_id)
    if user is None or not user.is_active:
        raise _unauthorized("Account is disabled or no longer exists")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_roles(*roles: UserRole) -> Callable[[User], Awaitable[User]]:
    async def checker(user: CurrentUser) -> User:
        if user.role not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Insufficient permissions")
        return user

    return checker
