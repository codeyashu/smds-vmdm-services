"""Build portal patches for CN/AE/US/GB extraction envelopes."""

from __future__ import annotations

from app.documents.extract.schemas.locale import (
    AeExtractionEnvelope,
    CnExtractionEnvelope,
    ExtractedAddress,
    GbExtractionEnvelope,
    LocaleNameField,
    UsExtractionEnvelope,
)
from app.documents.extract.supported_countries import locale_profile
from app.documents.mapping.field_paths import address_path, tax_number_path
from app.documents.mapping.to_patches import PRE_SELECT_CONFIDENCE, Evidence, Patch, _scalar_patch, _unmapped_patch


def _locale_name_patch(
    path: str,
    field_name: str | None,
    label: str,
    name: LocaleNameField | None,
    confidence: float,
    country: str,
) -> Patch | None:
    if name is None:
        return None
    profile = locale_profile(country)
    native = (name.native or "").strip() or None
    romanized = (name.romanized or name.english or "").strip() or None
    fallback = (name.english or name.romanized or name.native or "").strip()
    if not fallback:
        return None
    operational = romanized or fallback
    regex_ok = True
    pre = confidence >= PRE_SELECT_CONFIDENCE and regex_ok
    if profile and profile.dual_record and native:
        pre = False
    return Patch(
        path=path,
        value=operational,
        label=label,
        confidence=confidence,
        field_name=field_name,
        pre_selected=pre,
        regex_ok=regex_ok,
        native_value=native,
        romanized_value=romanized,
        field_policy="native_required" if native else "english_only",
        script=profile.default_script if profile and native else "en",
        locale_charset_code=profile.locale_charset_code if profile and native else None,
        locale_charset_name=profile.locale_charset_name if profile and native else None,
    )


def _address_patches(
    address: ExtractedAddress | None,
    confidence: float,
    country: str,
) -> list[Patch]:
    if address is None:
        return []
    profile = locale_profile(country)
    rows: list[tuple[str, str, str | None, str | None]] = [
        ("buildingName", "Building name", address.building_name, None),
        ("streetNumber", "Street/house number", address.street_number, None),
        ("streetName", "Street", address.street_name, None),
        ("district", "District", address.district, None),
        ("cityName", "City", address.city_name, "cityCode"),
        ("postalCode", "Postal code", address.postal_code, None),
    ]
    patches: list[Patch] = []
    for field, label, value, needs_resolution in rows:
        if not value or not str(value).strip():
            continue
        text = str(value).strip()
        pre = confidence >= PRE_SELECT_CONFIDENCE
        if profile and profile.dual_record and any(ord(ch) > 127 for ch in text):
            pre = False
        patch = Patch(
            path=address_path(field),
            value=text,
            label=label,
            confidence=confidence,
            needs_resolution=needs_resolution,
            pre_selected=pre,
            regex_ok=True,
            native_value=text if profile and profile.dual_record and any(ord(ch) > 127 for ch in text) else None,
            romanized_value=None,
            field_policy="native_required" if profile and profile.dual_record and any(ord(ch) > 127 for ch in text) else "english_only",
            script=profile.default_script if profile and any(ord(ch) > 127 for ch in text) else "en",
            locale_charset_code=profile.locale_charset_code if profile and any(ord(ch) > 127 for ch in text) else None,
            locale_charset_name=profile.locale_charset_name if profile and any(ord(ch) > 127 for ch in text) else None,
        )
        patches.append(patch)
    return patches


def patches_from_cn_envelope(envelope: CnExtractionEnvelope) -> tuple[list[Patch], list[dict]]:
    patches: list[Patch] = []
    unmapped: list[dict] = []
    if envelope.doc_type == "CN_BUSINESS_LICENSE" and envelope.business_license:
        block = envelope.business_license
        conf = block.confidence or envelope.doc_type_confidence
        if block.uscc:
            patch = _scalar_patch(
                tax_number_path("TAXNO1"),
                None,
                block.uscc.strip(),
                "USCC",
                conf,
                tax_type_code="TAXNO1",
            )
            if patch:
                patch.field_policy = "latin_id"
                patch.script = "en"
                patches.append(patch)
        for path, field_name, label, name in (
            ("legalName", "legalName", "Legal name", block.legal_name),
            ("tradingName", "tradingName", "Trading name", block.trading_name),
        ):
            row = _locale_name_patch(path, field_name, label, name, conf, "CN")
            if row:
                patches.append(row)
        patches.extend(_address_patches(block.registered_address, conf, "CN"))
    if envelope.doc_type == "CN_BANK_ACCOUNT_PERMIT" and envelope.bank_permit:
        block = envelope.bank_permit
        conf = block.confidence or envelope.doc_type_confidence
        for path, label, value in (
            ("vendorBankAccounts.0.bankAccountNumber", "Bank account number", block.bank_account_number),
            ("vendorBankAccounts.0.bankName", "Bank name", block.bank_name),
        ):
            patch = _scalar_patch(path, None, value, label, conf)
            if patch:
                patches.append(patch)
    return patches, unmapped


