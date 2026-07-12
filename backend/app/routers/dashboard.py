"""
Dashboard router — business metrics for the home page.

Everything derives from live rows at read time (no materialized state):
pipeline counts/value by status, accepted revenue by month, active entity
counts, and the most recently touched estimates.
"""
from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.customer import Customer
from app.models.design import Design
from app.models.estimate import Estimate
from app.models.user import User
from app.routers.estimates import _summary_stmt, _summary
from app.schemas.estimate import EstimateSummary
from app.services.auth import get_current_user

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])

MONTHS_BACK = 6


class StatusMetric(BaseModel):
    status: str
    count: int
    total: int  # sum of grand totals (rupees)


class MonthlyRevenue(BaseModel):
    month: date  # first day of the month
    total: int


class DashboardMetrics(BaseModel):
    pipeline: list[StatusMetric]
    monthly_revenue: list[MonthlyRevenue]
    active_customers: int
    active_designs: int
    recent_estimates: list[EstimateSummary]


def _months_back_start(today: date, months: int) -> date:
    """First day of the month `months - 1` months before today's month."""
    year, month = today.year, today.month - (months - 1)
    while month <= 0:
        year -= 1
        month += 12
    return date(year, month, 1)


@router.get("/metrics", response_model=DashboardMetrics, summary="Business dashboard metrics")
async def dashboard_metrics(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    # Live pipeline: exclude deleted estimates, superseded revisions (their
    # replacement carries the value), and estimates of deleted customers.
    live = (
        Estimate.deleted_at.is_(None),
        Estimate.status != "superseded",
        Customer.deleted_at.is_(None),
    )

    pipeline_rows = (await db.execute(
        select(
            Estimate.status,
            func.count(Estimate.id),
            func.coalesce(func.sum(Estimate.grand_total), 0),
        )
        .join(Customer, Customer.id == Estimate.customer_id)
        .where(*live)
        .group_by(Estimate.status)
    )).all()

    since = _months_back_start(datetime.now(timezone.utc).date(), MONTHS_BACK)
    month_col = func.date_trunc("month", Estimate.accepted_at).label("month")
    monthly_rows = (await db.execute(
        select(month_col, func.coalesce(func.sum(Estimate.grand_total), 0))
        .join(Customer, Customer.id == Estimate.customer_id)
        .where(
            *live,
            Estimate.status == "accepted",
            Estimate.accepted_at.is_not(None),
            Estimate.accepted_at >= since,
        )
        .group_by(month_col)
        .order_by(month_col)
    )).all()

    active_customers = (await db.execute(
        select(func.count(Customer.id)).where(Customer.deleted_at.is_(None))
    )).scalar() or 0
    active_designs = (await db.execute(
        select(func.count(Design.id)).where(Design.deleted_at.is_(None))
    )).scalar() or 0

    recent_rows = (await db.execute(
        _summary_stmt()
        .join(Customer, Customer.id == Estimate.customer_id)
        .where(*live)
        .order_by(Estimate.updated_at.desc())
        .limit(5)
    )).all()

    return DashboardMetrics(
        pipeline=[
            StatusMetric(status=s, count=c, total=int(t or 0))
            for s, c, t in pipeline_rows
        ],
        monthly_revenue=[
            MonthlyRevenue(month=m.date() if isinstance(m, datetime) else m, total=int(t or 0))
            for m, t in monthly_rows
        ],
        active_customers=active_customers,
        active_designs=active_designs,
        recent_estimates=[_summary(e, fc) for e, fc in recent_rows],
    )
