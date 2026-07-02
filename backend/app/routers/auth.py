"""
Auth router — login, refresh tokens, get current user.
Account creation is invite-only: use POST /users (admin/owner only).
"""
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.ratelimit import limiter
from app.database import get_db
from app.models.user import User, ROLE_ADMIN
from app.schemas.user import (
    UserLogin, UserResponse, TokenResponse, RefreshRequest, ChangePasswordRequest,
)
from app.services.auth import (
    verify_password, hash_password,
    create_access_token, create_refresh_token,
    decode_token, get_current_user,
)

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/login", response_model=TokenResponse, summary="Login with email and password")
@limiter.limit("10/minute")
async def login(request: Request, data: UserLogin, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == data.email))
    user = result.scalar_one_or_none()
    if not user or not verify_password(data.password, user.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )
    return TokenResponse(
        access_token=create_access_token(str(user.id)),
        refresh_token=create_refresh_token(str(user.id)),
    )


@router.post("/refresh", response_model=TokenResponse, summary="Exchange refresh token for new tokens")
@limiter.limit("20/minute")
async def refresh(request: Request, data: RefreshRequest, db: AsyncSession = Depends(get_db)):
    payload = decode_token(data.refresh_token)
    if payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type — expected refresh token",
        )
    user_id = payload.get("sub")
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return TokenResponse(
        access_token=create_access_token(str(user.id)),
        refresh_token=create_refresh_token(str(user.id)),
    )


@router.get("/me", response_model=UserResponse, summary="Get current authenticated user")
async def get_me(user: User = Depends(get_current_user)):
    return UserResponse.from_orm_user(user)


@router.post("/change-password", summary="Change your own password")
@limiter.limit("5/minute")
async def change_password(
    request: Request,
    data: ChangePasswordRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not verify_password(data.current_password, user.password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect",
        )
    user.password = hash_password(data.new_password)
    await db.flush()
    return {"message": "Password updated"}


@router.post(
    "/bootstrap-admin",
    summary="Promote a user to admin — only works if NO admin exists yet (first-run only)",
)
async def bootstrap_admin(data: dict, db: AsyncSession = Depends(get_db)):
    """
    One-time bootstrap: promotes the specified email to admin role.
    Only succeeds if there are currently zero admins in the system.
    Safe to call multiple times — becomes a no-op once any admin exists.
    """
    existing = await db.execute(select(User).where(User.role == ROLE_ADMIN))
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An admin already exists. This endpoint is disabled.",
        )
    email = data.get("email", "").strip()
    if not email:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="email required")
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    user.role = ROLE_ADMIN
    user.is_admin = True
    await db.flush()
    return {"message": f"{email} is now an admin"}
