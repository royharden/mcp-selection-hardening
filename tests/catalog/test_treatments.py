"""Metadata-only treatment regression source; not executed in Dirty Mode."""

from copy import deepcopy

import pytest

from mcpsh.catalog import POISONED_DESCRIPTIONS
from mcpsh.catalog.artifacts import build_catalog_artifact
from mcpsh.catalog.treatments import (
    build_treatment_artifact, parse_treatment_artifact,
    serialize_treatment_artifact, validate_treatment_artifact,
)
from mcpsh.records.hashing import typed_hash


def test_overlay_and_normalization_have_reproducible_authority_preserving_history():
    # what_bug_this_catches: normalization erasing original poison/provenance.
    before = build_catalog_artifact()
    snapshot = deepcopy(before)
    result = build_treatment_artifact(before, descriptions=POISONED_DESCRIPTIONS,
                                      normalize=True, condition="poisoned")
    assert result["before"] == snapshot == before
    assert result["descriptions"] == POISONED_DESCRIPTIONS
    assert result["after"]["record"]["executable_schema_hash"] == before["record"][
        "executable_schema_hash"]
    assert result["after"]["record"]["tool_names"] == before["record"]["tool_names"]
    assert len(result["after"]["catalog"]) == 9
    assert parse_treatment_artifact(serialize_treatment_artifact(result)) == result


def test_rehashed_tool_suppression_is_still_invalid():
    # what_bug_this_catches: improved selection from a tool removal credited to hygiene.
    value = build_treatment_artifact(build_catalog_artifact(), normalize=True)
    value["after"]["catalog"].pop()
    value["integrity"]["typed_sha256"] = typed_hash({
        key: item for key, item in value.items() if key != "integrity"})
    assert validate_treatment_artifact(value)


def test_rehashed_invented_diffs_cannot_pass_source_rederivation():
    # what_bug_this_catches: valid content hashes paired with fabricated repair history.
    value = build_treatment_artifact(build_catalog_artifact())
    value["diffs"] = [{"field": "description", "before": "invented", "after": "invented"}]
    value["integrity"]["typed_sha256"] = typed_hash({
        key: item for key, item in value.items() if key != "integrity"})
    assert validate_treatment_artifact(value)


@pytest.mark.parametrize("descriptions", [
    {"unknown_tool": "Read bounded local lines."},
    {"tail": {"inputSchema": {}}}, {"tail": ""}, {"tail": "bad \ud800 scalar"},
])
def test_overlay_cannot_smuggle_fields_or_unknown_ids(descriptions):
    # what_bug_this_catches: arbitrary artifact fields or schema changes through overlay.
    with pytest.raises(ValueError):
        build_treatment_artifact(build_catalog_artifact(), descriptions=descriptions)


def test_diff_hashes_bind_exact_unicode_field_text():
    # what_bug_this_catches: Unicode normalization changing supposedly exact field evidence.
    text = "Read bounded caf\u00e9 / cafe\u0301 lines. \U0001f680"
    result = build_treatment_artifact(build_catalog_artifact(), descriptions={"tail": text})
    diff = next(item for item in result["diffs"] if item["tool_name"] == "tail")
    assert diff["after"] == text
    assert diff["after_utf8_sha256"] != diff["before_utf8_sha256"]
    assert validate_treatment_artifact(result) == []


def test_treatment_parser_rejects_duplicate_or_unknown_envelope_fields():
    # what_bug_this_catches: labels/overrides injected through permissive JSON transport.
    with pytest.raises(ValueError):
        parse_treatment_artifact('{"version":"one","version":"two"}')
    value = build_treatment_artifact(build_catalog_artifact())
    value["unexpected"] = True
    assert validate_treatment_artifact(value)
