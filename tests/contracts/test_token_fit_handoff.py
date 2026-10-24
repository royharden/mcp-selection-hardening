"""Authored source regressions, unrun: captured events are never their own authority."""

import json

import pytest

from mcpsh.records import typed_hash
from mcpsh.runner.token_fit_capture import (
    capture_fit_handoff, pinned_fit_expectations, public_fit_status, read_private_provider_journal,
)


def event(phase, *, attempt=None):
    return {"event": "token_fit_proof", "trial_id": "public-trial", "turn_id": 1,
            "proof_sha256": "a" * 64, "phase": phase, "attempt_id": attempt,
            "operation_id": "public-operation" if attempt else None,
            "raw_request_sha256": "b" * 64, "checked_at": "2026-10-23T22:00:00+00:00",
            "proof": {"version": "m5-full-wire-token-fit-1", "status": "unknown",
                      "reasons": ["explicit source-test unavailable counter"],
                      "live_admission": False, "provider_billing_tokens": "unverified",
                      "created_at": "2026-10-23T22:00:00+00:00", "bindings": {},
                      "counter_receipt": None, "input_tokens": None,
                      "proof_sha256": "a" * 64, "scope": "full-wire-input-fit-only"}}


def test_all_proof_events_and_actual_wire_order_survive_without_credit():
    # Catches dropping unmatched/preflight evidence or sorting a real HTTP body away.
    wire = {"z": 1, "a": 2}
    journal = [event("preflight"), {"event": "request", "wire_body": wire,
                "attempt": {"attempt_id": "public-attempt", "operation_id": "public-operation",
                            "raw_request_hash": "b" * 64}},
               event("pre-send", attempt="public-attempt")]
    bundle = capture_fit_handoff(journal)
    assert [item["journal_sequence"] for item in bundle["events"]] == [1, 3]
    assert list(bundle["requests"][0]["wire_body"]) == ["z", "a"]
    assert bundle["expectations"] == []
    status = public_fit_status(attempts_total=3, trials_without_attempts=2, bundle=bundle)
    assert status["attempts_total"] == status["attempts_unknown"] == 3
    assert status["attempts_verified"] == 0
    assert status["expectations_sha256"] is None
    assert status["live_admission"] is status["billing_verified"] is False


def test_expectation_pin_never_defaults_to_its_submitted_hash():
    # Catches treating a producer's hash as independently selected expectation authority.
    with pytest.raises(ValueError, match="external typed authority"):
        pinned_fit_expectations([], expected_typed_sha256=None)
    assert pinned_fit_expectations([], expected_typed_sha256=typed_hash([])) == []


def test_incomplete_journal_rejects_without_returning_a_partial_prefix(tmp_path):
    # Catches publishing a clean-looking prefix after a crash-truncated provider event.
    path = tmp_path / "public-source-test-journal.jsonl"
    raw = (json.dumps(event("preflight")) + "\n" + '{"event":"request"').encode()
    path.write_bytes(raw)
    with pytest.raises(ValueError, match="incomplete"):
        read_private_provider_journal(path)
    assert path.read_bytes() == raw


def test_lineage_status_preserves_failed_unknown_attempt_denominator():
    lineage = {"complete": False, "expectations_sha256": "c" * 64,
               "attempts": [{"state": "verified-fit-only"}, {"state": "unknown"}, {"state": "invalid"}]}
    status = public_fit_status(attempts_total=3, trials_without_attempts=2, lineage=lineage)
    assert (status["attempts_total"], status["attempts_verified"], status["attempts_unknown"]) == (3, 1, 2)
    assert status["status"] == "unknown" and status["complete"] is False
    assert status["trials_without_attempts"] == 2


@pytest.mark.parametrize("total", [2, 4])
def test_caller_count_cannot_shrink_or_pad_lineage_denominator(total):
    # what_bug_this_catches: a caller count hiding unknown attempts or producing a negative unknown count.
    lineage = {"complete": False, "expectations_sha256": None, "trials_without_attempts": [],
               "attempts": [{"state": "verified-fit-only"}, {"state": "unknown"}, {"state": "invalid"}]}
    with pytest.raises(ValueError, match="lineage denominator"):
        public_fit_status(attempts_total=total, trials_without_attempts=0, lineage=lineage)
    with pytest.raises(ValueError, match="verified lineage"):
        public_fit_status(attempts_total=3, trials_without_attempts=1, lineage=lineage)
