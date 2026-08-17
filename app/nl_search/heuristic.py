"""Deterministic NL query parser — port of ``heuristic-parse.ts`` + ``vendor-code-lookup`` helpers."""

from __future__ import annotations

import re
from typing import Any

S4_BP_VENDOR_CODE_TYPE = "S4_BP_VNDR_CD"
SMDS_VENDOR_CODE_TYPE = "SMDS_VNDR_CD"
FACT_BP_VENDOR_CODE_TYPE = "FACT_BP_VNDR_CD"

NUMERIC_ALTERNATIVE_CODE_TYPES = (
    SMDS_VENDOR_CODE_TYPE,
    S4_BP_VENDOR_CODE_TYPE,
    FACT_BP_VENDOR_CODE_TYPE,
)

VENDOR_CODE_PATTERN = re.compile(r"\b([A-Z]{2}\d{5,})\b", re.IGNORECASE)
TAX_ID_PATTERN = re.compile(r"\b(?=[A-Z0-9]*\d)[A-Z0-9]{8,}\b", re.IGNORECASE)
LIST_ALL_VENDORS_PATTERN = re.compile(
    r"\b(all|every|any|list)\b[\s\S]*\bvendors?\b|\bvendors?\b[\s\S]*\b(in|from|for)\b",
    re.IGNORECASE,
)

COUNTRY_ALIASES: dict[str, str] = {
    "india": "IN",
    "indonesia": "ID",
    "brazil": "BR",
    "germany": "DE",
    "france": "FR",
    "italy": "IT",
    "spain": "ES",
    "china": "CN",
    "denmark": "DK",
    "sweden": "SE",
    "norway": "NO",
    "poland": "PL",
    "romania": "RO",
    "czech": "CZ",
    "czechia": "CZ",
    "slovakia": "SK",
    "switzerland": "CH",
    "netherlands": "NL",
    "belgium": "BE",
    "usa": "US",
    "united states": "US",
    "mexico": "MX",
    "thailand": "TH",
    "singapore": "SG",
    "malaysia": "MY",
    "australia": "AU",
    "canada": "CA",
    "portugal": "PT",
    "austria": "AT",
    "hungary": "HU",
    "finland": "FI",
    "ireland": "IE",
    "south africa": "ZA",
    "turkey": "TR",
    "uae": "AE",
    "united arab emirates": "AE",
    "uk": "GB",
    "united kingdom": "GB",
}

CITY_ALIASES: dict[str, str] = {
    "mumbai": "Mumbai",
    "bombay": "Mumbai",
    "chennai": "Chennai",
    "madras": "Chennai",
    "delhi": "Delhi",
    "new delhi": "Delhi",
    "bengaluru": "Bengaluru",
    "bangalore": "Bengaluru",
    "pune": "Pune",
    "hyderabad": "Hyderabad",
    "kolkata": "Kolkata",
    "calcutta": "Kolkata",
    "prague": "Prague",
    "bucharest": "Bucharest",
    "bratislava": "Bratislava",
    "zurich": "Zurich",
    "sao": "Sao Paulo",
    "sao paulo": "Sao Paulo",
}

STATUS_PHRASES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\bactive\b", re.IGNORECASE), "ACTIVE"),
    (re.compile(r"\binactive\b", re.IGNORECASE), "INACTIVE"),
    (re.compile(r"\bsuspended\b", re.IGNORECASE), "SUSPENDED"),
    (re.compile(r"\bpending\b", re.IGNORECASE), "PENDING"),
    (re.compile(r"\brejected\b", re.IGNORECASE), "REJECTED"),
]

WORKFLOW_PHRASES = [
    re.compile(r"\bin workflow\b", re.IGNORECASE),
    re.compile(r"\bworkflow pending\b", re.IGNORECASE),
    re.compile(r"\bpending workflow\b", re.IGNORECASE),
    re.compile(r"\bunder workflow\b", re.IGNORECASE),
    re.compile(r"\bawaiting approval\b", re.IGNORECASE),
    re.compile(r"\bapproval pending\b", re.IGNORECASE),
]

DRAFT_PHRASES = [
    re.compile(r"\bwith draft\b", re.IGNORECASE),
    re.compile(r"\bhas draft\b", re.IGNORECASE),
    re.compile(r"\bdraft vendors?\b", re.IGNORECASE),
    re.compile(r"\bunpublished changes\b", re.IGNORECASE),
]

