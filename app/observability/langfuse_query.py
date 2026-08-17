"""Read-only Langfuse queries for the observability admin API."""

import json
import os
from datetime import datetime, timedelta, timezone
from typing import Any

from app.observability.cost import resolve_effective_cost_usd
from app.observability.features import FEATURE_CATALOG, feature_label, infer_feature
from app.observability.langfuse_trace import get_langfuse_client, is_langfuse_enabled, langfuse_host

_TEST_TRACE_PREFIXES = ("pytest", "monitoring-test", "model-only-test")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.isoformat().replace("+00:00", "Z")


def _safe_float(value: Any) -> float:
    try:
        if value is None:
            return 0.0
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _safe_int(value: Any) -> int:
    try:
        if value is None:
            return 0
        return int(value)
    except (TypeError, ValueError):
        return 0


def _metric_value(row: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in row and row[key] is not None:
            return row[key]
    return None


def _is_test_trace(name: str) -> bool:
    lowered = name.lower()
    return any(lowered.startswith(prefix) for prefix in _TEST_TRACE_PREFIXES)


def _usage_from_details(usage_details: Any) -> tuple[int, int, int]:
    if not isinstance(usage_details, dict):
        return 0, 0, 0
    input_tokens = _safe_int(
        usage_details.get("input")
        or usage_details.get("prompt_tokens")
        or usage_details.get("input_tokens")
    )
    output_tokens = _safe_int(
        usage_details.get("output")
        or usage_details.get("completion_tokens")
        or usage_details.get("output_tokens")
    )
    total_tokens = _safe_int(usage_details.get("total") or usage_details.get("total_tokens"))
    if total_tokens == 0 and (input_tokens or output_tokens):
        total_tokens = input_tokens + output_tokens
    return input_tokens, output_tokens, total_tokens


def _metadata_dict(obs: Any) -> dict[str, Any]:
    metadata = getattr(obs, "metadata", None)
    if isinstance(metadata, dict):
        return metadata
    return {}


def _model_from_observation(obs: Any) -> str | None:
    model = getattr(obs, "provided_model_name", None) or getattr(obs, "providedModelName", None)
    if model:
        return str(model)
    metadata = _metadata_dict(obs)
    deployment = metadata.get("deployment") or metadata.get("model")
    return str(deployment) if deployment else None


def resolve_langfuse_project_urls() -> tuple[str | None, str | None, str | None]:
    """Return (dashboard_url, traces_url, project_id) for the configured Langfuse project."""
    if not is_langfuse_enabled():
        return None, None, None

    host = langfuse_host()
    env_project = os.getenv("LANGFUSE_PROJECT_ID", "").strip()
    if env_project:
        return (
            f"{host}/project/{env_project}",
            f"{host}/project/{env_project}/traces",
            env_project,
        )

    client = get_langfuse_client()
    if client is None:
        return f"{host}/", None, None

    try:
        response = client.api.projects.get()
        projects = getattr(response, "data", None) or []
        if not projects:
            return f"{host}/", None, None
        project_id = str(getattr(projects[0], "id", "") or "")
        if not project_id:
            return f"{host}/", None, None
        return (
            f"{host}/project/{project_id}",
            f"{host}/project/{project_id}/traces",
            project_id,
        )
    except Exception:  # noqa: BLE001
        return f"{host}/", None, None


def build_status_payload(
    *,
    llm_provider: str | None,
    llm_model: str | None,
) -> dict[str, Any]:
    dashboard_url, traces_url, project_id = resolve_langfuse_project_urls()
    return {
        "langfuseEnabled": is_langfuse_enabled(),
        "langfuseHost": langfuse_host() if is_langfuse_enabled() else None,
        "langfuseProjectId": project_id,
        "langfuseDashboardUrl": dashboard_url,
        "langfuseTracesUrl": traces_url,
        "llmProvider": llm_provider,
        "llmModel": llm_model,
        "features": FEATURE_CATALOG,
    }


def _metrics_query(
    *,
    from_ts: datetime,
    to_ts: datetime,
    dimensions: list[dict[str, str]] | None = None,
) -> str:
    payload: dict[str, Any] = {
        "view": "observations",
        "metrics": [
            {"measure": "count", "aggregation": "count"},
            {"measure": "totalCost", "aggregation": "sum"},
            {"measure": "totalTokens", "aggregation": "sum"},
            {"measure": "inputTokens", "aggregation": "sum"},
            {"measure": "outputTokens", "aggregation": "sum"},
        ],
        "filters": [
            {
                "column": "type",
                "operator": "=",
                "value": "GENERATION",
                "type": "string",
            }
        ],
        "fromTimestamp": _iso(from_ts),
        "toTimestamp": _iso(to_ts),
    }
    if dimensions:
        payload["dimensions"] = dimensions
    return json.dumps(payload)


def _parse_metrics_rows(response: Any) -> list[dict[str, Any]]:
    data = getattr(response, "data", None)
    if data is None:
        return []
    if isinstance(data, list):
        return [row if isinstance(row, dict) else dict(row) for row in data]
    return []


async def fetch_summary(days: int = 7, *, include_tests: bool = False) -> dict[str, Any]:
    client = get_langfuse_client()
    if client is None:
        return {
            "available": False,
            "reason": "Langfuse is not configured (set LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY).",
            "periodDays": days,
            "totals": None,
            "byFeature": [],
            "byModel": [],
        }

    days = max(1, min(days, 90))
    to_ts = _utc_now()
    from_ts = to_ts - timedelta(days=days)

    try:
        totals_resp = client.api.metrics.metrics(
            query=_metrics_query(from_ts=from_ts, to_ts=to_ts),
        )
        by_name_resp = client.api.metrics.metrics(
            query=_metrics_query(
                from_ts=from_ts,
                to_ts=to_ts,
                dimensions=[{"field": "name"}],
            ),
        )
        by_model_resp = client.api.metrics.metrics(
            query=_metrics_query(
                from_ts=from_ts,
                to_ts=to_ts,
                dimensions=[{"field": "providedModelName"}],
            ),
        )
    except Exception as exc:  # noqa: BLE001
        return {
            "available": False,
            "reason": f"Langfuse metrics query failed: {exc}",
            "periodDays": days,
            "totals": None,
            "byFeature": [],
            "byModel": [],
        }

    totals_row = _parse_metrics_rows(totals_resp)[0] if _parse_metrics_rows(totals_resp) else {}
    by_feature: dict[str, dict[str, Any]] = {}
    any_cost_estimated = False
    for row in _parse_metrics_rows(by_name_resp):
        trace_name = str(row.get("name") or "unknown")
        if not include_tests and _is_test_trace(trace_name):
            continue
        feature_id = infer_feature(trace_name)
        langfuse_cost = _safe_float(_metric_value(row, "sum_totalCost", "totalCost_sum", "totalCost"))
        input_tokens = _safe_int(_metric_value(row, "sum_inputTokens", "inputTokens_sum", "inputTokens"))
        output_tokens = _safe_int(_metric_value(row, "sum_outputTokens", "outputTokens_sum", "outputTokens"))
        cost_usd, cost_estimated = resolve_effective_cost_usd(langfuse_cost, input_tokens, output_tokens)
        if cost_estimated:
            any_cost_estimated = True
        bucket = by_feature.setdefault(
            feature_id,
            {
                "featureId": feature_id,
                "label": feature_label(feature_id),
                "generations": 0,
                "totalCostUsd": 0.0,
                "totalTokens": 0,
                "traceNames": [],
            },
        )
        bucket["generations"] += _safe_int(_metric_value(row, "count_count", "count"))
        bucket["totalCostUsd"] += cost_usd
        bucket["totalTokens"] += _safe_int(_metric_value(row, "sum_totalTokens", "totalTokens_sum", "totalTokens"))
        if trace_name and trace_name not in bucket["traceNames"]:
            bucket["traceNames"].append(trace_name)

    by_model = []
    for row in _parse_metrics_rows(by_model_resp):
        model = str(row.get("providedModelName") or row.get("name") or "unknown")
        if model == "unknown" or model.lower() == "none":
            continue
        langfuse_cost = _safe_float(_metric_value(row, "sum_totalCost", "totalCost_sum", "totalCost"))
        input_tokens = _safe_int(_metric_value(row, "sum_inputTokens", "inputTokens_sum", "inputTokens"))
        output_tokens = _safe_int(_metric_value(row, "sum_outputTokens", "outputTokens_sum", "outputTokens"))
        cost_usd, cost_estimated = resolve_effective_cost_usd(langfuse_cost, input_tokens, output_tokens)
        if cost_estimated:
            any_cost_estimated = True
        by_model.append(
            {
                "model": model,
                "generations": _safe_int(_metric_value(row, "count_count", "count")),
                "totalCostUsd": cost_usd,
                "totalTokens": _safe_int(_metric_value(row, "sum_totalTokens", "totalTokens_sum", "totalTokens")),
            }
        )

    totals_langfuse_cost = _safe_float(_metric_value(totals_row, "sum_totalCost", "totalCost_sum", "totalCost"))
    totals_input_tokens = _safe_int(_metric_value(totals_row, "sum_inputTokens", "inputTokens_sum", "inputTokens"))
    totals_output_tokens = _safe_int(_metric_value(totals_row, "sum_outputTokens", "outputTokens_sum", "outputTokens"))
    totals_tokens = _safe_int(_metric_value(totals_row, "sum_totalTokens", "totalTokens_sum", "totalTokens"))
    totals_generations = _safe_int(_metric_value(totals_row, "count_count", "count"))
    totals_cost, totals_cost_estimated = resolve_effective_cost_usd(
        totals_langfuse_cost,
        totals_input_tokens,
        totals_output_tokens,
    )
    if totals_cost_estimated:
        any_cost_estimated = True

    if not include_tests:
        totals_generations = sum(row["generations"] for row in by_feature.values())
        totals_cost = sum(row["totalCostUsd"] for row in by_feature.values())
        totals_tokens = sum(row["totalTokens"] for row in by_feature.values())

    return {
        "available": True,
        "periodDays": days,
        "fromTimestamp": _iso(from_ts),
        "toTimestamp": _iso(to_ts),
        "totals": {
            "generations": totals_generations,
            "totalCostUsd": totals_cost,
            "totalTokens": totals_tokens,
            "costEstimated": any_cost_estimated,
        },
        "byFeature": sorted(
            by_feature.values(),
            key=lambda row: (row["totalCostUsd"], row["generations"]),
            reverse=True,
        ),
        "byModel": sorted(by_model, key=lambda row: (row["totalCostUsd"], row["generations"]), reverse=True),
    }


async def fetch_recent_generations(limit: int = 25, *, include_tests: bool = False) -> dict[str, Any]:
    client = get_langfuse_client()
    if client is None:
        return {
            "available": False,
            "reason": "Langfuse is not configured.",
            "items": [],
        }

    limit = max(1, min(limit, 100))
    fetch_limit = min(limit * 3, 100) if not include_tests else limit
    try:
        response = client.api.observations.get_many(
            type="GENERATION",
            fields="core,basic,usage,trace_context,model,metadata",
            limit=fetch_limit,
            parse_io_as_json=False,
        )
    except Exception as exc:  # noqa: BLE001
        return {
            "available": False,
            "reason": f"Langfuse observations query failed: {exc}",
            "items": [],
        }

    items: list[dict[str, Any]] = []
    for obs in getattr(response, "data", []) or []:
        name = str(getattr(obs, "name", None) or "unknown")
        if not include_tests and _is_test_trace(name):
            continue
        trace_id = getattr(obs, "trace_id", None) or getattr(obs, "traceId", None)
        feature_id = infer_feature(name)
        trace_url = None
        if trace_id:
            try:
                trace_url = client.get_trace_url(trace_id=trace_id)
            except Exception:  # noqa: BLE001
                trace_url = None
        start_time = getattr(obs, "start_time", None) or getattr(obs, "startTime", None)
        usage_details = getattr(obs, "usage_details", None) or getattr(obs, "usageDetails", None)
        input_tokens, output_tokens, total_tokens = _usage_from_details(usage_details)
        langfuse_cost = _safe_float(
            getattr(obs, "total_cost", None) or getattr(obs, "totalCost", None)
        )
        cost_usd, cost_estimated = resolve_effective_cost_usd(langfuse_cost, input_tokens, output_tokens)
        items.append(
            {
                "id": getattr(obs, "id", None),
                "traceId": trace_id,
                "name": name,
                "featureId": feature_id,
                "featureLabel": feature_label(feature_id),
                "model": _model_from_observation(obs),
                "startTime": start_time.isoformat() if hasattr(start_time, "isoformat") else start_time,
                "totalCostUsd": cost_usd,
                "costEstimated": cost_estimated,
                "inputTokens": input_tokens,
                "outputTokens": output_tokens,
                "totalTokens": total_tokens,
                "sessionId": getattr(obs, "session_id", None) or getattr(obs, "sessionId", None),
                "traceUrl": trace_url,
                "hasUsage": bool(usage_details),
            }
        )
        if len(items) >= limit:
            break

    return {
        "available": True,
        "items": items,
    }
