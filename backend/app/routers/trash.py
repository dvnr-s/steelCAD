"""
Trash router — discover soft-deleted records so they can be restored.

Soft deletes were previously invisible: nothing listed them, so restore
endpoints were unreachable without knowing an ID. Admin/owner only, matching
the delete/restore role gate.
"""
from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.customer import Customer
from app.models.design import Design
from app.models.estimate import Estimate
from app.models.user import User, ROLE_ADMIN, ROLE_OWNER
from app.routers.estimates import _summary_stmt
from app.schemas.estimate import EstimateSummary
from app.services.auth import require_role

router = APIRouter(prefix="/trash", tags=["Trash"])

_LIMIT = 100  # per entity type — a single shop's trash never realistically exceeds this


class TrashedCustomer(BaseModel):
    id: UUID
    name: str
    company: Optional[str] = None
    phone: Optional[str] = None
    deleted_at: datetime

    model_config = {"from_attributes": True}


class TrashedDesign(BaseModel):
    id: UUID
    name: str
    description: Optional[str] = None
    deleted_at: datetime

    model_config = {"from_attributes": True}


class TrashedEstimate(EstimateSummary):
    deleted_at: datetime
    customer_deleted: bool = False  # restore requires the customer first


class TrashResponse(BaseModel):
    customers: list[TrashedCustomer]
    designs: list[TrashedDesign]
    estimates: list[TrashedEstimate]


@router.get("", response_model=TrashResponse, summary="List soft-deleted records (admin/owner)")
async def list_trash(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(ROLE_ADMIN, ROLE_OWNER)),
):
    customers = (await db.execute(
        select(Customer).where(Customer.deleted_at.is_not(None))
        .order_by(Customer.deleted_at.desc()).limit(_LIMIT)
    )).scalars().all()

    designs = (await db.execute(
        select(Design).where(Design.deleted_at.is_not(None))
        .order_by(Design.deleted_at.desc()).limit(_LIMIT)
    )).scalars().all()

    est_rows = (await db.execute(
        _summary_stmt().where(Estimate.deleted_at.is_not(None))
        .order_by(Estimate.deleted_at.desc()).limit(_LIMIT)
    )).all()

    return TrashResponse(
        customers=[TrashedCustomer.model_validate(c) for c in customers],
        designs=[TrashedDesign.model_validate(d) for d in designs],
        estimates=[
            TrashedEstimate(
                id=e.id, number=e.number, revision=e.revision or 1,
                title=e.title, status=e.status,
                customer_id=e.customer_id, customer_name=e.customer.name,
                frame_count=fc, grand_total=int(e.grand_total or 0),
                created_at=e.created_at, updated_at=e.updated_at,
                deleted_at=e.deleted_at,
                customer_deleted=e.customer.deleted_at is not None,
            )
            for e, fc in est_rows
        ],
    )
