"""Catalog transport regression source; not run during Dirty Mode construction."""

from copy import deepcopy

import pytest

from mcpsh.catalog.artifacts import (
    artifact_pins, build_catalog_artifact, parse_catalog_artifact,
    serialize_catalog_artifact, validate_catalog_artifact,
)
from mcpsh.records.hashing import typed_hash


def test_reproducible_catalog_record_and_raw_identity_are_separate():
    # what_bug_this_catches: treating canonical JSON identity as original wire bytes.
    first = build_catalog_artifact("clean", ordering_seed=17)
    second = build_catalog_artifact("clean", ordering_seed=17)
    assert serialize_catalog_artifact(first) == serialize_catalog_artifact(second)
    raw = serialize_catalog_artifact(first)
    spaced = " \n" + raw
    assert parse_catalog_artifact(spaced) == first
    assert artifact_pins(first, raw=raw)["typed_sha256"] == artifact_pins(
        first, raw=spaced)["typed_sha256"]
    assert artifact_pins(first, raw=raw)["raw_sha256"] != artifact_pins(
        first, raw=spaced)["raw_sha256"]
    assert "raw_sha256" not in artifact_pins(first)


def test_metadata_changes_do_not_change_executable_schema_identity():
    # what_bug_this_catches: metadata poison redefining server execution authority.
    clean = build_catalog_artifact("clean")
    poisoned = build_catalog_artifact("poisoned")
    assert clean["record"]["executable_schema_hash"] == poisoned["record"][
        "executable_schema_hash"]
    assert clean["record"]["presented_metadata_hash"] != poisoned["record"][
        "presented_metadata_hash"]
    assert len(artifact_pins(clean)["qualified_tool_ids"]) == 9


def test_rehashing_schema_drift_never_makes_it_authoritative():
    # what_bug_this_catches: accepting a self-consistent attacker-owned schema hash.
    artifact = build_catalog_artifact()
    artifact["catalog"][0]["inputSchema"]["additionalProperties"] = True
    artifact["record"]["executable_schema_hash"] = typed_hash({
        tool["name"]: tool["inputSchema"] for tool in artifact["catalog"]})
    artifact["integrity"]["typed_sha256"] = typed_hash({
        key: value for key, value in artifact.items() if key != "integrity"})
    assert validate_catalog_artifact(artifact)[0]["code"] == "SCHEMA_DRIFT"


def test_catalog_reorder_cannot_disagree_with_seed_even_after_rehash():
    # what_bug_this_catches: order provenance that describes a different presentation.
    artifact = build_catalog_artifact()
    artifact["catalog"].reverse()
    artifact["record"]["tool_names"].reverse()
    artifact["integrity"]["typed_sha256"] = typed_hash({
        key: value for key, value in artifact.items() if key != "integrity"})
    assert validate_catalog_artifact(artifact)[0]["code"] == "TOOL_ORDER"


def test_extra_fields_duplicate_ids_and_forged_server_are_rejected():
    # what_bug_this_catches: importing undeclared labels or display-name identity.
    original = build_catalog_artifact()
    extra = deepcopy(original)
    extra["undeclared"] = "not part of this transport"
    duplicate = deepcopy(original)
    duplicate["catalog"][0] = deepcopy(duplicate["catalog"][1])
    forged = deepcopy(original)
    forged["record"]["server_instance_id"] = "untrusted-server-display-name"
    assert validate_catalog_artifact(extra)[0]["code"] == "ARTIFACT_FIELDS"
    assert validate_catalog_artifact(duplicate)[0]["code"] == "TOOL_SET"
    assert validate_catalog_artifact(forged)[0]["code"] == "SERVER_ID"


@pytest.mark.parametrize("raw", [b'{"a":1,"a":2}', b'{"a":NaN}',
                                  b'{"a":Infinity}', b'\xff', b'[]'])
def test_malformed_transport_is_rejected(raw):
    # what_bug_this_catches: duplicate-key/nonfinite/encoding input silently normalized.
    with pytest.raises(ValueError):
        parse_catalog_artifact(raw)


def test_raw_pin_must_belong_to_supplied_artifact():
    # what_bug_this_catches: pairing one payload's raw hash with another typed record.
    clean = build_catalog_artifact("clean")
    poisoned = build_catalog_artifact("poisoned")
    with pytest.raises(ValueError):
        artifact_pins(clean, raw=serialize_catalog_artifact(poisoned))


def test_bounds_and_strict_seed_type_are_enforced():
    # what_bug_this_catches: boolean seed or oversized transport bypassing bounds.
    with pytest.raises(ValueError):
        build_catalog_artifact(ordering_seed=True)
    with pytest.raises(ValueError):
        parse_catalog_artifact(b" " * 1_048_577)
