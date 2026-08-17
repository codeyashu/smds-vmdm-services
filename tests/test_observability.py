"""Tests for feature inference and Langfuse helpers."""

from app.observability.features import infer_feature
from app.observability.langfuse_trace import build_generation_metadata, update_generation_usage


def test_infer_feature_maps_trace_names():
    assert infer_feature("extract.envelope") == "doc_extract"
    assert infer_feature("company_search.adjudicate") == "company_search"
    assert infer_feature("nl_search.parse_repair") == "nl_search"
    assert infer_feature("steward_assist.explain_validation") == "steward_assist"
    assert infer_feature("onboard.chat_plan") == "onboard_chat"


def test_build_generation_metadata_includes_feature():
    metadata = build_generation_metadata("company_search.similarity", provider="azure")
    assert metadata["feature"] == "company_search"
    assert metadata["provider"] == "azure"
    assert metadata["traceName"] == "company_search.similarity"


def test_update_generation_usage_noop_when_generation_missing():
    update_generation_usage(None, input_tokens=10, output_tokens=5, output={"ok": True})


class _FakeGeneration:
    def __init__(self) -> None:
        self.payload: dict | None = None

    def update(self, **kwargs):
        self.payload = kwargs


def test_update_generation_usage_sets_usage_and_output():
    generation = _FakeGeneration()
    update_generation_usage(
        generation,
        input_tokens=12,
        output_tokens=8,
        total_tokens=20,
        output={"parsed": True},
        model="gpt-test",
    )
    assert generation.payload == {
        "output": {"parsed": True},
        "usage_details": {"input": 12, "output": 8, "total": 20},
        "cost_details": {"input": 12 * 2.0 / 1_000_000, "output": 8 * 8.0 / 1_000_000, "total": 12 * 2.0 / 1_000_000 + 8 * 8.0 / 1_000_000},
        "model": "gpt-test",
    }


def test_estimate_cost_from_tokens():
    from app.observability.cost import estimate_cost_usd, resolve_effective_cost_usd

    assert estimate_cost_usd(1_000_000, 0) == 2.0
    assert estimate_cost_usd(0, 1_000_000) == 8.0
    cost, estimated = resolve_effective_cost_usd(0.0, 524, 40)
    assert estimated is True
    assert cost > 0
    cost, estimated = resolve_effective_cost_usd(0.01, 524, 40)
    assert estimated is False
    assert cost == 0.01
