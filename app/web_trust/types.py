"""Web-trust verification types."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

WebTrustStatus = Literal["off", "active", "registry_only", "pilot"]
WebTrustBand = Literal["high", "medium", "low", "insufficient"]
WebTrustVerdict = Literal["same", "likely", "different"]
WebTrustSourceType = Literal[
    "government_registry",
    "commercial_directory",
    "company_website",
    "format_validator",
    "other",
]
WebTrustVerificationMode = Literal["format_check", "live_registry", "web_enrichment"]
FieldMatchStatus = Literal["match", "partial", "mismatch", "unknown"]


class WebTrustConnector(BaseModel):
    id: str
    type: str
    fields: list[str] = Field(default_factory=list)
    authority: float = 0.5


class WebTrustPlaybook(BaseModel):
    countryCode: str
    status: WebTrustStatus = "off"
    submitPolicy: Literal["advisory", "required"] = "advisory"
    minTrustToAutoProceed: int = 70
    connectors: list[WebTrustConnector] = Field(default_factory=list)
    allowlistedDomains: list[str] = Field(default_factory=list)
    fallbackWebSearch: bool = False


class WebTrustAddressInput(BaseModel):
    contactAddressPurposeCode: str | None = "BILL_TO"
    streetName: str | None = None
    streetNumber: str | None = None
    buildingName: str | None = None
    cityName: str | None = None
    postalCode: str | None = None
    iso2CountryCode: str | None = None


class WebTrustVerifyRequest(BaseModel):
    tradingName: str | None = None
    legalName: str | None = None
    iso2CountryCode: str
    taxIdentificationNumbers: list[str] = Field(default_factory=list)
    address: WebTrustAddressInput | None = None
    website: str | None = None


class FieldConfidence(BaseModel):
    field: str
    label: str
    score: int
    status: FieldMatchStatus
    leftDisplay: str | None = None
    rightDisplay: str | None = None
    skipReason: str | None = None


class WebTrustSource(BaseModel):
    url: str
    domain: str
    retrievedAt: str


class WebMatchedRecord(BaseModel):
    id: str
    sourceType: WebTrustSourceType
    verificationMode: WebTrustVerificationMode = "format_check"
    sourceUrl: str | None = None
    connectorId: str
    displayName: str
    extractedFields: dict[str, Any] = Field(default_factory=dict)
    matchScore: int
    fieldEvidence: list[FieldConfidence] = Field(default_factory=list)
    llmVerdict: WebTrustVerdict | None = None
    llmReason: str | None = None
    authorityWeight: float = 0.5


class BillToAddressReview(BaseModel):
    purposeCode: str = "BILL_TO"
    completenessScore: int = 0
    fieldEvidence: list[FieldConfidence] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


class FieldCorrelationSummary(BaseModel):
    correlationScore: int = 0
    correlatedFieldCount: int = 0
    isolatedMatch: bool = True
    bestSourceId: str | None = None
    bestSourceName: str | None = None
    narrative: str | None = None


class WebTrustVerifyResponse(BaseModel):
    skipped: bool = False
    skipReason: str | None = None
    reviewId: str | None = None
    countryCode: str
    playbookStatus: WebTrustStatus = "off"
    trustScore: int | None = None
    trustBand: WebTrustBand | None = None
    enteredData: dict[str, Any] = Field(default_factory=dict)
    billToAddressReview: BillToAddressReview | None = None
    learningHints: list[str] = Field(default_factory=list)
    matchedRecords: list[WebMatchedRecord] = Field(default_factory=list)
    fieldEvidence: list[FieldConfidence] = Field(default_factory=list)
    fieldCorrelation: FieldCorrelationSummary | None = None
    sources: list[WebTrustSource] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    verificationDisclaimer: str | None = None
    minTrustToAutoProceed: int = 70
    submitPolicy: Literal["advisory", "required"] = "advisory"
