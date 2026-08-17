"""Langfuse configuration smoke test."""

from app.observability.langfuse_trace import is_langfuse_enabled, trace_generation


def test_langfuse_trace_smoke_when_configured():
    if not is_langfuse_enabled():
        return
    with trace_generation("pytest-smoke", model="test", input={"ping": True}) as gen:
        assert gen is not None
        gen.update(output={"pong": True})
