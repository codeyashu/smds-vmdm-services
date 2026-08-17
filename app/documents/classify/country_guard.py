"""Country prefix guard for document type codes."""

from __future__ import annotations


def doc_type_matches_country(country_code: str, doc_type: str) -> bool:
    country = country_code.strip().upper()
    doc_type_norm = doc_type.strip().upper()
    if not country or not doc_type_norm or doc_type_norm == "UNKNOWN":
        return False
    return doc_type_norm.startswith(f"{country}_")
