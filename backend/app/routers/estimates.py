"""
Estimates router.

An estimate belongs to a customer and contains multiple frames (doors/windows),
each with its own geometry and quantity. Frame line totals are aggregated and
estimate-level discount / GST / advance are applied to the total.

Also exposes a stateless POST /price used by the canvas for live unit pricing.
"""
import csv
import io
from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import Response
from sqlalchemy import select, func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload, joinedload, noload
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.customer import Customer
from app.models.design import Design
from app.models.estimate import Estimate, EstimateFrame
from app.models.rate import Rate
from app.models.user import User, ROLE_ADMIN, ROLE_OWNER
from app.schemas.estimate import (
    PriceRequest, UnitBreakdown, FrameInput, FrameUpdate, FrameDetail,
    EstimateCreate, EstimateUpdate, EstimateStatusUpdate, EstimateDetail,
    EstimateSummary, CustomerBrief,
)
from app.services.auth import get_current_user, require_role
from app.services.access import assert_can_write, assert_editable
from app.services.ratelimit import limiter
from app.services.audit import record_audit
from app.services.pricing import price_design, _apply_commercial_terms, _round2, sum_other_charges
from app.services.validation import validate_design_tree, validate_tree_bounds
from app.services.bom import build_bom
from app.services.pdf import generate_estimate_pdf
from app.routers.settings import get_or_create_company

router = APIRouter(tags=["Estimates"])


# ─── Helpers ────────────────────────────────────────────────────────

async def _load_rates(db: AsyncSession) -> tuple[dict, dict]:
    """Return (values, snapshot) for the current rate table."""
    rows = (await db.execute(select(Rate))).scalars().all()
    values = {r.item_code: float(r.rate) for r in rows}
    snapshot = {
        r.item_code: {"rate": float(r.rate), "unit": r.unit, "label": r.label}
        for r in rows
    }
    return values, snapshot


async def _recompute(estimate: Estimate, db: AsyncSession) -> None:
    """Re-price every frame and roll up the estimate totals (mutates in place)."""
    values, snapshot = await _load_rates(db)
    subtotal = 0.0
    for fr in estimate.frames:
        try:
            unit = price_design(fr.tree_json, values, discount_type=None, discount_value=0, advance_pct=0)
        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Pricing error in frame '{fr.name}': {e}",
            )
        fr.unit_breakdown = unit
        fr.unit_subtotal = unit["subtotal"]
        fr.line_total = _round2(unit["subtotal"] * fr.quantity)
        subtotal += fr.line_total

    subtotal = _round2(subtotal)
    terms = _apply_commercial_terms(
        subtotal, estimate.discount_type,
        float(estimate.discount_value or 0), float(estimate.advance_pct or 0),
        # The estimate's FROZEN snapshot — a company GST change must never
        # silently reprice an existing estimate through a recompute.
        gst_pct=float(estimate.gst_pct if estimate.gst_pct is not None else 18),
        other_charges=estimate.other_charges or [],
    )
    estimate.rate_snapshot = snapshot
    estimate.subtotal = subtotal
    estimate.discount_amount = terms["discount_amount"]
    estimate.taxable = terms["taxable"]
    estimate.gst = terms["gst"]
    estimate.grand_total = terms["grand_total"]
    estimate.advance_amount = terms["advance_amount"]


def _is_expired(estimate: Estimate) -> bool:
    """Derived at read time — self-correcting when valid_until is edited, no
    scheduler needed. Only a live 'sent' quote can be expired; accepting an
    expired quote remains allowed (business calls that judgement)."""
    return (
        estimate.status == "sent"
        and estimate.valid_until is not None
        and estimate.valid_until < datetime.now(timezone.utc).date()
    )


