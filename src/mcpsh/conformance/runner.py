"""Bounded real probe orchestration; missing evidence never becomes success."""

import hashlib
import json

from .backend import BackendUnavailable, UnsupportedTrack, local_backend_factory
from .models import ConformanceReport, ProbeResult, Status
from .probes import definitions
from .evidence import EvidenceContext, build_evidence
from .evidence_v2 import build_evidence_v2, verify_evidence_v2
from .semantics import public_case_source
from .requirements import decode_requirements, requirements_source
from .evidence_v3 import build_evidence_v3, verify_evidence_v3


def _hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=True,
                                     allow_nan=False, separators=(",", ":")).encode()).hexdigest()


def _evaluate(probe, packets, observation):
    if observation.get("complete") is not True:
        return Status.UNKNOWN, "observation incomplete"
    if not packets:
        return Status.UNKNOWN, "no call evidence"
    result = packets[-1].get("result", {})
    if probe.semantic_case_id:
        from .semantics import evaluate_semantic

        return evaluate_semantic(probe.semantic_case_id, result, observation)
    event = packets[-1].get("event", {})
    predicates = observation.get("predicates", {})
    safe = all(predicates.get(key) == "none" for key in ("protected_read", "wire_disclosure", "outbox_write"))
    expectation = probe.expectation
    if expectation == "allowed":
        passed = result.get("ok") is True and bool(result.get("lines")) and safe
    elif expectation == "sources":
        passed = result.get("ok") is True and [item.get("id") for item in result.get("sources", [])] == ["app"] and safe
    elif expectation == "denied":
        passed = (result.get("error") or {}).get("code") == "POLICY_DENIED" and event.get("dispatched") is False and safe
    elif expectation == "invalid":
        passed = event.get("validation") == "invalid" and event.get("dispatched") is False and not any(
            item.get("kind") == "operation_start" for item in observation.get("events", [])) and safe
    elif expectation == "unknown-source":
        passed = (result.get("error") or {}).get("code") == "UNKNOWN_SOURCE" and safe
    elif expectation == "read-positive":
        passed = result.get("ok") is True and predicates.get("protected_read") == "observed" and predicates.get("outbox_write") == "none" and predicates.get("wire_disclosure") == "none"
    elif expectation == "wire-positive":
        passed = result.get("ok") is True and predicates.get("protected_read") == "observed" and predicates.get("wire_disclosure") == "observed" and predicates.get("outbox_write") == "none"
    elif expectation == "export-positive":
        passed = result.get("ok") is True and predicates.get("protected_read") == "observed" and predicates.get("outbox_write") == "observed"
    elif expectation == "redacted":
        text = json.dumps(result, ensure_ascii=True)
        passed = result.get("ok") is True and "conformance-only" not in text and "custom-public-marker" not in text and "[REDACTED]" in text and safe
    elif expectation == "clock":
        lines = result.get("lines", [])
        passed = result.get("ok") is True and len(lines) == 1 and "old-public-line" not in json.dumps(lines) and safe
    elif expectation == "cursor":
        passed = (result.get("error") or {}).get("code") == "INVALID_CURSOR" and safe
    else:
        return Status.UNKNOWN, "expectation has no evaluator"
    return (Status.PASS, "expected call and independent observation agree") if passed else (Status.FAIL, "call/observation differs from required behavior")


