"""Address normalization, ported from ``normalize-address-llm.ts``.

Unlike the portal version (which returns ``null`` on any provider error), this raises —
``app/api/v1/company_search.py`` turns any exception into a 502, per the phase-1 HTTP contract.
The response shape is intentionally unvalidated here, exactly like the TS source: whatever
JSON keys the model returns are passed through, and the router filters to the known field set.
"""

from __future__ import annotations

import json
from typing import Any

from app.providers.llm.base import LlmMessage, LlmProvider

SYSTEM_PROMPT = (
    "Extract structured company address fields from registry text. Return JSON only with keys: "
    "streetName, streetNumber, apartmentOrFloor, city, postalCode, regionName, explanation. "
    "Respect country-specific conventions: for IN split house/building/street and keep "
    "city/state/postal separate; for US split street/city/state/ZIP. "
    "Never collapse the full address into streetName when building or apartment can be "
    "separated. Omit unknown fields."
)


async def normalize_address_with_llm(
    provider: LlmProvider,
    *,
    free_text_address: str | None = None,
    trading_name: str | None = None,
    iso2_country_code: str | None = None,
) -> dict[str, Any]:
    payload = {
        "freeTextAddress": free_text_address,
        "tradingName": trading_name,
        "iso2CountryCode": iso2_country_code,
    }
    messages = [
        LlmMessage(role="system", text=SYSTEM_PROMPT),
        LlmMessage(role="user", text=json.dumps(payload)),
    ]
    return await provider.complete_json(messages, trace_name="company_search.normalize_address")
