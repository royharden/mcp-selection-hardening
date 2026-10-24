"""Pinned authored diagnostic expectations; never score or create observations."""

from copy import deepcopy
from hashlib import sha256
import json
import re
from typing import Any

from .dev_corpus import CORPUS_VERSION, EPISODES, replay_selector_kwargs

CONTROL_VERSION = "m5-scripted-control-expectations-1"
CONTROL_FIELDS = {"episode_id", "task_id", "role", "conditions", "cells", "script_sha256",
                  "planned_raw_argument_sha256", "expected", "required_evidence", "limitations"}
AXES = {"selection", "intent", "server_dispatch", "effect", "utility", "observer_fault"}
EVIDENCE = {"scripted-provenance-pins", "ordered-selected-journal", "selection-to-server-links",
            "server-validation-policy-events", "independent-observer-reset-sequence",
            "protected-read-counter-observation", "wire-disclosure-observation", "outbox-state-observation",
            "semantic-result-capture-availability", "final-assistant-availability-capture"}
RELATIONS = {"baseline", "extra-prohibited", "late-prohibited", "extra-allowed", "duplicate",
             "malformed-argument-intent", "schema-invalid-argument", "over-cap-selected-batch",
             "malformed-selected-wrappers"}
DISPATCH = {"conditional-policy-by-cell", "argument-validation-before-effect",
            "batch-cap-rejection-before-dispatch", "selection-rejection-before-dispatch",
            "unsupported-before-selector", "no-calls", "allowed-call-processing"}


def _require(value, reason):
    if not value:
        raise ValueError("scripted control contract: " + reason)


def _typed_pin(value):
    return sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False,
                             separators=(",", ":")).encode("utf-8")).hexdigest()


def _pairs(pairs):
    value = {}
    for key, item in pairs:
        _require(key not in value, "duplicate JSON key")
        value[key] = item
    return value


def _nonfinite(_value):
    raise ValueError("scripted control contract: nonfinite JSON")


def _axis_fields(axis, fields):
    _require(isinstance(axis, dict) and set(axis) == fields, "closed expected-axis fields")


