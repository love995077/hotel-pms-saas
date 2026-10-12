"""Onboard a hotel and its first (owner) user.

    uv run python -m app.scripts.create_hotel --name "Sea View" --slug sea-view \
        --email owner@example.com --full-name "Asha Rao"

The password is read from PMS_OWNER_PASSWORD, or prompted for.
"""

import argparse
import asyncio
import getpass
import os

from app.database import engine
from app.schemas.onboarding import MIN_PASSWORD_LENGTH
from app.services.onboarding import register_hotel


async def create_hotel(name: str, slug: str, email: str, full_name: str, password: str) -> None:
    try:
        hotel = await register_hotel(name, slug, email, full_name, password)
    finally:
        await engine.dispose()
    print(f"Created hotel {slug!r} ({hotel.id}) with owner {email}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a hotel and its owner user")
    parser.add_argument("--name", required=True)
    parser.add_argument("--slug", required=True)
    parser.add_argument("--email", required=True)
    parser.add_argument("--full-name", required=True)
    args = parser.parse_args()

    password = os.environ.get("PMS_OWNER_PASSWORD") or getpass.getpass("Owner password: ")
    if len(password) < MIN_PASSWORD_LENGTH:
        parser.error(f"Password must be at least {MIN_PASSWORD_LENGTH} characters")
    asyncio.run(create_hotel(args.name, args.slug, args.email, args.full_name, password))


if __name__ == "__main__":
    main()
