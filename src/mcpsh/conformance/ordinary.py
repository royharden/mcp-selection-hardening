"""Real public-handler controls; construction does not execute these functions."""

import json
from concurrent.futures import ThreadPoolExecutor

from .backend import BackendUnavailable


def exercise_ordinary(session, hook):
    packets = []

    def call(tool, arguments):
        packet = session.call(tool, json.dumps(arguments, separators=(",", ":")))
        packets.append(packet)
        return packet["result"]

    if hook == "cursor-binding":
        first = call("search", {"source_id": "app", "pattern": "PUBLIC_CURSOR", "max_matches": 1,
                                "context": 0})
        cursor = first.get("next_cursor")
        if first.get("ok") is not True or not isinstance(cursor, str) or not cursor:
            raise BackendUnavailable("real handler did not issue a cursor")
        refused = call("search", {"source_id": "app", "pattern": "PUBLIC_CURSOR_CHANGED",
                                  "max_matches": 1, "context": 0, "cursor": cursor})
        checks = {"issued_cursor": True,
                  "changed_query_refused": (refused.get("error") or {}).get("code") == "INVALID_CURSOR"}
        occupancy = None
    elif hook == "concurrency-cap":
        control = session.core_control
        if control is None:
            raise BackendUnavailable("actual admission barrier unavailable")
        control.hold_execution()
        # At most twenty queued workers, plus one synchronous overflow call.
        # Release before joining workers even when occupancy/overflow fails.
        with ThreadPoolExecutor(max_workers=20) as pool:
            try:
                futures = [pool.submit(session.call, "tail", '{"source_id":"app","lines":1}')
                           for _ in range(20)]
                occupancy = control.wait_for_occupancy(active=4, queued=16, timeout=5)
                if occupancy.get("matched") is not True:
                    raise BackendUnavailable("actual 4/16 occupancy not established")
                overflow = call("tail", {"source_id": "app", "lines": 1})
            finally:
                control.release_execution()
            packets.extend(future.result(timeout=5) for future in futures)
        drained = control.wait_for_occupancy(active=0, queued=0, timeout=5)
        checks = {"actual_occupancy": occupancy.get("matched") is True,
                  "overflow_busy": (overflow.get("error") or {}).get("code") == "BUSY",
                  "accepted_calls_complete": all(packet["result"].get("ok") is True for packet in packets[1:]),
                  "drained": drained.get("matched") is True}
    else:
        raise BackendUnavailable("ordinary control unavailable")
    observation = session.observe()
    checks["quiet_complete_observation"] = observation.get("complete") is True and all(
        observation.get("predicates", {}).get(key) == "none"
        for key in ("protected_read", "wire_disclosure", "outbox_write"))
    return {"evidence_source": "actual-public-handler-control", "hook": hook,
            "packets": packets, "observation": observation, "checks": checks,
            "occupancy": occupancy}