def _detail(estimate: Estimate) -> EstimateDetail:
    return EstimateDetail(
        id=estimate.id,
        number=estimate.number,
        revision=estimate.revision or 1,
        parent_id=estimate.parent_id,
        title=estimate.title,
        notes=estimate.notes,
        status=estimate.status,
        quote_date=estimate.quote_date,
        valid_until=estimate.valid_until,
        terms=estimate.terms,
        customer=CustomerBrief.model_validate(estimate.customer),
        discount_type=estimate.discount_type,
        discount_value=float(estimate.discount_value or 0),
        advance_pct=float(estimate.advance_pct or 0),
        gst_pct=float(estimate.gst_pct if estimate.gst_pct is not None else 18),
        is_expired=_is_expired(estimate),
        frames=[FrameDetail.model_validate(f) for f in estimate.frames],
        subtotal=float(estimate.subtotal or 0),
        other_charges=estimate.other_charges or [],
        other_charges_total=sum_other_charges(estimate.other_charges),
        discount_amount=float(estimate.discount_amount or 0),
        taxable=float(estimate.taxable or 0),
        gst=float(estimate.gst or 0),
        grand_total=int(estimate.grand_total or 0),
        advance_amount=int(estimate.advance_amount or 0),
        created_at=estimate.created_at,
        updated_at=estimate.updated_at,
    )


async def _assign_unique_number(estimate: Estimate, db: AsyncSession) -> None:
    """Allocate the next EST-#### number with a retry loop guarding the UNIQUE
    constraint against concurrent creates. The estimate must already be db.add()'ed."""
    for _ in range(5):
        # no_autoflush: the pending estimate has number=None and would violate
        # NOT NULL if this SELECT triggered an autoflush.
        with db.no_autoflush:
            estimate.number = (
                await db.execute(select(func.coalesce(func.max(Estimate.number), 0)))
            ).scalar() + 1
        try:
            async with db.begin_nested():
                await db.flush()
            return
        except IntegrityError:
            continue
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail="Could not allocate an estimate number — please retry.",
    )


async def _get_estimate_or_404(
    estimate_id: UUID, db: AsyncSession, *,
    include_deleted: bool = False, for_update: bool = False,
) -> Estimate:
    conditions = [Estimate.id == estimate_id]
    if not include_deleted:
        conditions.append(Estimate.deleted_at.is_(None))
    stmt = (
        select(Estimate)
        .where(*conditions)
        .options(selectinload(Estimate.frames), joinedload(Estimate.customer))
    )
    if for_update:
        # Serializes concurrent frame mutations on one estimate (sort_order
        # allocation). OF Estimate locks only the estimates row — Postgres
        # forbids locking the nullable side of the customer outer join.
        stmt = stmt.with_for_update(of=Estimate)
    result = await db.execute(stmt)
    estimate = result.scalar_one_or_none()
    if not estimate:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Estimate not found")
    return estimate


def _summary_stmt():
    """Summary-list query: frames are NOT loaded (each frame's JSONB tree is heavy
    and `lazy=\"selectin\"` would pull all of them); frame_count comes from a
    correlated COUNT subquery instead."""
    frame_count = (
        select(func.count(EstimateFrame.id))
        .where(EstimateFrame.estimate_id == Estimate.id)
        .correlate(Estimate)
        .scalar_subquery()
    )
    return select(Estimate, frame_count.label("frame_count")).options(noload(Estimate.frames))


def _summary(e: Estimate, frame_count: int) -> EstimateSummary:
    return EstimateSummary(
        id=e.id, number=e.number, revision=e.revision or 1, title=e.title, status=e.status,
        customer_id=e.customer_id, customer_name=e.customer.name,
        frame_count=frame_count, grand_total=int(e.grand_total or 0),
        is_expired=_is_expired(e),
        created_at=e.created_at, updated_at=e.updated_at,
    )


def _frame_fields_from_tree(tree: dict) -> dict:
    """Derive the denormalized frame columns from a geometry tree."""
    frame = tree.get("frame", {})
    return {
        "outer_width": tree.get("outerWidth", frame.get("width", 0)),
        "outer_height": tree.get("outerHeight", frame.get("height", 0)),
        "section_size": tree.get("sectionSize", "5"),
        "gauge": tree.get("gauge", "18G"),
    }


