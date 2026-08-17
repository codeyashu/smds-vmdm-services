"""Doc-type classification: deterministic keyword anchors first, LLM tiebreak only when
the anchors are ambiguous. Keyword anchoring alone resolves the common cases (a GST cert
always says "GSTIN", a PAN card "Permanent Account Number") at zero model cost.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

DocType = str  # e.g. "IN_GST_CERTIFICATE"

_AADHAAR_RE = re.compile(r"\b\d{4}\s+\d{4}\s+\d{4}\b")

# Ordered by specificity; first strong match wins.
_ANCHORS: list[tuple[DocType, tuple[str, ...]]] = [
    ("IN_GST_CERTIFICATE", ("goods and services tax", "gstin", "registration certificate", "reg-06")),
    (
        "IN_PAN_CARD",
        (
            "permanent account number",
            "income tax department",
            "आयकर",
            "sole proprietor",
        ),
    ),
    ("IN_DEED_OF_PARTNERSHIP", ("deed of partnership", "partnership deed", "llp agreement", "limited liability partnership")),
    (
        "IN_MTO_IATA_CHA_CERTIFICATE",
        ("multimodal transport operator", "mto licence", "mto certificate", "customs house agent", "cha certificate"),
    ),
    ("IN_IEC_CERTIFICATE", ("importer exporter code", "iec certificate", "directorate general of foreign trade", "dgft")),
    ("IN_ADDRESS_PROOF", ("address proof", "utility bill", "electricity bill", "rent agreement")),
    ("IN_CANCELLED_CHEQUE", ("ifsc", "cancelled", "a/c no", "account number", "micr")),
    ("IN_UDYAM_CERTIFICATE", ("udyam", "msme", "ministry of micro")),
    ("IN_CERTIFICATE_OF_INCORPORATION", ("certificate of incorporation", "corporate identity number", "cin")),
]

# Filename substrings (normalised) → doc type hint when OCR anchors are weak.
_FILENAME_PATTERNS: list[tuple[DocType, tuple[str, ...]]] = [
    ("IN_PAN_CARD", ("pan_card", "pan_aadhaar", "business_pan", "sole_proprietor")),
    ("IN_GST_CERTIFICATE", ("gst_certificate", "gst_cert")),
    ("IN_ADDRESS_PROOF", ("address_proof",)),
    ("IN_MTO_IATA_CHA_CERTIFICATE", ("mto_iata", "iata_cha", "cha_certificate")),
    ("IN_IEC_CERTIFICATE", ("importer_exporter", "iec_certificate")),
    ("IN_CERTIFICATE_OF_INCORPORATION", ("certificate_of_incorporation",)),
    ("IN_DEED_OF_PARTNERSHIP", ("deed_of_partnership", "partnership_deed")),
    ("IN_CANCELLED_CHEQUE", ("cancelled_cheque", "bank_cheque")),
    ("IN_UDYAM_CERTIFICATE", ("udyam",)),
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


def classify_by_filename(filename: str | None) -> DocType | None:
    """Weak doc-type hint from upload filename when OCR text is sparse."""
    if not filename:
        return None
    lowered = filename.lower().replace("-", "_")
    for doc_type, patterns in _FILENAME_PATTERNS:
        if any(pattern in lowered for pattern in patterns):
            return doc_type
    return None


def is_aadhaar_only_document(text: str) -> bool:
    """True when OCR text is clearly an Aadhaar card with no PAN markers."""
    lowered = (text or "").lower()
    has_aadhaar = any(
        marker in lowered
        for marker in ("aadhaar", "uidai", "enrolment no", "unique identification authority")
    )
    has_pan = any(marker in lowered for marker in ("permanent account number", "income tax department"))
    return has_aadhaar and not has_pan


def extract_aadhaar_number(text: str) -> str | None:
    match = _AADHAAR_RE.search(text or "")
    if not match:
        return None
    return re.sub(r"\s+", "", match.group(0))


def resolve_filename_hint(filename: str | None, ocr_text: str) -> DocType | None:
    """Filename hint adjusted when the embedded text contradicts it (e.g. Aadhaar-only upload named pan_aadhaar)."""
    hinted = classify_by_filename(filename)
    if hinted == "IN_PAN_CARD" and is_aadhaar_only_document(ocr_text):
        return "IN_ADDRESS_PROOF"
    return hinted
