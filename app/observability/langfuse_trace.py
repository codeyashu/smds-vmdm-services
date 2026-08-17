"""Langfuse tracing for LLM calls — optional when keys are configured."""

from __future__ import annotations

import os
from contextlib import contextmanager
from functools import lru_cache
from typing import Any, Iterator

from app.observability.cost import cost_details_for_usage
from app.observability.features import infer_feature


def langfuse_host() -> str:
    return (
        os.getenv("LANGFUSE_HOST")
        or os.getenv("LANGFUSE_BASE_URL")
        or "https://cloud.langfuse.com"
    ).rstrip("/")


def is_langfuse_enabled() -> bool:
    return bool(os.getenv("LANGFUSE_PUBLIC_KEY") and os.getenv("LANGFUSE_SECRET_KEY"))


@lru_cache(maxsize=1)
def get_langfuse_client() -> Any | None:
    if not is_langfuse_enabled():
        return None
    from langfuse import Langfuse

    return Langfuse(
        public_key=os.getenv("LANGFUSE_PUBLIC_KEY"),
        secret_key=os.getenv("LANGFUSE_SECRET_KEY"),
        host=langfuse_host(),
    )


def build_generation_metadata(
    trace_name: str,
    *,
    provider: str | None = None,
    model: str | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    metadata: dict[str, Any] = {
        "feature": infer_feature(trace_name),
        "traceName": trace_name,
    }
    if provider:
        metadata["provider"] = provider
    if model:
        metadata["deployment"] = model
    if extra:
        metadata.update(extra)
    return metadata


def update_generation_usage(
    generation: Any,
    *,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
    total_tokens: int | None = None,
    output: Any = None,
    model: str | None = None,
) -> None:
    if generation is None:
        return
    usage_details: dict[str, int] = {}
    if input_tokens is not None:
        usage_details["input"] = max(0, int(input_tokens))
    if output_tokens is not None:
        usage_details["output"] = max(0, int(output_tokens))
    if total_tokens is not None:
        usage_details["total"] = max(0, int(total_tokens))
    elif usage_details:
        usage_details["total"] = usage_details.get("input", 0) + usage_details.get("output", 0)
    try:
        update_kwargs: dict[str, Any] = {}
        if output is not None:
            update_kwargs["output"] = output
        if usage_details:
            update_kwargs["usage_details"] = usage_details
            input_count = usage_details.get("input", 0)
            output_count = usage_details.get("output", 0)
            if input_count or output_count:
                update_kwargs["cost_details"] = cost_details_for_usage(input_count, output_count)
        if model:
            update_kwargs["model"] = model
        if update_kwargs:
            generation.update(**update_kwargs)
    except Exception:  # noqa: BLE001
        return


@contextmanager
def trace_generation(
    name: str,
    *,
    model: str | None = None,
    input: Any = None,
    metadata: dict[str, Any] | None = None,
) -> Iterator[Any]:
    client = get_langfuse_client()
    if client is None:
        yield None
        return

    merged_metadata = build_generation_metadata(name, model=model, extra=metadata)
    try:
        with client.start_as_current_observation(
            as_type="generation",
            name=name,
            model=model,
            input=input,
            metadata=merged_metadata,
        ) as generation:
            yield generation
        client.flush()
    except Exception:  # noqa: BLE001
        yield None

