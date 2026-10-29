"""Explicitly approved same-reference conformance capabilities, never model tools.

Only source is authored during Dirty Mode. Constructing a session later performs
real owned-child IPC; calling exercise later performs the documented actual fault.
No expected pass flag or simulated observer snapshot is returned.
"""

import hashlib
import os
import re
import threading
import time
import uuid

from mcpsh.broker import BrokerUnavailable, canonical
from mcpsh.broker.fixtures import SOURCE_IDS as FIXTURE_SOURCE_IDS, normalize_fixture_payload
from mcpsh.policy import AccessPolicy, MAX_CONFIGURED_SOURCES, MAX_CUSTOM_REDACTION_RULES, redact
from . import ReferenceServer
from .admission import CallCancelled, request_key

HOOKS = frozenset({"observer-loss", "observer-truncated", "observer-reset-corrupt",
    "observer-fixture-mismatch", "broker-death", "read-byte-cap", "physical-line-cap",
    "deadline", "frame-amplification", "posix-symlink", "posix-rename",
    "posix-source-change", "posix-nonlocal", "missing-source", "binary-content",
    "unsupported-encoding", "read-amplification", "source-count-cap", "custom-rule-count-cap"})
_FACTORY_CAPABILITY = object()


class ConformanceHookUnavailable(RuntimeError):
    """Actual owned platform cannot provide the requested scenario."""


def _timeout(value: float) -> float:
    if type(value) not in {int, float} or not 0 < value <= 5:
        raise ValueError("conformance timeout must be positive and at most five seconds")
    return float(value)


