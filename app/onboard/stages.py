"""Onboard enrichment stage runners — services-owned; MDM direct when configured."""

from __future__ import annotations

import base64
from typing import Any

from app.documents.validation.adjudicate import adjudicate_bundle
from app.documents.extract.pipeline import run_extraction
from app.documents.ingestion.validate_upload import UploadRejected, validate_upload
from app.core.config import get_settings
from app.mdm.address_mapping import (
    build_postal_address_search_line,
    extract_city_fields_from_select,
    patches_from_select_address,
)
from app.mdm.city_reference import resolve_city_reference_patches
from app.mdm.config import is_mdm_configured
from app.mdm.company_search import search_company_external
from app.mdm.duplicate_search import build_duplicate_request, search_duplicate_vendors
from app.mdm.external_address import select_external_address
from app.onboard import mcp_gateway
from app.onboard.adjudication_patches import patches_from_adjudication
from app.onboard.enrichment_merge import apply_patches_to_form_state, merge_enrichment_plan
from app.onboard.extraction_mapping import (
    patches_from_bff_address,
    patches_from_extract_results,
    patches_from_registry_summary,
    read_only_hints_from_results,
    summarize_duplicate_matches,
)
from app.onboard.stage_gate import decide_stage, gated_step_id

ADDRESS_BASE_PATH = "postalAddresses.0"


def _merge_patches(*groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[str, Any] = {}
    for group in groups:
        for patch in group:
            if isinstance(patch, dict) and patch.get("path"):
                merged[str(patch["path"])] = patch.get("value")
    return [{"path": path, "value": value} for path, value in merged.items()]


def _read_bill_to_address(form_state: dict[str, Any]) -> dict[str, Any]:
    addresses = form_state.get("postalAddresses")
    if isinstance(addresses, list) and addresses and isinstance(addresses[0], dict):
        return addresses[0]
    return {}


def _working_state(context: dict[str, Any]) -> dict[str, Any]:
    return context.get("workingState") or context.get("formState") or {}


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

    adjudication = adjudicate_bundle(country_code, results, _working_state(context))
    context["documentAdjudication"] = adjudication.as_dict()
    if adjudication.warnings:
        context.setdefault("adjudicationWarnings", []).extend(adjudication.warnings)

    all_doc_patches = patches_from_extract_results(results)
    preview_patches = patches_from_adjudication(adjudication.as_dict(), mode="agent")
    hints = read_only_hints_from_results(results)
    if hints:
        context["readOnlyHints"] = hints

    if all_doc_patches:
        groups = list(context.get("patchGroups") or [])
        groups.append(all_doc_patches)
        context["patchGroups"] = groups
        if preview_patches:
            context["workingState"] = apply_patches_to_form_state(_working_state(context), preview_patches)
        return "extract", context

    return "extract_empty", context


async def run_address_stage(context: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    form_state = _working_state(context)
    country_code = str(context.get("countryCode") or "IN")
    gate = decide_stage("address_enrich", form_state, context.get("resolvedStages"))
    if not gate["run"]:
        return gated_step_id("address_enrich", gate["reason"]), context

    address = _read_bill_to_address(form_state)
    search_line = build_postal_address_search_line(address)
    if not search_line.strip():
        return "address_enrich_skipped", context

    try:
        if is_mdm_configured():
            result = await select_external_address(search_line, country_code)
            base_patches = patches_from_select_address(ADDRESS_BASE_PATH, result)
            city_fields = extract_city_fields_from_select(result)
            country_obj = result.get("country")
            iso = country_code
            if isinstance(country_obj, dict) and country_obj.get("iso2CountryCode"):
                iso = str(country_obj["iso2CountryCode"])
            city_patches = await resolve_city_reference_patches(
                ADDRESS_BASE_PATH,
                iso,
                city_fields,
            )
            raw_patches = _merge_patches(base_patches, city_patches)
        else:
            response = await mcp_gateway.invoke_read_tool(
                "enrich_address",
                {"body": {"searchLine": search_line, "countryCode": country_code}},
            )
            raw_patches = patches_from_bff_address(response.get("patches") or [])

        if raw_patches:
            groups = list(context.get("patchGroups") or [])
            groups.append(raw_patches)
            context["patchGroups"] = groups
            context["workingState"] = apply_patches_to_form_state(form_state, raw_patches)
            return "address_enrich", context
        return "address_enrich_empty", context
    except Exception:  # noqa: BLE001
        return "address_enrich_skipped", context


async def run_registry_stage(context: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    form_state = _working_state(context)
    country_code = str(context.get("countryCode") or "IN")
    gate = decide_stage("registry", form_state, context.get("resolvedStages"))
    if not gate["run"]:
        return gated_step_id("registry", gate["reason"]), context

    trading_name = str(form_state.get("tradingName") or "").strip()
    if not trading_name:
        return "registry_skipped", context

    address = _read_bill_to_address(form_state)
    try:
        if is_mdm_configured():
            response = await search_company_external(
                {
                    "iso2CountryCode": country_code,
                    "tradingName": trading_name,
                    "city": str(address.get("cityName") or ""),
                    "streetName": str(address.get("streetName") or ""),
                    "postalCode": str(address.get("postalCode") or ""),
                    "limit": "3",
                }
            )
        else:
            response = await mcp_gateway.invoke_read_tool(
                "search_company_registry",
                {
                    "query": {
                        "iso2CountryCode": country_code,
                        "tradingName": trading_name,
                        "city": str(address.get("cityName") or ""),
                        "streetName": str(address.get("streetName") or ""),
                        "postalCode": str(address.get("postalCode") or ""),
                        "limit": "3",
                    }
                },
            )

        summaries = response.get("customerSummaries") or []
        if not summaries:
            return "registry_empty", context
        top = summaries[0]
        raw_patches = patches_from_registry_summary(top, trading_name)
        groups = list(context.get("patchGroups") or [])
        groups.append(raw_patches)
        context["patchGroups"] = groups
        context["workingState"] = apply_patches_to_form_state(form_state, raw_patches)
        return "registry", context
    except Exception:  # noqa: BLE001
        return "registry_skipped", context


async def run_duplicate_stage(context: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    form_state = _working_state(context)
    country_code = str(context.get("countryCode") or "IN")
    gate = decide_stage("duplicate_precheck", form_state, context.get("resolvedStages"))
    if not gate["run"]:
        return gated_step_id("duplicate_precheck", gate["reason"]), context

    try:
        if is_mdm_configured():
            request = build_duplicate_request(form_state, country_code)
            response = await search_duplicate_vendors(request)
        else:
            response = await mcp_gateway.invoke_read_tool(
                "search_duplicates",
                {"body": {"formState": form_state, "countryCode": country_code}},
            )

        items = response.get("items") or []
        if items:
            context["duplicateMatches"] = summarize_duplicate_matches(items)
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

    plan = merge_enrichment_plan(
        session_id,
        country_code,
        patch_groups,
        form_state,
        duplicate_matches=context.get("duplicateMatches"),
        steps_completed=context.get("stepsCompleted") or [],
        read_only_hints=context.get("readOnlyHints"),
        warnings=warnings or None,
    )
    return plan, context
