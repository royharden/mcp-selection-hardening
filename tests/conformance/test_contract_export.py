"""Portable contract regression source; no builder/test invocation has run here."""

import hashlib
import json
from dataclasses import replace

import pytest

from mcpsh.conformance.export import build_contract_bundle, packaged_bundle_inputs, validate_contract_bundle


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=True, allow_nan=False, separators=(",", ":")).encode() + b"\n"


@pytest.fixture
def contract():
    return build_contract_bundle(packaged_bundle_inputs())


def validate(contract, files=None, bundle_pin=None):
    return validate_contract_bundle(files or contract.to_files(),
        expected_bundle_sha256=bundle_pin or contract.bundle_sha256,
        expected_manifest_sha256=contract.manifest_sha256,
        expected_runtime_schema_sha256=contract.runtime_schema_sha256)


def reseal_payloads(files):
    index = json.loads(files["bundle.json"])
    for row in index["files"]:
        if row["path"] in files:
            raw = files[row["path"]]
            row.update(sha256=hashlib.sha256(raw).hexdigest(), bytes=len(raw))
    files["bundle.json"] = canonical(index)
    return hashlib.sha256(files["bundle.json"]).hexdigest()


def test_deterministic_bytes_do_not_depend_on_input_mapping_order():
    # what_bug_this_catches: nondeterministic schema enumeration changes bundle pins.
    inputs = packaged_bundle_inputs()
    first = build_contract_bundle(inputs)
    second = build_contract_bundle(replace(inputs, schemas=dict(reversed(list(inputs.schemas.items())))))
    assert first.files == second.files
    assert first.bundle_sha256 == second.bundle_sha256


def test_integrity_never_becomes_platform_or_s1_acceptance(contract):
    # what_bug_this_catches: successful source export advertises measured safety.
    result = validate(contract)
    assert result["valid"] is True
    assert result["verdict"] == "integrity-only"
    assert result["runtime_acceptance"] == "pending"
    assert result["s1_operational_acceptance"] is False
    assert result["platform_claims"]["filesystem-posix"] == "pending"


def test_missing_required_payload_rejects(contract):
    # what_bug_this_catches: detached package silently omits a hard schema/case file.
    files = contract.to_files()
    files.pop("schemas/evidence-v2.schema.json")
    assert validate(contract, files)["valid"] is False


def test_path_escape_rejects_even_with_new_index_pin(contract):
    # what_bug_this_catches: an externally pinned index becomes arbitrary host reads.
    files = contract.to_files()
    index = json.loads(files["bundle.json"])
    index["files"][0]["path"] = "../outside.json"
    files["bundle.json"] = canonical(index)
    pin = hashlib.sha256(files["bundle.json"]).hexdigest()
    assert validate(contract, files, pin)["valid"] is False


def test_source_claim_cannot_be_promoted_to_posix_pass(contract):
    # what_bug_this_catches: recomputing a source hash creates false platform proof.
    files = contract.to_files()
    index = json.loads(files["bundle.json"])
    index["platform_claims"]["filesystem-posix"] = "passed"
    files["bundle.json"] = canonical(index)
    pin = hashlib.sha256(files["bundle.json"]).hexdigest()
    result = validate(contract, files, pin)
    assert "bundle.claim-promotion" in result["violations"]


def test_remote_schema_reference_is_not_fetched_or_accepted(contract):
    # what_bug_this_catches: schema integrity inspection triggers external resolution.
    files = contract.to_files()
    schema = json.loads(files["schemas/evidence-v2.schema.json"])
    schema["properties"]["semantic"] = {"$ref": "https://example.invalid/remote.json"}
    files["schemas/evidence-v2.schema.json"] = canonical(schema)
    assert validate(contract, files, reseal_payloads(files))["valid"] is False


def test_unknown_schema_identity_rejects(contract):
    # what_bug_this_catches: a future schema is silently treated as the frozen format.
    files = contract.to_files()
    schema = json.loads(files["schemas/evidence-v1.schema.json"])
    schema["$id"] = "urn:mcpsh:conformance-evidence:unsupported"
    files["schemas/evidence-v1.schema.json"] = canonical(schema)
    assert validate(contract, files, reseal_payloads(files))["valid"] is False


def test_runtime_schema_bool_cannot_equal_numeric_bound():
    # what_bug_this_catches: Python True==1 weakens strict executable schema identity.
    inputs = packaged_bundle_inputs()
    schemas = json.loads(json.dumps(inputs.runtime_schemas))
    schemas["tail"]["properties"]["lines"]["minimum"] = True
    with pytest.raises(ValueError, match="runtime schema"):
        build_contract_bundle(replace(inputs, runtime_schemas=schemas))
