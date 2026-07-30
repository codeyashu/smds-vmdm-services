"""Onboard enrichment stage runners — real tool calls via MCP gateway."""

from __future__ import annotations

import base64
from typing import Any

from app.documents.extract.pipeline import run_extraction
from app.documents.ingestion.validate_upload import UploadRejected, validate_upload
from app.core.config import get_settings
from app.onboard import mcp_gateway


def _read_bill_to_address(form_state: dict[str, Any]) -> dict[str, Any]:
    addresses = form_state.get("postalAddresses")
    if isinstance(addresses, list) and addresses and isinstance(addresses[0], dict):
        return addresses[0]
    return {}


async def run_extract_stage(context: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    files = context.get("files") or []
    country_code = str(context.get("countryCode") or "IN")
    doc_availability = context.get("docAvailability") or ("full" if files else "none")

    if doc_availability == "none" or not files:
        return "extract_skipped", context

    settings = get_settings()
    results: list[dict[str, Any]] = []
    extraction_failures: list[dict[str, str]] = []

    for entry in files:
        name = str(entry.get("name") or "upload")
        raw_b64 = entry.get("contentBase64")
        if not isinstance(raw_b64, str):
            extraction_failures.append({"fileName": name, "reason": "Missing file content."})
            continue
        content = base64.b64decode(raw_b64)
        try:
            validated = validate_upload(content, settings)
            result = await run_extraction(validated.content, validated.mime, country_code)
            results.append(result.as_dict())
        except UploadRejected as exc:
            extraction_failures.append({"fileName": name, "reason": exc.message})
            results.append(
                {
                    "documentId": "",
                    "docType": "UNKNOWN",
                    "docTypeConfidence": 0.0,
                    "patches": [],
                    "crossChecks": [],
                    "warnings": [exc.message],
                    "unmapped": [],
                }
            )
        except Exception as exc:  # noqa: BLE001
            extraction_failures.append({"fileName": name, "reason": str(exc)})
            results.append(
                {
                    "documentId": "",
                    "docType": "UNKNOWN",
                    "docTypeConfidence": 0.0,
                    "patches": [],
                    "crossChecks": [],
                    "warnings": [str(exc)],
                    "unmapped": [],
                }
            )

    context["extractResults"] = results
    context["extractionFailures"] = extraction_failures

    file_names = [str(entry.get("name") or f"file-{i + 1}") for i, entry in enumerate(files)]
    try:
        mapped = await mcp_gateway.invoke_read_tool(
            "map_extraction_results",
            {
                "body": {
                    "countryCode": country_code,
                    "results": results,
                    "fileNames": file_names,
                }
            },
        )
        patch_groups = mapped.get("patchGroups") or []
        if patch_groups:
            context["patchGroups"] = patch_groups
        if mapped.get("readOnlyHints"):
            context["readOnlyHints"] = mapped["readOnlyHints"]
        mapped_warnings = mapped.get("warnings") or []
        if mapped_warnings:
            context["mappedWarnings"] = mapped_warnings
    except Exception:  # noqa: BLE001
        pass

    applyable_count = sum(len(group) for group in context.get("patchGroups") or [])

    if applyable_count > 0:
        return "extract", context
    return "extract_empty", context


async def run_address_stage(context: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    form_state = context.get("workingState") or context.get("formState") or {}
    country_code = str(context.get("countryCode") or "IN")
    address = _read_bill_to_address(form_state)
    search_line = " ".join(
        str(address.get(key) or "").strip()
        for key in ("streetName", "cityName", "postalCode", "regionCode")
        if address.get(key)
    ).strip()
    if not search_line:
        return "address_enrich_skipped", context

    try:
        await mcp_gateway.invoke_read_tool(
            "enrich_address",
            {"body": {"searchLine": search_line, "countryCode": country_code}},
        )
        return "address_enrich", context
    except Exception:  # noqa: BLE001
        return "address_enrich_empty", context


async def run_registry_stage(context: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    form_state = context.get("workingState") or context.get("formState") or {}
    country_code = str(context.get("countryCode") or "IN")
    trading_name = str(form_state.get("tradingName") or "").strip()
    if not trading_name:
        return "registry_skipped", context

    address = _read_bill_to_address(form_state)
    try:
        await mcp_gateway.invoke_read_tool(
            "search_company_registry",
            {
                "query": {
                    "iso2CountryCode": country_code,
                    "tradingName": trading_name,
                    "city": str(address.get("cityName") or ""),
                    "streetName": str(address.get("streetName") or ""),
                    "postalCode": str(address.get("postalCode") or ""),
                    "limit": "5",
                }
            },
        )
        return "registry", context
    except Exception:  # noqa: BLE001
        return "registry_empty", context


async def run_duplicate_stage(context: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    form_state = context.get("workingState") or context.get("formState") or {}
    country_code = str(context.get("countryCode") or "IN")
    try:
        await mcp_gateway.invoke_read_tool(
            "search_duplicates",
            {"body": {"formState": form_state, "countryCode": country_code}},
        )
        return "duplicate_precheck", context
    except Exception:  # noqa: BLE001
        return "duplicate_precheck_skipped", context


async def run_build_plan_stage(context: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    session_id = str(context.get("sessionId") or "")
    country_code = str(context.get("countryCode") or "IN")
    form_state = context.get("formState") or {}
    patch_groups = context.get("patchGroups") or []
    warnings = [
        f"{item['fileName']}: {item['reason']}"
        for item in context.get("extractionFailures") or []
        if isinstance(item, dict) and item.get("fileName") and item.get("reason")
    ]
    warnings.extend(context.get("mappedWarnings") or [])

    try:
        response = await mcp_gateway.invoke_read_tool(
            "propose_vendor_patch",
            {
                "body": {
                    "sessionId": session_id,
                    "countryCode": country_code,
                    "formState": form_state,
                    "patchGroups": patch_groups,
                    "stepsCompleted": context.get("stepsCompleted") or [],
                    "readOnlyHints": context.get("readOnlyHints"),
                    "warnings": warnings or None,
                }
            },
        )
        plan = response.get("plan") or {
            "sessionId": session_id,
            "countryCode": country_code,
            "options": [],
            "stepsCompleted": context.get("stepsCompleted") or [],
            "warnings": warnings,
        }
        return plan, context
    except Exception:  # noqa: BLE001
        plan = {
            "sessionId": session_id,
            "countryCode": country_code,
            "options": [],
            "stepsCompleted": context.get("stepsCompleted") or [],
            "warnings": warnings,
        }
        return plan, context
