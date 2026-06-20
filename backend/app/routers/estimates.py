"""
Estimates router — generate estimates, list versions, get details, download PDF.
"""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.design import Design
from app.models.estimate import EstimateVersion
from app.models.rate import Rate
from app.models.user import User
from app.schemas.estimate import EstimateRequest, EstimateResponse, EstimateListItem
from app.services.auth import get_current_user
from app.services.pricing import price_design
from app.services.pdf import generate_estimate_pdf

router = APIRouter(tags=["Estimates"])


@router.post(
    "/designs/{design_id}/estimate",
    response_model=EstimateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Generate an estimate for a design",
)
async def create_estimate(
    design_id: UUID,
    data: EstimateRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    # Load design
    result = await db.execute(select(Design).where(Design.id == design_id))
    design = result.scalar_one_or_none()
    if not design:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Design not found")

    # Load current rates as snapshot (PR-6)
    rates_result = await db.execute(select(Rate))
    rates_rows = rates_result.scalars().all()
    rate_values = {r.item_code: float(r.rate) for r in rates_rows}
    rate_snapshot = {
        r.item_code: {"rate": float(r.rate), "unit": r.unit, "label": r.label}
        for r in rates_rows
    }

    # Run pricing engine
    try:
        breakdown = price_design(
            tree=design.tree_json,
            rates=rate_values,
            discount_type=data.discount_type,
            discount_value=data.discount_value,
            advance_pct=data.advance_pct,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Pricing error: {e}",
        )

    # Get next version number
    version_result = await db.execute(
        select(func.coalesce(func.max(EstimateVersion.version_number), 0))
        .where(EstimateVersion.design_id == design_id)
    )
    next_version = version_result.scalar() + 1

    # Create immutable estimate version (PR-7)
    estimate = EstimateVersion(
        design_id=design_id,
        version_number=next_version,
        rate_snapshot=rate_snapshot,
        breakdown_json=breakdown,
        subtotal=breakdown["subtotal"],
        discount_type=data.discount_type,
        discount_value=data.discount_value,
        taxable=breakdown["taxable"],
        gst=breakdown["gst"],
        grand_total=breakdown["grand_total"],
        advance_pct=data.advance_pct,
    )
    db.add(estimate)
    await db.flush()
    await db.refresh(estimate)

    return EstimateResponse(
        id=estimate.id,
        design_id=estimate.design_id,
        version_number=estimate.version_number,
        breakdown=breakdown,
        rate_snapshot=rate_snapshot,
        created_at=estimate.created_at,
    )


@router.get(
    "/designs/{design_id}/estimates",
    response_model=list[EstimateListItem],
    summary="List estimate versions for a design",
)
async def list_estimates(
    design_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(EstimateVersion)
        .where(EstimateVersion.design_id == design_id)
        .order_by(EstimateVersion.version_number.desc())
    )
    estimates = result.scalars().all()
    return [
        EstimateListItem(
            id=e.id,
            version_number=e.version_number,
            grand_total=e.grand_total,
            created_at=e.created_at,
        )
        for e in estimates
    ]


@router.get(
    "/estimates/{estimate_id}",
    response_model=EstimateResponse,
    summary="Get a specific estimate version",
)
async def get_estimate(
    estimate_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(EstimateVersion).where(EstimateVersion.id == estimate_id)
    )
    estimate = result.scalar_one_or_none()
    if not estimate:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Estimate not found")

    return EstimateResponse(
        id=estimate.id,
        design_id=estimate.design_id,
        version_number=estimate.version_number,
        breakdown=estimate.breakdown_json,
        rate_snapshot=estimate.rate_snapshot,
        created_at=estimate.created_at,
    )


@router.get(
    "/estimates/{estimate_id}/pdf",
    summary="Download estimate as PDF",
    response_class=Response,
)
async def download_estimate_pdf(
    estimate_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(EstimateVersion).where(EstimateVersion.id == estimate_id)
    )
    estimate = result.scalar_one_or_none()
    if not estimate:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Estimate not found")

    # Load design for metadata
    design_result = await db.execute(
        select(Design).where(Design.id == estimate.design_id)
    )
    design = design_result.scalar_one_or_none()

    pdf_bytes = generate_estimate_pdf(
        design_name=design.name if design else "Unknown",
        design_dims=(
            f"{float(design.outer_width)}ft × {float(design.outer_height)}ft"
            if design else ""
        ),
        section_info=(
            f"{design.section_size}\" {design.gauge}"
            if design else ""
        ),
        breakdown=estimate.breakdown_json,
        rate_snapshot=estimate.rate_snapshot,
        version_number=estimate.version_number,
        created_at=estimate.created_at,
    )

    filename = (
        f"SteelCAD_Estimate_{design.name if design else 'Unknown'}"
        f"_v{estimate.version_number}.pdf"
    )

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
