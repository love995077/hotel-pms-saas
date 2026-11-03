"""webhook deliveries can be logged as ignored (authenticated, but not a booking)

Revision ID: 0009
Revises: 0008
Create Date: 2026-11-03
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "channel_webhook_events"
_NAME = "ck_channel_webhook_events_status_valid"
# What migration 0005 actually created: its explicit name went through the
# naming convention a second time and was then shortened by PostgreSQL.
_LEGACY_NAME = "ck_channel_webhook_events_ck_channel_webhook_events_sta_341a"


def upgrade() -> None:
    # Either name may be present: the legacy one on databases built by 0005,
    # the clean one on a database that has been downgraded past this revision.
    for name in (_LEGACY_NAME, _NAME):
        op.execute(f"ALTER TABLE {_TABLE} DROP CONSTRAINT IF EXISTS {name}")
    op.create_check_constraint(
        op.f(_NAME), _TABLE, "status IN ('processed', 'duplicate', 'rejected', 'ignored')"
    )


def downgrade() -> None:
    op.execute(f"DELETE FROM {_TABLE} WHERE status = 'ignored'")  # noqa: S608
    op.drop_constraint(op.f(_NAME), _TABLE, type_="check")
    op.create_check_constraint(
        op.f(_NAME), _TABLE, "status IN ('processed', 'duplicate', 'rejected')"
    )
