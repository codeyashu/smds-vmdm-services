"""Commercial directory and company website enrichment for TrustLens."""

from __future__ import annotations

import asyncio
import re
from html import unescape
from typing import Any
from urllib.parse import urlparse

import httpx

from app.mdm.company_search import search_company_external
from app.mdm.config import is_mdm_configured

_TITLE_RE = re.compile(r"<title[^>]*>([^<]+)</title>", re.IGNORECASE | re.DOTALL)
_OG_SITE_RE = re.compile(
    r'<meta[^>]+property=["\']og:site_name["\'][^>]+content=["\']([^"\']+)["\']',
    re.IGNORECASE,
)
_OG_TITLE_RE = re.compile(
    r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']+)["\']',
    re.IGNORECASE,
)
_OG_DESC_RE = re.compile(
    r'<meta[^>]+(?:name|property)=["\'](?:description|og:description)["\'][^>]+content=["\']([^"\']+)["\']',
    re.IGNORECASE,
)
_JSON_LD_RE = re.compile(
    r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
    re.IGNORECASE | re.DOTALL,
)


def _run_async(coro: Any) -> Any:
    return asyncio.run(coro)


def _pick_primary_address(summary: dict[str, Any]) -> dict[str, Any] | None:
    addresses = summary.get("addresses") or []
    if not isinstance(addresses, list):
        return None
    for entry in addresses:
        if isinstance(entry, dict) and entry.get("type") == "PRIMARY":
            return entry
    return addresses[0] if addresses and isinstance(addresses[0], dict) else None


def _summary_to_extracted(summary: dict[str, Any], country: str) -> dict[str, Any]:
    address = _pick_primary_address(summary)
    street = ""
    if address:
        street = " ".join(
            part
            for part in [
                address.get("streetNumber"),
                address.get("streetName"),
                address.get("apartmentOrFloor"),
            ]
            if part
        ).strip()
    tax_id = ""
    for entry in summary.get("taxIdentifiers") or []:
        if not isinstance(entry, dict):
            continue
        candidate = entry.get("taxIdentificationNumber") or entry.get("taxNumber")
        if candidate:
            tax_id = str(candidate).strip()
            break
    return {
        "tradingName": summary.get("companyName") or summary.get("legalName"),
        "legalName": summary.get("legalName") or summary.get("companyName"),
        "taxIdentificationNumber": tax_id or None,
        "cityName": (address or {}).get("city") or summary.get("city"),
        "postalCode": (address or {}).get("postalCode") or summary.get("postalCode"),
        "street": street or summary.get("customerAddressCombined"),
        "iso2CountryCode": summary.get("iso2CountryCode") or country,
        "website": summary.get("url"),
    }


def lookup_commercial_directory(
    *,
    country: str,
    trading_name: str | None,
    legal_name: str | None,
    tax_ids: list[str],
    address: dict[str, Any] | None,
    website: str | None,
) -> dict[str, Any] | None:
    if not is_mdm_configured():
        return None
    if not trading_name and not legal_name and not tax_ids:
        return None

    address = address or {}
    params = {
        "iso2CountryCode": country,
        "tradingName": trading_name or legal_name,
        "taxReference": tax_ids[0] if tax_ids else None,
        "city": address.get("cityName"),
        "streetName": address.get("streetName"),
        "streetNumber": address.get("streetNumber"),
        "postalCode": address.get("postalCode"),
        "regionName": address.get("regionName"),
        "url": website,
        "limit": 3,
    }
    try:
        response = _run_async(search_company_external(params))
    except Exception:  # noqa: BLE001
        return None

    summaries = response.get("customerSummaries") or []
    if not summaries:
        return None

    top = summaries[0]
    if not isinstance(top, dict):
        return None

    source_type = str(top.get("sourceType") or "DNB").upper()
    extracted = _summary_to_extracted(top, country)
    source_url = top.get("url")
    if not source_url:
        source_url = f"https://www.dnb.com/" if source_type == "DNB" else None

    return {
        "connectorId": "commercial_directory",
        "sourceType": "commercial_directory",
        "verificationMode": "web_enrichment",
        "sourceUrl": source_url,
        "displayName": f"{source_type} directory ({extracted.get('tradingName') or 'match'})",
        "extracted": extracted,
        "authorityWeight": 0.75,
        "llmReason": (
            f"Top commercial registry hit from {source_type}. "
            "Compare names, tax IDs, and address — not a government filing."
        ),
    }


def _normalize_website_url(url: str) -> str:
    cleaned = url.strip()
    if not cleaned:
        return ""
    if not cleaned.startswith(("http://", "https://")):
        cleaned = f"https://{cleaned}"
    return cleaned


def _clean_html_text(value: str) -> str:
    return re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", value))).strip()


def _extract_json_ld_org(html: str) -> dict[str, str | None]:
    import json

    for match in _JSON_LD_RE.finditer(html):
        try:
            payload = json.loads(match.group(1))
        except (json.JSONDecodeError, TypeError):
            continue
        nodes = payload if isinstance(payload, list) else [payload]
        for node in nodes:
            if not isinstance(node, dict):
                continue
            node_type = str(node.get("@type") or "")
            if "Organization" not in node_type and node_type not in ("Corporation", "LocalBusiness"):
                continue
            address = node.get("address")
            street = city = postal = None
            if isinstance(address, dict):
                street = address.get("streetAddress")
                city = address.get("addressLocality")
                postal = address.get("postalCode")
            return {
                "tradingName": node.get("name"),
                "street": street,
                "cityName": city,
                "postalCode": postal,
            }
    return {}


def _extract_page_signals(html: str) -> dict[str, str | None]:
    title_match = _TITLE_RE.search(html)
    title = _clean_html_text(title_match.group(1)) if title_match else None
    og_site = _OG_SITE_RE.search(html)
    og_title = _OG_TITLE_RE.search(html)
    og_desc = _OG_DESC_RE.search(html)
    json_ld = _extract_json_ld_org(html)
    return {
        "title": title,
        "ogSiteName": _clean_html_text(og_site.group(1)) if og_site else None,
        "ogTitle": _clean_html_text(og_title.group(1)) if og_title else None,
        "description": _clean_html_text(og_desc.group(1)) if og_desc else None,
        **json_ld,
    }


def probe_company_website(url: str | None) -> dict[str, Any] | None:
    normalized = _normalize_website_url(url or "")
    if not normalized:
        return None

    domain = urlparse(normalized).netloc
    if not domain:
        return None

    try:
        with httpx.Client(
            timeout=10.0,
            follow_redirects=True,
            headers={"User-Agent": "VMDM-TrustLens/1.0 (+vendor-verification)"},
        ) as client:
            response = client.get(normalized)
            if response.status_code >= 400:
                return None
            html = response.text[:80_000]
    except Exception:  # noqa: BLE001
        return None

    signals = _extract_page_signals(html)
    trading_name = (
        signals.get("tradingName")
        or signals.get("ogSiteName")
        or signals.get("ogTitle")
        or signals.get("title")
    )
    if not trading_name:
        return None

    return {
        "connectorId": "company_website",
        "sourceType": "company_website",
        "verificationMode": "web_enrichment",
        "sourceUrl": normalized,
        "displayName": f"Company website ({domain})",
        "extracted": {
            "tradingName": trading_name,
            "legalName": trading_name,
            "cityName": signals.get("cityName"),
            "postalCode": signals.get("postalCode"),
            "street": signals.get("street"),
            "iso2CountryCode": None,
        },
        "authorityWeight": 0.6,
        "llmReason": (
            "Official company website — page title, Open Graph, and structured data "
            "compared to your trading name and address."
        ),
    }
