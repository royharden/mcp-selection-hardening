"""Authored semantic authority/projection regressions; no tests have run."""

import hashlib
import json

import pytest

from mcpsh.conformance.evidence import EvidenceContext, PIN_NAMES, build_evidence, digest
from mcpsh.conformance.evidence_v2 import build_evidence_v2, verify_evidence_v2
from mcpsh.conformance.manifest import semantic_manifest, verify_semantic_manifest
from mcpsh.conformance.models import ProbeDefinition
from mcpsh.conformance.semantics import get_case, public_case_source, semantic_cases


def authority():
    return semantic_manifest(public_case_source(), grammar_source_sha256="1" * 64,
                              parser_source_sha256="2" * 64)


def record():
    manifest = authority()
    case = get_case("literal-dot")
    binding = {"server_instance_id": "server-one", "trial_id": "trial-one", "child_pid": None,
               "fixture_id": "public-one", "fixture_payload_sha256": "3" * 64, "platform_scope": "synthetic-memory"}
    observation = {"observer_version": "public-observer", "trial_id": "trial-one", "complete": True,
        "reset_verified": True, "sequence_complete": True, "wire_complete": True,
        "predicates": {"protected_read": "none", "wire_disclosure": "none", "outbox_write": "none"},
        "events": [{"trial_id": "trial-one", "epoch": "epoch-one", "sequence": 1}]}
    frames = [{"direction": direction, "sequence": index, "request_key": "call-one", "sha256": "4" * 64,
               "bytes": 20, "response_expected": direction == "request"}
              for index, direction in enumerate(("request", "response"), 1)]
    probe = ProbeDefinition("semantic-literal-dot", "public control", ("synthetic-memory",), "semantic:literal-dot")
    context = EvidenceContext("5" * 64, {name: "6" * 64 for name in PIN_NAMES})
    base = build_evidence(context=context, probe=probe, track="synthetic-memory", session_binding=binding,
                          frames=frames, observation=observation, scope="actual-memory")
    return build_evidence_v2(base, manifest=manifest, case_id=case.case_id,
        result={"ok": True, "coverage": {"complete": True, "semantic_complete": True}},
        actual_raw_arguments_sha256=hashlib.sha256(case.call.raw_arguments.encode("utf-8")).hexdigest(),
        actual_case_source_sha256=manifest["case_source_sha256"]), manifest


def verify(value, manifest, expected=None):
    return verify_evidence_v2(value, semantic_manifest=manifest,
        expected_manifest_sha256=expected or manifest["manifest_sha256"],
        expected_probe_id="semantic-literal-dot", expected_track="synthetic-memory",
        expected_request_sha256="5" * 64, expected_source_pins={name: "6" * 64 for name in PIN_NAMES},
        expected_server_instance_id="server-one", expected_fixture_payload_sha256="3" * 64)


def seal(value):
    value["record_sha256"] = digest({key: child for key, child in value.items() if key != "record_sha256"})
    return value


def test_v2_structural_positive_control():
    # what_bug_this_catches: schema extension has no valid complete structural case.
    value, manifest = record()
    assert verify(value, manifest)["creditable"] is True


def test_actual_raw_call_must_match_golden_arguments():
    # what_bug_this_catches: a different handler request inherits expected-case credit.
    value, manifest = record()
    value["semantic"]["actual_raw_arguments_sha256"] = "7" * 64
    result = verify(seal(value), manifest)
    assert result["creditable"] is False
    assert "semantic.actual-raw-call" in result["violations"]


def test_case_source_change_does_not_inherit_old_expectation_pin():
    # what_bug_this_catches: changed gold expectations after admission keep old credit.
    value, manifest = record()
    value["semantic"]["case_source_sha256"] = "8" * 64
    assert verify(seal(value), manifest)["creditable"] is False


def test_unknown_parse_coverage_never_earns_actual_credit():
    # what_bug_this_catches: correct UNKNOWN bin is mistaken for parsed coverage.
    value, manifest = record()
    value["semantic"]["coverage_kind"] = "unknown"
    result = verify(seal(value), manifest)
    assert result["valid"] is True
    assert result["creditable"] is False


def test_v2_component_record_stays_diagnostic():
    # what_bug_this_catches: the semantic extension bypasses v1 scope restrictions.
    value, manifest = record()
    value["scope"] = "component-diagnostic"
    assert verify(seal(value), manifest)["creditable"] is False


def test_v2_mixed_effect_unknown_retains_observed_state():
    # what_bug_this_catches: v2 translation drops a known effect while rejecting credit.
    value, manifest = record()
    value["observation"]["complete"] = False
    value["observation"]["predicates"] = {"protected_read": "observed", "wire_disclosure": "unknown", "outbox_write": "unknown"}
    result = verify(seal(value), manifest)
    assert result["creditable"] is False
    assert result["predicates"]["protected_read"] == "observed"


def test_changed_grammar_version_cannot_reuse_manifest_authority():
    # what_bug_this_catches: stale public gold survives a producer semantic change.
    manifest = authority()
    pin = manifest["manifest_sha256"]
    manifest["grammar_version"] = "changed-grammar"
    manifest["manifest_sha256"] = digest({key: value for key, value in manifest.items() if key != "manifest_sha256"})
    assert verify_semantic_manifest(manifest, expected_manifest_sha256=pin)["valid"] is False


def test_missing_required_probe_rejects_even_when_self_hash_updated():
    # what_bug_this_catches: dropping a difficult case becomes self-approved scope.
    manifest = authority()
    expected = manifest["manifest_sha256"]
    manifest["required_probe_ids"]["stdio"].pop()
    manifest["manifest_sha256"] = digest({key: value for key, value in manifest.items() if key != "manifest_sha256"})
    assert verify_semantic_manifest(manifest, expected_manifest_sha256=expected)["valid"] is False


def test_public_case_expansion_is_bounded():
    # what_bug_this_catches: repeat metadata bypasses physical-line/scan caps.
    package = json.loads(public_case_source())
    package["cases"][-1]["repeat_lines"] = 501
    with pytest.raises(ValueError, match="expansion"):
        semantic_cases(json.dumps(package).encode("utf-8"))
