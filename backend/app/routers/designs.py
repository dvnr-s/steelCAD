"""
Designs router — CRUD operations for steel window/door designs.
Validates tree structure on create and update.
"""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.design import Design
from app.models.user import User
from app.schemas.design import (
    DesignCreate, DesignUpdate, DesignResponse, DesignListItem,
)
from app.services.auth import get_current_user
from app.services.validation import validate_design_tree

router = APIRouter(prefix="/designs", tags=["Designs"])


def _design_response(design: Design) -> DesignResponse:
    """Convert ORM Design to response schema."""
    return DesignResponse(
        id=design.id,
        name=design.name,
        description=design.description,
        tree_json=design.tree_json,
        outer_width=float(design.outer_width),
        outer_height=float(design.outer_height),
        section_size=design.section_size,
        gauge=design.gauge,
        created_by=design.created_by,
        created_by_name=design.creator.name if design.creator else "Unknown",
        created_at=design.created_at,
        updated_at=design.updated_at,
    )


@router.get("", response_model=list[DesignListItem], summary="List all designs")
async def list_designs(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Design)
        .order_by(Design.updated_at.desc())
        .offset(skip)
        .limit(limit)
    )
    designs = result.scalars().all()

    return [
        DesignListItem(
            id=d.id,
            name=d.name,
            description=d.description,
            product_type=(d.tree_json or {}).get("productType", "window"),
            outer_width=float(d.outer_width),
            outer_height=float(d.outer_height),
            section_size=d.section_size,
            gauge=d.gauge,
            created_by_name=d.creator.name if d.creator else "Unknown",
            created_at=d.created_at,
            updated_at=d.updated_at,
        )
        for d in designs
    ]


@router.post(
    "",
    response_model=DesignResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new design",
)
async def create_design(
    data: DesignCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    # Validate tree structure
    tree_dict = data.tree_json.model_dump(mode="json")
    errors = validate_design_tree(tree_dict)
    if errors:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"validation_errors": errors},
        )

    design = Design(
        name=data.name,
        description=data.description,
        tree_json=tree_dict,
        outer_width=data.outerWidth,
        outer_height=data.outerHeight,
        section_size=data.sectionSize,
        gauge=data.gauge,
        created_by=user.id,
    )
    db.add(design)
    await db.flush()
    await db.refresh(design)

    return _design_response(design)


@router.get("/{design_id}", response_model=DesignResponse, summary="Get a design by ID")
async def get_design(
    design_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(select(Design).where(Design.id == design_id))
    design = result.scalar_one_or_none()
    if not design:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Design not found")

    return _design_response(design)


@router.put("/{design_id}", response_model=DesignResponse, summary="Update a design")
async def update_design(
    design_id: UUID,
    data: DesignUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(select(Design).where(Design.id == design_id))
    design = result.scalar_one_or_none()
    if not design:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Design not found")

    if data.name is not None:
        design.name = data.name
    if data.description is not None:
        design.description = data.description
    if data.tree_json is not None:
        tree_dict = data.tree_json.model_dump(mode="json")
        errors = validate_design_tree(tree_dict)
        if errors:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={"validation_errors": errors},
            )
        design.tree_json = tree_dict
        design.outer_width = data.tree_json.outerWidth
        design.outer_height = data.tree_json.outerHeight
        design.section_size = data.tree_json.sectionSize
        design.gauge = data.tree_json.gauge

    await db.flush()
    await db.refresh(design)

    return _design_response(design)


@router.delete(
    "/{design_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a design",
)
async def delete_design(
    design_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(select(Design).where(Design.id == design_id))
    design = result.scalar_one_or_none()
    if not design:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Design not found")

    await db.delete(design)
