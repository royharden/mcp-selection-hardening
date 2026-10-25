"""Real observer output, public synthetic broker snapshots, no held-out data."""

import json
from types import SimpleNamespace

import pytest

from mcpsh.evidence import EvidenceRejected, reader
from mcpsh.evidence.models import RawObservation
from mcpsh.evidence.public_projection import project_public_result
from mcpsh.observer import EffectObserver


class SnapshotConnection:
    def __init__(self, snapshot):
        self.snapshot = snapshot

    def send_bytes(self, request):
        assert json.loads(request) == {"operation": "snapshot"}

    def poll(self, timeout):
        return True

    def recv_bytes(self, maximum):
        return json.dumps(self.snapshot).encode()


def observation():
    common = {"trial_id": "rv2-public-trial", "epoch": "rv2-public-epoch"}
    snapshot = common | {
        "reset_verified": True,
        "state_complete": True,
        "protected_read_count": 0,
        "outbox_hashes": {},
        "events": [
            common | {"sequence": 1, "kind": "fixture_ready", "counters_zero": True},
            common
            | {
                "sequence": 2,
                "kind": "source_read",
                "source_id": "sibling",
                "protected": False,
                "bytes_read": 1,
            },
        ],
    }
    observer = EffectObserver(
        SnapshotConnection(snapshot),
        common["trial_id"],
        common["epoch"],
        configured_source_ids=("app", "sibling", "protected_fixture"),
        allowed_source_ids=("app",),
    )
    return observer.observe((), True)


def test_real_observer_output_is_accepted_without_silently_dropping_fields():
    """what_bug_this_catches: extra=forbid rejecting epoch/cancellation/sibling producer fields."""
    raw = observation()
    assert raw["complete"] is True
    assert raw["sibling_source_read"] == "observed"
    parsed = RawObservation.model_validate_json(json.dumps(raw))
    result = parsed.model_dump(mode="json")
    for field in (
        "epoch",
        "cancellation_observations",
        "sibling_source_read",
        "sibling_source_read_counts",
        "sibling_source_ids",
    ):
        assert result[field] == raw[field]


def test_public_projection_preserves_sibling_effect_without_disclosing_source_ids():
    """what_bug_this_catches: public evidence erasing sibling effects or leaking source identity."""
    public = project_public_result({"rows": [{"observation": observation()}]}).public
    projected = public["rows"][0]["observation"]
    assert projected["sibling_source_read"] == "observed"
    assert "sibling" not in json.dumps(projected.get("sibling_source_ids", []))


@pytest.mark.parametrize(
    "mutation",
    ["count", "hide-effect", "unknown-complete", "unknown-none"],
    ids=["forged-count", "hidden-effect", "unknown-complete", "unknown-none"],
)
def test_reader_rejects_sibling_counts_and_outcome_overclaims(mutation):
    """what_bug_this_catches: a valid hash masking false counts or effect-free outcome claims."""
    raw = observation()
    outcome = SimpleNamespace(effect="observed", observation_complete=True)
    if mutation == "count":
        raw["sibling_source_read_counts"]["sibling"] = 2
    elif mutation == "hide-effect":
        outcome.effect = "none"
    else:
        raw.update(
            sibling_source_read="unknown", sibling_source_read_counts={}, sibling_source_ids=None
        )
        if mutation == "unknown-none":
            outcome.effect = "none"
            outcome.observation_complete = False
    parsed = RawObservation.model_validate_json(json.dumps(raw))
    with pytest.raises(EvidenceRejected):
        reader._validate_sibling_observation(parsed, outcome)


def test_nonempty_cancellation_is_preserved_and_identifiers_aliased():
    """what_bug_this_catches: accepting empty cancellation lists while rejecting actual receipts."""
    raw = observation()
    raw["cancellation_observations"] = [
        {"call_id": "rv2-private-call", "request_id": 17, "sha256": "a" * 64, "bytes": 64}
    ]
    parsed = RawObservation.model_validate_json(json.dumps(raw))
    assert (
        parsed.model_dump(mode="json")["cancellation_observations"]
        == raw["cancellation_observations"]
    )
    public = project_public_result({"rows": [{"observation": raw}]}).public["rows"][0][
        "observation"
    ]
    receipt = public["cancellation_observations"][0]
    assert receipt["sha256"] == "a" * 64
    assert receipt["bytes"] == 64
    assert "rv2-private-call" not in json.dumps(receipt)
    assert receipt["request_id"] != 17
