"""Authored component regressions; these are not broker death/runtime evidence."""

import pytest

from mcpsh.conformance.observer_controls import exercise_observer


@pytest.mark.parametrize("hook", ["observer-loss", "observer-truncated", "observer-reset-corrupt", "observer-fixture-mismatch"])
def test_fault_channel_cannot_earn_safe_observation(hook):
    # what_bug_this_catches: damaged isolation/reset/sequence accepted as safe.
    baseline = {"complete": True, "events": [{"sequence": 1, "trial_id": "public-control",
                "epoch": "one", "kind": "fixture_ready", "counters_zero": True}],
                "before_hash": "a", "after_hash": "a", "outbox_hashes": {},
                "protected_read_count": 0, "reset_verified": True,
                "fixture_payload_sha256": "1" * 64}
    result = exercise_observer(baseline, hook)
    assert result["after"]["complete"] is False
    assert result["after"]["predicates"]["protected_read"] == "unknown"
    assert result["after"]["predicates"]["outbox_write"] == "unknown"
