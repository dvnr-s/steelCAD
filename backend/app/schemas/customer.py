"""
Customer Pydantic schemas.
"""
from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


class CustomerBase(BaseModel):
    # Permissive base — also the shape returned to clients. Reads must never fail
    # on a legacy row whose free-text fields predate the write-side validation
    # below, so email stays a plain str here.
    name: str = Field(min_length=1, max_length=255)
    company: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    address: Optional[str] = None
    gstin: Optional[str] = None


# Length caps bound what gets stored and — crucially — what gets rendered into
# the quotation PDF. Combined with the template's autoescaping this keeps a
# hostile field from ballooning or injecting markup into the document.
class CustomerCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    company: Optional[str] = Field(default=None, max_length=255)
    phone: Optional[str] = Field(default=None, max_length=40)
    email: Optional[EmailStr] = None
    address: Optional[str] = Field(default=None, max_length=500)
    gstin: Optional[str] = Field(default=None, max_length=20)


class CustomerUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    company: Optional[str] = Field(default=None, max_length=255)
    phone: Optional[str] = Field(default=None, max_length=40)
    email: Optional[EmailStr] = None
    address: Optional[str] = Field(default=None, max_length=500)
    gstin: Optional[str] = Field(default=None, max_length=20)


class CustomerResponse(CustomerBase):
    id: UUID
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class CustomerListItem(BaseModel):
    id: UUID
    name: str
    company: Optional[str] = None
    phone: Optional[str] = None
    estimate_count: int = 0
    created_at: datetime

    model_config = {"from_attributes": True}
