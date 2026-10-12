from sqlalchemy import text

from app.core.security import DUMMY_PASSWORD_HASH, Principal, verify_password
from app.database import engine
from app.models import UserRole


async def authenticate(hotel_slug: str, email: str, password: str) -> Principal | None:
    """Check credentials; return the caller's identity or None.

    Runs before any tenant is known, so it cannot read the RLS-protected tables
    directly. ``auth_lookup_user`` is a SECURITY DEFINER function that returns
    exactly one active user of one active hotel and nothing else.
    """
    async with engine.connect() as connection:
        result = await connection.execute(
            text(
                "SELECT user_id, hotel_id, hashed_password, role "
                "FROM auth_lookup_user(:hotel_slug, :email)"
            ),
            {"hotel_slug": hotel_slug, "email": email},
        )
        row = result.one_or_none()

    hashed_password = row.hashed_password if row else DUMMY_PASSWORD_HASH
    if not verify_password(password, hashed_password) or row is None:
        return None
    return Principal(user_id=row.user_id, hotel_id=row.hotel_id, role=UserRole(row.role))
