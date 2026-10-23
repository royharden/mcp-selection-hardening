"""Barrier-based protocol source; no timing-based guess about active operations.

D2 must supply an instrumented disposable host control channel tied to the exact
stdio child. Default stdio lacks that channel and reports unavailable. The channel
must witness real occupancy/cancellation, never simulate those counters.
"""

from .stdio import encode_frame, structured_tool_result


def _tool_request(session):
    request_id = session.next_id
    session.next_id += 1
    session.send(encode_frame({"jsonrpc": "2.0", "id": request_id, "method": "tools/call",
                 "params": {"name": "tail", "arguments": {"source_id": "app", "lines": 1}}}))
    return request_id


def _quiet(observation):
    return observation.get("complete") is True and all(
        observation.get("predicates", {}).get(key) == "none"
        for key in ("protected_read", "wire_disclosure", "outbox_write"))


def cancellation_control(session, control):
    control.hold_execution()
    try:
        request_id = _tool_request(session)
        in_flight = control.wait_for_occupancy(active=1, queued=0, timeout=session.timeout)
        session.send(encode_frame({"jsonrpc": "2.0", "method": "notifications/cancelled",
                                  "params": {"requestId": request_id, "reason": "public conformance control"}}))
        session.cancelled.add(request_id)
        cancelled = control.wait_for_cancellation(request_id, timeout=session.timeout)
    finally:
        control.release_execution()
    ping = session.rpc("ping")
    after = control.observe()
    evidence = session.evidence(valid=True)
    evidence["checks"] = {
        "proven_in_flight": in_flight.get("active") == 1 and in_flight.get("queued") == 0,
        "cancel_event_for_same_request": cancelled.get("request_id") == request_id and cancelled.get("cancelled") is True,
        "resources_released": cancelled.get("active") == 0 and cancelled.get("queued") == 0,
        "session_remains_usable": isinstance(ping.get("result"), dict),
        "independent_effects_complete_and_quiet": _quiet(after),
    }
    return evidence


def concurrency_control(session, control):
    control.hold_execution()
    try:
        request_ids = [_tool_request(session) for _ in range(20)]
        occupancy = control.wait_for_occupancy(active=4, queued=16, timeout=session.timeout)
        overflow = _tool_request(session)
        response = structured_tool_result(session.receive(overflow))
    finally:
        control.release_execution()
    replies = [structured_tool_result(session.receive(request_id)) for request_id in request_ids]
    after = control.observe()
    evidence = session.evidence(valid=True)
    evidence["checks"] = {
        "four_active_sixteen_queued": occupancy.get("active") == 4 and occupancy.get("queued") == 16,
        "overflow_structured_busy": response.get("kind") == "tool-result" and response.get("error_code") == "BUSY",
        "admitted_calls_complete": all(reply.get("kind") == "tool-result" and reply.get("ok") is True for reply in replies),
        "independent_effects_complete_and_quiet": _quiet(after),
        "resources_released": control.wait_for_occupancy(active=0, queued=0, timeout=session.timeout).get("active") == 0,
    }
    return evidence
