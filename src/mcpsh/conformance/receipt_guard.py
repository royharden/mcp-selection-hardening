"""Validate trusted receipts within one newly owned session, never across probes."""

import hashlib
import json

TRUSTED_HOOKS = frozenset({"missing-source", "binary-content", "unsupported-encoding",
                         "read-amplification", "source-count-cap", "custom-rule-count-cap"})
COMPONENT_HOOKS = frozenset({"source-count-cap", "custom-rule-count-cap"})
ERRORS = {"missing-source": "SOURCE_MISSING", "binary-content": "BINARY_CONTENT",
          "unsupported-encoding": "UNSUPPORTED_ENCODING", "read-amplification": "LIMIT_EXCEEDED",
          "source-count-cap": "CONFIG_INVALID", "custom-rule-count-cap": "CONFIG_INVALID"}
# Exact producer evidence_scope per hook (server/conformance.py exercise).
SCOPES = {"missing-source": "actual-owned-reference", "binary-content": "actual-owned-reference",
          "unsupported-encoding": "actual-owned-reference", "read-amplification": "actual-owned-broker-budget",
          "source-count-cap": "component-diagnostic", "custom-rule-count-cap": "component-diagnostic"}
# Normative maxima from requirements-v1; deliberately literal so production drift is caught.
READ_LIMIT_BYTES = 8388608
CAP_METRICS = {"source-count-cap": ("AccessPolicy", 100, "configured_sources",
                                    "attempted_configured_sources", "policy_validation_maximum"),
               "custom-rule-count-cap": ("redact-configuration", 32, "custom_rules",
                                         "attempted_custom_rules", "validation_maximum")}


class ReceiptGuard:
    def __init__(self, identity):
        self.identity = dict(identity)
        self.sequence = 0
        self.seen_calls = set()
        self.bound = None

    def accept(self, hook, evidence):
        if not isinstance(evidence, dict) or evidence.get("hook") != hook:
            raise ValueError("missing or wrong hook receipt")
        for key, value in self.identity.items():
            if value is None or evidence.get(key) != value:
                raise ValueError("hook session identity changed: " + key)
        seq = evidence.get("sequence")
        if type(seq) is not int or seq <= self.sequence:
            raise ValueError("duplicate or stale hook sequence")
        bound = tuple(evidence.get(key) for key in ("conformance_session_id", "broker_pid", "broker_epoch"))
        if any(value is None for value in bound) or (self.bound is not None and bound != self.bound):
            raise ValueError("hook broker/session binding changed")
        for name in ("before", "after"):
            observation = evidence.get(name)
            if not isinstance(observation, dict) or observation.get("trial_id") != evidence["trial_id"]:
                raise ValueError("missing same-trial observation")
            if observation.get("epoch") != evidence.get("broker_epoch"):
                raise ValueError("observation epoch differs from producer")
            attribution = observation.get("conformance_attribution", {})
            for key in (*self.identity, "conformance_session_id", "broker_pid", "broker_epoch"):
                if attribution.get(key) != evidence.get(key):
                    raise ValueError("observation belongs to another fixture/control")
        if not isinstance(evidence.get("control_receipt"), dict) or not evidence["control_receipt"]:
            raise ValueError("missing producer control receipt")
        packet = evidence.get("call")
        if packet is not None:
            event = packet.get("event", {})
            call_id = event.get("call_id")
            if not isinstance(call_id, str) or call_id in self.seen_calls:
                raise ValueError("missing or duplicate captured call")
            wire = json.dumps(packet["result"], sort_keys=True, ensure_ascii=True,
                              allow_nan=False, separators=(",", ":")).encode()
            if hashlib.sha256(wire).hexdigest() != packet.get("wire_sha256"):
                raise ValueError("captured result hash differs")
            if not isinstance(event.get("raw_arguments"), str):
                raise ValueError("raw call receipt missing")
            if event.get("trial_id") != evidence["trial_id"] or event.get("server_instance_id") != evidence["server_instance_id"]:
                raise ValueError("captured call belongs to another reference")
            if hashlib.sha256(event["raw_arguments"].encode("utf-8", "surrogatepass")).hexdigest() != event.get("raw_hash"):
                raise ValueError("raw call hash differs")
            self.seen_calls.add(call_id)
        self.bound, self.sequence = bound, seq


