"""C1 D2-producer <-> v7-consumer seam regressions; authored, unrun in Dirty Mode.

Fixtures mirror the exact return shape of server/conformance.py exercise() and the
memory/POSIX broker receipts. No broker, child process, fixture or probe is started.
"""

import copy
import hashlib
import json
import shutil
from pathlib import Path

import pytest

from mcpsh.conformance.receipt_guard import (CAP_METRICS, ERRORS, SCOPES, TRUSTED_HOOKS,
                                             ReceiptGuard, refusal_checks)

IDENTITY = {"server_instance_id": "server", "trial_id": "trial", "fixture_id": "epoch",
            "fixture_payload_sha256": "a" * 64, "approval_id": "approval-1", "child_pid": 123}


def _observation(sequence=1):
    attribution = {**IDENTITY, "conformance_session_id": "control", "broker_pid": 456,
                   "broker_epoch": "epoch", "sequence": sequence}
    return {"trial_id": "trial", "epoch": "epoch", "complete": True, "after_hash": "h",
            "protected_read_count": 0, "outbox_hashes": {},
            "predicates": {"protected_read": "none", "outbox_write": "none", "wire_disclosure": "none"},
            "conformance_attribution": attribution}


def _call(code):
    result = {"ok": False, "error": {"code": code}}
    wire = json.dumps(result, sort_keys=True, ensure_ascii=True, allow_nan=False,
                      separators=(",", ":")).encode()
    raw = '{"source_id":"app","lines":500}'
    return {"event": {"call_id": "trial:1", "trial_id": "trial", "server_instance_id": "server",
                      "raw_arguments": raw, "raw_hash": hashlib.sha256(raw.encode()).hexdigest(),
                      "dispatched": True},
            "result": result, "wire_sha256": hashlib.sha256(wire).hexdigest()}


def producer_evidence(hook, *, track="synthetic-memory"):
    """Exact exercise() field set for each of the six reconciled hooks."""
    receipt, packet, restoration, metrics = None, None, None, {}
    if hook in CAP_METRICS:
        validator, maximum, configured, attempted, reported = CAP_METRICS[hook]
        receipt = {"operation": "actual-production-configuration-validation",
                   "attempts": [{"validator": validator, "offered_count": maximum, "accepted": True,
                                 "validation_exception": None},
                                {"validator": validator, "offered_count": maximum + 1, "accepted": False,
                                 "validation_exception": {"type": "ValueError", "message": "limit"}}],
                   "probe_error_code": "CONFIG_INVALID"}
        metrics = {configured: 3 if hook == "source-count-cap" else 1, attempted: maximum + 1,
                   reported: maximum}
        receipt["metrics"] = metrics
        error_code = "CONFIG_INVALID"
        source = "actual-production-config-component"
    elif hook == "read-amplification":
        metrics = {"aggregate_read_bytes": 2 * 3145728, "read_limit_bytes": 8388608,
                   "completed_scans": 2, "requested_scans": 3, "requested_scan_bytes": 9437184}
        receipt = {"applied": True, "probe_error_code": "LIMIT_EXCEEDED",
                   "validation_exception": {"type": "ReadLimitExceeded", "message": "budget"},
                   "metrics": metrics}
        if track == "filesystem-posix":
            receipt["restoration_receipt"] = {"applied": True}
        else:
            receipt["restored"] = True
        error_code = "LIMIT_EXCEEDED"
        source = "actual-owned-reference-conformance"
    else:
        receipt = {"applied": True}
        packet = _call(ERRORS[hook])
        restoration = {"applied": True}
        error_code = ERRORS[hook]
        source = "actual-owned-reference-conformance"
    before = _observation()
    after = copy.deepcopy(before)
    return {**IDENTITY, "conformance_session_id": "control", "broker_pid": 456, "broker_epoch": "epoch",
            "platform_scope": track, "sequence": 1, "evidence_source": source,
            "evidence_scope": SCOPES[hook], "hook": hook, "before": before, "after": after,
            "observation": after, "control_receipt": receipt, "restoration_receipt": restoration,
            "call": packet, "error_code": error_code, "metrics": metrics,
            "observed_state_unchanged": True, "outside_effect": "none"}


@pytest.mark.parametrize("hook,track", [("missing-source", "filesystem-posix"),
    ("binary-content", "filesystem-posix"), ("unsupported-encoding", "filesystem-posix"),
    ("read-amplification", "synthetic-memory"), ("read-amplification", "filesystem-posix"),
    ("source-count-cap", "synthetic-memory"), ("custom-rule-count-cap", "filesystem-posix")])
def test_reconciled_producer_receipt_is_accepted_and_checked(hook, track):
    evidence = producer_evidence(hook, track=track)
    ReceiptGuard(IDENTITY).accept(hook, evidence)
    checks = refusal_checks(hook, evidence)
    assert checks is not None and all(checks.values()), checks


def test_scope_table_covers_exactly_the_six_trusted_hooks():
    assert set(SCOPES) == set(ERRORS) == TRUSTED_HOOKS


