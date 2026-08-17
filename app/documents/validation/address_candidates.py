"""Collect address candidates from extraction payloads."""

from __future__ import annotations

from typing import Any

from app.documents.validation.types import AddressCandidate


def collect_address_candidates(extractions: list[dict[str, Any]]) -> list[AddressCandidate]:
    out: list[AddressCandidate] = []
    for extraction in extractions:
        for raw in extraction.get("addressCandidates") or []:
            if not isinstance(raw, dict):
                continue
            try:
                out.append(AddressCandidate.model_validate(raw))
            except Exception:
                continue
    return out
