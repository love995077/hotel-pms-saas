"""Create a demo hotel with rooms, guests and reservations around today.

    uv run python -m app.scripts.seed_demo

For local development only. The owner password is read from PMS_DEMO_PASSWORD
and defaults to a value printed at the end. Run it once; a second run fails
because the hotel slug already exists.
"""

import asyncio
import os
import random
from datetime import datetime, timedelta
from decimal import Decimal
from uuid import uuid4
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError
from app.core.security import hash_password
from app.database import engine, tenant_session
from app.models import BookingSource, Guest, Hotel, Reservation, Room, RoomType, User, UserRole
from app.schemas.reservation import ReservationCreate
from app.services.reservations import assign_room, check_in, check_out, create_reservation

SLUG = "demo-hotel"
EMAIL = "owner@example.com"
DEFAULT_PASSWORD = "demo-password-123"  # noqa: S105 - local demo data only

ROOM_TYPES = [
    ("Standard Room", "STD", Decimal("2800.00"), 2, ["101", "102", "103", "104", "105", "106"]),
    ("Deluxe Room", "DLX", Decimal("5200.00"), 3, ["201", "202", "203", "204", "205"]),
    ("Heritage Suite", "STE", Decimal("9800.00"), 4, ["301", "302", "303"]),
]
GUESTS = [
    ("Asha", "Rao"), ("Vikram", "Mehta"), ("Meera", "Nair"), ("Rohan", "Kapoor"),
    ("Priya", "Iyer"), ("Arjun", "Singh"), ("Kavya", "Reddy"), ("Imran", "Khan"),
    ("Sara", "D'Souza"), ("Dev", "Malhotra"), ("Ananya", "Bose"), ("Nikhil", "Joshi"),
    ("Tara", "Menon"), ("Kabir", "Shah"), ("Ishita", "Verma"), ("Farhan", "Ali"),
    ("Leela", "Pillai"), ("Aditya", "Gupta"), ("Zoya", "Mirza"), ("Rahul", "Desai"),
]  # fmt: skip
SOURCES = [
    BookingSource.DIRECT, BookingSource.WALK_IN, BookingSource.WEBSITE,
    BookingSource.BOOKING_COM, BookingSource.BOOKING_COM, BookingSource.MAKEMYTRIP,
    BookingSource.MAKEMYTRIP, BookingSource.AGODA, BookingSource.EXPEDIA,
    BookingSource.AIRBNB, BookingSource.CORPORATE, BookingSource.GOIBIBO,
]  # fmt: skip


async def _assign_any_room(session: AsyncSession, reservation: Reservation) -> bool:
    rooms = await session.scalars(
        select(Room).where(Room.room_type_id == reservation.room_type_id).order_by(Room.room_number)
    )
    for room in rooms:
        try:
            await assign_room(session, reservation.id, room.id)
        except ConflictError:
            continue
        return True
    return False


async def seed(password: str) -> None:
    rng = random.Random(7)  # noqa: S311 - reproducible demo data, not security
    hotel_id = uuid4()
    today = datetime.now(ZoneInfo("Asia/Kolkata")).date()

    async with tenant_session(hotel_id) as session:
        session.add(Hotel(id=hotel_id, name="The Demo Residency", slug=SLUG))
        await session.flush()
        session.add(
            User(
                hotel_id=hotel_id,
                email=EMAIL,
                hashed_password=hash_password(password),
                full_name="Demo Owner",
                role=UserRole.OWNER,
            )
        )

        room_types = []
        for name, code, rate, occupancy, numbers in ROOM_TYPES:
            room_type = RoomType(
                hotel_id=hotel_id, name=name, code=code, base_rate=rate, max_occupancy=occupancy
            )
            session.add(room_type)
            await session.flush()
            session.add_all(
                Room(hotel_id=hotel_id, room_type_id=room_type.id, room_number=n, floor=n[0])
                for n in numbers
            )
            room_types.append(room_type)

        guests = [
            Guest(
                hotel_id=hotel_id,
                first_name=first,
                last_name=last,
                email=f"{first}.{last}@example.com".lower().replace("'", ""),
            )
            for first, last in GUESTS
        ]
        session.add_all(guests)
        await session.flush()

        created = 0
        for index in range(44):
            room_type = rng.choice(room_types)
            arrival = today + timedelta(days=rng.randint(-6, 16))
            departure = arrival + timedelta(days=rng.randint(1, 5))
            source = rng.choice(SOURCES)
            try:
                reservation = await create_reservation(
                    session,
                    ReservationCreate(
                        guest_id=rng.choice(guests).id,
                        room_type_id=room_type.id,
                        check_in_date=arrival,
                        check_out_date=departure,
                        adults=rng.randint(1, 2),
                        rate_per_night=room_type.base_rate + rng.choice([0, 0, 300, 600, -200]),
                        source=source,
                        external_reference=f"DEMO-{index:03d}"
                        if source not in (BookingSource.DIRECT, BookingSource.WALK_IN)
                        else None,
                    ),
                )
            except ConflictError:
                continue  # that room type is full for those nights
            created += 1

            # Leave some future arrivals unassigned, as a real front desk would.
            if arrival > today + timedelta(days=3) and rng.random() < 0.45:
                continue
            if not await _assign_any_room(session, reservation):
                continue
            if arrival <= today:
                await check_in(session, reservation.id)
                if departure <= today:
                    await check_out(session, reservation.id)

    await engine.dispose()
    print(f"Seeded {created} reservations for 'The Demo Residency'.")
    print(f"  Hotel:    {SLUG}")
    print(f"  Email:    {EMAIL}")
    print(f"  Password: {password}")


def main() -> None:
    try:
        asyncio.run(seed(os.environ.get("PMS_DEMO_PASSWORD") or DEFAULT_PASSWORD))
    except IntegrityError:
        raise SystemExit(f"Hotel '{SLUG}' already exists; nothing was changed.") from None


if __name__ == "__main__":
    main()
