"""Tax-identifier classification, ported from ``normalize-tax-llm.ts``.

Filtering matches the TS exactly: ``taxTypeCode`` must match ``^TAXNO\\d+$`` case-insensitively
(tested against the raw, untrimmed string, mirroring the TS regex test) and both
``taxTypeCode``/``taxIdentificationNumber`` must be non-empty after trimming. An empty result
list is a valid 200 (the portal treats it as "unavailable"), unlike the TS source which returns
``null`` in that case — see the deviation note in the router.
"""

from __future__ import annotations

import json
import re
from typing import Any

from app.providers.llm.base import LlmMessage, LlmProvider

SYSTEM_PROMPT = (
    "Classify company tax identifiers for a vendor master form. Return JSON only: "
    "{ assignments: [{ taxTypeCode, taxIdentificationNumber, label }] }. "
    "For India: GSTIN -> TAXNO4, PAN -> TAXNO3, 11-digit VAT -> TAXNO1. Use uppercase values "
    "without spaces. Omit unknown identifiers."
)

_TAX_TYPE_CODE_RE = re.compile(r"^TAXNO\d+$", re.IGNORECASE)


async def classify_tax_with_llm(
    provider: LlmProvider,
    *,
    raw_identifiers: Any,
    iso2_country_code: str,
) -> list[dict[str, Any]]:
    payload = {"rawIdentifiers": raw_identifiers, "iso2CountryCode": iso2_country_code}
    messages = [
        LlmMessage(role="system", text=SYSTEM_PROMPT),
        LlmMessage(role="user", text=json.dumps(payload)),
    ]
    result = await provider.complete_json(messages, trace_name="company_search.classify_tax")

    assignments = result.get("assignments")
    if not isinstance(assignments, list):
        return []

    out: list[dict[str, Any]] = []
    for entry in assignments:
        if not isinstance(entry, dict):
            continue
        tax_type_code = entry.get("taxTypeCode")
        tax_id = entry.get("taxIdentificationNumber")
        if not isinstance(tax_type_code, str) or not tax_type_code.strip():
            continue
        if not _TAX_TYPE_CODE_RE.match(tax_type_code):
            continue
        if not isinstance(tax_id, str) or not tax_id.strip():
            continue
        out.append(
            {
                "taxTypeCode": tax_type_code,
                "taxIdentificationNumber": tax_id,
                "label": entry.get("label"),
            }
        )
    return out
