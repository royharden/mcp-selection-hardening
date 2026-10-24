"""Authored normative proof/full-suite regressions; no conformance execution."""

import hashlib

from mcpsh.conformance.evidence import EvidenceContext, PIN_NAMES, build_evidence
from mcpsh.conformance.evidence_v2 import build_evidence_v2
from mcpsh.conformance.evidence_v3 import build_evidence_v3, verify_evidence_v3
from mcpsh.conformance.export import packaged_bundle_inputs
from mcpsh.conformance.models import ConformanceReport, ProbeDefinition, ProbeResult, Status
from mcpsh.conformance.requirements import audit_requirements, decode_requirements, requirements_source


def diagnostic_record():
    raw = requirements_source()
    inventory = decode_requirements(raw)
    manifest = packaged_bundle_inputs().required_manifest
    context = EvidenceContext("1" * 64, {name: "2" * 64 for name in PIN_NAMES})
    binding = {"server_instance_id": "source-unit-server", "trial_id": "source-unit-trial", "child_pid": None,
        "fixture_id": "public-unit", "fixture_payload_sha256": "3" * 64, "platform_scope": "synthetic-memory"}
    observation = {"observer_version": "public-unit", "trial_id": binding["trial_id"], "complete": True,
        "reset_verified": True, "sequence_complete": True, "wire_complete": True,
        "predicates": {"protected_read": "none", "outbox_write": "none", "wire_disclosure": "none"},
        "events": [{"trial_id": binding["trial_id"], "epoch": "public-unit-epoch", "sequence": 1}]}
    frames = [{"direction": direction, "sequence": index, "request_key": "one", "bytes": 20,
        "sha256": "4" * 64, "response_expected": direction == "request"}
        for index, direction in enumerate(("request", "response"), 1)]
    probe = ProbeDefinition("allowed-read", "public unit", ("synthetic-memory",), "allowed")
    v1 = build_evidence(context=context, probe=probe, track="synthetic-memory", session_binding=binding,
                        frames=frames, observation=observation, scope="component-diagnostic")
    v2 = build_evidence_v2(v1, manifest=manifest, case_id=None, result={}, actual_raw_arguments_sha256=None,
                           actual_case_source_sha256=manifest["case_source_sha256"])
    record = build_evidence_v3(v2, inventory=inventory)
    selection = {"semantic_manifest": manifest, "expected_manifest_sha256": manifest["manifest_sha256"],
        "expected_probe_id": "allowed-read", "expected_track": "synthetic-memory",
        "expected_request_sha256": context.request_sha256, "expected_source_pins": context.source_pins,
        "expected_server_instance_id": binding["server_instance_id"],
        "expected_fixture_payload_sha256": binding["fixture_payload_sha256"]}
    return raw, inventory, probe, record, selection


def test_v3_requires_separate_external_inventory_pin():
    # what_bug_this_catches: record's own inventory hash is treated as authority.
    raw, _, _, record, selection = diagnostic_record()
    result = verify_evidence_v3(record, requirements_raw=raw,
        expected_requirements_manifest_sha256=None, **selection)
    assert result["creditable"] is False
    assert "requirements.external-pin" in result["violations"]


def test_cached_credited_boolean_cannot_upgrade_component_record():
    # what_bug_this_catches: aggregation trusts a cached pass instead of actual attribution.
    raw, inventory, probe, record, selection = diagnostic_record()
    row = ProbeResult("allowed-read", "synthetic-memory", Status.PASS, True, "unit",
        {"provenance": record, "verification": {"valid": True, "creditable": True}})
    audit = audit_requirements(raw, expected_requirements_manifest_sha256=inventory.sha256,
        registry=(probe,), results=(row,), tracks=("synthetic-memory",),
        evidence_bindings={"synthetic-memory/allowed-read": selection})
    assert audit["platforms"]["synthetic-memory"]["verdict"] == "pending"
    negative = next(item for item in audit["platforms"]["synthetic-memory"]["requirements"] if item["requirement_id"] == "observer-negative-controls")
    assert any("proof.wrong-platform-scope:allowed-read" == issue for issue in negative["violations"])


def test_full_suite_flag_cannot_approve_missing_inventory():
    # what_bug_this_catches: old positional report construction bypasses new normative gate.
    report = ConformanceReport((), ("synthetic-memory",), (), True, "public-unit")
    result = report.to_dict()
    assert result["platforms"]["synthetic-memory"]["verdict"] == "pending"
    assert result["normative_coverage"]["authority_valid"] is False


def test_wrong_inventory_pin_does_not_change_requirement_denominator():
    # what_bug_this_catches: failure to authorize becomes an empty successful suite.
    raw = requirements_source()
    inventory = decode_requirements(raw)
    result = audit_requirements(raw, expected_requirements_manifest_sha256="0" * 64,
        registry=(), results=(), tracks=("filesystem-posix",))
    assert result["platforms"]["filesystem-posix"]["required_requirements"] == sum(
        "filesystem-posix" in row.tracks for row in inventory.requirements)
    assert result["platforms"]["filesystem-posix"]["filesystem_proof"] is False


def test_malformed_registry_preserves_known_normative_count():
    # what_bug_this_catches: malformed observations erase approved obligations.
    raw = requirements_source()
    result = audit_requirements(raw, expected_requirements_manifest_sha256=hashlib.sha256(raw).hexdigest(),
        registry=({"malformed": True},), results=(), tracks=("filesystem-posix",))
    assert result["audit_valid"] is False
    assert result["platforms"]["filesystem-posix"]["required_requirements"] > 0
    assert result["platforms"]["filesystem-posix"]["verdict"] == "pending"
