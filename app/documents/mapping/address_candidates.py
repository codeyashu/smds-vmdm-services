"""Build address role candidates from extraction envelopes — not all map to postalAddresses.0."""

from __future__ import annotations

from typing import Any

from app.documents.extract.schemas.india import (
    AddressProofExtraction,
    CoiExtraction,
    ExtractedAddress,
    GstExtraction,
    PartnershipExtraction,
    UdyamExtraction,
)
from app.documents.mapping.to_patches import Evidence


def _format_address_line(addr: ExtractedAddress | None) -> str:
    if addr is None:
        return ""
    parts = [
        addr.building_name,
        addr.street_number,
        addr.street_name,
        addr.district,
        addr.city_name,
        addr.region_name,
        addr.postal_code,
    ]
    return ", ".join(str(p).strip() for p in parts if p and str(p).strip())


def _fields_dict(addr: ExtractedAddress | None) -> dict[str, str | None]:
    if addr is None:
        return {}
    return {
        "buildingName": addr.building_name,
        "streetNumber": addr.street_number,
        "streetName": addr.street_name,
        "district": addr.district,
        "cityName": addr.city_name,
        "regionName": addr.region_name,
        "postalCode": addr.postal_code,
    }


def _evidence_dict(evidence: Evidence | None) -> dict[str, Any] | None:
    if evidence is None:
        return None
    out: dict[str, Any] = {"page": evidence.page}
    if evidence.bbox:
        out["bbox"] = evidence.bbox
    if evidence.snippet:
        out["snippet"] = evidence.snippet
    return out


def _candidate(
    *,
    candidate_key: str,
    address_role: str,
    label: str,
    addr: ExtractedAddress | None,
    source_doc_type: str,
    document_id: str,
    confidence: float,
    effective_date: str | None = None,
    evidence: Evidence | None = None,
) -> dict[str, Any] | None:
    line = _format_address_line(addr)
    if not line:
        return None
    return {
        "candidateKey": candidate_key,
        "addressRole": address_role,
        "label": label,
        "fullAddressText": line,
        "fields": _fields_dict(addr),
        "sourceDocType": source_doc_type,
        "documentId": document_id,
        "confidence": confidence,
        "effectiveDate": effective_date,
        "evidence": _evidence_dict(evidence),
    }


def candidates_from_gst(
    gst: GstExtraction,
    doc_type: str,
    document_id: str,
    evidence: Evidence | None = None,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    effective = gst.date_of_registration
    principal = _candidate(
        candidate_key=f"{doc_type}:principal_pob",
        address_role="principal_pob",
        label="Principal place of business",
        addr=gst.principal_place_of_business,
        source_doc_type=doc_type,
        document_id=document_id,
        confidence=gst.confidence,
        effective_date=effective,
        evidence=evidence,
    )
    if principal:
        out.append(principal)
    for idx, apob in enumerate(gst.additional_places_of_business or [], start=1):
        city = (apob.city_name or "").strip()
        label = f"Additional place {idx}" + (f" — {city}" if city else "")
        row = _candidate(
            candidate_key=f"{doc_type}:apob:{idx}",
            address_role="additional_pob",
            label=label,
            addr=apob,
            source_doc_type=doc_type,
            document_id=document_id,
            confidence=gst.confidence,
            effective_date=effective,
            evidence=evidence,
        )
        if row:
            out.append(row)
    return out


def candidates_from_coi(
    coi: CoiExtraction,
    doc_type: str,
    document_id: str,
    evidence: Evidence | None = None,
) -> list[dict[str, Any]]:
    row = _candidate(
        candidate_key=f"{doc_type}:registered_office",
        address_role="registered_office",
        label="Registered office",
        addr=coi.registered_office,
        source_doc_type=doc_type,
        document_id=document_id,
        confidence=coi.confidence,
        effective_date=coi.date_of_incorporation,
        evidence=evidence,
    )
    return [row] if row else []


def candidates_from_address_proof(
    address_proof: AddressProofExtraction,
    doc_type: str,
    document_id: str,
    evidence: Evidence | None = None,
) -> list[dict[str, Any]]:
    row = _candidate(
        candidate_key=f"{doc_type}:operational",
        address_role="operational",
        label="Address proof",
        addr=address_proof.address,
        source_doc_type=doc_type,
        document_id=document_id,
        confidence=address_proof.confidence,
        evidence=evidence,
    )
    return [row] if row else []


def candidates_from_partnership(
    partnership: PartnershipExtraction,
    doc_type: str,
    document_id: str,
    evidence: Evidence | None = None,
) -> list[dict[str, Any]]:
    row = _candidate(
        candidate_key=f"{doc_type}:registered_address",
        address_role="registered_office",
        label="Registered address (partnership)",
        addr=partnership.registered_address,
        source_doc_type=doc_type,
        document_id=document_id,
        confidence=partnership.confidence,
        evidence=evidence,
    )
    return [row] if row else []


def candidates_from_udyam(
    udyam: UdyamExtraction,
    doc_type: str,
    document_id: str,
    evidence: Evidence | None = None,
) -> list[dict[str, Any]]:
    row = _candidate(
        candidate_key=f"{doc_type}:plant",
        address_role="plant",
        label="Plant / enterprise address",
        addr=udyam.plant_address,
        source_doc_type=doc_type,
        document_id=document_id,
        confidence=udyam.confidence,
        evidence=evidence,
    )
    return [row] if row else []


def collect_address_candidates_from_envelope(
    envelope_doc_type: str,
    document_id: str,
    *,
    gst=None,
    coi=None,
    address_proof=None,
    partnership=None,
    udyam=None,
) -> list[dict[str, Any]]:
    """Collect role-tagged address candidates for one extraction envelope."""
    out: list[dict[str, Any]] = []
    if gst is not None and envelope_doc_type == "IN_GST_CERTIFICATE":
        out.extend(candidates_from_gst(gst, envelope_doc_type, document_id))
    if coi is not None and envelope_doc_type == "IN_CERTIFICATE_OF_INCORPORATION":
        out.extend(candidates_from_coi(coi, envelope_doc_type, document_id))
    if address_proof is not None and envelope_doc_type == "IN_ADDRESS_PROOF":
        out.extend(candidates_from_address_proof(address_proof, envelope_doc_type, document_id))
    if partnership is not None and envelope_doc_type == "IN_DEED_OF_PARTNERSHIP":
        out.extend(candidates_from_partnership(partnership, envelope_doc_type, document_id))
    if udyam is not None and envelope_doc_type == "IN_UDYAM_CERTIFICATE":
        out.extend(candidates_from_udyam(udyam, envelope_doc_type, document_id))
    return out
