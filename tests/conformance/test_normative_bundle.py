"""Portable v1/v2 source compatibility regressions; no export invocation here."""

from mcpsh.conformance.export import build_contract_bundle
from mcpsh.conformance.export_v2 import (build_normative_bundle, packaged_normative_inputs,
                                        validate_normative_bundle)


def bundle():
    inputs, raw, schemas = packaged_normative_inputs()
    return build_normative_bundle(inputs, requirements_raw=raw, schemas=schemas)


def validate(value, files=None, inventory_pin=None):
    return validate_normative_bundle(files or value.to_files(), expected_bundle_sha256=value.bundle_sha256,
        expected_manifest_sha256=value.manifest_sha256, expected_runtime_schema_sha256=value.runtime_schema_sha256,
        expected_requirements_manifest_sha256=inventory_pin)


def test_v2_integrity_does_not_self_approve_normative_authority():
    # what_bug_this_catches: embedded inventory SHA silently becomes external approval.
    result = validate(bundle())
    assert result["valid"] is True
    assert result["requirements_authority_valid"] is False
    assert result["conformance_acceptance"] == "pending"


def test_external_requirements_pin_is_separate_from_semantic_pin():
    # what_bug_this_catches: the semantic corpus digest substitutes for boundary authority.
    value = bundle()
    result = validate(value, inventory_pin=value.manifest_sha256)
    assert result["valid"] is False
    assert "requirements.external-pin" in result["violations"]


def test_missing_inventory_cannot_downgrade_v2_to_legacy():
    # what_bug_this_catches: absent normative resource falls back to registry-only export.
    value = bundle()
    files = value.to_files()
    files.pop("contracts/requirements-v1.json")
    assert validate(value, files)["valid"] is False


def test_v1_builder_still_has_explicit_legacy_identity():
    # what_bug_this_catches: normative extension silently changes frozen legacy bytes/format.
    inputs, _, _ = packaged_normative_inputs()
    legacy = build_contract_bundle(inputs)
    assert legacy.bundle_sha256 != bundle().bundle_sha256
    assert "contracts/requirements-v1.json" not in legacy.to_files()
