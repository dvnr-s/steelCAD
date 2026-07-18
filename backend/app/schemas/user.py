"""
User-related Pydantic schemas.
"""
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, EmailStr, field_validator

from app.models.user import ROLE_ADMIN, ROLE_SALES

RoleType = Literal["admin", "owner", "sales"]


class UserInvite(BaseModel):
    """Admin/owner-side schema for creating a new invited user."""
    email: EmailStr
    name: str
    password: str
    role: RoleType = ROLE_SALES

    @field_validator("password")
    @classmethod
    def password_min_length(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        return v


class UserRoleUpdate(BaseModel):
    """Payload for changing a user's role."""
    role: RoleType


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class ChangePasswordRequest(BaseModel):
    """Self-service password change for the logged-in user."""
    current_password: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def new_password_min_length(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        return v


class DeleteAccountRequest(BaseModel):
    """Self-service account deletion — requires the current password."""
    password: str


class AdminPasswordReset(BaseModel):
    """Admin-set replacement password for another user."""
    new_password: str

    @field_validator("new_password")
    @classmethod
    def new_password_min_length(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        return v


class UserResponse(BaseModel):
    id: UUID
    email: str
    name: str
    role: RoleType
    is_admin: bool
    created_at: datetime

    model_config = {"from_attributes": True}

    @classmethod
    def from_orm_user(cls, user) -> "UserResponse":
        return cls(
            id=user.id,
            email=user.email,
            name=user.name,
            role=user.role,
            is_admin=(user.role == ROLE_ADMIN),
            created_at=user.created_at,
        )


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str
