"""Versioned v3 frame rule: declared broker-control probes bind a control receipt.

Only probes in the closed BROKER_CONTROL_PROBES table may carry empty frames, and only
when the bound receipt recomputes cleanly. The rule is never inferred from empty frames,
and v1/v2 verification semantics are unchanged.
"""

import json
import re

from .evidence import digest
from .receipt_guard import SCOPES, read_amplification_checks

FRAME_RULE_VERSION = "m5-broker-control-receipt-v1"
FRAME_RULES = frozenset({FRAME_RULE_VERSION})
# Closed, versioned declaration: probe -> tracks whose proof is a broker-control receipt.
BROKER_CONTROL_PROBES = {"read-amplification": frozenset({"synthetic-memory", "filesystem-posix"})}
RULE_CHECKS = {"read-amplification": read_amplification_checks}
RULE_FIELDS = frozenset({"rule", "probe_id", "track", "evidence_scope", "error_code",
                         "receipt", "receipt_sha256", "identity"})
IDENTITY_FIELDS = frozenset({"approval_id", "conformance_session_id", "server_instance_id",
                             "trial_id", "child_pid", "broker_pid", "broker_epoch", "fixture_id",
                             "fixture_payload_sha256", "sequence"})
# The only v1 violations an empty frame list produces; waived solely by a valid binding.
WAIVED_FRAME_VIOLATIONS = frozenset({"frames.missing-or-cap", "frames.response-attribution"})
MAX_RECEIPT_BYTES = 16 * 1024
_APPROVAL = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}")
_HEX = re.compile(r"[a-f0-9]{64}")


def is_broker_control(probe_id, track):
    return track in BROKER_CONTROL_PROBES.get(probe_id, frozenset())


def build_frame_rule(evidence, *, probe_id, track):
    """Bind the actual producer receipt; None when there is nothing to bind."""
    if not is_broker_control(probe_id, track) or not isinstance(evidence, dict):
        return None
    receipt = evidence.get("control_receipt")
    if not isinstance(receipt, dict) or not receipt:
        return None
    return {"rule": FRAME_RULE_VERSION, "probe_id": probe_id, "track": track,
            "evidence_scope": evidence.get("evidence_scope"), "error_code": evidence.get("error_code"),
            "receipt": receipt, "receipt_sha256": digest(receipt),
            "identity": {key: evidence.get(key) for key in IDENTITY_FIELDS}}


def attach_frame_rule(document, binding):
    value = {**document, "frame_rule": binding}
    value["record_sha256"] = digest({key: item for key, item in value.items() if key != "record_sha256"})
    return value


def _text(value, maximum=256):
    return type(value) is str and 0 < len(value.encode("utf-8")) <= maximum and "\x00" not in value


def verify_frame_rule(binding, *, document, expected_probe_id, expected_track,
                      expected_server_instance_id, expected_fixture_payload_sha256):
    """Return rule violations; empty means the receipt may stand in for frames."""
    if type(binding) is not dict or set(binding) != RULE_FIELDS:
        return ["frame-rule.fields"]
    issues = []
    if binding["rule"] not in FRAME_RULES:
        issues.append("frame-rule.version")
    probe_id, track = binding["probe_id"], binding["track"]
    if probe_id != expected_probe_id or track != expected_track or probe_id != document.get("probe_id") or track != document.get("track"):
        issues.append("frame-rule.selection")
    if not is_broker_control(probe_id, track):
        # Model-facing and undeclared probes can never use the rule.
        return sorted(set(issues + ["frame-rule.undeclared-probe"]))
    if document.get("frames") != []:
        issues.append("frame-rule.frames-present")
    receipt = binding["receipt"]
    if type(receipt) is not dict or not receipt:
        return sorted(set(issues + ["frame-rule.receipt-digest"]))
    encoded = json.dumps(receipt, ensure_ascii=True, allow_nan=False, sort_keys=True, separators=(",", ":"))
    if len(encoded) > MAX_RECEIPT_BYTES or digest(receipt) != binding["receipt_sha256"]:
        issues.append("frame-rule.receipt-digest")
    if binding["evidence_scope"] != SCOPES[probe_id]:
        issues.append("frame-rule.scope")
    if binding["error_code"] != receipt.get("probe_error_code"):
        issues.append("frame-rule.error-code")
    try:
        checks = RULE_CHECKS[probe_id](receipt, receipt.get("metrics"), binding["error_code"])
    except (AttributeError, ArithmeticError, TypeError, ValueError):
        # Untrusted receipt content can only fail the rule, never crash verification.
        checks = None
    if checks is None or not all(checks.values()):
        issues.append("frame-rule.receipt-checks")
    # Dispatched to, and applied by, the owned broker for exactly this command.
    if receipt.get("applied") is not True or receipt.get("command") != probe_id:
        issues.append("frame-rule.broker-dispatch")
    identity = binding["identity"]
    if type(identity) is not dict or set(identity) != IDENTITY_FIELDS:
        return sorted(set(issues + ["frame-rule.same-child-binding"]))
    session = document.get("session") if type(document.get("session")) is dict else {}
    observation = document.get("observation") if type(document.get("observation")) is dict else {}
    bound = (type(identity["approval_id"]) is str and _APPROVAL.fullmatch(identity["approval_id"]) is not None
             and _text(identity["conformance_session_id"]) and _text(identity["broker_epoch"])
             and type(identity["broker_pid"]) is int and identity["broker_pid"] > 0
             and type(identity["child_pid"]) is int and identity["child_pid"] > 0
             and type(identity["sequence"]) is int and identity["sequence"] >= 1
             and identity["server_instance_id"] == session.get("server_instance_id") == expected_server_instance_id
             and identity["trial_id"] == session.get("trial_id")
             and identity["fixture_id"] == session.get("fixture_id")
             and type(identity["fixture_payload_sha256"]) is str and _HEX.fullmatch(identity["fixture_payload_sha256"]) is not None
             and identity["fixture_payload_sha256"] == session.get("fixture_payload_sha256") == expected_fixture_payload_sha256
             and session.get("child_pid") in {None, identity["child_pid"]}
             and identity["broker_epoch"] == observation.get("epoch")
             and receipt.get("trial_id") == identity["trial_id"] and receipt.get("epoch") == identity["broker_epoch"])
    if not bound:
        issues.append("frame-rule.same-child-binding")
    return sorted(set(issues))


def observation_complete(document):
    observation = document.get("observation") if type(document.get("observation")) is dict else {}
    predicates = observation.get("predicates") if type(observation.get("predicates")) is dict else {}
    return all(observation.get(key) is True for key in ("complete", "reset_verified", "sequence_complete", "wire_complete")) \
        and bool(predicates) and "unknown" not in predicates.values()
