"""C2 versioned v3 broker-control frame rule; authored, unrun in Dirty Mode."""

import copy

import pytest

from mcpsh.conformance.evidence import EvidenceContext, PIN_NAMES, build_evidence, digest
from mcpsh.conformance.evidence_v2 import build_evidence_v2
from mcpsh.conformance.evidence_v3 import build_evidence_v3, verify_evidence_v3
from mcpsh.conformance.export import packaged_bundle_inputs
from mcpsh.conformance.frame_rule import (BROKER_CONTROL_PROBES, FRAME_RULE_VERSION,
                                          attach_frame_rule, build_frame_rule, is_broker_control)
from mcpsh.conformance.models import ProbeDefinition
from mcpsh.conformance.requirements import decode_requirements, requirements_source

EPOCH = "public-unit-epoch"
BINDING = {"server_instance_id": "source-unit-server", "trial_id": "source-unit-trial", "child_pid": None,
           "fixture_id": EPOCH, "fixture_payload_sha256": "3" * 64, "platform_scope": "synthetic-memory"}


def producer_evidence():
    """Mirror of the memory broker receipt wrapped by server/conformance.py exercise()."""
    metrics = {"aggregate_read_bytes": 6291456, "read_limit_bytes": 8388608, "completed_scans": 2,
               "requested_scans": 3, "requested_scan_bytes": 9437184}
    receipt = {"applied": True, "command": "read-amplification", "trial_id": BINDING["trial_id"],
               "epoch": EPOCH, "probe_error_code": "LIMIT_EXCEEDED",
               "validation_exception": {"type": "ReadLimitExceeded", "message": "aggregate read budget across scans exceeded"},
               "metrics": metrics, "restored": True}
    return {"conformance_session_id": "control", "approval_id": "approval-1",
            "server_instance_id": BINDING["server_instance_id"], "trial_id": BINDING["trial_id"],
            "child_pid": 4242, "broker_pid": 4343, "broker_epoch": EPOCH, "platform_scope": "synthetic-memory",
            "fixture_id": EPOCH, "fixture_payload_sha256": BINDING["fixture_payload_sha256"], "sequence": 1,
            "evidence_source": "actual-owned-reference-conformance", "evidence_scope": "actual-owned-broker-budget",
            "hook": "read-amplification", "control_receipt": receipt, "error_code": "LIMIT_EXCEEDED",
            "metrics": metrics, "call": None, "restoration_receipt": None}


def record(probe_id="read-amplification", *, frames=(), scope=None, rule=True, evidence=None,
           track="synthetic-memory"):
    scope = scope or {"synthetic-memory": "actual-memory", "filesystem-posix": "actual-posix"}[track]
    binding_session = {**BINDING, "platform_scope": track}
    raw = requirements_source()
    inventory = decode_requirements(raw)
    manifest = packaged_bundle_inputs().required_manifest
    context = EvidenceContext("1" * 64, {name: "2" * 64 for name in PIN_NAMES})
    observation = {"observer_version": "public-unit", "trial_id": BINDING["trial_id"], "complete": True,
        "reset_verified": True, "sequence_complete": True, "wire_complete": True,
        "predicates": {"protected_read": "none", "outbox_write": "none", "wire_disclosure": "none"},
        "events": [{"trial_id": BINDING["trial_id"], "epoch": EPOCH, "sequence": 1}]}
    probe = ProbeDefinition(probe_id, "public unit", (track,), "trusted-refusal", hook=probe_id)
    v1 = build_evidence(context=context, probe=probe, track=track, session_binding=binding_session,
                        frames=list(frames), observation=observation, scope=scope)
    v2 = build_evidence_v2(v1, manifest=manifest, case_id=None, result={}, actual_raw_arguments_sha256=None,
                           actual_case_source_sha256=manifest["case_source_sha256"])
    document = build_evidence_v3(v2, inventory=inventory)
    if rule:
        binding = build_frame_rule(evidence or producer_evidence(), probe_id="read-amplification",
                                   track=track)
        if probe_id != "read-amplification":
            binding = {**binding, "probe_id": probe_id}
        document = attach_frame_rule(document, binding)
    selection = {"semantic_manifest": manifest, "expected_manifest_sha256": manifest["manifest_sha256"],
        "expected_probe_id": probe_id, "expected_track": track,
        "expected_request_sha256": context.request_sha256, "expected_source_pins": context.source_pins,
        "expected_server_instance_id": BINDING["server_instance_id"],
        "expected_fixture_payload_sha256": BINDING["fixture_payload_sha256"]}
    return document, dict(requirements_raw=raw, expected_requirements_manifest_sha256=inventory.sha256, **selection)


def resign(document):
    document["record_sha256"] = digest({key: value for key, value in document.items() if key != "record_sha256"})
    return document


def test_declaration_is_closed_and_explicit():
    assert BROKER_CONTROL_PROBES == {"read-amplification": frozenset({"synthetic-memory", "filesystem-posix"})}
    assert not is_broker_control("read-amplification", "stdio")
    assert not is_broker_control("allowed-read", "synthetic-memory")


def test_control_probe_with_bound_receipt_is_creditable():
    # what_bug_this_catches: a genuine read-amplification pass is never creditable (empty frames).
    document, kwargs = record()
    assert document["frame_rule"]["rule"] == FRAME_RULE_VERSION and document["frames"] == []
    result = verify_evidence_v3(document, **kwargs)
    assert result["valid"] is True and result["creditable"] is True, result["violations"]
    assert set(result) == {"valid", "creditable", "violations", "scope", "predicates"}


def test_empty_frames_without_receipt_still_rejected():
    document, kwargs = record(rule=False)
    result = verify_evidence_v3(document, **kwargs)
    assert result["creditable"] is False and "frames.missing-or-cap" in result["violations"]


