"""
Authentication service — JWT creation/validation, password hashing, FastAPI dependencies.
"""
import secrets
from datetime import datetime, timedelta, timezone
from typing import Callable

import bcrypt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.models.user import User

settings = get_settings()
security = HTTPBearer()


# ─── Password utilities ────────────────────────────────────────────

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))


# Hash of a random throwaway secret. Login verifies against this when the email
# doesn't match any account, so a failed login takes the same time either way —
# otherwise response timing would reveal which emails have accounts.
_ENUMERATION_GUARD_HASH = hash_password(secrets.token_urlsafe(16))


def burn_password_check() -> None:
    """Spend one bcrypt verification on a dummy hash (timing equalizer)."""
    verify_password("invalid", _ENUMERATION_GUARD_HASH)


def anonymize_user(user: User) -> None:
    """Scrub a user's personal data in place and disable the account.

    The row must survive (designs/customers/estimates hold NOT NULL created_by
    FKs), so deletion = anonymization: email and name are replaced, the password
    is reset to an unusable random hash, and deleted_at both hides the account
    and invalidates any outstanding JWTs via get_current_user.
    """
    user.email = f"deleted-{user.id}@anonymized.invalid"
    user.name = "Deleted user"
    user.password = hash_password(secrets.token_urlsafe(32))
    user.is_admin = False
    user.deleted_at = datetime.now(timezone.utc)


# ─── JWT utilities ─────────────────────────────────────────────────

def create_access_token(user_id: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {"sub": user_id, "exp": expire, "type": "access"}
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def create_refresh_token(user_id: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    payload = {"sub": user_id, "exp": expire, "type": "refresh"}
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_token(token: str) -> dict:
    try:
        payload = jwt.decode(
            token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM]
        )
        return payload
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )


# ─── FastAPI dependencies ──────────────────────────────────────────

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Validate Bearer token and return the authenticated User."""
    payload = decode_token(credentials.credentials)
    if payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type — expected access token",
        )
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
        )
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user or user.deleted_at is not None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )
    return user


def require_role(*roles: str) -> Callable:
    """
    Dependency factory — returns a FastAPI dependency that ensures the
    current user has one of the specified roles.

    Usage:
        user: User = Depends(require_role("admin", "owner"))
    """
    async def dependency(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access restricted to: {', '.join(roles)}",
            )
        return user
    return dependency


# Back-compat alias — existing callers of require_admin continue to work.
require_admin = require_role("admin", "owner")
