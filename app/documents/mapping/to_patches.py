"""Turn per-doctype extractions into portal-shaped patches.

A `Patch` mirrors the portal's `CompanyEnrichmentPatch { path, value }` (plus metadata the
picker uses) so the portal's existing apply path consumes it unchanged. `pre_selected`
encodes the plan's UI invariants at the source:
  - confidence >= 0.80, AND
  - the value passes its IN ruleset regex, AND
  - it is not part of a failing cross-check.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from app.documents.extract.schemas.india import (
    AddressProofExtraction,
    ChequeExtraction,
    CoiExtraction,
    ExtractedAddress,
    GstExtraction,
    IecExtraction,
    MtoExtraction,
    PanExtraction,
    PartnershipExtraction,
)
from app.documents.mapping.field_paths import (
    IN_NOT_APPLICABLE,
    address_path,
    passes_field_regex,
    tax_number_path,
)
from app.documents.rules.in_patterns import (
    is_natural_person,
    normalize_identifier,
    region_for_gstin,
)

PRE_SELECT_CONFIDENCE = 0.80


@dataclass
class Evidence:
    page: int = 1
    bbox: list[float] | None = None
    snippet: str | None = None


@dataclass
class Patch:
    path: str
    value: Any
    label: str
    confidence: float
    field_name: str | None = None  # portal ruleset fieldName, for the regex gate
    tax_type_code: str | None = None
    needs_resolution: str | None = None  # e.g. "cityCode" — client resolves via reference data
    pre_selected: bool = False
    regex_ok: bool = True
    evidence: Evidence | None = None
    native_value: str | None = None
    romanized_value: str | None = None
    field_policy: str | None = None
    script: str | None = None
    locale_charset_code: str | None = None
    locale_charset_name: str | None = None

    def as_dict(self) -> dict[str, Any]:
        d = asdict(self)
        if self.evidence is None:
            d.pop("evidence", None)
        return {k: v for k, v in d.items() if v is not None or k in ("value", "pre_selected")}


def _decide_pre_select(field_name: str | None, value: str, confidence: float) -> tuple[bool, bool]:
    """Return (regex_ok, pre_selected)."""
    regex_ok = True if field_name is None else passes_field_regex(field_name, value)
    pre = confidence >= PRE_SELECT_CONFIDENCE and regex_ok
    return regex_ok, pre


def _scalar_patch(
    path: str,
    field_name: str | None,
    value: str | None,
    label: str,
    confidence: float,
    evidence: Evidence | None = None,
    *,
    tax_type_code: str | None = None,
    needs_resolution: str | None = None,
) -> Patch | None:
    if not value or not value.strip():
        return None
    if field_name in IN_NOT_APPLICABLE:
        return None
    v = value.strip()
    regex_ok, pre = _decide_pre_select(field_name, v, confidence)
    return Patch(
        path=path,
        value=v,
        label=label,
        confidence=confidence,
        field_name=field_name,
        tax_type_code=tax_type_code,
        needs_resolution=needs_resolution,
        pre_selected=pre,
        regex_ok=regex_ok,
        evidence=evidence,
    )


def _unmapped_patch(key: str, label: str, value: str, confidence: float) -> Patch:
    return Patch(
        path=f"_unmapped.{key}",
        value=value.strip(),
        label=label,
        confidence=confidence,
        pre_selected=False,
        regex_ok=True,
    )


def _weak_name_patch(
    path: str,
    value: str,
    label: str,
    confidence: float,
    evidence: Evidence | None = None,
) -> Patch | None:
    p = _scalar_patch(path, "tradingName" if path == "tradingName" else None, value, label, confidence, evidence)
    if p:
        p.pre_selected = False
    return p

def _address_patches(addr: ExtractedAddress | None, confidence: float) -> list[Patch]:
    if addr is None:
        return []
    out: list[Patch] = []
    scalar_map = [
        ("buildingName", addr.building_name, "Building name"),
        ("streetNumber", addr.street_number, "Street/house number"),
        ("streetName", addr.street_name, "Street"),
        ("district", addr.district, "District"),
        ("postalCode", addr.postal_code, "Postal code"),
    ]
    for field_name, value, label in scalar_map:
        p = _scalar_patch(address_path(field_name), field_name, value, label, confidence)
        if p:
            out.append(p)
    # City is a name here; the portal resolves it to an opaque GEO cityCode via reference data.
    if addr.city_name and addr.city_name.strip():
        out.append(
            Patch(
                path=address_path("cityName"),
                value=addr.city_name.strip(),
                label="City",
                confidence=confidence,
                field_name=None,  # cityName is not itself ruleset-gated; cityCode is, post-resolution
                needs_resolution="cityCode",
                pre_selected=False,  # never pre-select until the client resolves a real cityCode
                regex_ok=True,
            )
        )
    return out


def patches_from_coi(coi: CoiExtraction, evidence: Evidence | None = None) -> list[Patch]:
    out: list[Patch] = []
    if coi.cin:
        out.append(_unmapped_patch("cin", "CIN", coi.cin, coi.confidence))
    if coi.company_name:
        trading = _weak_name_patch("tradingName", coi.company_name, "Trading name", coi.confidence, evidence)
        if trading:
            out.append(trading)
        legal = _weak_name_patch("legalName", coi.company_name, "Legal name", coi.confidence, evidence)
        if legal:
            out.append(legal)
    return out


def patches_from_address_proof(
    address_proof: AddressProofExtraction, evidence: Evidence | None = None
) -> list[Patch]:
    out: list[Patch] = []
    if address_proof.holder_name:
        trading = _weak_name_patch(
            "tradingName", address_proof.holder_name, "Trading name", address_proof.confidence, evidence
        )
        if trading:
            out.append(trading)
    out.extend(_address_patches(address_proof.address, address_proof.confidence))
    return out


def patches_from_iec(iec: IecExtraction, evidence: Evidence | None = None) -> list[Patch]:
    out: list[Patch] = []
    if iec.iec_code:
        out.append(_unmapped_patch("iecCode", "IEC", normalize_identifier(iec.iec_code), iec.confidence))
    if iec.holder_name:
        trading = _weak_name_patch("tradingName", iec.holder_name, "Trading name", iec.confidence, evidence)
        if trading:
            out.append(trading)
    return out


def patches_from_partnership(
    partnership: PartnershipExtraction, evidence: Evidence | None = None
) -> list[Patch]:
    out: list[Patch] = []
    if partnership.registration_number:
        out.append(
            _unmapped_patch(
                "partnershipRegistrationNo",
                "Partnership registration number",
                partnership.registration_number,
                partnership.confidence,
            )
        )
    if partnership.firm_name:
        trading = _weak_name_patch(
            "tradingName", partnership.firm_name, "Trading name", partnership.confidence, evidence
        )
        if trading:
            out.append(trading)
        legal = _weak_name_patch("legalName", partnership.firm_name, "Legal name", partnership.confidence, evidence)
        if legal:
            out.append(legal)
    out.extend(_address_patches(partnership.registered_address, partnership.confidence))
    return out


def patches_from_mto(mto: MtoExtraction, evidence: Evidence | None = None) -> list[Patch]:
    out: list[Patch] = []
    if mto.licence_number:
        out.append(
            _unmapped_patch(
                "mtoLicenceNo",
                "MTO/IATA/CHA licence number",
                mto.licence_number.strip(),
                mto.confidence,
            )
        )
    if mto.holder_name:
        trading = _weak_name_patch("tradingName", mto.holder_name, "Trading name", mto.confidence, evidence)
        if trading:
            out.append(trading)
    return out


def patches_from_pan(pan: PanExtraction, evidence: Evidence | None = None) -> list[Patch]:
    out: list[Patch] = []
    if pan.pan:
        v = normalize_identifier(pan.pan)
        p = _scalar_patch(
            tax_number_path("TAXNO3"),
            "TAXNO3",
            v,
            "India: TIN/PAN",
            pan.confidence,
            evidence,
            tax_type_code="TAXNO3",
        )
        if p:
            out.append(p)
        natural = is_natural_person(v)
        if natural is not None:
            out.append(
                Patch(
                    path="taxInformation.isNaturalPerson",
                    value=natural,
                    label="Is natural person",
                    confidence=pan.confidence,
                    field_name="isNaturalPerson",
                    pre_selected=pan.confidence >= PRE_SELECT_CONFIDENCE,
                )
            )
    if pan.holder_name:
        p = _scalar_patch(
            "tradingName", "tradingName", pan.holder_name, "Trading name", pan.confidence, evidence
        )
        # Name off a PAN is a weak source; leave it for the steward, never pre-select.
        if p:
            p.pre_selected = False
            out.append(p)
    return out


def patches_from_gst(gst: GstExtraction, evidence: Evidence | None = None) -> list[Patch]:
    out: list[Patch] = []
    if gst.gstin:
        v = normalize_identifier(gst.gstin)
        p = _scalar_patch(
            tax_number_path("TAXNO4"),
            "TAXNO4",
            v,
            "India: GSTIN",
            gst.confidence,
            evidence,
            tax_type_code="TAXNO4",
        )
        if p:
            out.append(p)
        # Region can be derived from the GSTIN state code even if the address block omits it.
        region = region_for_gstin(v)
        if region:
            rp = _scalar_patch(
                address_path("regionCode"), "regionCode", region, "Region (state)", gst.confidence, evidence
            )
            if rp:
                out.append(rp)
    if gst.trade_name:
        p = _scalar_patch(
            "tradingName", "tradingName", gst.trade_name, "Trading name", gst.confidence, evidence
        )
        if p:
            out.append(p)
    if gst.legal_name:
        p = _scalar_patch("legalName", None, gst.legal_name, "Legal name", gst.confidence, evidence)
        if p:
            out.append(p)
    out.extend(_address_patches(gst.principal_place_of_business, gst.confidence))
    return _dedupe_region(out)


def patches_from_cheque(cheque: ChequeExtraction, evidence: Evidence | None = None) -> list[Patch]:
    out: list[Patch] = []
    if cheque.account_number:
        p = _scalar_patch(
            "vendorBankAccounts.0.bankAccountNumber",
            "bankAccountNumber",
            cheque.account_number,
            "Bank account number",
            cheque.confidence,
            evidence,
        )
        if p:
            out.append(p)
    if cheque.ifsc:
        # IFSC is not written directly — the portal resolves it to bankingInstitutionCode via
        # bank-master. Flag it for that resolution and never pre-select a raw IFSC.
        out.append(
            Patch(
                path="vendorBankAccounts.0.ifsc",
                value=normalize_identifier(cheque.ifsc),
                label="IFSC",
                confidence=cheque.confidence,
                field_name=None,
                needs_resolution="bankingInstitutionCode",
                pre_selected=False,
                evidence=evidence,
            )
        )
    if cheque.bank_name:
        p = _scalar_patch(
            "vendorBankAccounts.0.bankName", None, cheque.bank_name, "Bank name", cheque.confidence, evidence
        )
        if p:
            p.pre_selected = False  # display/context; confirmed by institution resolution
            out.append(p)
    return out


def _dedupe_region(patches: list[Patch]) -> list[Patch]:
    """If both the address block and the GSTIN produced a regionCode, keep the first only."""
    seen_region = False
    out: list[Patch] = []
    for p in patches:
        if p.path == address_path("regionCode"):
            if seen_region:
                continue
            seen_region = True
        out.append(p)
    return out