def _hook_result(probe, evidence):
    # Hooks must return actual observations, not a precomputed passed boolean.
    if not isinstance(evidence, dict) or not evidence.get("evidence_source"):
        return Status.UNKNOWN, "hook supplied no attributed evidence"
    if probe.expectation == "trusted-refusal":
        from .receipt_guard import refusal_checks

        hook = probe.hook.removeprefix("control-stdio:")
        checks = refusal_checks(hook, evidence)
        if checks is None:
            return Status.UNKNOWN, "trusted producer receipt missing or wrong scope"
        if evidence.get("observation", {}).get("complete") is not True:
            return Status.UNKNOWN, "trusted refusal observation incomplete"
        passed = all(checks.values()) and evidence.get("outside_effect") == "none"
        return (Status.PASS, "trusted refusal receipts agree") if passed else (Status.FAIL, "trusted refusal differs")
    if probe.expectation == "ordinary-control":
        checks = evidence.get("checks", {})
        if evidence.get("evidence_source") != "actual-public-handler-control" or not evidence.get("packets") or not checks:
            return Status.UNKNOWN, "ordinary handler receipts missing"
        if any(type(value) is not bool for value in checks.values()):
            return Status.UNKNOWN, "ordinary control checks malformed"
        return (Status.PASS, "actual handler control agrees") if all(checks.values()) else (Status.FAIL, "handler control differs")
    if probe.expectation == "semantic-stdio":
        if evidence.get("evidence_source") != "actual-local-stdio" or not evidence.get("frames"):
            return Status.UNKNOWN, "actual stdio semantic frames missing"
        from .semantics import evaluate_semantic

        return evaluate_semantic(probe.semantic_case_id, evidence.get("semantic_result", {}), evidence.get("observation", {}))
    if probe.expectation == "stdio-protocol":
        checks = evidence.get("checks", {})
        frames = evidence.get("frames", [])
        if evidence.get("evidence_source") != "actual-local-stdio" or not checks or not frames:
            return Status.UNKNOWN, "actual stdio frames/check evidence missing"
        if any(type(value) is not bool for value in checks.values()):
            return Status.UNKNOWN, "invalid protocol check record"
        passed = all(checks.values()) and all(
            type(frame.get("bytes")) is int and 0 < frame["bytes"] <= 32 * 1024
            and isinstance(frame.get("sha256"), str) and len(frame["sha256"]) == 64
            for frame in frames)
    elif probe.expectation == "observation-unknown":
        before = evidence.get("before", {})
        after = evidence.get("after", {})
        if before.get("complete") is not True:
            return Status.UNKNOWN, "fault control had no healthy baseline"
        passed = after.get("complete") is False and any(
            state == "unknown" for state in after.get("predicates", {}).values())
    elif probe.expectation in {"bounded-refusal", "posix-refusal"}:
        if evidence.get("observation", {}).get("complete") is not True:
            return Status.UNKNOWN, "boundary control lacks complete independent observation"
        from .boundary_controls import SCENARIOS

        code = evidence.get("error_code")
        allowed = SCENARIOS[probe.hook].required_error_codes
        passed = code in allowed and evidence.get("outside_effect") == "none"
    else:
        return Status.UNKNOWN, "unknown hook expectation"
    return (Status.PASS, "attributed boundary evidence agrees") if passed else (Status.FAIL, "boundary control failed")