STOP_WORDS = frozenset(
    {
        "vendor",
        "vendors",
        "find",
        "search",
        "show",
        "get",
        "lookup",
        "named",
        "called",
        "with",
        "from",
        "in",
        "the",
        "and",
        "for",
        "all",
        "every",
        "any",
        "list",
        "present",
        "active",
        "inactive",
        "suspended",
        "pending",
        "rejected",
        "workflow",
        "workflows",
        "approval",
        "draft",
        "drafts",
        "tax",
        "id",
        "ids",
        "code",
        "codes",
    }
)

KNOWN_ISO2 = frozenset(
    {
        "IN",
        "BR",
        "CZ",
        "RO",
        "SK",
        "IT",
        "CH",
        "DE",
        "FR",
        "ES",
        "US",
        "GB",
        "NL",
        "BE",
        "PL",
        "CN",
        "DK",
        "SE",
        "NO",
        "ID",
    }
)

SMDS_QUERY_PATTERNS = [
    re.compile(r"\b(?:smds\s*)?(?:vendor\s*)?code\s*[:\s#-]*(\d{4,10})\b", re.IGNORECASE),
    re.compile(r"\bsmds\s+(\d{4,10})\b", re.IGNORECASE),
    re.compile(r"\bSMDS_VNDR_CD\s*[:\s#-]*(\d{4,10})\b", re.IGNORECASE),
]

MDG_BP_QUERY_PATTERNS = [
    re.compile(
        r"\b(?:sap\s*)?mdg\s*(?:bp\s*)?(?:vendor\s*)?(?:code\s*)?[:\s#-]*(\d{4,10})\b",
        re.IGNORECASE,
    ),
    re.compile(r"\bsap\s+(\d{4,10})\s+code\b", re.IGNORECASE),
    re.compile(r"\bsap\s+code\s+(\d{4,10})\b", re.IGNORECASE),
    re.compile(r"\b(?:s4\s*)?bp\s*(?:vendor\s*)?code\s*[:\s#-]*(\d{4,10})\b", re.IGNORECASE),
    re.compile(r"\bS4_BP_VNDR_CD\s*[:\s#-]*(\d{4,10})\b", re.IGNORECASE),
]

_SMDS_IN_QUERY = re.compile(r"\bsmds\b", re.IGNORECASE)
_MDG_CONFIDENCE_MARKERS = (
    re.compile(r"\bmdg\b", re.IGNORECASE),
    re.compile(r"\bbp\b", re.IGNORECASE),
    re.compile(r"\bsap\b", re.IGNORECASE),
    re.compile(r"\bsmds\b", re.IGNORECASE),
)
_COUNTRY_TAGGED = re.compile(r"\b(?:in|country)\s+([A-Za-z]{2})\b", re.IGNORECASE)
_ISO2_TOKEN = re.compile(r"\b([A-Z]{2})\b")
_BARE_NUMERIC_CODE = re.compile(r"^\d{4,10}$")


def normalize_numeric_alternative_code(code: str) -> str:
    trimmed = code.strip()
    if not re.fullmatch(r"\d+", trimmed):
        return trimmed
    return trimmed.zfill(10)


def detect_alternative_code_lookup(query: str) -> dict[str, str] | None:
    trimmed = query.strip()
    if not trimmed:
        return None

    for pattern in SMDS_QUERY_PATTERNS:
        match = pattern.search(trimmed)
        if match and match.group(1) and _SMDS_IN_QUERY.search(trimmed):
            code = normalize_numeric_alternative_code(match.group(1))
            return {
                "code": code,
                "codeType": SMDS_VENDOR_CODE_TYPE,
                "summary": f"Open vendor by SMDS vendor code {code}",
            }

    for pattern in MDG_BP_QUERY_PATTERNS:
        match = pattern.search(trimmed)
        if match and match.group(1):
            code = normalize_numeric_alternative_code(match.group(1))
            return {
                "code": code,
                "codeType": S4_BP_VENDOR_CODE_TYPE,
                "summary": f"Open vendor by SAP MDG BP code {code}",
            }

    if _BARE_NUMERIC_CODE.fullmatch(trimmed):
        return {
            "code": trimmed,
            "summary": f"Open vendor by alternative code {trimmed}",
        }

    return None


