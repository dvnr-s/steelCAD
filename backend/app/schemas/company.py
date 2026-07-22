"""
Company settings schemas — the seller profile used to brand the quotation PDF.
"""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, field_validator


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
    # Cap at ~700 KB of base64 (~512 KB image). The value is rendered into an
    # <img src> in the quotation PDF, so it must be an inline data: URI only —
    # never a file:// or http(s):// URL that WeasyPrint would fetch server-side.
    logo_data_url: Optional[str] = Field(default=None, max_length=700_000)
    address: Optional[str] = Field(default=None, max_length=500)
    phone: Optional[str] = Field(default=None, max_length=40)
    email: Optional[str] = Field(default=None, max_length=255)
    gstin: Optional[str] = Field(default=None, max_length=20)
    bank_details: Optional[str] = Field(default=None, max_length=1000)
    default_terms: Optional[str] = Field(default=None, max_length=4000)
    gst_pct: Optional[float] = Field(default=None, ge=0, le=100)
    default_advance_pct: Optional[float] = Field(default=None, ge=0, le=100)
    currency_symbol: Optional[str] = Field(default=None, min_length=1, max_length=8)

    @field_validator("logo_data_url")
    @classmethod
    def _logo_must_be_data_uri(cls, v: Optional[str]) -> Optional[str]:
        if v and not v.lower().startswith("data:image/"):
            raise ValueError("logo_data_url must be an inline data:image/ URI")
        return v
