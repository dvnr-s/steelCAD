"""
Settings router — company profile (seller identity) used to brand quotation PDFs.

  GET /settings/company  — any authenticated user (the PDF + builder need it)
  PUT /settings/company  — admin/owner only
"""
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.company import CompanySettings
from app.models.user import User, ROLE_ADMIN, ROLE_OWNER
from app.schemas.company import CompanySettingsResponse, CompanySettingsUpdate
from app.services.auth import get_current_user, require_role

router = APIRouter(prefix="/settings", tags=["Settings"])


async def get_or_create_company(db: AsyncSession) -> CompanySettings:
    """Return the singleton company row (id=1), creating it on first access."""
    company = (await db.execute(select(CompanySettings).where(CompanySettings.id == 1))).scalar_one_or_none()
    if company is None:
        company = CompanySettings(id=1)
        db.add(company)
        await db.flush()
    return company


@router.get("/company", response_model=CompanySettingsResponse, summary="Get company profile")
async def get_company(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return await get_or_create_company(db)


@router.put("/company", response_model=CompanySettingsResponse, summary="Update company profile (admin/owner)")
async def update_company(
    data: CompanySettingsUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(ROLE_ADMIN, ROLE_OWNER)),
):
    company = await get_or_create_company(db)
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(company, field, value)
    await db.flush()
    await db.refresh(company)
    return company