def _includes_word(text: str, phrase: str) -> bool:
    return re.search(rf"\b{re.escape(phrase)}\b", text, re.IGNORECASE) is not None


def _detect_country(text: str, vendor_code: str | None = None) -> str | None:
    for name, iso2 in sorted(COUNTRY_ALIASES.items(), key=lambda item: len(item[0]), reverse=True):
        if _includes_word(text, name):
            return iso2

    tagged = _COUNTRY_TAGGED.search(text)
    if tagged:
        iso2 = tagged.group(1).upper()
        if iso2 in KNOWN_ISO2:
            return iso2

    for match in _ISO2_TOKEN.finditer(text.upper()):
        iso2 = match.group(1)
        if vendor_code and vendor_code.startswith(iso2):
            continue
        if iso2 in KNOWN_ISO2:
            return iso2

    return None


def _extract_city_name(text: str) -> str | None:
    for alias, city in sorted(CITY_ALIASES.items(), key=lambda item: len(item[0]), reverse=True):
        if _includes_word(text, alias):
            return city
    return None


def _is_known_city_token(value: str) -> bool:
    lower = value.lower()
    return lower in CITY_ALIASES


def _extract_vendor_status(text: str) -> str | None:
    for pattern, status in STATUS_PHRASES:
        if pattern.search(text):
            return status
    return None


def _extract_in_workflow(text: str) -> bool:
    return any(pattern.search(text) for pattern in WORKFLOW_PHRASES)


def _extract_has_draft_intent(text: str) -> bool:
    return any(pattern.search(text) for pattern in DRAFT_PHRASES)


def _is_list_all_vendors_query(text: str) -> bool:
    return LIST_ALL_VENDORS_PATTERN.search(text) is not None


def _build_location_summary(country: str, vendor_status: str | None = None, city_name: str | None = None) -> str:
    place = f"{city_name}, {country}" if city_name else country
    if vendor_status:
        return f"{vendor_status} vendors in {place}"
    return f"Vendors in {place}"


def _strip_known_locations(text: str, country: str | None = None, city_name: str | None = None) -> str:
    working = text
    if city_name:
        for alias, city in CITY_ALIASES.items():
            if city == city_name:
                working = re.sub(rf"\b{re.escape(alias)}\b", " ", working, flags=re.IGNORECASE)
    if country:
        for name, iso2 in COUNTRY_ALIASES.items():
            if iso2 == country:
                working = re.sub(rf"\b{re.escape(name)}\b", " ", working, flags=re.IGNORECASE)
        working = re.sub(rf"\b{re.escape(country)}\b", " ", working, flags=re.IGNORECASE)
    return working


def _extract_trading_name(
    text: str,
    country: str | None = None,
    city_name: str | None = None,
    tax_id: str | None = None,
    code: str | None = None,
) -> str | None:
    working = text

    if code:
        working = re.sub(re.escape(code), " ", working, flags=re.IGNORECASE)
    if tax_id:
        working = re.sub(re.escape(tax_id), " ", working, flags=re.IGNORECASE)
    working = _strip_known_locations(working, country, city_name)

    for pattern, _status in STATUS_PHRASES:
        working = pattern.sub(" ", working)
    working = LIST_ALL_VENDORS_PATTERN.sub(" ", working)

    tokens = [
        token.strip()
        for token in re.split(r"[\s,;]+", working)
        if token.strip()
        and token.strip().lower() not in STOP_WORDS
        and not _is_known_city_token(token.strip())
    ]

    name = " ".join(tokens).strip()
    if len(name) < 3:
        return None
    return name


def _heuristic_result(**fields: Any) -> dict[str, Any]:
    return {key: value for key, value in fields.items() if value is not None}


def should_use_heuristic_immediately(result: dict[str, Any]) -> bool:
    if result.get("intent") == "code_lookup" and result.get("confidence") != "low":
        return True
    if result.get("taxId"):
        return False
    trading_name = (result.get("tradingName") or "").strip()
    if result.get("country") and trading_name:
        return True
    if result.get("confidence") != "high":
        return False
    if result.get("inWorkflow") and result.get("country"):
        return True
    if result.get("country") and not trading_name:
        return True
    return False


