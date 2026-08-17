"""Tests for semantic score blending."""

from app.company_search.blend_scores import blend_semantic_scores


def test_blend_raises_name_score():
    scored = [
        {
            "summary": {"companyExternalId": "IN001"},
            "fieldConfidence": [
                {"field": "tradingName", "label": "Name", "score": 50, "status": "partial"},
            ],
            "overallScore": 50,
            "overallMatch": {"score": 50, "comparedFields": 1, "skippedFields": 0},
        }
    ]
    similarity = [{"id": "IN001", "nameScore": 95, "addressScore": 0}]
    blended = blend_semantic_scores(scored, similarity)
    assert blended[0]["overallScore"] == 95
    assert "tradingName" in blended[0]["aiRaisedFields"]
