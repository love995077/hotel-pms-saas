import asyncio
from uuid import UUID

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy import select

from app.api.deps import (
    BILLING,
    LEDGER_CONTROL,
    CurrentUser,
    DbSession,
    get_current_user,
    require_roles,
)
from app.core.exceptions import NotFoundError
from app.models import Folio, FolioTransaction, Reservation
from app.schemas.billing import (
    ChargeCreate,
    FolioDetailRead,
    FolioOpen,
    FolioRead,
    FolioTransactionRead,
    PaymentCreate,
    ReversalCreate,
)
from app.services import folios as service
from app.services.crud import get_or_404
from app.services.invoices import prepare_invoice, render_invoice_pdf

router = APIRouter(prefix="/folios", tags=["folios"], dependencies=[Depends(get_current_user)])
_billing = Depends(require_roles(*BILLING))
_ledger_control = Depends(require_roles(*LEDGER_CONTROL))


async def _detail(db: DbSession, folio: Folio) -> FolioDetailRead:
    totals = await service.folio_totals(db, folio.id)
    transactions = await service.list_transactions(db, folio.id)
    return FolioDetailRead(
        **FolioRead.model_validate(folio).model_dump(),
        total_debits=totals.total_debits,
        total_credits=totals.total_credits,
        balance=totals.balance,
        transactions=[FolioTransactionRead.model_validate(t) for t in transactions],
    )


@router.post("", response_model=FolioDetailRead, dependencies=[_billing])
async def open_folio(data: FolioOpen, db: DbSession) -> FolioDetailRead:
    """Open the folio for a reservation, or return it if it already exists.

    Folios open automatically at check-in; use this to take an advance earlier.
    """
    reservation = await get_or_404(db, Reservation, data.reservation_id)
    return await _detail(db, await service.ensure_folio(db, reservation))


@router.get("", response_model=FolioDetailRead)
async def get_folio_for_reservation(reservation_id: UUID, db: DbSession) -> FolioDetailRead:
    folio = await db.scalar(select(Folio).where(Folio.reservation_id == reservation_id))
    if folio is None:
        raise NotFoundError("Folio not found")
    return await _detail(db, folio)


@router.get("/{folio_id}", response_model=FolioDetailRead)
async def get_folio(folio_id: UUID, db: DbSession) -> FolioDetailRead:
    return await _detail(db, await get_or_404(db, Folio, folio_id))


@router.post(
    "/{folio_id}/charges",
    response_model=FolioTransactionRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[_billing],
)
async def post_charge(
    folio_id: UUID, data: ChargeCreate, db: DbSession, user: CurrentUser
) -> FolioTransaction:
    return await service.post_charge(
        db,
        folio_id,
        description=data.description,
        amount=data.amount,
        gst_rate=data.gst_rate,
        sac_code=data.sac_code,
        business_date=data.business_date,
        created_by=user.id,
    )


@router.post(
    "/{folio_id}/payments",
    response_model=FolioTransactionRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[_billing],
)
async def post_payment(
    folio_id: UUID, data: PaymentCreate, db: DbSession, user: CurrentUser
) -> FolioTransaction:
    return await service.post_payment(
        db,
        folio_id,
        amount=data.amount,
        payment_method=data.payment_method,
        reference=data.reference,
        created_by=user.id,
    )


@router.post(
    "/{folio_id}/transactions/{transaction_id}/reverse",
    response_model=FolioTransactionRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[_ledger_control],
)
async def reverse_transaction(
    folio_id: UUID, transaction_id: UUID, data: ReversalCreate, db: DbSession, user: CurrentUser
) -> FolioTransaction:
    """Ledger lines are never edited or deleted; this posts a compensating line."""
    return await service.reverse_transaction(
        db, folio_id, transaction_id, reason=data.reason, created_by=user.id
    )


@router.get(
    "/{folio_id}/invoice",
    dependencies=[_billing],
    response_class=Response,
    responses={
        200: {"content": {"application/pdf": {}}, "description": "The invoice as an A4 PDF"},
        409: {"description": "Nothing has been charged to the folio"},
    },
)
async def download_invoice(folio_id: UUID, db: DbSession) -> Response:
    """The folio's GST invoice as a PDF.

    A closed folio gets a tax invoice; its number is issued the first time this
    is called and stays the same afterwards. An open folio gets a pro forma
    invoice with no number.
    """
    invoice = await prepare_invoice(db, folio_id)
    # Laying out a PDF is CPU work; keep it off the event loop.
    pdf = await asyncio.to_thread(render_invoice_pdf, invoice)
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{invoice.filename}"',
            "Cache-Control": "no-store",
        },
    )


@router.post("/{folio_id}/close", response_model=FolioDetailRead, dependencies=[_billing])
async def close_folio(folio_id: UUID, db: DbSession) -> FolioDetailRead:
    return await _detail(db, await service.close_folio(db, folio_id))
