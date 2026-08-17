"""Country guard tests."""

from app.documents.classify.country_guard import doc_type_matches_country


def test_doc_type_matches_country_prefix():
    assert doc_type_matches_country("IN", "IN_PAN_CARD")
    assert not doc_type_matches_country("DK", "IN_PAN_CARD")
    assert not doc_type_matches_country("IN", "UNKNOWN")
