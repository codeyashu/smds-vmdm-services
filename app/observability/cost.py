"""LLM cost estimation when Langfuse has no model price match."""

from __future__ import annotations

import os


def _per_token_rates() -> tuple[float, float]:
    input_per_mtok = float(os.getenv("LLM_COST_INPUT_PER_MTOK", "2.0"))
    output_per_mtok = float(os.getenv("LLM_COST_OUTPUT_PER_MTOK", "8.0"))
    return input_per_mtok / 1_000_000, output_per_mtok / 1_000_000


def estimate_cost_usd(input_tokens: int, output_tokens: int) -> float:
    inp_rate, out_rate = _per_token_rates()
    return max(0, int(input_tokens)) * inp_rate + max(0, int(output_tokens)) * out_rate


def cost_details_for_usage(input_tokens: int, output_tokens: int) -> dict[str, float]:
    inp_rate, out_rate = _per_token_rates()
    input_cost = max(0, int(input_tokens)) * inp_rate
    output_cost = max(0, int(output_tokens)) * out_rate
    return {
        "input": input_cost,
        "output": output_cost,
        "total": input_cost + output_cost,
    }


def resolve_effective_cost_usd(
    langfuse_cost: float,
    input_tokens: int,
    output_tokens: int,
) -> tuple[float, bool]:
    """Return (cost_usd, is_estimated). Prefer Langfuse when non-zero."""
    if langfuse_cost > 0:
        return langfuse_cost, False
    if input_tokens or output_tokens:
        return estimate_cost_usd(input_tokens, output_tokens), True
    return 0.0, False
