"""auth lookup function

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-01
"""

from collections.abc import Sequence

from sqlalchemy.engine import make_url

from alembic import op
from app.config import get_settings

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Login happens before a tenant is known, so the runtime role (blocked by
    # RLS) cannot find the user itself. This function runs with the rights of
    # its owner, the migration role, which must be able to bypass RLS
    # (superuser or BYPASSRLS). It exposes one active user of one active hotel
    # per call and is executable only by the runtime role.
    op.execute(
        """
        CREATE FUNCTION auth_lookup_user(p_hotel_slug text, p_email text)
        RETURNS TABLE (user_id uuid, hotel_id uuid, hashed_password text, role text)
        LANGUAGE sql
        STABLE
        SECURITY DEFINER
        SET search_path = public, pg_temp
        AS $$
            SELECT u.id, u.hotel_id, u.hashed_password::text, u.role::text
            FROM hotels AS h
            JOIN users AS u ON u.hotel_id = h.id
            WHERE h.slug = p_hotel_slug
              AND lower(u.email) = lower(p_email)
              AND h.is_active
              AND u.is_active
        $$
        """
    )
    app_role = make_url(get_settings().database_url).username
    quoted_role = op.get_bind().dialect.identifier_preparer.quote(app_role or "")
    op.execute("REVOKE ALL ON FUNCTION auth_lookup_user(text, text) FROM PUBLIC")
    op.execute(f"GRANT EXECUTE ON FUNCTION auth_lookup_user(text, text) TO {quoted_role}")


def downgrade() -> None:
    op.execute("DROP FUNCTION auth_lookup_user(text, text)")
