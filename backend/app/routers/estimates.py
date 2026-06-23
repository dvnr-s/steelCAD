"""
Estimates router.

An estimate belongs to a customer and contains multiple frames (doors/windows),
each with its own geometry and quantity. Frame line totals are aggregated and
estimate-level discount / GST / advance are applied to the total.

Also exposes a stateless POST /price used by the canvas for live unit pricing.
"""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload, joinedload
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.customer import Customer
from app.models.design import Design
from app.models.estimate import Estimate, EstimateFrame
from app.models.rate import Rate
from app.models.user import User
from app.schemas.estimate import (
    PriceRequest, UnitBreakdown, FrameInput, FrameUpdate, FrameDetail,
    EstimateCreate, EstimateUpdate, EstimateDetail, EstimateSummary, CustomerBrief,
)
from app.services.auth import get_current_user
from app.services.pricing import price_design, _apply_commercial_terms, _round2
from app.services.validation import validate_design_tree
from app.services.pdf import generate_estimate_pdf

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
    )
    estimate.rate_snapshot = snapshot
    estimate.subtotal = subtotal
    estimate.discount_amount = terms["discount_amount"]
    estimate.taxable = terms["taxable"]
    estimate.gst = terms["gst"]
    estimate.grand_total = terms["grand_total"]
    estimate.advance_amount = terms["advance_amount"]


def _detail(estimate: Estimate) -> EstimateDetail:
    return EstimateDetail(
        id=estimate.id,
        number=estimate.number,
        title=estimate.title,
        notes=estimate.notes,
        status=estimate.status,
        customer=CustomerBrief.model_validate(estimate.customer),
        discount_type=estimate.discount_type,
        discount_value=float(estimate.discount_value or 0),
        advance_pct=float(estimate.advance_pct or 0),
        frames=[FrameDetail.model_validate(f) for f in estimate.frames],
        subtotal=float(estimate.subtotal or 0),
        discount_amount=float(estimate.discount_amount or 0),
        taxable=float(estimate.taxable or 0),
        gst=float(estimate.gst or 0),
        grand_total=int(estimate.grand_total or 0),
        advance_amount=int(estimate.advance_amount or 0),
        created_at=estimate.created_at,
        updated_at=estimate.updated_at,
    )


async def _get_estimate_or_404(estimate_id: UUID, db: AsyncSession) -> Estimate:
    result = await db.execute(
        select(Estimate)
        .where(Estimate.id == estimate_id)
        .options(selectinload(Estimate.frames), joinedload(Estimate.customer))
    )
    estimate = result.scalar_one_or_none()
    if not estimate:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Estimate not found")
    return estimate


def _frame_fields_from_tree(tree: dict) -> dict:
    """Derive the denormalized frame columns from a geometry tree."""
    frame = tree.get("frame", {})
    return {
        "outer_width": tree.get("outerWidth", frame.get("width", 0)),
        "outer_height": tree.get("outerHeight", frame.get("height", 0)),
        "section_size": tree.get("sectionSize", "5"),
        "gauge": tree.get("gauge", "18G"),
    }


# ─── Stateless price preview ────────────────────────────────────────

@router.post("/price", response_model=UnitBreakdown, summary="Price a geometry tree (no persistence)")
async def price_preview(
    data: PriceRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
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

    next_number = (await db.execute(select(func.coalesce(func.max(Estimate.number), 0)))).scalar() + 1

    estimate = Estimate(
        customer_id=customer_id,
        number=next_number,
        title=data.title,
        notes=data.notes,
        discount_type=data.discount_type,
        discount_value=data.discount_value,
        advance_pct=data.advance_pct,
        created_by=user.id,
    )
    estimate.customer = customer  # populate relationship to avoid an async lazy-load
    estimate.frames = []          # initialize collection so _recompute doesn't lazy-load
    db.add(estimate)
    await db.flush()
    await _recompute(estimate, db)
    await db.flush()
    return _detail(estimate)


@router.get(
    "/customers/{customer_id}/estimates",
    response_model=list[EstimateSummary],
    summary="List a customer's estimates",
)
async def list_estimates(
    customer_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Estimate).where(Estimate.customer_id == customer_id).order_by(Estimate.number.desc())
    )
    estimates = result.scalars().all()
    return [
        EstimateSummary(
            id=e.id, number=e.number, title=e.title, status=e.status,
            customer_id=e.customer_id, customer_name=e.customer.name,
            frame_count=len(e.frames), grand_total=int(e.grand_total or 0),
            created_at=e.created_at, updated_at=e.updated_at,
        )
        for e in estimates
    ]


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
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(estimate, field, value)
    await _recompute(estimate, db)
    await db.flush()
    return _detail(estimate)


@router.delete("/estimates/{estimate_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete an estimate")
async def delete_estimate(
    estimate_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    estimate = await _get_estimate_or_404(estimate_id, db)
    await db.delete(estimate)


# ─── Frames within an estimate ──────────────────────────────────────

@router.post("/estimates/{estimate_id}/frames", response_model=EstimateDetail, summary="Add a frame")
async def add_frame(
    estimate_id: UUID,
    data: FrameInput,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    estimate = await _get_estimate_or_404(estimate_id, db)

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


@router.delete("/estimates/{estimate_id}/frames/{frame_id}", response_model=EstimateDetail, summary="Remove a frame")
async def delete_frame(
    estimate_id: UUID,
    frame_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    estimate = await _get_estimate_or_404(estimate_id, db)
    frame = next((f for f in estimate.frames if f.id == frame_id), None)
    if not frame:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Frame not found")
    await db.delete(frame)
    await db.flush()
    await db.refresh(estimate, ["frames"])
    await _recompute(estimate, db)
    await db.flush()
    return _detail(estimate)


# ─── PDF ────────────────────────────────────────────────────────────

@router.get("/estimates/{estimate_id}/pdf", summary="Download estimate as PDF", response_class=Response)
async def download_estimate_pdf(
    estimate_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    estimate = await _get_estimate_or_404(estimate_id, db)
    pdf_bytes = generate_estimate_pdf(estimate)
    filename = f"SteelCAD_Estimate_EST-{estimate.number:04d}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
