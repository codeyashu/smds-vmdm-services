"""Cross-document address candidate reconciliation vs form snapshot."""

from __future__ import annotations

import re
from typing import Any

from app.documents.validation.normalize import fuzzy_ratio

_PIN_RE = re.compile(r"\b(\d{6})\b")


def _normalize_token(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.strip().lower())


def _extract_pins(text: str) -> list[str]:
    return _PIN_RE.findall(text or "")


def _pin_near_match(a: str, b: str) -> bool:
    if not a or not b:
        return False
    if a == b:
        return True
    if len(a) == 6 and len(b) == 6:
        mismatches = sum(1 for x, y in zip(a, b) if x != y)
        return mismatches <= 1
    return False


def _contains_locality(haystack: str, needle: str) -> bool:
    if not haystack or not needle:
        return False
    h = haystack.lower()
    n = needle.strip().lower()
    return bool(n) and n in h


def _street_superset_score(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    na, nb = _normalize_token(a), _normalize_token(b)
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0
    if na in nb or nb in na:
        return 0.92
    return fuzzy_ratio(a, b) / 100.0


def _read_form_address(form_snapshot: dict[str, Any] | None) -> dict[str, str]:
    if not form_snapshot:
        return {}
    rows = form_snapshot.get("postalAddresses")
    if not isinstance(rows, list) or not rows or not isinstance(rows[0], dict):
        return {}
    row = rows[0]
    keys = ("buildingName", "streetName", "streetNumber", "district", "cityName", "postalCode", "regionCode")
    return {k: str(row.get(k) or "").strip() for k in keys if str(row.get(k) or "").strip()}


def _form_is_empty(form_addr: dict[str, str]) -> bool:
    return not any(form_addr.values())


def score_candidate_vs_form(
    candidate: dict[str, Any],
    form_addr: dict[str, str],
) -> tuple[float, list[str], list[str]]:
    """Return (alignment_score 0-1, matched_fields, gaps)."""
    fields = candidate.get("fields") if isinstance(candidate.get("fields"), dict) else {}
    full_text = str(candidate.get("fullAddressText") or "")
    matched: list[str] = []
    gaps: list[str] = []
    weights: list[tuple[float, float]] = []

    pin_form = form_addr.get("postalCode", "")
    pin_cand = str(fields.get("postalCode") or "")
    pins_in_line = _extract_pins(full_text)
    pin_hit = False
    if pin_form and pin_cand and _pin_near_match(pin_form, pin_cand):
        pin_hit = True
    elif pin_form and any(_pin_near_match(pin_form, p) for p in pins_in_line):
        pin_hit = True
    if pin_form:
        weights.append((0.25, 1.0 if pin_hit else 0.0))
        (matched if pin_hit else gaps).append("postalCode")

    for key, weight in (
        ("cityName", 0.2),
        ("district", 0.15),
        ("streetName", 0.2),
        ("buildingName", 0.1),
    ):
        form_val = form_addr.get(key, "")
        cand_val = str(fields.get(key) or "")
        if not form_val:
            if cand_val:
                gaps.append(key)
            continue
        if not cand_val:
            gaps.append(key)
            weights.append((weight, 0.0))
            continue
        if _contains_locality(full_text, form_val) or fuzzy_ratio(form_val, cand_val) >= 85:
            matched.append(key)
            weights.append((weight, 1.0))
        elif key == "streetName":
            ss = _street_superset_score(form_val, cand_val)
            if ss >= 0.9:
                matched.append(key)
                weights.append((weight, ss))
            else:
                gaps.append(key)
                weights.append((weight, ss))
        else:
            gaps.append(key)
            weights.append((weight, fuzzy_ratio(form_val, cand_val) / 100.0))

    if _form_is_empty(form_addr):
        role = str(candidate.get("addressRole") or "")
        role_bonus = {
            "operational": 0.15,
            "additional_pob": 0.1,
            "principal_pob": 0.05,
            "registered_office": 0.0,
            "plant": 0.0,
        }.get(role, 0.0)
        conf = float(candidate.get("confidence") or 0.0)
        return min(1.0, 0.5 + role_bonus + conf * 0.35), [], list(fields.keys())

    total_w = sum(w for w, _ in weights) or 1.0
    score = sum(w * s for w, s in weights) / total_w
    return score, matched, gaps


def reconcile_address_candidates(
    candidates: list[dict[str, Any]],
    form_snapshot: dict[str, Any] | None,
) -> dict[str, Any]:
    """Rank candidates and pick recommended billing address."""
    form_addr = _read_form_address(form_snapshot)
    if not candidates:
        return {
            "selectedCandidateKey": None,
            "alignmentScore": 0.0,
            "rationale": "No address candidates were extracted from the uploaded documents.",
            "ranked": [],
        }

    ranked: list[dict[str, Any]] = []
    for cand in candidates:
        score, matched, gaps = score_candidate_vs_form(cand, form_addr)
        ranked.append(
            {
                **cand,
                "alignmentScore": round(score, 3),
                "matchedFields": matched,
                "gaps": gaps,
                "recommendedForBillTo": False,
            }
        )

    ranked.sort(key=lambda row: float(row.get("alignmentScore") or 0.0), reverse=True)
    top = ranked[0]
    top["recommendedForBillTo"] = True

    if _form_is_empty(form_addr):
        rationale = (
            f"Suggested {top.get('label')} from {top.get('sourceDocType')} "
            f"(role: {top.get('addressRole')}, score {float(top.get('alignmentScore') or 0):.0%})."
        )
    else:
        rationale = (
            f"Best match to the form is {top.get('label')} "
            f"({len(top.get('matchedFields') or [])} fields align, "
            f"score {float(top.get('alignmentScore') or 0):.0%})."
        )

    return {
        "selectedCandidateKey": top.get("candidateKey"),
        "alignmentScore": top.get("alignmentScore"),
        "rationale": rationale,
        "ranked": ranked,
    }
