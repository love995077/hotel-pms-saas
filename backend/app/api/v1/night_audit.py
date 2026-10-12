from collections.abc import Sequence
from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select

from app.api.deps import LEDGER_CONTROL, CurrentUser, DbSession, get_current_user, require_roles
from app.models import NightAuditRun
from app.schemas.billing import NightAuditRequest, NightAuditRunRead
from app.services.folios import hotel_today
from app.services.night_audit import run_night_audit

router = APIRouter(
    prefix="/night-audit", tags=["night audit"], dependencies=[Depends(get_current_user)]
)


@router.post(
    "/run",
    response_model=NightAuditRunRead,
    dependencies=[Depends(require_roles(*LEDGER_CONTROL))],
)
async def run(data: NightAuditRequest, db: DbSession, user: CurrentUser) -> NightAuditRun:
    """Run the night audit now. Normally the scheduler does this every night."""
    business_date = data.business_date or await hotel_today(db) - timedelta(days=1)
    return await run_night_audit(db, business_date, run_by=user.id)


@router.get("/runs", response_model=list[NightAuditRunRead])
async def list_runs(
    db: DbSession,
    limit: Annotated[int, Query(ge=1, le=366)] = 31,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Sequence[NightAuditRun]:
    statement = (
        select(NightAuditRun)
        .order_by(NightAuditRun.business_date.desc())
        .limit(limit)
        .offset(offset)
    )
    return (await db.scalars(statement)).all()
