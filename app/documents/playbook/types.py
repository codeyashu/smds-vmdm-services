"""Semantic document playbook types — stable logical field IDs + typed bindings."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

BindKind = Literal["taxSlot", "scalar", "address", "bank", "unmapped"]
NeedsResolution = Literal["cityCode", "bankingInstitutionCode"]


class TaxSlotBind(BaseModel):
    kind: Literal["taxSlot"] = "taxSlot"
    tax_type_code: str = Field(alias="taxTypeCode")

    model_config = {"populate_by_name": True}


class ScalarBind(BaseModel):
    kind: Literal["scalar"] = "scalar"
    form_path: str = Field(alias="formPath")

    model_config = {"populate_by_name": True}


class AddressBind(BaseModel):
    kind: Literal["address"] = "address"
    role: Literal["primary"] = "primary"
    field: str


class BankBind(BaseModel):
    kind: Literal["bank"] = "bank"
    index: int = 0
    field: str


class UnmappedBind(BaseModel):
    kind: Literal["unmapped"] = "unmapped"
    key: str


class FieldBinding(BaseModel):
    logical_field_id: str = Field(alias="logicalFieldId")
    label: str
    bind: dict[str, Any]
    validator: str | None = None
    singleton: bool = False
    needs_resolution: NeedsResolution | None = Field(default=None, alias="needsResolution")

    model_config = {"populate_by_name": True}


class DocumentPlaybookEntry(BaseModel):
    doc_type: str = Field(alias="docType")
    writable: bool = True
    attributes: list[str]
    address_roles: list[str] = Field(default_factory=list, alias="addressRoles")

    model_config = {"populate_by_name": True}


class CountryPlaybook(BaseModel):
    country_code: str = Field(alias="countryCode")
    version: int = 1
    bindings: list[FieldBinding] = Field(default_factory=list)
    documents: list[DocumentPlaybookEntry] = Field(default_factory=list)
    multi_source_fields: dict[str, list[str]] = Field(default_factory=dict, alias="multiSourceFields")
    name_fuzzy_threshold: float = Field(default=0.82, alias="nameFuzzyThreshold")
    address_fuzzy_threshold: float = Field(default=0.75, alias="addressFuzzyThreshold")

    model_config = {"populate_by_name": True}

    def binding_map(self) -> dict[str, FieldBinding]:
        return {row.logical_field_id: row for row in self.bindings}

    def doc_map(self) -> dict[str, DocumentPlaybookEntry]:
        return {row.doc_type: row for row in self.documents}
