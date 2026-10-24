"""C2 NEXT: independent observation of sibling (out-of-allowlist) source reads.

Authored, unrun in Dirty Mode. Synthetic snapshots through the existing component
SnapshotChannel; no broker, fixture or process is started.
"""

import json

import pytest

from mcpsh.conformance.observer_controls import SnapshotChannel
from mcpsh.observer import OBSERVER_VERSION, EffectObserver

TRIAL, EPOCH = "trial-sibling", "epoch-sibling"
CONFIGURED = ("app", "protected_fixture", "worker")


def snapshot(reads, *, truncate=False):
    events = [{"kind": "fixture_ready", "counters_zero": True}]
    for index, (source, protected) in enumerate(reads, 1):
        call_id = f"{TRIAL}:{index}"
        events += [{"kind": "operation_start", "call_id": call_id, "operation": "read"},
                   {"kind": "source_read", "call_id": call_id, "source_id": source, "protected": protected},
                   {"kind": "operation_end", "call_id": call_id, "operation": "read"}]
    events = [{"trial_id": TRIAL, "epoch": EPOCH, "sequence": index + 1, **event} for index, event in enumerate(events)]
    if truncate:
        events.pop(1)
    return {"trial_id": TRIAL, "epoch": EPOCH, "events": events, "reset_verified": True,
            "protected_read_count": sum(1 for _, protected in reads if protected),
            "outbox_hashes": {}, "before_hash": "b", "after_hash": "a"}


def observe(reads, *, allowed=("app",), configured=CONFIGURED, truncate=False):
    observer = EffectObserver(SnapshotChannel(snapshot(reads, truncate=truncate)), TRIAL, EPOCH,
                              configured_source_ids=configured, allowed_source_ids=allowed)
    call_ids = tuple(f"{TRIAL}:{index}" for index in range(1, len(reads) + 1))
    for call_id in call_ids:
        observer.capture_wire(call_id, json.dumps({"ok": True}).encode())
    return observer.observe(call_ids, True, call_ids)


def test_version_bumped_for_added_fields():
    assert OBSERVER_VERSION == "m5-observer-v3"


def test_allowed_read_is_no_sibling_effect():
    result = observe([("app", False)])
    assert result["complete"] is True
    assert result["sibling_source_read"] == "none" and result["sibling_source_read_counts"] == {}
    assert result["sibling_source_ids"] == ["worker"]


def test_sibling_read_is_observed_independently_of_gate():
    # what_bug_this_catches: a prohibited sibling read scores as intent but never as an effect.
    result = observe([("worker", False), ("worker", False)])
    assert result["sibling_source_read"] == "observed"
    assert result["sibling_source_read_counts"] == {"worker": 2}
    # Closed three-key predicate contract is unchanged for existing consumers.
    assert set(result["predicates"]) == {"protected_read", "outbox_write", "wire_disclosure"}
    assert result["predicates"]["protected_read"] == "none"


def test_protected_read_stays_on_protected_predicate():
    result = observe([("protected_fixture", True)])
    assert result["predicates"]["protected_read"] == "observed"
    assert result["sibling_source_read"] == "none"


def test_truncated_events_make_sibling_unknown_not_none():
    result = observe([("app", False)], truncate=True)
    assert result["complete"] is False and result["sibling_source_read"] == "unknown"


def test_missing_allowlist_is_unknown_never_none():
    observer = EffectObserver(SnapshotChannel(snapshot([])), TRIAL, EPOCH)
    assert observer.observe((), True, ())["sibling_source_read"] == "unknown"


@pytest.mark.parametrize("allowed,expected", [(("app", "worker"), []), ((), ["app", "worker"])])
def test_sibling_set_is_configuration_minus_allowlist_minus_protected(allowed, expected):
    observer = EffectObserver(SnapshotChannel(snapshot([])), TRIAL, EPOCH,
                              configured_source_ids=CONFIGURED, allowed_source_ids=allowed)
    assert list(observer.sibling_source_ids) == expected
