"""
Audit router — read the activity trail (admin/owner only).
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.audit import AuditLog
from app.models.user import User, ROLE_ADMIN, ROLE_OWNER
from app.schemas.audit import AuditEntry
from app.services.auth import require_role

router = APIRouter(prefix="/audit", tags=["Audit"])


@router.get("", response_model=list[AuditEntry], summary="List recent activity (admin/owner)")
async def list_audit(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(ROLE_ADMIN, ROLE_OWNER)),
):
    rows = (await db.execute(
        select(AuditLog).order_by(AuditLog.created_at.desc()).offset(skip).limit(limit)
    )).scalars().all()
    return [
        AuditEntry(
            id=r.id, actor_id=r.actor_id,
            actor_name=r.actor.name if r.actor else "System",
            action=r.action, entity_type=r.entity_type, entity_id=r.entity_id,
            summary=r.summary, created_at=r.created_at,
        )
        for r in rows
    ]
