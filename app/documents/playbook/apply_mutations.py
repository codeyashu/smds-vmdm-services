"""Apply-config mutations — ported from portal extraction-config-store."""

from __future__ import annotations

from typing import Any

from app.documents.playbook.apply_config import load_apply_config, playbook_to_apply_config
from app.documents.playbook.apply_overlay_store import (
    ApplyAttribute,
    ApplyDocument,
    CountryApplyConfig,
    load_apply_overlay,
    save_apply_overlay,
)
from app.documents.playbook.config_store import load_country_playbook


def _attribute_id(doc_type: str, form_path: str) -> str:
    import re

    slug = re.sub(r"[^a-zA-Z0-9]+", "_", form_path)
    return f"{doc_type}__{slug}"


def _empty_config(country_code: str) -> CountryApplyConfig:
    return CountryApplyConfig(
        countryCode=country_code.upper(),
        documents=[],
        multiSourceFields={},
        updatedAt="1970-01-01T00:00:00+00:00",
    )


def _ensure_overlay(country_code: str) -> CountryApplyConfig:
    overlay = load_apply_overlay(country_code)
    if overlay is not None:
        return overlay
    playbook = load_country_playbook(country_code)
    if playbook is not None:
        raw = playbook_to_apply_config(playbook)
        return CountryApplyConfig.model_validate(raw)
    return _empty_config(country_code)


def save_country_apply_config(raw: dict[str, Any]) -> dict[str, Any]:
    from app.documents.classify.country_guard import doc_type_matches_country

    config = CountryApplyConfig.model_validate(raw)
    for doc in config.documents:
        if not doc_type_matches_country(config.country_code, doc.doc_type):
            raise ValueError(
                f"Document type {doc.doc_type} does not match country {config.country_code}."
            )
    saved = save_apply_overlay(config)
    return saved.as_dict()


def upsert_extraction_doc(country_code: str, input_doc: dict[str, Any]) -> dict[str, Any]:
    config = _ensure_overlay(country_code)
    doc_type = str(input_doc.get("docType") or "").strip()
    if not doc_type:
        raise ValueError("Doc type is required")

    existing = next((d for d in config.documents if d.doc_type == doc_type), None)
    attributes: list[ApplyAttribute] = []
    if input_doc.get("attributes"):
        for attr in input_doc["attributes"]:
            form_path = str(attr.get("formPath") or "").strip()
            attributes.append(
                ApplyAttribute(
                    id=_attribute_id(doc_type, form_path),
                    label=str(attr.get("label") or "").strip(),
                    formPath=form_path,
                    enabled=bool(attr.get("enabled", True)),
                    mandatory=bool(attr.get("mandatory", False)),
                    writable=bool(attr.get("writable", True)),
                    needsResolution=attr.get("needsResolution"),
                )
            )
    elif existing:
        attributes = list(existing.attributes)

    next_doc = ApplyDocument(
        docType=doc_type,
        writable=bool(input_doc.get("writable", existing.writable if existing else True)),
        attributes=attributes,
    )

    if existing:
        documents = [
            next_doc if d.doc_type == doc_type else d
            for d in config.documents
        ]
    else:
        documents = [*config.documents, next_doc]

    saved = save_apply_overlay(
        CountryApplyConfig(
            countryCode=config.country_code,
            documents=documents,
            multiSourceFields=dict(config.multi_source_fields),
            updatedAt=config.updated_at,
        )
    )
    return saved.as_dict()


def remove_extraction_doc(country_code: str, doc_type: str) -> dict[str, Any]:
    config = _ensure_overlay(country_code)
    documents = [d for d in config.documents if d.doc_type != doc_type]
    multi = {
        k: [t for t in v if t != doc_type]
        for k, v in config.multi_source_fields.items()
    }
    multi = {k: v for k, v in multi.items() if v}
    saved = save_apply_overlay(
        CountryApplyConfig(
            countryCode=config.country_code,
            documents=documents,
            multiSourceFields=multi,
            updatedAt=config.updated_at,
        )
    )
    return saved.as_dict()


def upsert_extraction_attribute(
    country_code: str,
    doc_type: str,
    input_attr: dict[str, Any],
    attribute_id: str | None = None,
) -> dict[str, Any]:
    config = _ensure_overlay(country_code)
    doc = next((d for d in config.documents if d.doc_type == doc_type), None)
    if doc is None:
        return upsert_extraction_doc(country_code, {"docType": doc_type, "attributes": [input_attr]})

    form_path = str(input_attr.get("formPath") or "").strip()
    label = str(input_attr.get("label") or "").strip()
    if not form_path or not label:
        raise ValueError("Label and form path are required")

    next_attr = ApplyAttribute(
        id=attribute_id or _attribute_id(doc_type, form_path),
        label=label,
        formPath=form_path,
        enabled=bool(input_attr.get("enabled", True)),
        mandatory=bool(input_attr.get("mandatory", False)),
        writable=bool(input_attr.get("writable", True)),
        needsResolution=input_attr.get("needsResolution"),
    )

    attrs = [a for a in doc.attributes if a.id != next_attr.id]
    attrs.append(next_attr)
    attrs.sort(key=lambda a: a.label)

    documents = [
        ApplyDocument(docType=d.doc_type, writable=d.writable, attributes=attrs if d.doc_type == doc_type else d.attributes)
        for d in config.documents
    ]

    saved = save_apply_overlay(
        CountryApplyConfig(
            countryCode=config.country_code,
            documents=documents,
            multiSourceFields=dict(config.multi_source_fields),
            updatedAt=config.updated_at,
        )
    )
    return saved.as_dict()


def remove_extraction_attribute(country_code: str, doc_type: str, attr_id: str) -> dict[str, Any]:
    config = _ensure_overlay(country_code)
    documents: list[ApplyDocument] = []
    for doc in config.documents:
        if doc.doc_type != doc_type:
            documents.append(doc)
            continue
        attrs = [a for a in doc.attributes if a.id != attr_id]
        if attrs:
            documents.append(ApplyDocument(docType=doc.doc_type, writable=doc.writable, attributes=attrs))

    saved = save_apply_overlay(
        CountryApplyConfig(
            countryCode=config.country_code,
            documents=documents,
            multiSourceFields=dict(config.multi_source_fields),
            updatedAt=config.updated_at,
        )
    )
    return saved.as_dict()
