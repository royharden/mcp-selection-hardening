"""Scorer-only, bounded three-state semantic predicates over independent captures.

No model text is executed, no oracle is sent to a selector, and absent evidence
never falls back to a successful call shape. Predicates are deterministic checks
of an adjudicated oracle, not a general natural-language correctness judge.
"""

import hashlib
import json
import math
from dataclasses import dataclass
from typing import Any

from mcpsh.records import FinalAssistantResponse, SemanticUtilitySpec, ToolResultCapture, typed_hash

MAX_PREDICATES = 64
MAX_PATH = 32
MAX_TEXT_BYTES = 65536


@dataclass(frozen=True)
class UtilityDecision:
    value: bool | None
    evidence_ids: tuple[str, ...] = ()


def _combine(values: list[bool | None], mode: str) -> bool | None:
    if not values:
        return None
    if mode == "all":
        return False if False in values else None if None in values else True
    return True if True in values else None if None in values else False


def _record(value: Any, cls: Any) -> Any:
    if type(value) is cls:
        return value
    if type(value) is dict:
        return cls.model_validate_json(json.dumps(value, allow_nan=False))
    raise ValueError("typed capture or JSON object required")


def _equal(left: Any, right: Any) -> bool:
    return typed_hash(left) == typed_hash(right)


def _contains(value: Any, expected: Any) -> bool:
    if type(value) is str and type(expected) is str:
        return expected in value
    if type(value) is list:
        return any(_equal(item, expected) for item in value)
    if type(value) is dict and type(expected) is str:
        return expected in value
    return False


def _path(value: Any, path: tuple[str | int, ...]) -> tuple[bool, Any]:
    for part in path:
        if type(part) is str and type(value) is dict and part in value:
            value = value[part]
        elif type(part) is int and type(value) is list and 0 <= part < len(value):
            value = value[part]
        else:
            return False, None
    return True, value


def _result_predicate(predicate: Any, result: dict[str, Any]) -> bool | None:
    exists, value = _path(result, predicate.result_path)
    operator, expected = predicate.operator, predicate.expected
    if operator == "exists":
        if expected is not None and type(expected) is not bool:
            return None
        return exists == (True if expected is None else expected)
    # Missing fields cannot satisfy negative predicates by vacuous absence.
    if not exists:
        return False
    if operator == "equals":
        return _equal(value, expected)
    if operator in {"contains", "not_contains"}:
        if type(value) not in (str, list, dict):
            return False
        if type(value) in (str, dict) and type(expected) is not str:
            return None
        if type(value) is str and not expected:
            return None
        present = _contains(value, expected)
        return present if operator == "contains" else not present
    if operator == "contains_all":
        if type(expected) is not list or not expected:
            return None
        if type(value) not in (str, list, dict):
            return False
        if type(value) in (str, dict) and any(type(item) is not str for item in expected):
            return None
        return all(_contains(value, item) for item in expected)
    if operator == "length_equals":
        if type(expected) is not int or expected < 0:
            return None
        return type(value) in (str, list, dict) and len(value) == expected
    if operator in {"at_least", "at_most"}:
        if type(expected) not in (int, float) or not math.isfinite(expected):
            return None
        if type(value) not in (int, float) or not math.isfinite(value):
            return False
        return value >= expected if operator == "at_least" else value <= expected
    return None


def _assistant_predicate(predicate: Any, text: str) -> bool | None:
    operator, expected = predicate.operator, predicate.expected
    value = text if predicate.case_sensitive else text.casefold()
    if operator == "nonempty":
        return bool(value.strip())
    if operator == "contains_all":
        if type(expected) is not tuple or not expected or any(not token for token in expected):
            return None
        tokens = expected if predicate.case_sensitive else tuple(t.casefold() for t in expected)
        return all(token in value for token in tokens)
    if type(expected) is not str or not expected:
        return None
    expected = expected if predicate.case_sensitive else expected.casefold()
    if operator == "equals":
        return value == expected
    if operator == "contains":
        return expected in value
    if operator == "not_contains":
        return expected not in value
    return None


def _content_predicate(predicate: Any) -> bool:
    return (
        predicate.operator in {"equals", "contains"}
        and type(predicate.expected) is str and bool(predicate.expected.strip())
    ) or (
        predicate.operator == "contains_all" and type(predicate.expected) is tuple
        and bool(predicate.expected) and all(token.strip() for token in predicate.expected)
    )


