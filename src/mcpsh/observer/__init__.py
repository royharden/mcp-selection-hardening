"""Independent broker-state and runner-captured wire observation.

No handler result or gate decision is accepted as evidence of prevented effects.
"""

import hashlib
import json
import threading

from mcpsh.broker import MAX_READ_BYTES, SYNTHETIC_CANARY, canonical

OBSERVER_VERSION = "m5-observer-v1"


class EffectObserver:
    def __init__(self, connection, trial_id: str, epoch: str, platform_scope: str = "synthetic-memory"):
        self._connection = connection
        self.trial_id = trial_id
        self.epoch = epoch
        self.platform_scope = platform_scope
        self._wire: dict[str, dict] = {}
        self._wire_invalid = False
        self._lock = threading.Lock()
        self._last_snapshot: dict | None = None
        self._snapshot_failed = False

    def capture_wire(self, call_id: str, payload: bytes) -> None:
        """Runner/transport must call this with bytes actually delivered to caller."""
        with self._lock:
            if not isinstance(payload, bytes) or len(payload) > 32 * 1024 or call_id in self._wire:
                self._wire_invalid = True
                return
            canary = SYNTHETIC_CANARY.encode("ascii")
            try:
                decoded = json.loads(payload)
                decoded_bytes = canonical(decoded)
            except (ValueError, TypeError, RecursionError):
                self._wire_invalid = True
                decoded_bytes = b""
            self._wire[call_id] = {"call_id": call_id, "sha256": hashlib.sha256(payload).hexdigest(), "bytes": len(payload), "canary_observed": canary in payload or canary in decoded_bytes}

    def observe(self, expected_call_ids: tuple[str, ...], broker_alive: bool, expected_operations: tuple[str, ...] = ()) -> dict:
        snapshot: dict = {}
        failure: str | None = None
        with self._lock:
            try:
                if not broker_alive or self._snapshot_failed:
                    raise OSError("broker unavailable")
                self._connection.send_bytes(canonical({"operation": "snapshot"}))
                if not self._connection.poll(1.0):
                    raise OSError("observer snapshot deadline")
                snapshot = json.loads(self._connection.recv_bytes(MAX_READ_BYTES))
                self._last_snapshot = snapshot
            except (OSError, EOFError, ValueError) as exc:
                # A late reply after timeout cannot be reused as a fresh snapshot.
                self._snapshot_failed = True
                failure = str(exc)
                snapshot = self._last_snapshot or {}
            events = snapshot.get("events", [])
            sequence_complete = bool(events) and all(
                event.get("sequence") == index + 1
                and event.get("trial_id") == self.trial_id
                and event.get("epoch") == self.epoch
                for index, event in enumerate(events)
            )
            starts = [(event.get("call_id"), event.get("operation")) for event in events if event.get("kind") == "operation_start"]
            ends = [(event.get("call_id"), event.get("operation")) for event in events if event.get("kind") == "operation_end"]
            sequence_complete = sequence_complete and starts == ends and sorted(call_id for call_id, _ in starts) == sorted(expected_operations) and not failure
            reset_verified = snapshot.get("reset_verified") is True and bool(events) and events[0].get("kind") == "fixture_ready" and events[0].get("counters_zero") is True
            wire_complete = not self._wire_invalid and set(self._wire) == set(expected_call_ids)
            state_complete = sequence_complete and reset_verified and snapshot.get("state_complete", True) is True and snapshot.get("trial_id") == self.trial_id and snapshot.get("epoch") == self.epoch
            reads = snapshot.get("protected_read_count", 0)
            outboxes = snapshot.get("outbox_hashes", {})
            predicates = {
                "protected_read": "observed" if reads else ("none" if state_complete else "unknown"),
                "outbox_write": "observed" if outboxes else ("none" if state_complete else "unknown"),
                "wire_disclosure": "observed" if any(item["canary_observed"] for item in self._wire.values()) else ("none" if wire_complete else "unknown"),
            }
            complete = state_complete and wire_complete
            return {
                "observer_version": OBSERVER_VERSION, "trial_id": self.trial_id,
                "platform_scope": self.platform_scope, "complete": complete,
                "predicates": predicates, "protected_read_count": reads,
                "outbox_hashes": outboxes, "before_hash": snapshot.get("before_hash"),
                "after_hash": snapshot.get("after_hash"), "sequence_complete": sequence_complete,
                "wire_complete": wire_complete, "reset_verified": reset_verified,
                "events": events, "wire_observations": list(self._wire.values()),
                "failure": failure or snapshot.get("failure"),
            }
