"""outbound availability sync for channel connections

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-01
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Existing table: its RLS policy and (hotel_id, id) key already cover these.
    op.add_column("channel_connections", sa.Column("outbound_url", sa.String(2048), nullable=True))
    op.add_column(
        "channel_connections", sa.Column("last_push_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column("channel_connections", sa.Column("last_push_ok", sa.Boolean(), nullable=True))
    op.add_column(
        "channel_connections", sa.Column("last_push_detail", sa.String(300), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("channel_connections", "last_push_detail")
    op.drop_column("channel_connections", "last_push_ok")
    op.drop_column("channel_connections", "last_push_at")
    op.drop_column("channel_connections", "outbound_url")
