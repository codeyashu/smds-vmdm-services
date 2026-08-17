"""Register Azure deployment pricing in Langfuse so generations auto-cost."""

from __future__ import annotations

import logging
import os
import re

from app.observability.cost import _per_token_rates
from app.observability.langfuse_trace import get_langfuse_client, is_langfuse_enabled

logger = logging.getLogger(__name__)

_registered: set[str] = set()


def _prices_match(existing_input: float, existing_output: float, inp_rate: float, out_rate: float) -> bool:
    return abs(existing_input - inp_rate) < 1e-12 and abs(existing_output - out_rate) < 1e-12


def _find_custom_model(client: object, deployment: str) -> object | None:
    page = 1
    while True:
        response = client.api.models.list(page=page, limit=100)
        for model in response.data or []:
            if model.model_name == deployment and not getattr(model, "is_langfuse_managed", True):
                return model
        meta = getattr(response, "meta", None)
        if not meta or page >= meta.total_pages:
            break
        page += 1
    return None


def ensure_langfuse_model_pricing(model_name: str | None) -> None:
    if not model_name or not is_langfuse_enabled():
        return
    deployment = model_name.strip()
    if not deployment or deployment in _registered:
        return

    client = get_langfuse_client()
    if client is None:
        return

    inp_rate, out_rate = _per_token_rates()
    pattern = f"(?i)^({re.escape(deployment)})$"
    try:
        from langfuse.api.commons.types.model_usage_unit import ModelUsageUnit

        existing = _find_custom_model(client, deployment)
        if existing and _prices_match(existing.input_price, existing.output_price, inp_rate, out_rate):
            logger.debug("Langfuse model pricing already current for %s", deployment)
        elif existing:
            client.api.models.delete(id=str(existing.id))
            logger.info("Langfuse model pricing replaced for %s", deployment)
            client.api.models.create(
                model_name=deployment,
                match_pattern=pattern,
                unit=ModelUsageUnit.TOKENS,
                input_price=inp_rate,
                output_price=out_rate,
            )
            logger.info(
                "Langfuse model pricing synced for %s (input=%s output=%s per token)",
                deployment,
                inp_rate,
                out_rate,
            )
        else:
            client.api.models.create(
                model_name=deployment,
                match_pattern=pattern,
                unit=ModelUsageUnit.TOKENS,
                input_price=inp_rate,
                output_price=out_rate,
            )
            logger.info("Langfuse model pricing registered for %s", deployment)
    except Exception as exc:  # noqa: BLE001
        logger.debug("Langfuse model pricing skipped for %s: %s", deployment, exc)

    _registered.add(deployment)


def ensure_default_langfuse_model_pricing() -> None:
    deployment = os.getenv("DOCAI_AOAI_DEPLOYMENT", "").strip()
    if deployment:
        ensure_langfuse_model_pricing(deployment)
