"""Barrier-based protocol source; no timing-based guess about active operations.

The inherited fixed-command channel binds the instrumented exact owned stdio child.
Missing or incomplete receipts remain unknown; counters are never simulated.
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


def _same_child_receipt(receipt, control):
    identity = control.identity
    for key in ("child_pid", "server_instance_id", "trial_id", "fixture_id", "fixture_payload_sha256", "platform_scope"):
        if receipt.get(key) != identity.get(key) or identity.get(key) is None:
            raise ValueError("control receipt belongs to another child/fixture")
    if not receipt.get("broker_epoch") or not receipt.get("conformance_session_id"):
        raise ValueError("control receipt lacks core epoch/session")


def cancellation_control(session, control):
    control.hold_execution()
    try:
        request_id = _tool_request(session)
        in_flight = control.wait_for_occupancy(active=1, queued=0, timeout=session.timeout)
        _same_child_receipt(in_flight, control)
        session.send(encode_frame({"jsonrpc": "2.0", "method": "notifications/cancelled",
                                  "params": {"requestId": request_id, "reason": "public conformance control"}}))
        session.cancelled.add(request_id)
        cancelled = control.wait_for_cancellation(request_id, timeout=session.timeout)
        _same_child_receipt(cancelled, control)
        if any(cancelled.get(key) != in_flight.get(key) for key in ("broker_epoch", "conformance_session_id")):
            raise ValueError("cancellation control epoch/session changed")
    finally:
        control.release_execution()
    if in_flight.get("matched") is not True or cancelled.get("cancelled") is not True or cancelled.get("timed_out") is True:
        raise TimeoutError("cancellation receipt incomplete")
    if type(cancelled.get("request_id")) is not type(request_id) or cancelled.get("request_id") != request_id:
        raise ValueError("cancellation belongs to another exact request")
    if not cancelled.get("cancel_frame_sha256") or not cancelled.get("call_id"):
        raise ValueError("cancellation lacks raw-frame/call receipt")
    ping = session.rpc("ping")
    after = control.observe()
    evidence = session.evidence(valid=True)
    evidence["control_receipts"] = {"in_flight": in_flight, "cancelled": cancelled, "after": after}
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
        _same_child_receipt(occupancy, control)
        if occupancy.get("matched") is not True:
            raise TimeoutError("exact occupancy receipt missing")
        overflow = _tool_request(session)
        response = structured_tool_result(session.receive(overflow))
    finally:
        control.release_execution()
    replies = [structured_tool_result(session.receive(request_id)) for request_id in request_ids]
    after = control.observe()
    evidence = session.evidence(valid=True)
    drained = control.wait_for_occupancy(active=0, queued=0, timeout=session.timeout)
    _same_child_receipt(drained, control)
    if any(drained.get(key) != occupancy.get(key) for key in ("broker_epoch", "conformance_session_id")):
        raise ValueError("occupancy core epoch/session changed")
    evidence["control_receipts"] = {"occupancy": occupancy, "drained": drained, "after": after}
    evidence["checks"] = {
        "four_active_sixteen_queued": occupancy.get("active") == 4 and occupancy.get("queued") == 16,
        "overflow_structured_busy": response.get("kind") == "tool-result" and response.get("error_code") == "BUSY",
        "admitted_calls_complete": all(reply.get("kind") == "tool-result" and reply.get("ok") is True for reply in replies),
        "independent_effects_complete_and_quiet": _quiet(after),
        "resources_released": drained.get("matched") is True and drained.get("active") == 0 and drained.get("queued") == 0,
    }
    return evidence
