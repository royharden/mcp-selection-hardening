"""Real observer component exercised with explicit synthetic fault-channel inputs.

This is a component control, not an actual broker-kill or filesystem proof. A
healthy real broker snapshot supplies the baseline; faults alter a copy only.
"""

import copy
import json


class SnapshotChannel:
    def __init__(self, snapshot, *, lost=False):
        self.snapshot = snapshot
        self.lost = lost

    def send_bytes(self, payload):
        if self.lost:
            raise OSError("synthetic observer channel loss")
        if json.loads(payload) != {"operation": "snapshot"}:
            raise ValueError("unexpected observer operation")

    def poll(self, timeout):
        return not self.lost

    def recv_bytes(self, maximum):
        raw = json.dumps(self.snapshot, ensure_ascii=True).encode("utf-8")
        if len(raw) > maximum:
            raise OSError("bounded synthetic snapshot exceeds channel cap")
        return raw


def exercise_observer(baseline, hook):
    from mcpsh.observer import EffectObserver

    if baseline.get("complete") is not True or not baseline.get("events"):
        return {"evidence_source": "observer-component-control", "before": baseline, "after": {}}
    event = baseline["events"][0]
    snapshot = {key: copy.deepcopy(baseline[key]) for key in (
        "events", "before_hash", "after_hash", "outbox_hashes", "protected_read_count",
        "reset_verified", "fixture_payload_sha256")}
    snapshot.update(trial_id=event["trial_id"], epoch=event["epoch"], state_complete=True)
    damaged = copy.deepcopy(snapshot)
    if hook == "observer-truncated":
        damaged["events"] = []
    elif hook == "observer-reset-corrupt":
        damaged["reset_verified"] = False
    elif hook == "observer-fixture-mismatch":
        damaged["fixture_payload_sha256"] = "0" * 64
    elif hook != "observer-loss":
        raise ValueError("unknown observer control")
    observer = EffectObserver(SnapshotChannel(damaged, lost=hook == "observer-loss"),
                              event["trial_id"], event["epoch"],
                              fixture_payload_sha256=snapshot["fixture_payload_sha256"])
    observed = observer.observe((), broker_alive=True)
    return {"evidence_source": "observer-component-control", "before": baseline, "after": observed}
