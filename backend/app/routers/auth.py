"""
Auth router — register, login, refresh tokens, get current user.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User
from app.schemas.user import (
    UserCreate, UserLogin, UserResponse, TokenResponse, RefreshRequest,
)
from app.services.auth import (
    hash_password, verify_password,
    create_access_token, create_refresh_token,
    decode_token, get_current_user,
)

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post(
    "/register",
    response_model=TokenResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user account",
)
async def register(data: UserCreate, db: AsyncSession = Depends(get_db)):
    # Check for existing email
    result = await db.execute(select(User).where(User.email == data.email))
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        )

    user = User(
        email=data.email,
        password=hash_password(data.password),
        name=data.name,
    )
    db.add(user)
    await db.flush()

    return TokenResponse(
        access_token=create_access_token(str(user.id)),
        refresh_token=create_refresh_token(str(user.id)),
    )


@router.post("/login", response_model=TokenResponse, summary="Login with email and password")
async def login(data: UserLogin, db: AsyncSession = Depends(get_db)):
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
async def refresh(data: RefreshRequest, db: AsyncSession = Depends(get_db)):
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
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )

    return TokenResponse(
        access_token=create_access_token(str(user.id)),
        refresh_token=create_refresh_token(str(user.id)),
    )


@router.get("/me", response_model=UserResponse, summary="Get current authenticated user")
async def get_me(user: User = Depends(get_current_user)):
    return user


@router.post(
    "/bootstrap-admin",
    summary="Promote a user to admin — only works if NO admin exists yet (first-run only)",
)
async def bootstrap_admin(
    data: dict,
    db: AsyncSession = Depends(get_db),
):
    """
    One-time bootstrap: makes the specified email an admin.
    Only succeeds if there are currently zero admins in the system.
    Safe to call multiple times — becomes a no-op once any admin exists.
    """
    # Refuse if an admin already exists
    existing_admin = await db.execute(select(User).where(User.is_admin == True))
    if existing_admin.scalar_one_or_none():
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

    user.is_admin = True
    await db.flush()
    return {"message": f"{email} is now an admin"}
