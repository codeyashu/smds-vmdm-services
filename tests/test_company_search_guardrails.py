"""Pure value-shaping helpers ported from the portal's llm-guardrails.ts. No LLM involved."""

from __future__ import annotations

from app.company_search.guardrails import clamp_score, read_string_list, read_trimmed_string


def test_clamp_score_rounds_and_clamps():
    assert clamp_score(50.4) == 50
    assert clamp_score(50.5) == 51  # JS Math.round rounds .5 up, not banker's rounding
    assert clamp_score(-5) == 0
    assert clamp_score(150) == 100
    assert clamp_score("77") == 77


def test_clamp_score_rejects_non_numeric():
    assert clamp_score("not a number") is None
    assert clamp_score(None) is None
    assert clamp_score(True) is None
    assert clamp_score(float("nan")) is None
    assert clamp_score(float("inf")) is None


def test_read_trimmed_string_trims_and_caps_length():
    assert read_trimmed_string("  hello  ") == "hello"
    assert read_trimmed_string("   ") is None
    assert read_trimmed_string(123) is None
    assert read_trimmed_string("abcdef", max_length=3) == "abc"


def test_read_string_list_dedupes_case_insensitively_and_caps():
    result = read_string_list(["Acme Ltd", "acme ltd", "  Other Co  ", "", 5, "Third"], limit=2)
    assert result == ["Acme Ltd", "Other Co"]


def test_read_string_list_rejects_non_list():
    assert read_string_list("not a list", limit=5) == []
    assert read_string_list(None, limit=5) == []