@pytest.mark.parametrize("hook,scope", [("read-amplification", "actual-owned-reference"),
    ("missing-source", "actual-owned-broker-budget"), ("binary-content", "component-diagnostic"),
    ("source-count-cap", "actual-owned-reference"), ("custom-rule-count-cap", "actual-posix")])
def test_receipt_from_another_scope_is_never_relabelled(hook, scope):
    evidence = producer_evidence(hook)
    evidence["evidence_scope"] = scope
    assert refusal_checks(hook, evidence) is None


@pytest.mark.parametrize("hook", sorted(CAP_METRICS))
def test_config_cap_producer_maximum_drift_fails(hook):
    evidence = producer_evidence(hook)
    reported = CAP_METRICS[hook][4]
    evidence["metrics"][reported] += 1
    assert refusal_checks(hook, evidence)["producer_maximum_normative"] is False


@pytest.mark.parametrize("hook", sorted(CAP_METRICS))
def test_config_cap_missing_metrics_is_unknown(hook):
    evidence = producer_evidence(hook)
    evidence["metrics"] = {}
    assert refusal_checks(hook, evidence) is None


def test_read_amplification_stimulus_within_budget_is_not_amplification():
    evidence = producer_evidence("read-amplification")
    evidence["metrics"]["requested_scan_bytes"] = 8388608
    assert refusal_checks("read-amplification", evidence)["stimulus_exceeds_budget"] is False


def test_read_amplification_early_deadline_is_not_budget_refusal():
    evidence = producer_evidence("read-amplification")
    evidence["metrics"].update(completed_scans=1, aggregate_read_bytes=3145728)
    assert refusal_checks("read-amplification", evidence)["refused_at_budget_boundary"] is False


@pytest.mark.parametrize("hook", ["missing-source", "binary-content", "unsupported-encoding"])
def test_structured_refusal_before_broker_dispatch_is_not_credit(hook):
    evidence = producer_evidence(hook, track="filesystem-posix")
    evidence["call"]["event"]["dispatched"] = False
    assert refusal_checks(hook, evidence)["broker_dispatched"] is False


def test_trusted_refusal_end_to_end_status_uses_producer_fields():
    from mcpsh.conformance.models import Status
    from mcpsh.conformance.probes import definitions
    from mcpsh.conformance.runner import _hook_result

    probes = {probe.probe_id: probe for probe in definitions()}
    for hook in sorted(TRUSTED_HOOKS):
        track = "filesystem-posix" if hook in {"missing-source", "binary-content", "unsupported-encoding"} else "synthetic-memory"
        status, _ = _hook_result(probes[hook], producer_evidence(hook, track=track))
        assert status == Status.PASS, hook
        alias, _ = _hook_result(probes["control-stdio-" + hook], producer_evidence(hook, track=track))
        assert alias == Status.PASS, hook


def test_stdio_alias_identity_uses_reference_fixture_instance_not_fixture_ref():
    # The producer attributes reference.fixture_id; a host reporting fixture_ref
    # would make every control-stdio alias an identity mismatch.
    evidence = producer_evidence("source-count-cap")
    with pytest.raises(ValueError):
        ReceiptGuard({**IDENTITY, "fixture_id": "public-conformance-v1"}).accept("source-count-cap", evidence)
    source = (Path(__file__).resolve().parents[2] / "src/mcpsh/conformance/stdio_host.py").read_text(encoding="utf-8")
    assert '"fixture_id": reference.fixture_id' in source
    assert 'fixture["fixture_ref"]' not in source


def _package_copy(tmp_path):
    package = Path(__file__).resolve().parents[2] / "src/mcpsh"
    target = tmp_path / "mcpsh"
    for name in ("server", "broker", "observer", "conformance", "policy"):
        (target / name).mkdir(parents=True)
        for path in (package / name).glob("*.py"):
            shutil.copyfile(path, target / name / path.name)
    (target / "catalog").mkdir()
    shutil.copyfile(package / "catalog/schemas.py", target / "catalog/schemas.py")
    return target


def test_source_pin_closure_covers_bounds_policy_and_schemas(tmp_path, monkeypatch):
    from mcpsh.conformance import evidence

    target = _package_copy(tmp_path)
    monkeypatch.setattr(evidence, "__file__", str(target / "conformance/evidence.py"))
    original = evidence.source_pins()
    assert set(original) == evidence.PIN_NAMES
    for relative, pin in (("policy/__init__.py", "server"), ("catalog/schemas.py", "server"),
                          ("broker/bounds.py", "broker"), ("server/conformance.py", "server")):
        path = target / relative
        saved = path.read_bytes()
        path.write_bytes(saved + b"\n# drift\n")
        assert evidence.source_pins()[pin] != original[pin], relative
        path.write_bytes(saved)
    assert evidence.source_pins() == original


@pytest.mark.parametrize("relative", ["broker/bounds.py", "server/conformance.py", "policy/__init__.py"])
def test_missing_producer_module_breaks_closure(tmp_path, monkeypatch, relative):
    from mcpsh.conformance import evidence

    target = _package_copy(tmp_path)
    monkeypatch.setattr(evidence, "__file__", str(target / "conformance/evidence.py"))
    (target / relative).unlink()
    with pytest.raises((ValueError, OSError)):
        evidence.source_pins()
