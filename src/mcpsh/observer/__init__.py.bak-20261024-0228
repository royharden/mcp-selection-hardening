"""Independent broker-state and runner-captured wire observation.

No handler result or gate decision is accepted as evidence of prevented effects.
"""

import hashlib
import json
import threading

from mcpsh.broker import MAX_READ_BYTES, SYNTHETIC_CANARY, canonical

OBSERVER_VERSION = "m5-observer-v2"


class EffectObserver:
    def __init__(self, connection, trial_id: str, epoch: str, platform_scope: str = "synthetic-memory", sentinels: tuple[str, ...] | None = None, fixture_payload_sha256: str | None = None):
        self._connection = connection
        self.trial_id = trial_id
        self.epoch = epoch
        self.platform_scope = platform_scope
        self._sentinels = sentinels if sentinels is not None else (SYNTHETIC_CANARY,)
        self.fixture_payload_sha256 = fixture_payload_sha256
        self._wire: dict[str, dict] = {}
        self._cancellation_wire: dict[str, dict] = {}
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
            def contains_protected(value, depth=0):
                if depth > 32:
                    return False
                if isinstance(value, str):
                    if any(value == sentinel or sentinel in value.splitlines() or (len(sentinel) >= 16 and sentinel in value) for sentinel in self._sentinels):
                        return True
                    # SDK text content can itself be an encoded JSON result.
                    try:
                        nested = json.loads(value)
                    except (ValueError, TypeError, RecursionError):
                        return False
                    return contains_protected(nested, depth + 1) if nested != value else False
                if isinstance(value, list):
                    return any(contains_protected(item, depth + 1) for item in value)
                if isinstance(value, dict):
                    return any(contains_protected(item, depth + 1) for item in value.values())
                return False
            try:
                decoded = json.loads(payload)
                observed = contains_protected(decoded)
            except (ValueError, TypeError, RecursionError):
                self._wire_invalid = True
                observed = any(sentinel.encode("utf-8") in payload for sentinel in self._sentinels)
            self._wire[call_id] = {"call_id": call_id, "sha256": hashlib.sha256(payload).hexdigest(), "bytes": len(payload), "canary_observed": observed}

    def capture_cancellation(self, call_id: str, request_id, payload: bytes) -> None:
        """Actual incoming protocol bytes account for an optional cancelled reply."""
        if type(payload) is not bytes or len(payload) > 32 * 1024:
            raise ValueError("bounded cancellation wire required")
        frame = json.loads(payload)
        value = frame.get("params", {}).get("requestId")
        if frame.get("method") != "notifications/cancelled" or type(value) is not type(request_id) or value != request_id:
            raise ValueError("cancellation provenance mismatch")
        with self._lock:
            self._cancellation_wire[call_id] = {"call_id": call_id, "request_id": request_id,
                "sha256": hashlib.sha256(payload).hexdigest(), "bytes": len(payload)}

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
            wire_complete = not self._wire_invalid and (set(self._wire) | set(self._cancellation_wire)) == set(expected_call_ids)
            fixture_matches = self.fixture_payload_sha256 is None or snapshot.get("fixture_payload_sha256") == self.fixture_payload_sha256
            state_complete = sequence_complete and reset_verified and fixture_matches and snapshot.get("state_complete", True) is True and snapshot.get("trial_id") == self.trial_id and snapshot.get("epoch") == self.epoch
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
                "epoch": self.epoch,
                "fixture_payload_sha256": self.fixture_payload_sha256,
                "platform_scope": self.platform_scope, "complete": complete,
                "predicates": predicates, "protected_read_count": reads,
                "outbox_hashes": outboxes, "before_hash": snapshot.get("before_hash"),
                "after_hash": snapshot.get("after_hash"), "sequence_complete": sequence_complete,
                "wire_complete": wire_complete, "reset_verified": reset_verified,
                "events": events, "wire_observations": list(self._wire.values()),
                "cancellation_observations": list(self._cancellation_wire.values()),
                "failure": failure or snapshot.get("failure"),
            }
