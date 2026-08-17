"""Tests for enrichment plan merge (services brain)."""

from app.onboard.enrichment_merge import merge_enrichment_plan


def test_merge_enrichment_plan_dedupes_by_source_and_path():
    patch_groups = [
        [
            {
                "path": "tradingName",
                "label": "Trading name",
                "value": "Acme",
                "confidence": 0.9,
                "source": "document",
                "sourceLabel": "PAN",
            }
        ],
        [
            {
                "path": "tradingName",
                "label": "Trading name",
                "value": "Acme Ltd",
                "confidence": 0.7,
                "source": "registry",
                "sourceLabel": "Registry",
            }
        ],
    ]
    plan = merge_enrichment_plan("sess-1", "IN", patch_groups, {})
    assert len(plan["options"]) == 2
    assert plan["conflicts"]


def test_merge_enrichment_plan_preselects_high_confidence():
    patch_groups = [
        [
            {
                "path": "tradingName",
                "label": "Trading name",
                "value": "Acme",
                "confidence": 0.95,
                "source": "document",
                "sourceLabel": "GST",
            }
        ]
    ]
    plan = merge_enrichment_plan("sess-1", "IN", patch_groups, {})
    assert plan["options"][0]["preSelected"] is True
