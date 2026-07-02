"""
Company settings schemas — the seller profile used to brand the quotation PDF.
"""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class CompanySettingsResponse(BaseModel):
    name: str
    logo_data_url: Optional[str] = None
    address: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    gstin: Optional[str] = None
    bank_details: Optional[str] = None
    default_terms: Optional[str] = None
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class CompanySettingsUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    logo_data_url: Optional[str] = None
    address: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    gstin: Optional[str] = None
    bank_details: Optional[str] = None
    default_terms: Optional[str] = None
