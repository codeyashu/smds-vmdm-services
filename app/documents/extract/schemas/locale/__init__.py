"""Per-country extraction schemas for CN, AE, US, GB."""

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


class LocaleNameField(BaseModel):
    native: str | None = Field(default=None, description="Verbatim local-script name from the document")
    romanized: str | None = Field(
        default=None,
        description="Transliterated English/Latin operational name — never translate proper nouns",
    )
    english: str | None = Field(
        default=None,
        description="English text printed on the document, when present as a separate zone",
    )


class CnBusinessLicenseExtraction(BaseModel):
    uscc: str | None = Field(default=None, description="18-char Unified Social Credit Code")
    legal_name: LocaleNameField | None = None
    trading_name: LocaleNameField | None = None
    registered_address: ExtractedAddress | None = None
    confidence: float = 0.0


class CnBankPermitExtraction(BaseModel):
    bank_account_number: str | None = None
    bank_name: str | None = None
    confidence: float = 0.0


class AeTradeLicenseExtraction(BaseModel):
    trade_license_number: str | None = None
    legal_name: LocaleNameField | None = None
    trading_name: LocaleNameField | None = None
    registered_address: ExtractedAddress | None = None
    confidence: float = 0.0


class AeVatCertificateExtraction(BaseModel):
    trn: str | None = Field(default=None, description="15-digit UAE TRN starting with 100")
    legal_name: LocaleNameField | None = None
    confidence: float = 0.0


class UsW9Extraction(BaseModel):
    ein: str | None = Field(default=None, description="Employer Identification Number XX-XXXXXXX")
    legal_name: str | None = None
    trading_name: str | None = None
    confidence: float = 0.0


class UsVoidedCheckExtraction(BaseModel):
    bank_account_number: str | None = None
    routing_number: str | None = None
    bank_name: str | None = None
    confidence: float = 0.0


class UsGoodStandingExtraction(BaseModel):
    state_registration_number: str | None = None
    legal_name: str | None = None
    confidence: float = 0.0


class GbCompaniesHouseExtraction(BaseModel):
    company_number: str | None = None
    legal_name: str | None = None
    registered_address: ExtractedAddress | None = None
    confidence: float = 0.0


class GbVatCertificateExtraction(BaseModel):
    vat_number: str | None = None
    legal_name: str | None = None
    confidence: float = 0.0


CN_ENVELOPE_DOC_TYPES = frozenset({"CN_BUSINESS_LICENSE", "CN_BANK_ACCOUNT_PERMIT", "UNKNOWN"})
AE_ENVELOPE_DOC_TYPES = frozenset({"AE_TRADE_LICENSE", "AE_VAT_CERTIFICATE", "UNKNOWN"})
US_ENVELOPE_DOC_TYPES = frozenset(
    {"US_W9", "US_VOIDED_CHECK", "US_CERTIFICATE_OF_GOOD_STANDING", "UNKNOWN"}
)
GB_ENVELOPE_DOC_TYPES = frozenset({"GB_COMPANIES_HOUSE_CERTIFICATE", "GB_VAT_CERTIFICATE", "UNKNOWN"})


class CnExtractionEnvelope(BaseModel):
    doc_type: str
    doc_type_confidence: float = 0.0
    business_license: CnBusinessLicenseExtraction | None = None
    bank_permit: CnBankPermitExtraction | None = None


class AeExtractionEnvelope(BaseModel):
    doc_type: str
    doc_type_confidence: float = 0.0
    trade_license: AeTradeLicenseExtraction | None = None
    vat_certificate: AeVatCertificateExtraction | None = None


class UsExtractionEnvelope(BaseModel):
    doc_type: str
    doc_type_confidence: float = 0.0
    w9: UsW9Extraction | None = None
    voided_check: UsVoidedCheckExtraction | None = None
    good_standing: UsGoodStandingExtraction | None = None


class GbExtractionEnvelope(BaseModel):
    doc_type: str
    doc_type_confidence: float = 0.0
    companies_house: GbCompaniesHouseExtraction | None = None
    vat_certificate: GbVatCertificateExtraction | None = None