def _copy_estimate(
    source: Estimate, user: User, *, gst_pct: float,
    title: str | None = None, revision: int = 1, parent_id: UUID | None = None,
    quote_date=None, valid_until=None,
) -> Estimate:
    """Deep-copy an estimate (terms + frames) as a fresh draft. Used by
    duplicate (new number, rev 1) and revise (same number, rev+1)."""
    copy = Estimate(
        customer_id=source.customer_id,
        number=source.number if revision > 1 else None,  # revise keeps the number
        title=title if title is not None else source.title,
        notes=source.notes,
        terms=source.terms,
        quote_date=quote_date or datetime.now(timezone.utc).date(),
        valid_until=valid_until or source.valid_until,
        status="draft",
        discount_type=source.discount_type,
        discount_value=source.discount_value,
        advance_pct=source.advance_pct,
        gst_pct=gst_pct,
        other_charges=list(source.other_charges or []),
        revision=revision,
        parent_id=parent_id,
        created_by=user.id,
    )
    copy.customer = source.customer  # populate relationship to avoid an async lazy-load
    copy.frames = [
        EstimateFrame(
            source_design_id=f.source_design_id,
            name=f.name,
            tree_json=f.tree_json,
            quantity=f.quantity,
            sort_order=f.sort_order,
            **_frame_fields_from_tree(f.tree_json),
        )
        for f in source.frames
    ]
    return copy


# ─── Stateless price preview ────────────────────────────────────────

@router.post("/price", response_model=UnitBreakdown, summary="Price a geometry tree (no persistence)")
@limiter.limit("120/minute")
async def price_preview(
    request: Request,
    data: PriceRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    # Bounds only — previews price in-progress trees, so full validation
    # would reject legitimate intermediate states.
    bounds_errors = validate_tree_bounds(data.tree_json)
    if bounds_errors:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"validation_errors": bounds_errors},
        )
    values, _ = await _load_rates(db)
    try:
        return price_design(data.tree_json, values, discount_type=None, discount_value=0, advance_pct=0)
    except (ValueError, KeyError) as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"Pricing error: {e}")


# ─── Estimates under a customer ─────────────────────────────────────