def heuristic_parse_natural_language(query: str) -> dict[str, Any] | None:
    trimmed = query.strip()
    if not trimmed:
        return None

    alternative_lookup = detect_alternative_code_lookup(trimmed)
    if alternative_lookup:
        confidence = (
            "high"
            if any(marker.search(trimmed) for marker in _MDG_CONFIDENCE_MARKERS)
            else "medium"
        )
        return _heuristic_result(
            intent="code_lookup",
            code=alternative_lookup["code"],
            codeType=alternative_lookup.get("codeType"),
            summary=alternative_lookup["summary"],
            source="heuristic",
            confidence=confidence,
        )

    code_match = VENDOR_CODE_PATTERN.search(trimmed)
    code_value = code_match.group(1).upper() if code_match else None
    if code_match and code_value:
        remainder = trimmed.replace(code_match.group(0), "", 1).strip()
        if not remainder or len(remainder) < 4:
            return _heuristic_result(
                intent="code_lookup",
                code=code_value,
                summary=f"Open vendor {code_value}",
                source="heuristic",
                confidence="high",
            )

    country = _detect_country(trimmed, code_value)
    city_name = _extract_city_name(trimmed)
    vendor_status = _extract_vendor_status(trimmed)
    in_workflow = _extract_in_workflow(trimmed)
    has_draft_intent = _extract_has_draft_intent(trimmed)
    list_all = _is_list_all_vendors_query(trimmed)
    tax_match = TAX_ID_PATTERN.search(trimmed)
    tax_id = None
    if tax_match:
        candidate = tax_match.group(0).upper()
        if candidate != code_value:
            tax_id = candidate
    trading_name = _extract_trading_name(trimmed, country, city_name, tax_id, code_value)

    if country and in_workflow:
        return _heuristic_result(
            intent="attribute_search",
            country=country,
            cityName=city_name,
            hasDraft=True,
            vendorStatus=vendor_status or "PENDING",
            inWorkflow=True,
            summary=f"Vendors in workflow in {country}",
            source="heuristic",
            confidence="high",
        )

    if country and has_draft_intent and (list_all or not trading_name):
        return _heuristic_result(
            intent="attribute_search",
            country=country,
            cityName=city_name,
            hasDraft=True,
            vendorStatus=vendor_status,
            summary=f"Vendors with draft in {country}",
            source="heuristic",
            confidence="high",
        )

    if country and (list_all or (vendor_status and not trading_name)):
        return _heuristic_result(
            intent="attribute_search",
            country=country,
            cityName=city_name,
            vendorStatus=vendor_status,
            summary=_build_location_summary(country, vendor_status, city_name),
            source="heuristic",
            confidence="high",
        )

    if tax_id and country:
        return _heuristic_result(
            intent="attribute_search",
            country=country,
            cityName=city_name,
            taxId=tax_id,
            tradingName=trading_name,
            summary=f"Tax ID {tax_id} in {country}",
            source="heuristic",
            confidence="high",
        )

    if tax_id:
        return _heuristic_result(
            intent="attribute_search",
            taxId=tax_id,
            tradingName=trading_name,
            summary=f"Tax ID {tax_id}",
            source="heuristic",
            confidence="high",
        )

    if trading_name and country:
        location = _build_location_summary(country, None, city_name).removeprefix("Vendors in ")
        return _heuristic_result(
            intent="attribute_search",
            country=country,
            cityName=city_name,
            tradingName=trading_name,
            vendorStatus=vendor_status,
            summary=f'"{trading_name}" in {location}',
            source="heuristic",
            confidence="high",
        )

    if trading_name and len(trading_name) >= 3:
        word_count = len(trading_name.split())
        return _heuristic_result(
            intent="attribute_search",
            tradingName=trading_name,
            vendorStatus=vendor_status,
            cityName=city_name,
            summary=f'Name contains "{trading_name}"',
            source="heuristic",
            confidence="medium" if word_count >= 2 else "low",
        )

    if country:
        return _heuristic_result(
            intent="attribute_search",
            country=country,
            cityName=city_name,
            vendorStatus=vendor_status,
            summary=_build_location_summary(country, vendor_status, city_name),
            source="heuristic",
            confidence="low",
        )

    return None
