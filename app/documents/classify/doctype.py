"""Doc-type classification: deterministic keyword anchors first, LLM tiebreak only when
the anchors are ambiguous. Keyword anchoring alone resolves the common cases (a GST cert
always says "GSTIN", a PAN card "Permanent Account Number") at zero model cost.
"""

from __future__ import annotations

from dataclasses import dataclass

DocType = str  # e.g. "IN_GST_CERTIFICATE"

# Ordered by specificity; first strong match wins.
_ANCHORS: list[tuple[DocType, tuple[str, ...]]] = [
    ("IN_GST_CERTIFICATE", ("goods and services tax", "gstin", "registration certificate", "reg-06")),
    ("IN_PAN_CARD", ("permanent account number", "income tax department", "आयकर")),
    ("IN_CANCELLED_CHEQUE", ("ifsc", "cancelled", "a/c no", "account number", "micr")),
    ("IN_UDYAM_CERTIFICATE", ("udyam", "msme", "ministry of micro")),
    ("IN_CERTIFICATE_OF_INCORPORATION", ("certificate of incorporation", "corporate identity number", "cin")),
]


@dataclass(frozen=True)
class Classification:
    doc_type: DocType | None
    confidence: float
    ambiguous: bool


def classify_by_anchors(text: str) -> Classification:
    lowered = (text or "").lower()
    scores: dict[DocType, int] = {}
    for doc_type, anchors in _ANCHORS:
        hits = sum(1 for a in anchors if a in lowered)
        if hits:
            scores[doc_type] = hits
    if not scores:
        return Classification(None, 0.0, ambiguous=True)
    ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    top_type, top_hits = ranked[0]
    runner_hits = ranked[1][1] if len(ranked) > 1 else 0
    # Confident when the leader clearly out-scores the runner-up.
    ambiguous = top_hits - runner_hits < 1
    confidence = min(0.99, 0.6 + 0.15 * top_hits) if not ambiguous else 0.5
    return Classification(top_type, confidence, ambiguous=ambiguous)
