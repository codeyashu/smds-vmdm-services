"""DocumentRequirement model — plain construction, no DB required."""

from __future__ import annotations

from app.requirements.models import DocumentRequirement


def test_document_requirement_defaults():
    row = DocumentRequirement(country_code="IN", doc_type="IN_PAN_CARD", label="PAN card")
    assert row.id is None
    assert row.is_mandatory is True
    assert row.sort_order == 0
    assert row.created_at is not None
    assert row.updated_at is not None


def test_document_requirement_accepts_explicit_values():
    row = DocumentRequirement(
        country_code="IN",
        doc_type="IN_UDYAM_CERTIFICATE",
        label="Udyam certificate",
        is_mandatory=False,
        sort_order=4,
    )
    assert row.is_mandatory is False
    assert row.sort_order == 4
