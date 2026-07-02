"""
Rates router — list all rates (any user), update/seed rates (admin only).
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.rate import Rate, RateHistory
from app.models.user import User, ROLE_ADMIN, ROLE_OWNER
from app.schemas.rate import RateResponse, RateUpdate
from app.services.auth import get_current_user, require_role
from app.services.audit import record_audit
from app.services.pricing import DEFAULT_RATES

router = APIRouter(prefix="/rates", tags=["Rates"])


@router.get("", response_model=list[RateResponse], summary="List all material rates")
async def list_rates(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(select(Rate).order_by(Rate.item_code))
    return result.scalars().all()


@router.put(
    "/{item_code}",
    response_model=RateResponse,
    summary="Update a material rate (admin only)",
)
async def update_rate(
    item_code: str,
    data: RateUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(ROLE_ADMIN, ROLE_OWNER)),
):
    result = await db.execute(select(Rate).where(Rate.item_code == item_code))
    rate = result.scalar_one_or_none()
    if not rate:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Rate '{item_code}' not found",
        )

    old_rate = float(rate.rate)
    rate.rate = data.rate
    db.add(RateHistory(item_code=item_code, old_rate=old_rate, new_rate=data.rate, actor_id=user.id))
    await db.flush()
    await db.refresh(rate)
    await record_audit(db, user, "rate.update", "rate", item_code,
                       f"{item_code}: ₹{old_rate} → ₹{data.rate}")
    return rate


@router.post(
    "/seed",
    status_code=status.HTTP_201_CREATED,
    summary="Seed default rates from spec §9.2 (admin only)",
)
async def seed_rates(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(ROLE_ADMIN, ROLE_OWNER)),
):
    """Populate the rates table with default values. Skips existing item codes."""
    created = 0
    skipped = 0

    for rate_data in DEFAULT_RATES:
        result = await db.execute(
            select(Rate).where(Rate.item_code == rate_data["item_code"])
        )
        if result.scalar_one_or_none():
            skipped += 1
            continue

        db.add(Rate(
            item_code=rate_data["item_code"],
            rate=rate_data["rate"],
            unit=rate_data["unit"],
            label=rate_data["label"],
        ))
        created += 1

    await db.flush()
    return {"message": f"Seeded {created} rates, skipped {skipped} existing"}
