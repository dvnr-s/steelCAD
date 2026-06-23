"""
Customers router — CRUD for clients that estimates are quoted to.
"""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.customer import Customer
from app.models.estimate import Estimate
from app.models.user import User
from app.schemas.customer import (
    CustomerCreate, CustomerUpdate, CustomerResponse, CustomerListItem,
)
from app.services.auth import get_current_user

router = APIRouter(prefix="/customers", tags=["Customers"])


@router.get("", response_model=list[CustomerListItem], summary="List customers")
async def list_customers(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    # Customers with a count of their estimates.
    count_sq = (
        select(Estimate.customer_id, func.count(Estimate.id).label("cnt"))
        .group_by(Estimate.customer_id)
        .subquery()
    )
    result = await db.execute(
        select(Customer, func.coalesce(count_sq.c.cnt, 0))
        .outerjoin(count_sq, count_sq.c.customer_id == Customer.id)
        .order_by(Customer.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    rows = result.all()
    return [
        CustomerListItem(
            id=c.id, name=c.name, company=c.company, phone=c.phone,
            estimate_count=cnt, created_at=c.created_at,
        )
        for c, cnt in rows
    ]


@router.post("", response_model=CustomerResponse, status_code=status.HTTP_201_CREATED, summary="Create a customer")
async def create_customer(
    data: CustomerCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    customer = Customer(**data.model_dump(), created_by=user.id)
    db.add(customer)
    await db.flush()
    await db.refresh(customer)
    return customer


@router.get("/{customer_id}", response_model=CustomerResponse, summary="Get a customer")
async def get_customer(
    customer_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(select(Customer).where(Customer.id == customer_id))
    customer = result.scalar_one_or_none()
    if not customer:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found")
    return customer


@router.put("/{customer_id}", response_model=CustomerResponse, summary="Update a customer")
async def update_customer(
    customer_id: UUID,
    data: CustomerUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(select(Customer).where(Customer.id == customer_id))
    customer = result.scalar_one_or_none()
    if not customer:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found")
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(customer, field, value)
    await db.flush()
    await db.refresh(customer)
    return customer


@router.delete("/{customer_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete a customer")
async def delete_customer(
    customer_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(select(Customer).where(Customer.id == customer_id))
    customer = result.scalar_one_or_none()
    if not customer:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found")
    await db.delete(customer)
