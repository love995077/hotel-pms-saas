from uuid import uuid4

from sqlalchemy.exc import IntegrityError

from app.core.exceptions import ConflictError
from app.core.security import hash_password
from app.database import tenant_session
from app.models import Hotel, User, UserRole


async def register_hotel(name: str, slug: str, email: str, full_name: str, password: str) -> Hotel:
    """Create a hotel and its first (owner) user in one transaction.

    Runs as the ordinary runtime role. No tenant exists yet, so the id is
    generated here and the session is scoped to it: that is what lets RLS
    accept the inserts, and it means this code can never touch another hotel.
    """
    hotel_id = uuid4()
    # Hashed before the transaction opens; argon2 is slow by design and should
    # not hold a database connection.
    hashed_password = hash_password(password)
    async with tenant_session(hotel_id) as session:
        hotel = Hotel(id=hotel_id, name=name, slug=slug)
        session.add(hotel)
        try:
            await session.flush()
        except IntegrityError as exc:
            # The unique constraint sees every hotel (constraint checks bypass
            # RLS), so it is the race-free arbiter of slug uniqueness.
            raise ConflictError("That hotel code is already taken") from exc
        session.add(
            User(
                hotel_id=hotel_id,
                email=email.lower(),
                hashed_password=hashed_password,
                full_name=full_name,
                role=UserRole.OWNER,
            )
        )
    return hotel
