"""Company-name LLM refinement, ported from ``normalize-company-name-llm.ts`` — LLM half only.

The deterministic ``normalizeCompanyNameRules`` stays in the portal; ``ruleBasedSuggestion`` is
sent here purely as prompt context, never as a fallback value. Per the phase-1 contract, an
empty/whitespace ``normalizedName`` from the model is a 502 (the portal falls back to
``ruleBasedSuggestion`` itself on any non-200) — this module never substitutes it in.
"""

from __future__ import annotations

import json

from app.providers.llm.base import LlmMessage, LlmProvider

SYSTEM_PROMPT = (
    "Normalize a company trading name for external registry lookup. Fix missing spaces, legal "
    "suffix spacing, and obvious OCR/concatenation errors. "
    "Return JSON only with keys: normalizedName, explanation. Preserve meaning; do not invent a "
    "different company."
)


class EmptyNormalizedNameError(ValueError):
    """Raised when the model returns an empty/whitespace normalizedName."""


async def normalize_name_with_llm(
    provider: LlmProvider,
    *,
    trading_name: str,
    iso2_country_code: str | None = None,
    rule_based_suggestion: str | None = None,
) -> dict[str, str]:
    payload = {
        "tradingName": trading_name,
        "iso2CountryCode": iso2_country_code,
        "ruleBasedSuggestion": rule_based_suggestion,
    }
    messages = [
        LlmMessage(role="system", text=SYSTEM_PROMPT),
        LlmMessage(role="user", text=json.dumps(payload)),
    ]
    result = await provider.complete_json(messages)

    raw_name = result.get("normalizedName")
    normalized_name = raw_name.strip() if isinstance(raw_name, str) else ""
    if not normalized_name:
        raise EmptyNormalizedNameError("Model returned an empty normalizedName.")

    out: dict[str, str] = {"normalizedName": normalized_name}
    raw_explanation = result.get("explanation")
    explanation = raw_explanation.strip() if isinstance(raw_explanation, str) else ""
    if explanation:
        out["explanation"] = explanation
    return out
