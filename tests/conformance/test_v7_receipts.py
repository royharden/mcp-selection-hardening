"""Authored regressions; execution deferred while Dirty Mode is open."""

import copy

import pytest

from mcpsh.conformance.receipt_guard import ReceiptGuard, refusal_checks


def receipt():
    identity = {"server_instance_id": "server", "trial_id": "trial",
                "fixture_payload_sha256": "a" * 64, "child_pid": 123}
    attribution = {**identity, "conformance_session_id": "control", "broker_pid": 456, "broker_epoch": "epoch"}
    observation = {"trial_id": "trial", "epoch": "epoch", "complete": True,
                   "conformance_attribution": attribution}
    return identity, {**identity, "conformance_session_id": "control", "broker_pid": 456,
        "broker_epoch": "epoch", "sequence": 1, "hook": "source-count-cap",
        "before": observation, "after": copy.deepcopy(observation),
        "control_receipt": {"attempts": [{"validation_exception": {"type": "ValueError"}}]},
        "evidence_source": "actual-production-config-component", "evidence_scope": "component-diagnostic",
        "error_code": "CONFIG_INVALID", "observed_state_unchanged": True}


@pytest.mark.parametrize("field,value", [("child_pid", 999), ("trial_id", "old"),
    ("fixture_payload_sha256", "b" * 64), ("sequence", True), ("control_receipt", None)])
def test_wrong_or_missing_receipt_is_rejected(field, value):
    identity, evidence = receipt()
    evidence[field] = value
    with pytest.raises(ValueError):
        ReceiptGuard(identity).accept("source-count-cap", evidence)


def test_duplicate_hook_result_cannot_be_reused():
    identity, evidence = receipt()
    guard = ReceiptGuard(identity)
    guard.accept("source-count-cap", evidence)
    with pytest.raises(ValueError):
        guard.accept("source-count-cap", evidence)


def test_component_cannot_assert_platform_scope():
    _, evidence = receipt()
    evidence["evidence_scope"] = "actual-posix"
    assert refusal_checks("source-count-cap", evidence) is None


def test_handwritten_pass_boolean_is_not_proof():
    assert refusal_checks("binary-content", {"passed": True, "error_code": "BINARY_CONTENT"}) is None


def test_aggregate_single_scan_is_not_read_amplification():
    _, evidence = receipt()
    evidence.update(evidence_source="actual-owned-reference-conformance", error_code="LIMIT_EXCEEDED",
        evidence_scope="actual-owned-broker-budget",
        metrics={"aggregate_read_bytes": 8388608, "read_limit_bytes": 8388608,
                 "completed_scans": 0, "requested_scans": 3, "requested_scan_bytes": 9437184})
    assert not all(refusal_checks("read-amplification", evidence).values())


@pytest.mark.parametrize("field,value", [("nonce", "other"), ("child_pid", 999), ("sequence", 2)])
def test_inherited_reply_cannot_cross_channel_boundary(field, value):
    from mcpsh.conformance.channel import verify_reply

    reply = {"schema_version": 1, "nonce": "own", "child_pid": 123, "sequence": 1,
             "command": "exercise", "payload": {}, "error": None}
    reply[field] = value
    with pytest.raises(ValueError):
        verify_reply(reply, nonce="own", child_pid=123, sequence=1, command="exercise")


def test_changed_fixture_generation_cannot_reuse_session():
    identity, evidence = receipt()
    guard = ReceiptGuard(identity)
    guard.accept("source-count-cap", evidence)
    evidence.update(sequence=2, broker_epoch="new-epoch")
    with pytest.raises(ValueError):
        guard.accept("source-count-cap", evidence)


def test_partial_child_teardown_attempts_remaining_owned_handles():
    from types import SimpleNamespace
    from mcpsh.conformance.stdio import StdioSession

    closed = []

    class Handle:
        def __init__(self, name, fail=False):
            self.name, self.fail = name, fail

        def close(self):
            closed.append(self.name)
            if self.fail:
                raise OSError("injected close failure")

    session = StdioSession.__new__(StdioSession)
    session.closed = False
    session.process = SimpleNamespace(poll=lambda: 0, stdin=Handle("stdin", True), stdout=Handle("stdout"))
    session.control = Handle("control")
    with pytest.raises(OSError):
        session.close()
    assert closed == ["stdin", "stdout", "control"]


def test_lost_reply_poisoning_prevents_late_result_reuse(monkeypatch):
    import queue
    import threading
    from mcpsh.conformance import channel
    from mcpsh.conformance.channel import InheritedControl

    control = InheritedControl.__new__(InheritedControl)
    control.failed, control.sequence, control.child_pid = False, 0, 123
    control.nonce, control.timeout = "own", 0.05
    control.inbox = queue.Queue()
    control.lock = threading.Lock()
    # No process, pipes or background reader is created by this fixture.
    control.to_child_write = 999
    monkeypatch.setattr(channel.os, "write", lambda descriptor, raw: len(raw))
    with pytest.raises((queue.Empty, TimeoutError)):
        control.request("exercise", hook="missing-source")
    assert control.failed is True
    control.inbox.put({"schema_version": 1, "nonce": "own", "child_pid": 123,
        "sequence": 1, "command": "exercise", "payload": {}, "error": None})
    with pytest.raises(ValueError):
        control.request("exercise", hook="missing-source")
