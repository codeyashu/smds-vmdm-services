"""Pydantic port of ``nl-search-params.schema.ts`` (the zod schema), with equivalent
validation — notably ``country`` must be exactly length 2 when present.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, field_validator

NlIntent = Literal["code_lookup", "attribute_search"]
NlParseSource = Literal["heuristic", "llm"]
NlConfidence = Literal["high", "medium", "low"]


class NlSearchParams(BaseModel):
    intent: NlIntent
    code: str | None = None
    codeType: str | None = None
    tradingName: str | None = None
    country: str | None = None
    taxId: str | None = None
    cityName: str | None = None
    streetName: str | None = None
    postalCode: str | None = None
    vendorStatus: str | None = None
    accountType: str | None = None
    tradingPartnerCode: str | None = None
    hasDraft: bool | None = None
    inWorkflow: bool | None = None
    summary: str | None = None

    @field_validator("country")
    @classmethod
    def _country_length(cls, value: str | None) -> str | None:
        if value is not None and len(value) != 2:
            raise ValueError("country must be exactly 2 characters")
        return value


class NlParseResult(NlSearchParams):
    source: NlParseSource
    confidence: NlConfidence