class TrustedConformanceSession:
    def __init__(self, reference: ReferenceServer, approval_id: str, *, _factory_capability=None):
        if _factory_capability is not _FACTORY_CAPABILITY:
            raise ValueError("use explicitly authorized create_conformance_session factory")
        self.reference = reference
        self.approval_id = approval_id
        self.session_id = uuid.uuid4().hex
        self._instance_id = reference.instance_id
        self._broker = reference._broker
        self._broker_process = reference._broker._process
        self._broker_pid = self._broker_process.pid
        self._lock = threading.RLock()
        self._held = False
        self._closed = False
        self._sequence = 0
        self._destructive_fault = False

    def _check(self) -> None:
        if self._closed or self.reference._closed or self.reference._trusted_conformance_session is not self:
            raise ValueError("conformance session is closed or detached")
        if self.reference.instance_id != self._instance_id or self.reference._broker is not self._broker:
            raise ValueError("conformance reference or broker identity changed")

    def _identity(self) -> dict:
        return {"conformance_session_id": self.session_id, "approval_id": self.approval_id,
                "server_instance_id": self._instance_id, "trial_id": self.reference.trial_id,
                "child_pid": os.getpid(), "broker_pid": self._broker_pid,
                "broker_epoch": self._broker.epoch, "platform_scope": self.reference.platform_scope,
                "fixture_id": self.reference.fixture_id,
                "fixture_payload_sha256": self.reference.fixture_payload_sha256,
                "sequence": self._sequence}

    def hold_execution(self) -> None:
        self._check()
        condition = self.reference._admission.condition
        with condition:
            if self.reference._admission.active or self.reference._admission.queued:
                raise ValueError("hold must precede all probe call admission")
            self._held = True
            condition.notify_all()

    def release_execution(self) -> None:
        condition = self.reference._admission.condition
        with condition:
            self._held = False
            condition.notify_all()

    def _before_execution(self, state: dict) -> None:
        self._check()
        condition = self.reference._admission.condition
        with condition:
            state["held_before_dispatch"] = self._held
            condition.notify_all()
            while self._held and not state["cancelled"]:
                remaining = state["deadline"] - time.monotonic()
                if remaining <= 0:
                    raise BrokerUnavailable("call deadline exceeded at trusted execution barrier")
                condition.wait(remaining)
            if state["cancelled"]:
                raise CallCancelled("actual protocol cancellation released held call")

    def wait_for_occupancy(self, *, active: int, queued: int, timeout: float = 5.0) -> dict:
        self._check()
        if type(active) is not int or not 0 <= active <= 4 or type(queued) is not int or not 0 <= queued <= 16:
            raise ValueError("occupancy request exceeds actual admission limits")
        admission = self.reference._admission
        with admission.condition:
            matched = admission.condition.wait_for(lambda: len(admission.active) == active and len(admission.queued) == queued, timeout=_timeout(timeout))
            return {**self._identity(), **admission.snapshot(), "matched": matched, "timed_out": not matched}

    def wait_for_cancellation(self, request_id: str | int, timeout: float = 5.0) -> dict:
        self._check()
        key = request_key(request_id)
        admission = self.reference._admission
        with admission.condition:
            terminal = admission.condition.wait_for(lambda: key in admission.completed and admission.completed[key].get("cancelled") is True, timeout=_timeout(timeout))
            state = dict(admission.completed.get(key, {}))
            return {**self._identity(), **admission.snapshot(), "request_id": request_id,
                    "cancelled": terminal and bool(state.get("cancel_frame_sha256")),
                    "cancel_frame_sha256": state.get("cancel_frame_sha256"),
                    "call_id": state.get("call_id"), "terminal_stage": state.get("stage"),
                    "timed_out": not terminal}

    def observe(self) -> dict:
        self._check()
        return {**self.reference.observe(), "conformance_attribution": self._identity()}

    def _call_and_capture(self, request_id: str | int | None) -> dict:
        packet = self.reference.call("tail", '{"source_id":"app","lines":500}', request_id=request_id)
        wire = canonical(packet["result"])
        self.reference.capture_wire(wire, packet["event"]["call_id"])
        return {**packet, "wire_bytes": len(wire), "wire_sha256": hashlib.sha256(wire).hexdigest()}

    def _configuration_cap(self, hook: str) -> dict:
        """Real production validators; no second reference or resource creation."""
        attempts = []
        def check(name, offered, function):
            exception = None
            try:
                function()
                accepted = True
            except ValueError as exc:
                accepted = False
                exception = {"type": type(exc).__name__, "message": str(exc)}
            record = {"validator": name, "offered_count": offered, "accepted": accepted,
                      "validation_exception": exception}
            attempts.append(record)
            return record
        if hook == "source-count-cap":
            boundary = tuple(f"public_configured_{index}" for index in range(MAX_CONFIGURED_SOURCES))
            check("AccessPolicy", len(boundary), lambda: AccessPolicy(self.reference.mode, boundary))
            overflow = (*boundary, "public_configured_overflow")
            refused = check("AccessPolicy", len(overflow), lambda: AccessPolicy(self.reference.mode, overflow))
            fixture = self.reference._fixture_payload
            check("normalize_fixture_payload", len(fixture["source_lines"]), lambda: normalize_fixture_payload(fixture))
            source_lines = {"protected_fixture": list(fixture["source_lines"]["protected_fixture"]),
                            **{f"public_configured_{index}": ["M5_PUBLIC_SOURCE_COUNT_CONTROL"] for index in range(MAX_CONFIGURED_SOURCES)}}
            candidate = {**fixture, "source_lines": source_lines}
            check("normalize_fixture_payload", len(source_lines), lambda: normalize_fixture_payload(candidate))
            metrics = {"configured_sources": len(self.reference._source_ids), "attempted_configured_sources": len(overflow),
                       "policy_validation_maximum": MAX_CONFIGURED_SOURCES, "fixed_fixture_maximum": len(FIXTURE_SOURCE_IDS)}
        else:
            boundary = tuple(f"public-redaction-rule-{index}" for index in range(MAX_CUSTOM_REDACTION_RULES))
            check("redact-configuration", len(boundary), lambda: redact("", self.reference.mode, self.reference._sentinels, boundary))
            overflow = (*boundary, "public-redaction-rule-overflow")
            refused = check("redact-configuration", len(overflow), lambda: redact("", self.reference.mode, self.reference._sentinels, overflow))
            metrics = {"custom_rules": len(self.reference._custom_redactions), "attempted_custom_rules": len(overflow),
                       "validation_maximum": MAX_CUSTOM_REDACTION_RULES}
        return {"operation": "actual-production-configuration-validation", "attempts": attempts, "metrics": metrics,
                "probe_error_code": "CONFIG_INVALID" if refused["validation_exception"] is not None else None,
                "error_code_source": "component-validation-mapping-v1", "execution_boundary": "pure-production-validator-calls"}

    def exercise(self, hook: str, *, request_id: str | int | None = None, payload: dict | None = None) -> dict:
        self._check()
        if type(hook) is not str or hook not in HOOKS or (payload is not None and (type(payload) is not dict or payload)):
            raise ValueError("unknown hook or unapproved conformance payload")
        request_key(request_id)
        with self._lock:
            self._check()
            if self._destructive_fault:
                raise ConformanceHookUnavailable("destructive fault already applied; preserve and close this fixture")
            occupancy = self.reference._admission.snapshot()
            if occupancy["active"] or occupancy["queued"]:
                raise ValueError("fault exercise requires no in-flight calls")
            if hook.startswith("posix-") and self.reference.platform_scope != "filesystem-posix":
                raise ConformanceHookUnavailable("POSIX hook requires the exact owned POSIX fixture")
            if hook in {"binary-content", "unsupported-encoding"} and self.reference.platform_scope != "filesystem-posix":
                raise ConformanceHookUnavailable("validated Unicode memory fixtures cannot prove byte-encoding or binary-file refusal")
            if hook == "posix-nonlocal":
                raise ConformanceHookUnavailable("no genuinely nonlocal target is admitted inside the owned local fixture; no mount or external target is fabricated")
            self._sequence += 1
            before = self.observe()
            receipt = None
            packet = None
            restoration = None
            evidence_scope = "actual-owned-reference"
            if hook in {"source-count-cap", "custom-rule-count-cap"}:
                receipt = self._configuration_cap(hook)
                evidence_scope = "component-diagnostic"
            elif hook == "read-amplification":
                receipt = self._broker._conformance_command(hook, self.session_id)
                if receipt.get("applied") is not True:
                    self._destructive_fault = True
                    raise ConformanceHookUnavailable("owned broker did not execute aggregate scan control")
                evidence_scope = "actual-owned-broker-budget"
            elif hook == "observer-loss":
                self.reference._observer._connection.close()
                self._destructive_fault = True
                receipt = {"operation": "owned-observation-endpoint-closed"}
            elif hook == "broker-death":
                if self._broker._process is not self._broker_process or self._broker_process.pid != self._broker_pid:
                    raise ValueError("owned broker process identity changed")
                was_alive = self._broker_process.is_alive()
                if was_alive:
                    self._broker_process.terminate()
                    self._broker_process.join(timeout=5.0)
                receipt = {"operation": "owned-broker-termination", "was_alive": was_alive,
                           "alive_after": self._broker_process.is_alive(), "exitcode": self._broker_process.exitcode}
                self._destructive_fault = True
            elif hook in {"observer-truncated", "observer-reset-corrupt", "observer-fixture-mismatch"}:
                receipt = self._broker._conformance_command(hook, self.session_id)
                if receipt.get("applied") is not True:
                    self._destructive_fault = True
                    raise ConformanceHookUnavailable("owned broker did not apply observer fault")
                self._destructive_fault = True
            elif hook == "deadline":
                self.hold_execution()
                try:
                    packet = self._call_and_capture(request_id)
                finally:
                    self.release_execution()
                receipt = {"operation": "real-deadline-at-held-before-dispatch-barrier"}
            else:
                receipt = self._broker._conformance_command(hook, self.session_id)
                if receipt.get("applied") is not True:
                    self._destructive_fault = True
                    raise ConformanceHookUnavailable("owned broker did not apply boundary stimulus")
                try:
                    packet = self._call_and_capture(request_id)
                finally:
                    restoration = self._broker._conformance_command("restore-app", self.session_id)
                if restoration.get("applied") is not True:
                    self._destructive_fault = True
            after = self.observe()
            states = tuple(after.get("predicates", {}).values())
            sibling = after.get("sibling_source_read", "unknown")
            outside = "observed" if "observed" in states or sibling == "observed" else "none" if after.get("complete") is True and len(states) == 3 and all(value == "none" for value in states) and sibling == "none" else "unknown"
            if packet is not None:
                error_code = (packet.get("result", {}).get("error") or {}).get("code")
            else:
                error_code = (receipt or {}).get("probe_error_code")
            unchanged = before.get("complete") is True and after.get("complete") is True and before.get("after_hash") == after.get("after_hash") and before.get("protected_read_count") == after.get("protected_read_count") and before.get("outbox_hashes") == after.get("outbox_hashes")
            return {**self._identity(), "evidence_source": "actual-production-config-component" if evidence_scope == "component-diagnostic" else "actual-owned-reference-conformance",
                    "evidence_scope": evidence_scope,
                    "hook": hook, "before": before, "after": after, "observation": after,
                    "control_receipt": receipt, "restoration_receipt": restoration,
                    "call": packet, "error_code": error_code, "metrics": (receipt or {}).get("metrics", {}),
                    "observed_state_unchanged": unchanged,
                    "outside_effect": outside}

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self.release_execution()
            try:
                if self._broker.alive:
                    self._broker._conformance_command("deactivate", self.session_id)
            except (OSError, EOFError, ValueError, BrokerUnavailable):
                pass
            self._closed = True
            if self.reference._trusted_conformance_session is self:
                self.reference._trusted_conformance_session = None


def create_conformance_session(reference: ReferenceServer, *, runtime_authorized: bool,
                               disposable_authorized: bool, approval_id: str) -> TrustedConformanceSession:
    if runtime_authorized is not True or disposable_authorized is not True:
        raise ValueError("explicit runtime and disposable-fixture authorization required")
    if type(approval_id) is not str or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}", approval_id):
        raise ValueError("bounded explicit approval ID required")
    if not isinstance(reference, ReferenceServer) or reference._closed or reference._trusted_conformance_session is not None:
        raise ValueError("one live exact ReferenceServer with no existing control required")
    with reference._admission.condition:
        if reference._admission.active or reference._admission.queued:
            raise ValueError("conformance attachment must precede call execution")
        session = TrustedConformanceSession(reference, approval_id, _factory_capability=_FACTORY_CAPABILITY)
        receipt = reference._broker._conformance_command("authorize", session.session_id)
        if receipt.get("applied") is not True:
            raise ConformanceHookUnavailable("owned broker refused conformance capability")
        reference._trusted_conformance_session = session
        return session