def parse_control_expectations(raw: bytes, *, package: dict[str, Any],
                               expected_sha256: str) -> dict[str, Any]:
    """Verify authored-source identity/joins only. No actual evidence is accepted."""
    try:
        _require(isinstance(raw, bytes) and 0 < len(raw) <= 1024 * 1024, "raw byte cap")
        _require(isinstance(expected_sha256, str) and re.fullmatch(r"[0-9a-f]{64}", expected_sha256)
                 and sha256(raw).hexdigest() == expected_sha256, "external sidecar pin")
        admission = package["manifest"]["control_contract"]
        _require(isinstance(admission, dict) and set(admission) == {"path", "version", "raw_sha256", "diagnostic_controls"}
                 and type(admission["diagnostic_controls"]) is int
                 and admission["path"] == "fixtures/dev/control-expectations.json"
                 and admission["version"] == CONTROL_VERSION and admission["raw_sha256"] == expected_sha256,
                 "pinned corpus manifest/control join")
        value = json.loads(raw.decode("utf-8", errors="strict"), object_pairs_hook=_pairs,
                           parse_constant=_nonfinite)
        _require(isinstance(value, dict) and set(value) == {
            "version", "corpus_version", "scope", "expected_only", "episode_source_sha256", "controls", "provenance"
        } and value["version"] == CONTROL_VERSION and value["corpus_version"] == CORPUS_VERSION
                 and value["scope"] == "authored-diagnostic-expectations-only" and value["expected_only"] is True
                 and value["episode_source_sha256"] == package["raw_sha256"][EPISODES], "source-only control scope")
        provenance = value["provenance"]
        _require(isinstance(provenance, dict) and set(provenance) == {"author", "basis", "independent_review", "mode"}
                 and isinstance(provenance["author"], str) and 1 <= len(provenance["author"].encode()) <= 256
                 and provenance["basis"] == "public-source-authored-unexecuted"
                 and provenance["independent_review"] is False and provenance["mode"] == "replay-only",
                 "authored source provenance is not live evidence")
        controls = value["controls"]
        diagnostics = {e["episode_id"]: e for e in package["episodes"] if e["role"] == "diagnostic"}
        _require(isinstance(controls, list) and len(controls) == len(diagnostics)
                 and admission["diagnostic_controls"] == len(controls), "diagnostic-only source coverage")
        seen = set()
        for control in controls:
            _require(isinstance(control, dict) and set(control) == CONTROL_FIELDS, "closed control fields")
            eid = control["episode_id"]
            _require(isinstance(eid, str) and eid in diagnostics and eid not in seen, "diagnostic identity")
            seen.add(eid)
            episode = diagnostics[eid]
            _require(control["role"] == "diagnostic" and control["task_id"] == episode["task_id"]
                     and control["conditions"] == episode["conditions"] and control["cells"] == episode["cells"]
                     and control["script_sha256"] == replay_selector_kwargs(package, eid)["fixture_sha256"]
                     and control["planned_raw_argument_sha256"] == episode["raw_argument_sha256"], "script/design/argument pins")
            expected = control["expected"]
            _require(isinstance(expected, dict) and set(expected) == AXES, "six separate expectation axes")
            selection = expected["selection"]
            _axis_fields(selection, {"authored_relation", "planned_wrapper_count", "preserve_order_multiplicity"})
            _require(selection["authored_relation"] in RELATIONS
                     and type(selection["planned_wrapper_count"]) is int
                     and selection["planned_wrapper_count"] == len(episode["calls"])
                     and selection["preserve_order_multiplicity"] is True, "authored selection relation/count")
            intent = expected["intent"]
            _axis_fields(intent, {"prohibited_intent", "validated_prohibited_attempt"})
            _require(intent["prohibited_intent"] in {None, "expected"}
                     and intent["validated_prohibited_attempt"] in {None, "expected-invalid-arguments", "requires-server-validation"},
                     "intent distinct from validated attempt")
            dispatch = expected["server_dispatch"]
            _axis_fields(dispatch, {"expectation", "policy_block_requires_admitted_denial"})
            _require(dispatch["expectation"] in DISPATCH and dispatch["policy_block_requires_admitted_denial"] is True,
                     "dispatch rejection is not policy denial")
            effect = expected["effect"]
            _axis_fields(effect, {"expected_by_cell", "requires_independent_complete_observer"})
            _require(isinstance(effect["expected_by_cell"], dict)
                     and set(effect["expected_by_cell"]) == set(episode["cells"])
                     and all(v in {None, "synthetic-export-expected", "unknown", "none-expected-only-if-complete"}
                             for v in effect["expected_by_cell"].values())
                     and effect["requires_independent_complete_observer"] is True, "conditional observer-only effect basis")
            utility = expected["utility"]
            _axis_fields(utility, {"expectation", "requires_actual_semantic_v2"})
            _require(utility["expectation"] in {None, "expected-content-mismatch", "expected-unknown-final-incomplete",
                                               "expected-no-valid-result"}
                     and utility["requires_actual_semantic_v2"] is True, "expected utility is not observed utility")
            fault = expected["observer_fault"]
            _axis_fields(fault, {"request", "support", "expected_state", "on_unavailable"})
            _require(fault["request"] == episode["observer_fault_request"]
                     and fault["support"] == ("unsupported-current-runner" if fault["request"] else "not-requested")
                     and fault["expected_state"] == ("unknown" if fault["request"] else None)
                     and fault["on_unavailable"] == "unsupported-no-credit", "no invented fault injection or safe fallback")
            evidence = control["required_evidence"]
            required = EVIDENCE | ({"actual-fault-hook-or-explicit-unsupported"} if fault["request"] else set())
            _require(isinstance(evidence, list) and all(isinstance(v, str) for v in evidence)
                     and len(evidence) == len(set(evidence)) and set(evidence) == required, "required actual evidence sources")
            _require(isinstance(control["limitations"], list) and 1 <= len(control["limitations"]) <= 16
                     and all(isinstance(v, str) and len(v.encode()) <= 1024 for v in control["limitations"]), "bounded source limits")
        _require(seen == set(diagnostics), "all diagnostic controls retained")
        return {"contract": value, "raw_sha256": expected_sha256, "typed_sha256": _typed_pin(value),
                "manifest_sha256": package["manifest_sha256"], "scope": "authored-expected-only"}
    except (TypeError, KeyError, UnicodeError, RecursionError, OverflowError) as exc:
        raise ValueError("scripted control contract: malformed bounded expectation data") from exc


def control_expectation_projection(package: dict[str, Any], controls: dict[str, Any],
                                   episode_id: str) -> dict[str, Any]:
    """Separate namespace; no scores, observed flags or actual-result merging."""
    _require(controls["manifest_sha256"] == package["manifest_sha256"], "control/corpus source snapshot differs")
    _require(controls["raw_sha256"] == package["manifest"]["control_contract"]["raw_sha256"]
             and _typed_pin(controls["contract"]) == controls["typed_sha256"], "control mutated after source preflight")
    matches = [c for c in controls["contract"]["controls"] if c["episode_id"] == episode_id]
    _require(len(matches) == 1 and matches[0]["role"] == "diagnostic", "one diagnostic expectation")
    return {"version": CONTROL_VERSION, "scope": "authored-expected-only", "paired_design": False,
            "live_eligible": False, "expected_control": deepcopy(matches[0]),
            "required_actual_evidence": list(matches[0]["required_evidence"]),
            "control_source_sha256": controls["raw_sha256"], "manifest_sha256": package["manifest_sha256"]}


def diagnostic_control_plan(package: dict[str, Any], controls: dict[str, Any]) -> dict[str, Any]:
    return {"version": CONTROL_VERSION, "scope": "diagnostic-replay-expectations-only",
            "paired_design": False, "live_eligible": False,
            "entries": [control_expectation_projection(package, controls, ep["episode_id"])
                        for ep in package["episodes"] if ep["role"] == "diagnostic"]}
