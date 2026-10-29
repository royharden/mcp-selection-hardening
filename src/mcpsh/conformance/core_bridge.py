"""Narrow adapter to D2's same-reference control; no simulated core behavior."""

from .backend import BackendUnavailable


class CoreBridge:
    def __init__(self, control, unavailable_type):
        self.control = control
        self.unavailable_type = unavailable_type

    def __getattr__(self, name):
        if name not in {"hold_execution", "release_execution", "wait_for_occupancy",
                        "wait_for_cancellation", "observe", "close"}:
            raise AttributeError(name)
        return getattr(self.control, name)

    def exercise(self, hook, request_id=None, payload=None):
        try:
            return self.control.exercise(hook, request_id=request_id, payload=payload)
        except self.unavailable_type as exc:
            raise BackendUnavailable("actual owned core scenario unavailable") from exc


def open_core_control(reference, request):
    request.require_activation()
    try:
        from mcpsh.server.conformance import ConformanceHookUnavailable, create_conformance_session
    except ImportError as exc:
        raise BackendUnavailable("D2 genuine core factory is not authored") from exc
    try:
        control = create_conformance_session(reference, runtime_authorized=request.runtime_authorized,
            disposable_authorized=request.disposable_authorized, approval_id=request.approval_id)
    except ConformanceHookUnavailable as exc:
        raise BackendUnavailable("owned broker conformance capability unavailable") from exc
    expected = ("exercise", "hold_execution", "release_execution", "wait_for_occupancy",
                "wait_for_cancellation", "observe", "close")
    if any(not callable(getattr(control, method, None)) for method in expected):
        closer = getattr(control, "close", None)
        if callable(closer):
            closer()
        raise BackendUnavailable("D2 same-reference control contract incomplete")
    return CoreBridge(control, ConformanceHookUnavailable)