def patches_from_ae_envelope(envelope: AeExtractionEnvelope) -> tuple[list[Patch], list[dict]]:
    patches: list[Patch] = []
    unmapped: list[dict] = []
    if envelope.doc_type == "AE_TRADE_LICENSE" and envelope.trade_license:
        block = envelope.trade_license
        conf = block.confidence or envelope.doc_type_confidence
        if block.trade_license_number:
            patches.append(
                _unmapped_patch("tradeLicenseNumber", "Trade licence number", block.trade_license_number, conf)
            )
        for path, field_name, label, name in (
            ("legalName", "legalName", "Legal name", block.legal_name),
            ("tradingName", "tradingName", "Trading name", block.trading_name),
        ):
            row = _locale_name_patch(path, field_name, label, name, conf, "AE")
            if row:
                patches.append(row)
        patches.extend(_address_patches(block.registered_address, conf, "AE"))
    if envelope.doc_type == "AE_VAT_CERTIFICATE" and envelope.vat_certificate:
        block = envelope.vat_certificate
        conf = block.confidence or envelope.doc_type_confidence
        if block.trn:
            patch = _scalar_patch(tax_number_path("TAXNO1"), None, block.trn.strip(), "TRN", conf, tax_type_code="TAXNO1")
            if patch:
                patch.field_policy = "latin_id"
                patch.script = "en"
                patches.append(patch)
        row = _locale_name_patch("legalName", "legalName", "Legal name", block.legal_name, conf, "AE")
        if row:
            patches.append(row)
    return patches, unmapped


def patches_from_us_envelope(envelope: UsExtractionEnvelope) -> tuple[list[Patch], list[dict]]:
    patches: list[Patch] = []
    unmapped: list[dict] = []
    if envelope.doc_type == "US_W9" and envelope.w9:
        block = envelope.w9
        conf = block.confidence or envelope.doc_type_confidence
        if block.ein:
            patch = _scalar_patch(tax_number_path("TAXNO1"), None, block.ein.strip(), "EIN", conf, tax_type_code="TAXNO1")
            if patch:
                patch.field_policy = "latin_id"
                patches.append(patch)
        for path, field_name, label, value in (
            ("legalName", "legalName", "Legal name", block.legal_name),
            ("tradingName", "tradingName", "Trading name", block.trading_name),
        ):
            patch = _scalar_patch(path, field_name, value, label, conf)
            if patch:
                patch.field_policy = "english_only"
                patches.append(patch)
    if envelope.doc_type == "US_VOIDED_CHECK" and envelope.voided_check:
        block = envelope.voided_check
        conf = block.confidence or envelope.doc_type_confidence
        for path, label, value in (
            ("vendorBankAccounts.0.bankAccountNumber", "Bank account number", block.bank_account_number),
            ("vendorBankAccounts.0.routingNumber", "Routing number", block.routing_number),
            ("vendorBankAccounts.0.bankName", "Bank name", block.bank_name),
        ):
            patch = _scalar_patch(path, None, value, label, conf)
            if patch:
                patch.pre_selected = False
                patches.append(patch)
    if envelope.doc_type == "US_CERTIFICATE_OF_GOOD_STANDING" and envelope.good_standing:
        block = envelope.good_standing
        conf = block.confidence or envelope.doc_type_confidence
        if block.state_registration_number:
            patches.append(
                _unmapped_patch(
                    "stateRegistrationNumber",
                    "State registration number",
                    block.state_registration_number,
                    conf,
                )
            )
        patch = _scalar_patch("legalName", "legalName", block.legal_name, "Legal name", conf)
        if patch:
            patches.append(patch)
    return patches, unmapped


def patches_from_gb_envelope(envelope: GbExtractionEnvelope) -> tuple[list[Patch], list[dict]]:
    patches: list[Patch] = []
    unmapped: list[dict] = []
    if envelope.doc_type == "GB_COMPANIES_HOUSE_CERTIFICATE" and envelope.companies_house:
        block = envelope.companies_house
        conf = block.confidence or envelope.doc_type_confidence
        if block.company_number:
            patches.append(_unmapped_patch("companyNumber", "Company number", block.company_number, conf))
        patch = _scalar_patch("legalName", "legalName", block.legal_name, "Legal name", conf)
        if patch:
            patches.append(patch)
        patches.extend(_address_patches(block.registered_address, conf, "GB"))
    if envelope.doc_type == "GB_VAT_CERTIFICATE" and envelope.vat_certificate:
        block = envelope.vat_certificate
        conf = block.confidence or envelope.doc_type_confidence
        if block.vat_number:
            patch = _scalar_patch(
                tax_number_path("TAXNO1"), None, block.vat_number.strip(), "VAT number", conf, tax_type_code="TAXNO1"
            )
            if patch:
                patch.field_policy = "latin_id"
                patches.append(patch)
        patch = _scalar_patch("legalName", "legalName", block.legal_name, "Legal name", conf)
        if patch:
            patches.append(patch)
    return patches, unmapped
