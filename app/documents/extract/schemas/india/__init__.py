"""Per-doctype extraction schemas for India (pydantic v2).

Each model is the exact JSON shape the LLM is constrained to return for one document type.
Fields are Optional because a scan may not carry every value; the mapping layer decides
what becomes a portal patch. `*_confidence` fields are model self-reported 0-1 scores,
later reconciled with Azure DI word confidences.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class FieldEvidence(BaseModel):
    page: int = 1
    bbox: list[float] | None = None
    snippet: str | None = None


class ExtractedAddress(BaseModel):
    building_name: str | None = None
    street_number: str | None = None
    street_name: str | None = None
    district: str | None = None
    city_name: str | None = None
    region_name: str | None = None
    postal_code: str | None = None


class PanExtraction(BaseModel):
    pan: str | None = Field(default=None, description="10-char PAN, LLLLLNNNNL")
    holder_name: str | None = None
    father_name: str | None = None
    date_of_birth: str | None = None
    confidence: float = 0.0


class GstExtraction(BaseModel):
    gstin: str | None = Field(default=None, description="15-char GSTIN")
    legal_name: str | None = None
    trade_name: str | None = None
    constitution_of_business: str | None = None
    principal_place_of_business: ExtractedAddress | None = None
    date_of_registration: str | None = None
    confidence: float = 0.0


class ChequeExtraction(BaseModel):
    account_number: str | None = None
    ifsc: str | None = None
    bank_name: str | None = None
    branch_name: str | None = None
    account_holder_name: str | None = None
    micr: str | None = None
    confidence: float = 0.0


class UdyamExtraction(BaseModel):
    udyam_number: str | None = None
    enterprise_name: str | None = None
    enterprise_type: str | None = None  # Micro / Small / Medium
    nic_codes: list[str] = Field(default_factory=list)
    plant_address: ExtractedAddress | None = None
    confidence: float = 0.0


class CoiExtraction(BaseModel):
    cin: str | None = None
    company_name: str | None = None
    date_of_incorporation: str | None = None
    registered_office: ExtractedAddress | None = None
    confidence: float = 0.0
