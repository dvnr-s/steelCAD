"""
Users router — invite-only user management (admin/owner only).

  GET  /users          — list all users
  POST /users          — create a new invited user
  PATCH /users/{id}/role — change a user's role
  DELETE /users/{id}   — delete a user (admin only)
"""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User, ROLE_ADMIN, ROLE_OWNER, ROLE_SALES
from app.schemas.user import UserInvite, UserResponse, UserRoleUpdate, AdminPasswordReset
from app.services.audit import record_audit
from app.services.auth import hash_password, require_role, anonymize_user

router = APIRouter(prefix="/users", tags=["Users"])


@router.get("", response_model=list[UserResponse], summary="List all users (admin/owner)")
async def list_users(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(ROLE_ADMIN, ROLE_OWNER)),
):
    result = await db.execute(
        select(User).where(User.deleted_at.is_(None)).order_by(User.created_at)
    )
    return [UserResponse.from_orm_user(u) for u in result.scalars().all()]


@router.post(
    "",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Invite a new user (admin/owner)",
)
async def create_user(
    data: UserInvite,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(ROLE_ADMIN, ROLE_OWNER)),
):
    # Owners can only create sales users
    if current_user.role == ROLE_OWNER and data.role != ROLE_SALES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Owners can only invite users with the 'sales' role",
        )

    existing = await db.execute(select(User).where(User.email == data.email))
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        )

    user = User(
        email=data.email,
        name=data.name,
        password=hash_password(data.password),
        role=data.role,
        is_admin=(data.role == ROLE_ADMIN),
    )
    db.add(user)
    await db.flush()
    await db.refresh(user)
    return UserResponse.from_orm_user(user)


@router.patch(
    "/{user_id}/role",
    response_model=UserResponse,
    summary="Change a user's role (admin/owner)",
)
async def update_user_role(
    user_id: UUID,
    data: UserRoleUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(ROLE_ADMIN, ROLE_OWNER)),
):
    # Owners can only set role to sales
    if current_user.role == ROLE_OWNER and data.role != ROLE_SALES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Owners can only assign the 'sales' role",
        )

    result = await db.execute(
        select(User).where(User.id == user_id, User.deleted_at.is_(None))
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    # Prevent demoting yourself
    if user.id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot change your own role",
        )

    user.role = data.role
    user.is_admin = (data.role == ROLE_ADMIN)
    await db.flush()
    await db.refresh(user)
    return UserResponse.from_orm_user(user)


@router.patch(
    "/{user_id}/password",
    summary="Reset a user's password (admin/owner)",
)
async def reset_user_password(
    user_id: UUID,
    data: AdminPasswordReset,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(ROLE_ADMIN, ROLE_OWNER)),
):
    result = await db.execute(
        select(User).where(User.id == user_id, User.deleted_at.is_(None))
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    # Owners may only reset sales users' passwords.
    if current_user.role == ROLE_OWNER and user.role != ROLE_SALES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Owners can only reset passwords for sales users",
        )
    user.password = hash_password(data.new_password)
    await db.flush()
    return {"message": "Password reset"}


@router.delete(
    "/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a user (admin only) — anonymizes all personal data",
)
async def delete_user(
    user_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(ROLE_ADMIN)),
):
    result = await db.execute(
        select(User).where(User.id == user_id, User.deleted_at.is_(None))
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    if user.id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete your own account",
        )

    # Anonymize rather than DELETE: the user's designs/customers/estimates keep
    # a NOT NULL created_by FK to this row, so a hard delete would either fail
    # or destroy business records. This scrubs PII and blocks login instead.
    anonymize_user(user)
    await db.flush()
    await record_audit(db, current_user, "user.delete", "user", user.id,
                       "account deleted and personal data anonymized")