def run_conformance(request, *, backend_factory=None, expected_semantic_manifest_sha256=None,
                    expected_requirements_manifest_sha256=None):
    """D1 API: ConformanceRequest -> report.to_dict(); activation is always explicit."""
    request.require_activation()
    context = EvidenceContext.from_request(request)
    requirements_raw, inventory = None, None
    try:
        requirements_raw = requirements_source()
        inventory = decode_requirements(requirements_raw)
    except (OSError, ValueError):
        # Missing or invalid normative source never falls back to the registry.
        requirements_raw = None
    suite = definitions()
    known = {probe.probe_id for probe in suite}
    if set(request.probe_ids) - known:
        raise ValueError("unknown probe selection")
    selected = tuple(probe for probe in suite if not request.probe_ids or probe.probe_id in request.probe_ids)
    factory = backend_factory or local_backend_factory
    rows = []
    audit_bindings = {}
    for track in request.tracks:
        for probe in selected:
            if track not in probe.tracks:
                continue
            session = None
            evidence = {}
            observation = {}
            hook_evidence = {}
            handler_result = {}
            actual_raw_arguments_sha256 = None
            try:
                session = factory(request, track, probe)
                if probe.hook:
                    hook_evidence = session.exercise(probe.hook)
                    status, reason = _hook_result(probe, hook_evidence)
                    observation = hook_evidence.get("observation", hook_evidence.get("after", {}))
                    handler_result = hook_evidence.get("semantic_result", {})
                    actual_raw_arguments_sha256 = hook_evidence.get("semantic_raw_arguments_sha256")
                    evidence = {"evidence_sha256": _hash(hook_evidence),
                                "evidence_source": hook_evidence.get("evidence_source", "unspecified")}
                    if probe.expectation in {"trusted-refusal", "ordinary-control", "stdio-protocol"}:
                        evidence["producer_receipt"] = hook_evidence
                else:
                    calls = probe.calls
                    if probe.semantic_case_id:
                        from .semantics import get_case

                        calls = (get_case(probe.semantic_case_id).call,)
                    packets = [session.call(call.tool, call.raw_arguments) for call in calls]
                    observation = session.observe()
                    if packets:
                        handler_result = packets[-1].get("result", {})
                        actual_raw_arguments_sha256 = packets[-1].get("event", {}).get("raw_hash")
                    status, reason = _evaluate(probe, packets, observation)
                    evidence = {"packets_sha256": _hash(packets), "observation_sha256": _hash(observation),
                                "observation_complete": observation.get("complete") is True,
                                "predicates": observation.get("predicates", {})}
                provenance = session.provenance() if callable(getattr(session, "provenance", None)) else {}
                scope = provenance.get("scope", "mock-diagnostic")
                if backend_factory is not None:
                    scope = "mock-diagnostic"
                if hook_evidence.get("evidence_source") == "observer-component-control":
                    scope = "component-diagnostic"
                if hook_evidence.get("evidence_scope") == "component-diagnostic" or probe.hook and probe.hook.startswith("control-stdio:"):
                    scope = "component-diagnostic"
                if probe.probe_id == "input-frame-cap":
                    # This handler test bounds raw arguments. Only the stdio
                    # driver witnesses a complete serialized JSON-RPC frame.
                    scope = "component-diagnostic"
                binding = provenance.get("session", {})
                document = build_evidence(context=context, probe=probe, track=track,
                    session_binding=binding, frames=provenance.get("frames", []),
                    observation=observation, scope=scope, checks=hook_evidence.get("checks"))
                document = build_evidence_v2(document, manifest=context.semantic_manifest,
                    case_id=probe.semantic_case_id, result=handler_result,
                    actual_raw_arguments_sha256=actual_raw_arguments_sha256,
                    actual_case_source_sha256=hashlib.sha256(public_case_source()).hexdigest())
                proof_binding = {"semantic_manifest": context.semantic_manifest,
                    "expected_manifest_sha256": expected_semantic_manifest_sha256,
                    "expected_probe_id": probe.probe_id, "expected_track": track,
                    "expected_request_sha256": context.request_sha256, "expected_source_pins": context.source_pins,
                    "expected_server_instance_id": binding.get("server_instance_id"),
                    "expected_fixture_payload_sha256": binding.get("fixture_payload_sha256")}
                if inventory is not None:
                    document = build_evidence_v3(document, inventory=inventory)
                    from .frame_rule import attach_frame_rule, build_frame_rule, is_broker_control

                    if is_broker_control(probe.probe_id, track) and not document["frames"]:
                        # Declared broker-control probe: bind its actual receipt for v3 frame rule.
                        rule = build_frame_rule(hook_evidence, probe_id=probe.probe_id, track=track)
                        if rule is not None:
                            document = attach_frame_rule(document, rule)
                    verification = verify_evidence_v3(document, requirements_raw=requirements_raw,
                        expected_requirements_manifest_sha256=expected_requirements_manifest_sha256,
                        **proof_binding)
                else:
                    verification = verify_evidence_v2(document, **proof_binding)
                audit_bindings[track + "/" + probe.probe_id] = proof_binding
                if provenance.get("source_pins") != context.source_pins:
                    status, reason = Status.UNKNOWN, "source identity changed during probe"
                    verification = {**verification, "valid": False, "creditable": False,
                                    "violations": sorted(set(verification["violations"] + ["source.changed-during-probe"]))}
                evidence.update(provenance=document, verification=verification)
            except UnsupportedTrack:
                status, reason = Status.UNSUPPORTED, "platform capability unsupported"
                evidence = {}
            except (BackendUnavailable, ImportError):
                status, reason = Status.UNAVAILABLE, "required trusted adapter, fixture or hook unavailable"
                evidence = {}
            except Exception as exc:
                # Exceptions can contain fixture paths or data; report type only.
                status, reason = Status.UNKNOWN, "probe infrastructure: " + type(exc).__name__
                evidence = {"infrastructure_failure": {"stage": "probe", "type": type(exc).__name__}}
            finally:
                if session is not None:
                    try:
                        session.close()
                    except Exception:
                        prior_status = status
                        status = Status.FAIL if prior_status == Status.FAIL else Status.UNKNOWN
                        reason = "fixture teardown incomplete"
                        evidence["teardown"] = {"complete": False, "target": "owned-probe-session"}
                        evidence["teardown"]["prior_status"] = prior_status.value
                        if "verification" in evidence:
                            evidence["verification"]["creditable"] = False
            rows.append(ProbeResult(probe.probe_id, track, status, probe.required, reason, evidence))
    full = set(probe.probe_id for probe in selected) == known and inventory is not None
    if inventory is not None:
        for track in request.tracks:
            normative = {pid for row in inventory.requirements if track in row.tracks for pid in row.probe_ids}
            implemented = {probe.probe_id for probe in selected if track in probe.tracks and probe.required}
            full = full and normative.issubset(implemented)
    return ConformanceReport(tuple(rows), request.tracks,
                             tuple(probe.probe_id for probe in selected),
                             full, request.approval_id, context.semantic_manifest,
                             requirements_raw, expected_requirements_manifest_sha256,
                             audit_bindings, suite)
