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
    gst_pct: float = 18
    default_advance_pct: float = 50
    currency_symbol: str = "₹"
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
    gst_pct: Optional[float] = Field(default=None, ge=0, le=100)
    default_advance_pct: Optional[float] = Field(default=None, ge=0, le=100)
    currency_symbol: Optional[str] = Field(default=None, min_length=1, max_length=8)