@router.post(
    "/customers/{customer_id}/estimates",
    response_model=EstimateDetail,
    status_code=status.HTTP_201_CREATED,
    summary="Create an estimate for a customer",
)
async def create_estimate(
    customer_id: UUID,
    data: EstimateCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    customer = (await db.execute(select(Customer).where(Customer.id == customer_id))).scalar_one_or_none()
    if not customer:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found")

    company = await get_or_create_company(db)
    today = datetime.now(timezone.utc).date()
    estimate = Estimate(
        customer_id=customer_id,
        title=data.title,
        notes=data.notes,
        terms=data.terms,
        quote_date=today,
        # Default a 30-day validity window when the caller doesn't specify one.
        valid_until=data.valid_until or (today + timedelta(days=30)),
        discount_type=data.discount_type,
        discount_value=data.discount_value,
        # Company defaults: advance falls back when omitted; GST is snapshotted
        # so later settings changes never reprice this estimate.
        advance_pct=data.advance_pct if data.advance_pct is not None else float(company.default_advance_pct),
        gst_pct=float(company.gst_pct),
        other_charges=[c.model_dump() for c in data.other_charges],
        created_by=user.id,
    )
    estimate.customer = customer  # populate relationship to avoid an async lazy-load
    estimate.frames = []          # initialize collection so _recompute doesn't lazy-load
    db.add(estimate)
    await _assign_unique_number(estimate, db)
    await _recompute(estimate, db)
    await db.flush()
    await record_audit(db, user, "estimate.create", "estimate", estimate.id,
                       f"EST-{estimate.number:04d} for {customer.name}")
    return _detail(estimate)


@router.get(
    "/customers/{customer_id}/estimates",
    response_model=list[EstimateSummary],
    summary="List a customer's estimates",
)
async def list_estimates(
    customer_id: UUID,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    q: str | None = Query(None, description="Search title; a numeric term also matches the estimate number"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    customer = (await db.execute(
        select(Customer).where(Customer.id == customer_id, Customer.deleted_at.is_(None))
    )).scalar_one_or_none()
    if not customer:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found")

    stmt = _summary_stmt().where(
        Estimate.customer_id == customer_id, Estimate.deleted_at.is_(None)
    )
    if q and q.strip():
        term = q.strip()
        conds = [Estimate.title.ilike(f"%{term}%")]
        if term.isdigit():
            conds.append(Estimate.number == int(term))
        stmt = stmt.where(or_(*conds))
    rows = (await db.execute(
        stmt.order_by(Estimate.number.desc()).offset(offset).limit(limit)
    )).all()
    return [_summary(e, fc) for e, fc in rows]


@router.get("/estimates", response_model=list[EstimateSummary], summary="Search estimates across all customers")
async def search_estimates(
    q: str | None = Query(None, description="Search title / customer name; a numeric term also matches the number"),
    status_filter: str | None = Query(None, alias="status"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    stmt = (
        _summary_stmt()
        .join(Customer, Customer.id == Estimate.customer_id)
        .where(Estimate.deleted_at.is_(None), Customer.deleted_at.is_(None))
    )
    if status_filter:
        stmt = stmt.where(Estimate.status == status_filter)
    if q and q.strip():
        term = q.strip()
        conds = [
            Estimate.title.ilike(f"%{term}%"),
            Customer.name.ilike(f"%{term}%"),
        ]
        if term.isdigit():
            conds.append(Estimate.number == int(term))
        stmt = stmt.where(or_(*conds))
    rows = (await db.execute(
        stmt.order_by(Estimate.updated_at.desc()).offset(offset).limit(limit)
    )).all()
    return [_summary(e, fc) for e, fc in rows]


@router.get("/estimates/{estimate_id}", response_model=EstimateDetail, summary="Get an estimate")
async def get_estimate(
    estimate_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    estimate = await _get_estimate_or_404(estimate_id, db)
    return _detail(estimate)


@router.put("/estimates/{estimate_id}", response_model=EstimateDetail, summary="Update estimate terms")
async def update_estimate(
    estimate_id: UUID,
    data: EstimateUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    estimate = await _get_estimate_or_404(estimate_id, db)
    assert_can_write(estimate, user)
    assert_editable(estimate)
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(estimate, field, value)
    await _recompute(estimate, db)
    await db.flush()
    return _detail(estimate)


@router.patch("/estimates/{estimate_id}/status", response_model=EstimateDetail, summary="Change estimate status")
async def set_estimate_status(
    estimate_id: UUID,
    data: EstimateStatusUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Move an estimate through its lifecycle (draft → sent → accepted/rejected).
    Always allowed (this is how a locked estimate is reopened to draft) — EXCEPT
    superseded, which is terminal. 'superseded' itself is not settable here (it
    only happens via /revise; the request schema rejects it)."""
    estimate = await _get_estimate_or_404(estimate_id, db)
    assert_can_write(estimate, user)
    if estimate.status == "superseded":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Superseded revisions are immutable — work with the latest revision.",
        )
    if data.status == "accepted" and estimate.status != "accepted":
        estimate.accepted_at = datetime.now(timezone.utc)
    elif data.status != "accepted":
        estimate.accepted_at = None  # un-accepting removes it from revenue
    estimate.status = data.status
    await db.flush()
    await record_audit(db, user, "estimate.status", "estimate", estimate.id,
                       f"EST-{estimate.number:04d} → {data.status}")
    return _detail(estimate)


@router.delete("/estimates/{estimate_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete an estimate")
async def delete_estimate(
    estimate_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(ROLE_ADMIN, ROLE_OWNER)),
):
    estimate = await _get_estimate_or_404(estimate_id, db)
    # Soft-delete: recoverable via POST /estimates/{id}/restore.
    estimate.deleted_at = datetime.now(timezone.utc)
    await record_audit(db, user, "estimate.delete", "estimate", estimate.id, f"EST-{estimate.number:04d}")


@router.post("/estimates/{estimate_id}/restore", response_model=EstimateDetail, summary="Restore a soft-deleted estimate")
async def restore_estimate(
    estimate_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(ROLE_ADMIN, ROLE_OWNER)),
):
    estimate = await _get_estimate_or_404(estimate_id, db, include_deleted=True)
    if estimate.customer.deleted_at is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Restore the customer first — this estimate belongs to a deleted customer.",
        )
    estimate.deleted_at = None
    await db.flush()
    await record_audit(db, user, "estimate.restore", "estimate", estimate.id,
                       f"EST-{estimate.number:04d}")
    return _detail(estimate)


@router.post(
    "/estimates/{estimate_id}/duplicate",
    response_model=EstimateDetail,
    status_code=status.HTTP_201_CREATED,
    summary="Duplicate an estimate (new draft, frames copied)",
)
async def duplicate_estimate(
    estimate_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    source = await _get_estimate_or_404(estimate_id, db)
    company = await get_or_create_company(db)
    title = (source.title or f"EST-{source.number:04d}")
    copy = _copy_estimate(source, user, gst_pct=float(company.gst_pct), title=f"{title} (copy)")
    db.add(copy)
    await _assign_unique_number(copy, db)
    await _recompute(copy, db)
    await db.flush()
    return _detail(copy)


@router.post(
    "/estimates/{estimate_id}/revise",
    response_model=EstimateDetail,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new revision of a locked estimate (source becomes superseded)",
)
async def revise_estimate(
    estimate_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Copy a sent/accepted/rejected quote as `number` rev `revision+1` (a fresh
    draft) and mark the source superseded. Unlike reopen-to-draft, this never
    mutates what the customer was actually sent."""
    source = await _get_estimate_or_404(estimate_id, db)
    assert_can_write(source, user)
    if source.status == "draft":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Draft estimates are edited directly — Revise is for locked (sent/accepted/rejected) quotes.",
        )
    if source.status == "superseded":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This revision was already superseded — revise the latest revision instead.",
        )

    company = await get_or_create_company(db)
    today = datetime.now(timezone.utc).date()
    copy = _copy_estimate(
        source, user,
        gst_pct=float(company.gst_pct),   # a revision is a new quote — fresh GST snapshot
        revision=source.revision + 1,
        parent_id=source.id,
        quote_date=today,
        valid_until=today + timedelta(days=30),
    )
    db.add(copy)
    try:
        # SAVEPOINT guards UNIQUE(number, revision): a concurrent revise of the
        # same source loses the race without poisoning the transaction.
        async with db.begin_nested():
            await db.flush()
    except IntegrityError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Someone just created this revision — reload and revise the latest revision.",
        )
    source.status = "superseded"
    await _recompute(copy, db)
    await db.flush()
    await record_audit(db, user, "estimate.revise", "estimate", copy.id,
                       f"EST-{copy.number:04d} rev {copy.revision} (supersedes rev {source.revision})")
    return _detail(copy)


# ─── Frames within an estimate ──────────────────────────────────────

@router.post("/estimates/{estimate_id}/frames", response_model=EstimateDetail, summary="Add a frame")
async def add_frame(
    estimate_id: UUID,
    data: FrameInput,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    estimate = await _get_estimate_or_404(estimate_id, db, for_update=True)
    assert_can_write(estimate, user)
    assert_editable(estimate)

    # Resolve the geometry tree: from the library design, or a provided one-off tree.
    tree = data.tree_json
    name = data.name
    source_design_id = data.source_design_id
    if source_design_id:
        design = (await db.execute(select(Design).where(Design.id == source_design_id))).scalar_one_or_none()
        if not design:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Source design not found")
        tree = design.tree_json
        name = name or design.name
    if not tree:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Provide either source_design_id or tree_json",
        )

    errors = validate_design_tree(tree)
    if errors:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"validation_errors": errors},
        )

    next_order = max((f.sort_order for f in estimate.frames), default=-1) + 1
    frame = EstimateFrame(
        estimate_id=estimate.id,
        source_design_id=source_design_id,
        name=name or "Frame",
        tree_json=tree,
        quantity=data.quantity,
        sort_order=next_order,
        **_frame_fields_from_tree(tree),
    )
    db.add(frame)
    await db.flush()
    await db.refresh(estimate, ["frames"])  # pull the new frame into the collection
    await _recompute(estimate, db)
    await db.flush()
    return _detail(estimate)


@router.put("/estimates/{estimate_id}/frames/{frame_id}", response_model=EstimateDetail, summary="Update a frame")
async def update_frame(
    estimate_id: UUID,
    frame_id: UUID,
    data: FrameUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    estimate = await _get_estimate_or_404(estimate_id, db)
    assert_can_write(estimate, user)
    assert_editable(estimate)
    frame = next((f for f in estimate.frames if f.id == frame_id), None)
    if not frame:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Frame not found")

    if data.name is not None:
        frame.name = data.name
    if data.quantity is not None:
        frame.quantity = data.quantity
    if data.tree_json is not None:
        errors = validate_design_tree(data.tree_json)
        if errors:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={"validation_errors": errors},
            )
        frame.tree_json = data.tree_json
        for field, value in _frame_fields_from_tree(data.tree_json).items():
            setattr(frame, field, value)

    await _recompute(estimate, db)
    await db.flush()
    return _detail(estimate)


@router.post("/estimates/{estimate_id}/frames/{frame_id}/duplicate", response_model=EstimateDetail, summary="Duplicate a frame")
async def duplicate_frame(
    estimate_id: UUID,
    frame_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    estimate = await _get_estimate_or_404(estimate_id, db, for_update=True)
    assert_can_write(estimate, user)
    assert_editable(estimate)
    src = next((f for f in estimate.frames if f.id == frame_id), None)
    if not src:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Frame not found")

    next_order = max((f.sort_order for f in estimate.frames), default=-1) + 1
    db.add(EstimateFrame(
        estimate_id=estimate.id,
        source_design_id=src.source_design_id,
        name=f"{src.name} (copy)",
        tree_json=src.tree_json,
        quantity=src.quantity,
        sort_order=next_order,
        **_frame_fields_from_tree(src.tree_json),
    ))
    await db.flush()
    await db.refresh(estimate, ["frames"])
    await _recompute(estimate, db)
    await db.flush()
    return _detail(estimate)


@router.delete("/estimates/{estimate_id}/frames/{frame_id}", response_model=EstimateDetail, summary="Remove a frame")
async def delete_frame(
    estimate_id: UUID,
    frame_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    estimate = await _get_estimate_or_404(estimate_id, db)
    assert_can_write(estimate, user)
    assert_editable(estimate)
    frame = next((f for f in estimate.frames if f.id == frame_id), None)
    if not frame:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Frame not found")
    await db.delete(frame)
    await db.flush()
    await db.refresh(estimate, ["frames"])
    await _recompute(estimate, db)
    await db.flush()
    return _detail(estimate)


# ─── BOM CSV ────────────────────────────────────────────────────────

@router.get("/estimates/{estimate_id}/bom.csv", summary="Download the bill of materials as CSV", response_class=Response)
async def download_estimate_bom_csv(
    estimate_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    estimate = await _get_estimate_or_404(estimate_id, db)
    bom = build_bom([
        {"quantity": f.quantity, "breakdown": f.unit_breakdown or {}}
        for f in estimate.frames
    ])
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["Item", "Quantity", "Unit", "Cost"])
    for row in bom:
        writer.writerow([row["label"], row["quantity"], row["unit"], row["cost"]])

    rev_suffix = f"_rev{estimate.revision}" if (estimate.revision or 1) > 1 else ""
    filename = f"SteelCAD_BOM_EST-{estimate.number:04d}{rev_suffix}.csv"
    # UTF-8 BOM so Excel decodes ₹ (and any non-ASCII labels) correctly.
    return Response(
        content=("\ufeff" + buf.getvalue()).encode("utf-8"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ─── PDF ────────────────────────────────────────────────────────────

@router.get("/estimates/{estimate_id}/pdf", summary="Download estimate as PDF", response_class=Response)
@limiter.limit("10/minute")  # WeasyPrint rendering is CPU-heavy
async def download_estimate_pdf(
    request: Request,
    estimate_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    estimate = await _get_estimate_or_404(estimate_id, db)
    company = await get_or_create_company(db)
    pdf_bytes = generate_estimate_pdf(estimate, company)
    rev_suffix = f"_rev{estimate.revision}" if (estimate.revision or 1) > 1 else ""
    filename = f"SteelCAD_Estimate_EST-{estimate.number:04d}{rev_suffix}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
