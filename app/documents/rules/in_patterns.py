"""India-specific identifier patterns and lookup tables.

Every pattern here is duplicated from the portal's live IN validation ruleset
(smds-vmdmportal `src/features/validation/__fixtures__/in-prospect-vendor.json` and
`in-bank-account.json`). They are used only as an *advisory* gate inside this service:
the portal's own `validateFormValues` stays the authority on what is submittable. If the
IN ruleset changes upstream, re-sync these.
"""

from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# Core identifier shapes
# ---------------------------------------------------------------------------

# PAN: 10 chars, LLLLL NNNN L. Portal fieldName TAXNO3 also accepts the sentinel "ZZ".
PAN_RE = re.compile(r"^[A-Z]{5}[0-9]{4}[A-Z]$")

# GSTIN: 15 chars. The portal accepts four shapes; this is the canonical (and by far the
# most common) one — NN LLLLL NNNN L X Z X. The others are handled by GSTIN_ANY_RE.
GSTIN_RE = re.compile(r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][0-9A-Z]Z[0-9A-Z]$")

# Union of the four accepted GSTIN shapes from the live IN ruleset (TAXNO4 regexPattern),
# uppercased. Used to accept a broader set for extraction; the strict form above is used
# for the PAN cross-check (chars 3-12).
GSTIN_ANY_RE = re.compile(
    r"^(?:"
    r"[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z].{3}"
    r"|[0-9]{2}[A-Z]{4}[0-9]{5}[A-Z][0-9][A-Z]{2}"
    r"|[0-9]{4}[A-Z]{3}[0-9]{5}[A-Z]{2}[0-9]"
    r"|[0-9]{4}[A-Z]{3}[0-9]{5}[A-Z]{3}"
    r")$"
)

# IFSC: 4 letters, a mandatory 0, then 6 alphanumerics.
IFSC_RE = re.compile(r"^[A-Z]{4}0[A-Z0-9]{6}$")

# Indian PIN code: exactly 6 digits (portal postalCode regex for IN).
PIN_RE = re.compile(r"^[0-9]{6}$")

# Udyam registration number: UDYAM-SS-DD-NNNNNNN.
UDYAM_RE = re.compile(r"^UDYAM-[A-Z]{2}-[0-9]{2}-[0-9]{7}$")

# CIN (Corporate Identification Number): 21 chars.
CIN_RE = re.compile(r"^[LUu][0-9]{5}[A-Z]{2}[0-9]{4}[A-Z]{3}[0-9]{6}$")


# ---------------------------------------------------------------------------
# GSTIN / PAN state code -> region (subdivision) code
# ---------------------------------------------------------------------------
# The first two digits of a GSTIN are the state code. The portal's `regionCode` uses the
# same two-letter subdivision space as reference-data city `subdivisionCode` (see the
# portal's docs/field-wiki/addresses.md). This table maps GST state code -> that code.

GST_STATE_CODE_TO_REGION: dict[str, str] = {
    "01": "JK",  # Jammu & Kashmir
    "02": "HP",  # Himachal Pradesh
    "03": "PB",  # Punjab
    "04": "CH",  # Chandigarh
    "05": "UT",  # Uttarakhand
    "06": "HR",  # Haryana
    "07": "DL",  # Delhi
    "08": "RJ",  # Rajasthan
    "09": "UP",  # Uttar Pradesh
    "10": "BR",  # Bihar
    "11": "SK",  # Sikkim
    "12": "AR",  # Arunachal Pradesh
    "13": "NL",  # Nagaland
    "14": "MN",  # Manipur
    "15": "MZ",  # Mizoram
    "16": "TR",  # Tripura
    "17": "ML",  # Meghalaya
    "18": "AS",  # Assam
    "19": "WB",  # West Bengal
    "20": "JH",  # Jharkhand
    "21": "OR",  # Odisha
    "22": "CT",  # Chhattisgarh
    "23": "MP",  # Madhya Pradesh
    "24": "GJ",  # Gujarat
    "25": "DD",  # Daman & Diu (legacy)
    "26": "DN",  # Dadra & Nagar Haveli and Daman & Diu
    "27": "MH",  # Maharashtra
    "28": "AP",  # Andhra Pradesh (old)
    "29": "KA",  # Karnataka
    "30": "GA",  # Goa
    "31": "LD",  # Lakshadweep
    "32": "KL",  # Kerala
    "33": "TN",  # Tamil Nadu
    "34": "PY",  # Puducherry
    "35": "AN",  # Andaman & Nicobar Islands
    "36": "TG",  # Telangana
    "37": "AD",  # Andhra Pradesh (new)
    "38": "LA",  # Ladakh
    "97": "OT",  # Other Territory
}

# PAN 4th character -> holder type. 'P' is the only individual/natural-person class.
PAN_HOLDER_TYPE: dict[str, str] = {
    "P": "individual",
    "C": "company",
    "H": "huf",  # Hindu Undivided Family
    "F": "firm",
    "A": "aop",  # Association of Persons
    "T": "trust",
    "B": "body_of_individuals",
    "L": "local_authority",
    "J": "artificial_juridical_person",
    "G": "government",
}


def normalize_identifier(value: str) -> str:
    """Uppercase and strip all internal whitespace — the canonical form used everywhere."""
    return re.sub(r"\s+", "", value or "").upper()


def gstin_state_code(gstin: str) -> str | None:
    v = normalize_identifier(gstin)
    return v[:2] if len(v) >= 2 and v[:2].isdigit() else None


def region_for_gstin(gstin: str) -> str | None:
    code = gstin_state_code(gstin)
    return GST_STATE_CODE_TO_REGION.get(code) if code else None


def pan_from_gstin(gstin: str) -> str | None:
    """GSTIN characters 3-12 (1-indexed) are the PAN of the registered entity."""
    v = normalize_identifier(gstin)
    if len(v) < 12:
        return None
    candidate = v[2:12]
    return candidate if PAN_RE.match(candidate) else None


def pan_holder_type(pan: str) -> str | None:
    v = normalize_identifier(pan)
    if not PAN_RE.match(v):
        return None
    return PAN_HOLDER_TYPE.get(v[3])


def is_natural_person(pan: str) -> bool | None:
    kind = pan_holder_type(pan)
    if kind is None:
        return None
    return kind == "individual"