def refusal_checks(hook, evidence):
    """No caller-supplied passed flag can replace raw producer evidence."""
    expected_source = "actual-production-config-component" if hook in COMPONENT_HOOKS else "actual-owned-reference-conformance"
    if evidence.get("evidence_source") != expected_source:
        return None
    if not evidence.get("control_receipt") or not evidence.get("before") or not evidence.get("after"):
        return None
    if hook not in SCOPES or evidence.get("evidence_scope") != SCOPES[hook]:
        # A producer receipt from another scope is never relabelled here.
        return None
    if not isinstance(evidence.get("metrics"), dict):
        return None
    if hook in COMPONENT_HOOKS:
        attempts = evidence["control_receipt"].get("attempts")
        if not isinstance(attempts, list) or not attempts:
            return None
        validator, maximum, configured, attempted, reported_maximum = CAP_METRICS[hook]
        metrics = evidence["metrics"]
        if any(type(metrics.get(key)) is not int for key in (configured, attempted, reported_maximum)):
            return None
        boundary = [row for row in attempts if row.get("validator") == validator and row.get("offered_count") == maximum]
        overflow = [row for row in attempts if row.get("validator") == validator and row.get("offered_count") == maximum + 1]
        if len(boundary) != 1 or len(overflow) != 1:
            return None
        return {"actual_validator_refused": evidence.get("error_code") == ERRORS[hook],
                "boundary_accepted": boundary[0].get("accepted") is True and boundary[0].get("validation_exception") is None,
                "overflow_exception": overflow[0].get("accepted") is False and
                    isinstance(overflow[0].get("validation_exception"), dict) and
                    overflow[0]["validation_exception"].get("type") == "ValueError",
                "producer_maximum_normative": metrics[reported_maximum] == maximum,
                "overflow_attempt_counted": metrics[attempted] == maximum + 1,
                "configured_within_maximum": 0 <= metrics[configured] <= maximum,
                "same_reference_unchanged": evidence.get("observed_state_unchanged") is True}
    if hook == "read-amplification":
        metrics = evidence["metrics"]
        keys = ("aggregate_read_bytes", "read_limit_bytes", "completed_scans", "requested_scans",
                "requested_scan_bytes")
        if any(type(metrics.get(key)) is not int for key in keys):
            return None
        return {"aggregate_budget_refused": evidence.get("error_code") == ERRORS[hook],
                "budget_exact": metrics["read_limit_bytes"] == READ_LIMIT_BYTES,
                "bounded_aggregate": 0 <= metrics["aggregate_read_bytes"] <= READ_LIMIT_BYTES,
                "stimulus_exceeds_budget": metrics["requested_scan_bytes"] > READ_LIMIT_BYTES,
                "real_multiple_scans": 1 <= metrics["completed_scans"] < metrics["requested_scans"] == 3,
                # Refusal at exactly the budget boundary, not an earlier deadline/other LIMIT_EXCEEDED.
                "refused_at_budget_boundary": metrics["requested_scan_bytes"] % 3 == 0 and
                    metrics["completed_scans"] == READ_LIMIT_BYTES // (metrics["requested_scan_bytes"] // 3) and
                    metrics["aggregate_read_bytes"] == metrics["completed_scans"] * (metrics["requested_scan_bytes"] // 3),
                "actual_broker_receipt": evidence["control_receipt"].get("applied") is True,
                "aggregate_restored": evidence["control_receipt"].get("restored") is True or
                    (evidence["control_receipt"].get("restoration_receipt") or {}).get("applied") is True,
                "actual_limit_exception": isinstance(evidence["control_receipt"].get("validation_exception"), dict)}
    packet = evidence.get("call")
    restore = evidence.get("restoration_receipt")
    if not isinstance(packet, dict) or not isinstance(restore, dict):
        return None
    return {"actual_call_refused": (packet.get("result", {}).get("error") or {}).get("code") == ERRORS[hook],
            # The refusal must come from the stimulated broker read, not pre-dispatch validation.
            "broker_dispatched": (packet.get("event") or {}).get("dispatched") is True,
            "stimulus_applied": evidence["control_receipt"].get("applied") is True,
            "owned_fixture_restored": restore.get("applied") is True}