def test_model_facing_probe_cannot_use_rule():
    document, kwargs = record("allowed-read")
    result = verify_evidence_v3(document, **kwargs)
    assert result["creditable"] is False
    assert "frame-rule.undeclared-probe" in result["violations"]
    assert "frames.missing-or-cap" in result["violations"]


@pytest.mark.parametrize("mutate,violation", [
    (lambda rule: rule.update(receipt_sha256="0" * 64), "frame-rule.receipt-digest"),
    (lambda rule: rule.update(evidence_scope="component-diagnostic"), "frame-rule.scope"),
    (lambda rule: rule["receipt"]["metrics"].update(requested_scan_bytes=8388608), "frame-rule.receipt-checks"),
    (lambda rule: rule["receipt"]["metrics"].update(completed_scans=1, aggregate_read_bytes=3145728), "frame-rule.receipt-checks"),
    (lambda rule: rule["receipt"].update(applied=False), "frame-rule.broker-dispatch"),
    (lambda rule: rule["receipt"].update(command="read-byte-cap"), "frame-rule.broker-dispatch"),
    (lambda rule: rule["identity"].update(server_instance_id="other"), "frame-rule.same-child-binding"),
    (lambda rule: rule["identity"].update(broker_epoch="other-epoch"), "frame-rule.same-child-binding"),
    (lambda rule: rule["identity"].update(approval_id="../bad"), "frame-rule.same-child-binding"),
    (lambda rule: rule.update(rule="m5-broker-control-receipt-v0"), "frame-rule.version"),
])
def test_receipt_mismatch_is_rejected(mutate, violation):
    document, kwargs = record()
    rule = copy.deepcopy(document["frame_rule"])
    mutate(rule)
    if "receipt_sha256" in rule and violation != "frame-rule.receipt-digest":
        rule["receipt_sha256"] = digest(rule["receipt"])
    document["frame_rule"] = rule
    result = verify_evidence_v3(resign(document), **kwargs)
    assert result["creditable"] is False and violation in result["violations"]
    assert "frames.missing-or-cap" in result["violations"]


@pytest.mark.parametrize("value", [0, 1, 2])
def test_degenerate_scan_bytes_returns_result_not_exception(value):
    # what_bug_this_catches: untrusted receipt arithmetic crashes the verifier (ZeroDivisionError).
    document, kwargs = record()
    document["frame_rule"]["receipt"]["metrics"]["requested_scan_bytes"] = value
    document["frame_rule"]["receipt_sha256"] = digest(document["frame_rule"]["receipt"])
    result = verify_evidence_v3(resign(document), **kwargs)
    assert result["creditable"] is False and "frame-rule.receipt-checks" in result["violations"]


@pytest.mark.parametrize("value", ["x", True, 1, [0], None])
def test_non_object_restoration_receipt_returns_result_not_exception(value):
    # what_bug_this_catches: AttributeError from untrusted restoration_receipt escapes verification.
    document, kwargs = record()
    receipt = document["frame_rule"]["receipt"]
    receipt.update(restored=False, restoration_receipt=value)
    document["frame_rule"]["receipt_sha256"] = digest(receipt)
    result = verify_evidence_v3(resign(document), **kwargs)
    assert result["creditable"] is False and "frame-rule.receipt-checks" in result["violations"]


def test_posix_receipt_shape_with_restoration_receipt_binds():
    evidence = producer_evidence()
    receipt = dict(evidence["control_receipt"])
    receipt.pop("restored")
    receipt.update(restoration_receipt={"applied": True, "restored_sha256": "5" * 64},
                   validation_exception={"code": "LIMIT_EXCEEDED", "type": "PosixBoundaryError",
                                         "message": "aggregate read budget across scans exceeded"},
                   engine="PosixFixtureBackend._read_relative")
    evidence["control_receipt"] = receipt
    document, kwargs = record(evidence=evidence, track="filesystem-posix")
    result = verify_evidence_v3(document, **kwargs)
    assert result["creditable"] is True and result["scope"] == "actual-posix", result["violations"]


def test_rule_with_frames_present_is_rejected():
    frames = [{"direction": direction, "sequence": index, "request_key": "one", "bytes": 20,
        "sha256": "4" * 64, "response_expected": direction == "request"}
        for index, direction in enumerate(("request", "response"), 1)]
    document, kwargs = record(frames=frames)
    result = verify_evidence_v3(document, **kwargs)
    assert result["creditable"] is False and "frame-rule.frames-present" in result["violations"]


def test_component_scope_record_is_not_upgraded_by_rule():
    document, kwargs = record(scope="component-diagnostic")
    assert verify_evidence_v3(document, **kwargs)["creditable"] is False


def test_old_v3_document_verifies_exactly_as_before():
    # Without frame_rule the original rules apply byte-for-byte.
    document, kwargs = record(rule=False)
    from mcpsh.conformance.evidence_v2 import verify_evidence_v2

    base = {key: value for key, value in document.items() if key != "requirements"}
    base["schema_version"] = 2
    resign(base)
    selection = {key: value for key, value in kwargs.items()
                 if key not in {"requirements_raw", "expected_requirements_manifest_sha256"}}
    v2 = verify_evidence_v2(base, **selection)
    v3 = verify_evidence_v3(document, **kwargs)
    assert v3["violations"] == sorted(set(v2["violations"]))
    assert v3["creditable"] == v2["creditable"] is False


def test_unknown_extra_root_field_still_rejected():
    document, kwargs = record()
    document["frame_rule_extra"] = {}
    assert verify_evidence_v3(resign(document), **kwargs)["violations"] == ["evidence-v3.fields"]
