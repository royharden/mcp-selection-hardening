"""Actual bounded call admission and cancellation; condition waits, no sleeps."""

import threading
import time


class CallCancelled(RuntimeError):
    pass


class AdmissionRefused(RuntimeError):
    pass


def request_key(value) -> tuple[type, object]:
    if value is not None and type(value) not in {str, int}:
        raise ValueError("JSON-RPC request ID must be string or integer")
    if isinstance(value, str) and (not value or len(value) > 128):
        raise ValueError("bounded nonempty request ID required")
    return type(value), value


class CallAdmission:
    def __init__(self):
        self.condition = threading.Condition(threading.RLock())
        self.active: dict[str, dict] = {}
        self.queued: dict[str, dict] = {}
        self.completed: dict[tuple[type, object], dict] = {}
        self.closed = False

    def enter(self, call_id: str, request_id, deadline: float) -> dict:
        key = request_key(request_id)
        with self.condition:
            if self.closed:
                raise AdmissionRefused("server admission closed")
            if request_id is not None and any(request_key(state["request_id"]) == key for state in (*self.active.values(), *self.queued.values())):
                raise AdmissionRefused("duplicate in-flight request ID")
            if len(self.queued) >= 16:
                raise AdmissionRefused("four active and sixteen queued calls already admitted")
            if request_id is not None:
                self.completed.pop(key, None)
            state = {"call_id": call_id, "request_id": request_id, "deadline": deadline,
                     "cancelled": False, "cancel_frame_sha256": None, "stage": "queued"}
            self.queued[call_id] = state
            self.condition.notify_all()
            while len(self.active) >= 4 or next(iter(self.queued), None) != call_id:
                if state["cancelled"]:
                    self._finish(state)
                    raise CallCancelled("queued call cancelled before execution")
                remaining = deadline - time.monotonic()
                if remaining <= 0 or self.closed:
                    self._finish(state)
                    raise AdmissionRefused("call queue deadline exceeded")
                self.condition.wait(remaining)
            if state["cancelled"]:
                self._finish(state)
                raise CallCancelled("call cancelled before execution")
            if time.monotonic() >= deadline:
                self._finish(state)
                raise AdmissionRefused("call admission deadline exceeded")
            self.queued.pop(call_id)
            state["stage"] = "active"
            self.active[call_id] = state
            self.condition.notify_all()
            return state

    def _finish(self, state: dict) -> None:
        self.active.pop(state["call_id"], None)
        self.queued.pop(state["call_id"], None)
        state["stage"] = "cancelled" if state["cancelled"] else "completed"
        if state["request_id"] is not None:
            self.completed[request_key(state["request_id"])] = dict(state)
            while len(self.completed) > 128:
                self.completed.pop(next(iter(self.completed)))
        self.condition.notify_all()

    def release(self, call_id: str) -> None:
        with self.condition:
            state = self.active.get(call_id) or self.queued.get(call_id)
            if state is not None:
                self._finish(state)

    def cancel(self, request_id, frame_hash: str) -> dict | None:
        key = request_key(request_id)
        with self.condition:
            for state in (*self.active.values(), *self.queued.values()):
                if request_key(state["request_id"]) == key:
                    state["cancelled"] = True
                    state["cancel_frame_sha256"] = frame_hash
                    self.condition.notify_all()
                    return dict(state)
            return None

    def snapshot(self) -> dict:
        with self.condition:
            return {"active": len(self.active), "queued": len(self.queued),
                    "active_calls": [{"call_id": value["call_id"], "request_id": value["request_id"]} for value in self.active.values()],
                    "queued_calls": [{"call_id": value["call_id"], "request_id": value["request_id"]} for value in self.queued.values()]}

    def close(self) -> None:
        with self.condition:
            self.closed = True
            for state in (*self.active.values(), *self.queued.values()):
                state["cancelled"] = True
            self.condition.notify_all()
