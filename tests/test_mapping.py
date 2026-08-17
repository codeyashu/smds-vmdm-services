"""Mapping tests — every emitted path/value obeys the portal contract. Zero Azure config."""

from __future__ import annotations

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
from app.documents.mapping import to_patches as tp
from app.documents.mapping.field_paths import IN_NOT_APPLICABLE, passes_field_regex

GSTIN_MH = "27AABCA1234F1Z5"
PAN_CO = "AABCA1234F"


def _by_path(patches, path):
    return next((p for p in patches if p.path == path), None)


def test_gstin_lands_at_taxno4_slot_index_3():
    patches = tp.patches_from_gst(GstExtraction(gstin=GSTIN_MH, confidence=0.99))
    p = _by_path(patches, "taxInformation.taxIdentificationNumbers.3.taxIdentificationNumber")
    assert p is not None
    assert p.tax_type_code == "TAXNO4"
    assert p.value == GSTIN_MH
    assert p.pre_selected is True  # high confidence + valid regex


def test_pan_lands_at_taxno3_slot_index_2_and_sets_natural_person():
    patches = tp.patches_from_pan(PanExtraction(pan=PAN_CO, confidence=0.95))
    p = _by_path(patches, "taxInformation.taxIdentificationNumbers.2.taxIdentificationNumber")
    assert p is not None and p.tax_type_code == "TAXNO3"
    natural = _by_path(patches, "taxInformation.isNaturalPerson")
    assert natural is not None and natural.value is False  # 4th char C -> company


def test_gstin_derives_region_when_address_omits_it():
    patches = tp.patches_from_gst(GstExtraction(gstin=GSTIN_MH, confidence=0.9))
    region = _by_path(patches, "postalAddresses.0.regionCode")
    assert region is not None and region.value == "MH"


def test_address_block_region_not_duplicated_by_gstin_region():
    gst = GstExtraction(
        gstin=GSTIN_MH,
        confidence=0.9,
        principal_place_of_business=ExtractedAddress(region_name="Maharashtra", city_name="Pune"),
    )
    patches = tp.patches_from_gst(gst)
    regions = [p for p in patches if p.path == "postalAddresses.0.regionCode"]
    assert len(regions) == 1


def test_city_name_needs_resolution_and_never_pre_selected():
    gst = GstExtraction(
        gstin=GSTIN_MH,
        confidence=0.99,
        principal_place_of_business=ExtractedAddress(city_name="Pune"),
    )
    patches = tp.patches_from_gst(gst)
    city = _by_path(patches, "postalAddresses.0.cityName")
    assert city is not None
    assert city.needs_resolution == "cityCode"
    assert city.pre_selected is False


def test_regex_failing_value_is_not_pre_selected():
    # A malformed postal code (letters) must fail the regex gate.
    gst = GstExtraction(
        gstin=GSTIN_MH,
        confidence=0.99,
        principal_place_of_business=ExtractedAddress(postal_code="ABC12"),
    )
    patches = tp.patches_from_gst(gst)
    pin = _by_path(patches, "postalAddresses.0.postalCode")
    assert pin is not None
    assert pin.regex_ok is False
    assert pin.pre_selected is False


def test_low_confidence_never_pre_selected():
    patches = tp.patches_from_gst(GstExtraction(gstin=GSTIN_MH, confidence=0.5))
    p = _by_path(patches, "taxInformation.taxIdentificationNumbers.3.taxIdentificationNumber")
    assert p.regex_ok is True and p.pre_selected is False


def test_ifsc_flagged_for_resolution_not_written_directly():
    patches = tp.patches_from_cheque(ChequeExtraction(ifsc="HDFC0001234", confidence=0.95))
    ifsc = _by_path(patches, "vendorBankAccounts.0.ifsc")
    assert ifsc.needs_resolution == "bankingInstitutionCode"
    assert ifsc.pre_selected is False


def test_not_applicable_fields_are_excluded():
    # A stray VAT (TAXNO1) proposal must be dropped for IN.
    assert "TAXNO1" in IN_NOT_APPLICABLE
    assert "ibanNumber" in IN_NOT_APPLICABLE


def test_every_gated_value_that_pre_selects_passes_its_regex():
    gst = GstExtraction(
        gstin=GSTIN_MH,
        trade_name="ACME LOGISTICS PVT LTD",
        confidence=0.99,
        principal_place_of_business=ExtractedAddress(
            street_name="MG Road", postal_code="411001", district="Pune City"
        ),
    )
    patches = tp.patches_from_gst(gst)
    for p in patches:
        if p.pre_selected and p.field_name:
            assert passes_field_regex(p.field_name, str(p.value)), p.path


def test_coi_emits_names_and_cin_patch():
    patches = tp.patches_from_coi(
        CoiExtraction(cin="U12345MH2020PTC123456", company_name="ACME LOGISTICS PVT LTD", confidence=0.9)
    )
    assert _by_path(patches, "_unmapped.cin") is not None
    trading = _by_path(patches, "tradingName")
    legal = _by_path(patches, "legalName")
    assert trading is not None and trading.pre_selected is False
    assert legal is not None and legal.pre_selected is False


def test_address_proof_emits_address_patches():
    patches = tp.patches_from_address_proof(
        AddressProofExtraction(
            holder_name="ACME LOGISTICS",
            address=ExtractedAddress(street_name="MG Road", postal_code="411001", city_name="Pune"),
            confidence=0.9,
        )
    )
    assert _by_path(patches, "postalAddresses.0.streetName") is not None
    assert _by_path(patches, "postalAddresses.0.postalCode") is not None
    assert _by_path(patches, "postalAddresses.0.cityName").needs_resolution == "cityCode"


def test_iec_emits_unmapped_patch():
    patches = tp.patches_from_iec(IecExtraction(iec_code="ABCDE1234F", confidence=0.92))
    iec = _by_path(patches, "_unmapped.iecCode")
    assert iec is not None and iec.value == "ABCDE1234F"


def test_partnership_emits_registration_and_names():
    patches = tp.patches_from_partnership(
        PartnershipExtraction(
            firm_name="ACME PARTNERS",
            registration_number="REG-123",
            confidence=0.88,
        )
    )
    assert _by_path(patches, "_unmapped.partnershipRegistrationNo") is not None
    assert _by_path(patches, "tradingName") is not None


def test_mto_emits_licence_patch():
    patches = tp.patches_from_mto(MtoExtraction(licence_number="MTO/12345", confidence=0.85))
    assert _by_path(patches, "_unmapped.mtoLicenceNo") is not None