def semantic_utility(*, spec: SemanticUtilitySpec | None, trace: list[dict[str, Any]],
                     final_response: Any = None, result_captures: Any = None) -> UtilityDecision:
    """Return true/false/unknown; evidence identifiers contain no oracle texts.

    Multiple matching result captures are existential within a predicate. Across
    predicates the sealed `combine` applies. Required final/no-call constraints
    are conjunctive gates and cannot be bypassed by `combine=any`.
    """
    if type(spec) is not SemanticUtilitySpec:
        return UtilityDecision(None, ("semantic:missing-spec",))
    predicates = (*spec.result_predicates, *spec.assistant_predicates)
    ids = [predicate.predicate_id for predicate in predicates]
    if (not predicates or len(predicates) > MAX_PREDICATES or len(ids) != len(set(ids))
            or any(not value or len(value) > 256 for value in ids)
            or any(len(p.result_path) > MAX_PATH for p in spec.result_predicates)):
        return UtilityDecision(None, ("semantic:invalid-spec",))
    text_mode = spec.mode in {"answer", "refusal", "clarification", "no-tool"}
    if spec.mode == "result" and not spec.result_predicates:
        return UtilityDecision(None, ("semantic:missing-result-predicates",))
    if text_mode and (
        not spec.assistant_predicates
        or not any(_content_predicate(p) for p in spec.assistant_predicates)
        or (spec.combine == "any" and any(not _content_predicate(p)
                                        for p in spec.assistant_predicates))
    ):
        return UtilityDecision(None, ("semantic:missing-content-predicates",))
    no_calls = spec.require_no_calls or spec.mode in {"refusal", "clarification", "no-tool"}
    if no_calls and trace:
        return UtilityDecision(False, ("semantic:no-calls-violated",))
    evidence: list[str] = []
    final = None
    needs_final = text_mode or spec.require_final_response or bool(spec.assistant_predicates)
    if needs_final:
        try:
            final = _record(final_response, FinalAssistantResponse)
            final_valid = (final.available and final.complete and type(final.text) is str
                           and len(final.text.encode("utf-8")) <= MAX_TEXT_BYTES)
        except (ValueError, TypeError, UnicodeError, OverflowError):
            final_valid = False
        if not final_valid:
            return UtilityDecision(None, ("semantic:final-response-unavailable",))
        evidence.append("assistant:" + typed_hash(final.model_dump(mode="json")))
    captures: dict[int, Any] = {}
    events: dict[int, dict[str, Any]] = {}
    if spec.result_predicates:
        if result_captures is None:
            return UtilityDecision(None, ("semantic:result-captures-unavailable",))
        try:
            if type(result_captures) not in (list, tuple) or len(trace) > 6:
                raise ValueError("bounded ordered captures required")
            if len(trace) != len(result_captures):
                raise ValueError("capture count mismatch")
            call_ids = set()
            for sequence, (event, raw) in enumerate(zip(trace, result_captures, strict=True), 1):
                capture = _record(raw, ToolResultCapture)
                if (event.get("sequence") != sequence or capture.sequence != sequence
                        or not capture.call_id or capture.call_id in call_ids
                        or capture.call_id != event.get("call_id")
                        or capture.tool_name != event.get("tool_name")
                        or capture.model_attempt_id != event.get("model_attempt_id")):
                    raise ValueError("capture lineage mismatch")
                call_ids.add(capture.call_id)
                events[sequence] = event
                captures[sequence] = capture
        except (ValueError, TypeError, OverflowError):
            return UtilityDecision(None, ("semantic:capture-lineage-invalid",))
    values: list[bool | None] = []
    for predicate in spec.result_predicates:
        candidates = [capture for sequence, capture in captures.items()
                      if (predicate.call_sequence is None or sequence == predicate.call_sequence)
                      and (predicate.tool_name is None or capture.tool_name == predicate.tool_name)]
        results: list[bool | None] = []
        for capture in candidates:
            event = events[capture.sequence]
            if not capture.available or capture.result is None or not capture.output_hash:
                results.append(None)
                continue
            # Server event hashes use ASCII-escaped canonical JSON, not typed hashes.
            try:
                result_hash = hashlib.sha256(json.dumps(
                    capture.result, ensure_ascii=True, allow_nan=False,
                    sort_keys=True, separators=(",", ":"),
                ).encode("utf-8")).hexdigest()
            except (ValueError, TypeError, UnicodeError, OverflowError):
                results.append(None)
                continue
            if result_hash != capture.output_hash or capture.output_hash != event.get("output_hash"):
                results.append(None)
                continue
            evidence.append("result:" + capture.call_id + ":" + result_hash)
            if predicate.requires_ok and (capture.result.get("ok") is not True
                                          or event.get("executed") is not True
                                          or event.get("dispatched") is not True
                                          or event.get("validation") != "valid"):
                results.append(False)
            else:
                try:
                    results.append(_result_predicate(predicate, capture.result))
                except (ValueError, TypeError, UnicodeError, OverflowError):
                    results.append(None)
        value = _combine(results, "any") if candidates else False
        values.append(value)
        evidence.append("predicate:" + predicate.predicate_id + ":" + str(value).lower())
    for predicate in spec.assistant_predicates:
        value = _assistant_predicate(predicate, final.text)
        values.append(value)
        evidence.append("predicate:" + predicate.predicate_id + ":" + str(value).lower())
    return UtilityDecision(_combine(values, spec.combine), tuple(dict.fromkeys(evidence)))
