"""India GSTIN live registry lookup via GSP (or fixture mode for dev/test)."""

from __future__ import annotations

import hashlib
import os
import time
from dataclasses import dataclass
from typing import Any

import httpx

from app.web_trust.tax_validators import validate_in_gstin

GST_PUBLIC_BASE = "https://www.gst.gov.in/"

# Dev/test fixture — keyed by normalized GSTIN.
FIXTURE_REGISTRY: dict[str, dict[str, Any]] = {
    "27AAPFU0939F1ZV": {
        "legalName": "ACME LOGISTICS PRIVATE LIMITED",
        "tradingName": "Acme Logistics",
        "gstStatus": "Active",
        "street": "1 MG Road Fort",
        "cityName": "Mumbai",
        "postalCode": "400001",
        "stateCode": "27",
    },
}


@dataclass(frozen=True)
class GstinLookupResult:
    extracted: dict[str, Any] | None = None
    limitation: str | None = None


def gst_gsp_api_key() -> str | None:
    value = os.environ.get("IN_GST_GSP_API_KEY", "").strip()
    return value or None


def gst_gsp_base_url() -> str | None:
    value = os.environ.get("IN_GST_GSP_BASE_URL", "").strip()
    return value or None


def gst_lookup_timeout_s() -> float:
    raw = os.environ.get("IN_GST_LOOKUP_TIMEOUT_S", "10").strip()
    try:
        return float(raw)
    except ValueError:
        return 10.0


def gst_lookup_path_template() -> str:
    return os.environ.get("IN_GST_GSP_LOOKUP_PATH", "/gstin/{gstin}").strip() or "/gstin/{gstin}"


def hash_gstin_for_trace(gstin: str) -> str:
    return hashlib.sha256(gstin.encode()).hexdigest()[:16]


def _inactive_status(status: str | None) -> bool:
    if not status:
        return False
    normalized = status.strip().lower()
    return normalized in {"cancelled", "canceled", "inactive", "suspended", "provisional"}


def _join_street_parts(*parts: Any) -> str | None:
    joined = " ".join(
        str(part).strip() for part in parts if isinstance(part, str) and str(part).strip()
    )
    return joined or None


def _normalize_gsp_payload(payload: dict[str, Any], gstin: str) -> dict[str, Any] | None:
    status = (
        payload.get("gstStatus")
        or payload.get("status")
        or payload.get("sts")
        or payload.get("Status")
    )
    if _inactive_status(str(status) if status is not None else None):
        return None

    legal_name = (
        payload.get("legalName")
        or payload.get("legal_name")
        or payload.get("lgnm")
        or payload.get("LegalName")
    )
    trading_name = (
        payload.get("tradingName")
        or payload.get("trade_name")
        or payload.get("tradeNam")
        or payload.get("TradeName")
        or legal_name
    )

    place = (
        payload.get("principalPlaceOfBusiness")
        or payload.get("principal_place")
        or payload.get("pradr")
        or payload.get("address")
        or {}
    )
    if isinstance(place, dict) and "addr" in place and isinstance(place["addr"], dict):
        addr = place["addr"]
    elif isinstance(place, dict):
        addr = place
    else:
        addr = {}

    street = _join_street_parts(
        addr.get("street"),
        addr.get("bnm"),
        addr.get("bno"),
        addr.get("st"),
        addr.get("addr"),
        addr.get("address_line_1"),
    )
    city = addr.get("cityName") or addr.get("loc") or addr.get("city") or addr.get("dst")
    postal = addr.get("postalCode") or addr.get("pincode") or addr.get("pin")
    state_code = (
        payload.get("stateCode")
        or addr.get("stateCode")
        or addr.get("stcd")
        or gstin[:2]
    )

    return {
        "taxIdentificationNumber": gstin,
        "legalName": legal_name,
        "tradingName": trading_name,
        "gstStatus": status or "Active",
        "street": street,
        "cityName": city,
        "postalCode": postal,
        "stateCode": state_code,
        "iso2CountryCode": "IN",
        "status": "registry_confirmed",
        "sourceUrl": f"{GST_PUBLIC_BASE}",
    }


def _fixture_lookup(gstin: str) -> GstinLookupResult:
    fixture = FIXTURE_REGISTRY.get(gstin)
    if not fixture:
        return GstinLookupResult(
            limitation=f"GSTIN {gstin} not found or inactive in registry (fixture mode).",
        )
    extracted = {
        "taxIdentificationNumber": gstin,
        "legalName": fixture["legalName"],
        "tradingName": fixture["tradingName"],
        "gstStatus": fixture["gstStatus"],
        "street": fixture.get("street"),
        "cityName": fixture.get("cityName"),
        "postalCode": fixture.get("postalCode"),
        "stateCode": fixture.get("stateCode"),
        "iso2CountryCode": "IN",
        "status": "registry_confirmed",
        "sourceUrl": GST_PUBLIC_BASE,
    }
    return GstinLookupResult(extracted=extracted)


def _gsp_http_lookup(gstin: str) -> GstinLookupResult:
    api_key = gst_gsp_api_key()
    base_url = gst_gsp_base_url()
    if not api_key or not base_url:
        return GstinLookupResult()

    path = gst_lookup_path_template().replace("{gstin}", gstin)
    url = f"{base_url.rstrip('/')}/{path.lstrip('/')}"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Accept": "application/json",
    }
    client_id = os.environ.get("IN_GST_GSP_CLIENT_ID", "").strip()
    if client_id:
        headers["X-Client-Id"] = client_id

    timeout = gst_lookup_timeout_s()
    for attempt in range(2):
        try:
            with httpx.Client(timeout=timeout) as client:
                response = client.get(url, headers=headers)
        except httpx.HTTPError:
            if attempt == 0:
                time.sleep(0.5)
                continue
            return GstinLookupResult(
                limitation="GST registry unavailable — format checks only.",
            )

        if response.status_code == 404:
            return GstinLookupResult(
                limitation=f"GSTIN {gstin} not found or inactive in registry.",
            )
        if response.status_code == 429:
            if attempt == 0:
                time.sleep(1.0)
                continue
            return GstinLookupResult(
                limitation="GST registry rate limited — format checks only.",
            )
        if response.status_code >= 500:
            if attempt == 0:
                time.sleep(0.5)
                continue
            return GstinLookupResult(
                limitation="GST registry unavailable — format checks only.",
            )
        if response.status_code != 200:
            return GstinLookupResult(
                limitation="GST registry unavailable — format checks only.",
            )

        try:
            payload = response.json()
        except ValueError:
            return GstinLookupResult(
                limitation="GST registry returned an invalid response — format checks only.",
            )

        if not isinstance(payload, dict):
            return GstinLookupResult(
                limitation="GST registry returned an invalid response — format checks only.",
            )

        extracted = _normalize_gsp_payload(payload, gstin)
        if extracted is None:
            return GstinLookupResult(
                limitation=f"GSTIN {gstin} not found or inactive in registry.",
            )
        extracted["sourceUrl"] = url
        return GstinLookupResult(extracted=extracted)

    return GstinLookupResult(limitation="GST registry unavailable — format checks only.")


def lookup_in_gstin(gstin: str) -> GstinLookupResult:
    """Look up GSTIN in GSP registry. No-op when credentials are unset."""
    normalized = gstin.strip().upper()
    if not validate_in_gstin(normalized):
        return GstinLookupResult()

    api_key = gst_gsp_api_key()
    if not api_key:
        return GstinLookupResult()

    if api_key == "fixture":
        return _fixture_lookup(normalized)

    return _gsp_http_lookup(normalized)
