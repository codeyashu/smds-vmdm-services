"""Country-specific classify anchors for locale extraction."""

from __future__ import annotations

from app.documents.classify.doctype import Classification, DocType

_COUNTRY_ANCHORS: dict[str, list[tuple[DocType, tuple[str, ...]]]] = {
    "CN": [
        ("CN_BUSINESS_LICENSE", ("营业执照", "统一社会信用代码", "business license", "uscc", "法定代表人")),
        ("CN_BANK_ACCOUNT_PERMIT", ("开户许可证", "bank account permit", "基本存款账户")),
    ],
    "AE": [
        ("AE_TRADE_LICENSE", ("trade licence", "trade license", "economic department", "رخصة", "تجارية")),
        ("AE_VAT_CERTIFICATE", ("tax registration", "trn", "vat certificate", "الرقم الضريبي")),
    ],
    "US": [
        ("US_W9", ("form w-9", "w-9", "employer identification", "request for taxpayer")),
        ("US_VOIDED_CHECK", ("routing number", "account number", "void", "check")),
        ("US_CERTIFICATE_OF_GOOD_STANDING", ("certificate of good standing", "secretary of state")),
    ],
    "GB": [
        ("GB_COMPANIES_HOUSE_CERTIFICATE", ("companies house", "certificate of incorporation", "company number")),
        ("GB_VAT_CERTIFICATE", ("vat registration", "hm revenue", "vat certificate")),
    ],
}

_COUNTRY_FILENAME_PATTERNS: dict[str, list[tuple[DocType, tuple[str, ...]]]] = {
    "CN": [
        ("CN_BUSINESS_LICENSE", ("business_license", "yingye_zhizhao", "uscc")),
        ("CN_BANK_ACCOUNT_PERMIT", ("bank_permit", "kaihu")),
    ],
    "AE": [
        ("AE_TRADE_LICENSE", ("trade_license", "trade_licence")),
        ("AE_VAT_CERTIFICATE", ("vat_certificate", "trn")),
    ],
    "US": [
        ("US_W9", ("w9", "w_9")),
        ("US_VOIDED_CHECK", ("voided_check", "cancelled_check")),
        ("US_CERTIFICATE_OF_GOOD_STANDING", ("good_standing",)),
    ],
    "GB": [
        ("GB_COMPANIES_HOUSE_CERTIFICATE", ("companies_house", "certificate_of_incorporation")),
        ("GB_VAT_CERTIFICATE", ("vat_certificate",)),
    ],
}


def classify_by_anchors_for_country(text: str, country: str) -> Classification:
    lowered = (text or "").lower()
    anchors = _COUNTRY_ANCHORS.get(country.strip().upper(), [])
    scores: dict[DocType, int] = {}
    for doc_type, keywords in anchors:
        hits = sum(1 for keyword in keywords if keyword.lower() in lowered)
        if hits:
            scores[doc_type] = hits
    if not scores:
        return Classification(None, 0.0, ambiguous=True)
    ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    top_type, top_hits = ranked[0]
    runner_hits = ranked[1][1] if len(ranked) > 1 else 0
    ambiguous = top_hits - runner_hits < 1
    confidence = min(0.99, 0.6 + 0.15 * top_hits) if not ambiguous else 0.5
    return Classification(top_type, confidence, ambiguous=ambiguous)


def resolve_filename_hint_for_country(filename: str | None, country: str) -> DocType | None:
    if not filename:
        return None
    lowered = filename.lower().replace("-", "_")
    patterns = _COUNTRY_FILENAME_PATTERNS.get(country.strip().upper(), [])
    for doc_type, hints in patterns:
        if any(hint in lowered for hint in hints):
            return doc_type
    return None
