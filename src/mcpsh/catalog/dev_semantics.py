"""Finite source-contract diagnostics, not a handler, parser, scorer or runner.

Paths/types/caps describe the inspected public success envelope. Supported means
structurally representable; expected values and actual captures stay unverified.
"""

import math
import re
from typing import Any

from .schemas import TOOL_SCHEMAS

PREFLIGHT_VERSION = "m5-dev-semantic-preflight-1"


def _array(item, maximum):
    return {"array": item, "maximum": maximum}


LINE = {"line_no": "integer", "byte_offset": "integer", "timestamp": ("string", "null"),
        "level": ("string", "null"), "timestamp_inherited": "boolean", "level_inherited": "boolean",
        "text": "string", "context": "boolean", "omitted": "null"}
SOURCE = {"id": "string", "display_path": "string", "readable": "boolean"}
MATCH = {"line_no": "integer"}
ERROR_GROUP = {"signature": "string", "level": "string", "first_in_coverage": LINE,
               "occurrence_count_in_coverage": "integer", "trace": _array("unknown", 0)}
COUNT_GROUP = {"key": "string", "count_in_coverage": "integer"}
COVERAGE = {"first_line": ("integer", "null"), "last_line": ("integer", "null"),
            "bytes_read": "integer", "total_lines": "integer", "complete": "boolean",
            "window_lines": "integer", "excluded_untimestamped": "integer", "scope": "string",
            "platform_scope": "string", "semantic_complete": "boolean", "counts_scope": "string",
            "parsing": {"version": "string", "format_counts": "object-unknown",
                        "unclassified_level_lines": "integer", "untimestamped_lines": "integer",
                        "unsupported_field_lines": "integer", "unclassified_code_error_lines": "integer"}}


def _envelope(tool, arguments=None):
    arguments = arguments or {}
    def bound(name, maximum, fallback=None):
        default = TOOL_SCHEMAS[tool]["properties"].get(name, {}).get("default", fallback)
        value = arguments.get(name, default)
        return min(maximum, value) if type(value) is int and value >= 0 else maximum
    groups = _array(COUNT_GROUP if tool == "error_counts" else ERROR_GROUP,
                    bound("max_groups", 100) if tool == "error_counts" else 100 if tool == "errors" else 0)
    line_cap = 0 if tool == "error_counts" else 100 if tool in {"errors", "find_literal"} else 500
    if tool == "tail":
        line_cap = bound("lines", 500)
    elif tool == "recent_lines":
        line_cap = bound("max_lines", 500)
    elif tool == "find_literal":
        line_cap = bound("max_matches", 100)
    elif tool == "search":
        line_cap = min(500, bound("max_matches", 100) * (1 + 2 * bound("context", 5)))
    elif tool == "read_range" and all(type(arguments.get(k)) is int for k in ("start_line", "end_line")):
        line_cap = max(0, min(500, arguments["end_line"] - arguments["start_line"] + 1))
    cursor = ("string", "null") if tool in {"search", "errors"} else "null"
    data = {"lines": _array(LINE, line_cap),
            "matches": _array(MATCH, bound("max_matches", 100) if tool in {"search", "find_literal"} else 0), "groups": groups,
            "next_cursor": cursor, "parser_version": "string"}
    if tool == "search":
        data["pattern_grammar_version"] = "string"
    if tool == "list_sources":
        data = {"sources": _array(SOURCE, 100)}
    if tool == "export_fixture":
        return None  # Broker effect output is not a legitimate positive dev utility contract.
    return {"schema_version": "integer", "ok": "boolean", "source_id": ("string", "null"),
            "generation_id": ("string", "null"), "content_trust": "string", "data": data,
            "lines": data.get("lines", _array(LINE, 0)),
            "matches": data.get("matches", _array(MATCH, 0)), "groups": data.get("groups", _array(ERROR_GROUP, 0)),
            "sources": data.get("sources", _array(SOURCE, 0)),
            "coverage": {"bytes_read": "integer", "complete": "boolean"} if tool == "list_sources" else COVERAGE,
            "truncated": "boolean", "truncation": {"output_lines": "boolean", "output_bytes": "boolean",
                                                     "input_window": "boolean", "oversize_line": "boolean"},
            "next_cursor": cursor if tool != "list_sources" else "null",
            "warnings": _array("string", 0), "hint": "string", "error": "null"}


def _resolve(node, path):
    for part in path:
        if isinstance(node, dict) and "array" in node:
            if type(part) is not int or not 0 <= part < node["maximum"]:
                return None
            node = node["array"]
        elif isinstance(node, dict) and type(part) is str and part in node:
            node = node[part]
        else:
            return None
    return node


def _compatible(node, value):
    if isinstance(node, tuple):
        return any(_compatible(kind, value) for kind in node)
    if isinstance(node, dict):
        if "array" in node:
            return (isinstance(value, list) and len(value) <= node["maximum"]
                    and all(_compatible(node["array"], item) for item in value))
        return (isinstance(value, dict) and set(value) == set(node)
                and all(_compatible(node[key], item) for key, item in value.items()))
    return {"integer": type(value) is int, "string": type(value) is str,
            "boolean": type(value) is bool, "null": value is None}.get(node, False)


def _operator_supported(node, operator, expected):
    if operator == "exists":
        return expected is None or type(expected) is bool
    if operator == "equals":
        return _compatible(node, expected)
    if operator == "length_equals":
        return (type(expected) is int and expected >= 0
                and (node == "string" or isinstance(node, dict))
                and (not isinstance(node, dict) or "array" not in node or expected <= node["maximum"]))
    if operator in {"at_least", "at_most"}:
        return node == "integer" and type(expected) in {int, float} and math.isfinite(expected)
    values = expected if operator == "contains_all" else [expected]
    if operator not in {"contains", "contains_all", "not_contains"} or not isinstance(values, list) or not values:
        return False
    if node == "string":
        return all(type(value) is str and bool(value) for value in values)
    if isinstance(node, dict) and "array" in node:
        return all(_compatible(node["array"], value) for value in values)
    if isinstance(node, dict):
        return all(type(value) is str and value in node for value in values)
    return False


def _argument_shape(value, schema):
    """Use canonical argument schema DATA; do not invoke server argument parsing."""
    if "anyOf" in schema:
        return any(_argument_shape(value, item) for item in schema["anyOf"])
    kind = schema.get("type")
    if kind == "object":
        properties = schema.get("properties", {})
        return (isinstance(value, dict) and set(schema.get("required", [])) <= set(value)
                and (schema.get("additionalProperties") is not False or set(value) <= set(properties))
                and all(key not in properties or _argument_shape(item, properties[key]) for key, item in value.items()))
    if kind == "integer":
        return (type(value) is int and schema.get("minimum", -math.inf) <= value
                <= schema.get("maximum", math.inf))
    if kind == "null":
        return value is None
    if kind == "string":
        if type(value) is not str or not schema.get("minLength", 0) <= len(value) <= schema.get("maxLength", 65536):
            return False
        value.encode("utf-8", errors="strict")
        if "enum" in schema and value not in schema["enum"]:
            return False
        if "pattern" in schema and re.search(schema["pattern"], value) is None:
            return False
        return True
    return False


def semantic_corpus_preflight(package: dict[str, Any]) -> dict[str, Any]:
    """Return bounded source diagnostics without evaluating a predicate or result."""
    diagnostics, uncertain = [], []
    def issue(task_id, code, predicate_id=None):
        diagnostics.append({"task_id": task_id, "code": code, "predicate_id": predicate_id})
    try:
        tasks = {t["public"]["task_id"]: t for t in package["tasks"]}
        fixtures = {f["fixture_ref"]: f for f in package["fixtures"]}
        pairs = package["oracle_package"]["cases"]
        if len(pairs) != 36:
            raise ValueError("all36 semantic source cases required")
        for pair in pairs:
            public, oracle = pair["public"], pair["oracle"]
            tid, spec = public["task_id"], oracle["utility_spec"]
            if public != tasks[tid]["public"] or fixtures[public["fixture_ref"]]["allowed_source_ids"] != public["allowed_source_ids"]:
                issue(tid, "fixture-public-policy-join")
            alternatives = oracle["alternatives"]
            tools = set()
            for alternative in alternatives:
                for call in alternative:
                    tool, args = call["tool_name"], call["arguments"]
                    tools.add(tool)
                    if tool not in TOOL_SCHEMAS or not _argument_shape(args, TOOL_SCHEMAS[tool]):
                        issue(tid, "canonical-argument-shape")
                        continue
                    if tool in oracle["prohibited_tools"] or args.get("source_id") in oracle["prohibited_source_ids"]:
                        issue(tid, "forbidden-positive-selection")
                    if "source_id" in args and args["source_id"] not in public["allowed_source_ids"]:
                        issue(tid, "selection-source-policy")
                    if tool == "read_range" and (args["end_line"] < args["start_line"] or args["end_line"] - args["start_line"] >= 500):
                        issue(tid, "semantic-range-cap")
                    for key in ("needle", "pattern"):
                        if key in args and len(args[key].encode("utf-8")) > 512:
                            issue(tid, "utf8-argument-cap")
                    if tool == "search" and re.fullmatch(r"[A-Za-z0-9 _:-]+", args["pattern"]) is None:
                        # The inspected grammar guarantees ordinary nonempty literals.
                        # Do not implement/execute another grammar for complex syntax.
                        uncertain.append({"task_id": tid, "fact": "nontrivial-pattern-needs-canonical-parser-activation"})
            mode = spec["mode"]
            positive = [p for p in spec["assistant_predicates"] if (
                p["operator"] in {"equals", "contains"} and type(p["expected"]) is str and bool(p["expected"].strip()))
                or (p["operator"] == "contains_all" and isinstance(p["expected"], list)
                    and bool(p["expected"]) and all(type(v) is str and bool(v.strip()) for v in p["expected"]))]
            if mode in {"answer", "refusal", "clarification", "no-tool"} and (
                not spec["require_final_response"] or not positive
                or (spec["combine"] == "any" and len(positive) != len(spec["assistant_predicates"]))):
                issue(tid, "missing-positive-final-content-gate")
            if mode in {"refusal", "clarification", "no-tool"} and not spec["require_no_calls"]:
                issue(tid, "missing-no-call-gate")
            if mode == "result" and not spec["result_predicates"]:
                issue(tid, "call-only-result-proxy")
            for predicate in spec["result_predicates"]:
                pid, tool, sequence = predicate["predicate_id"], predicate["tool_name"], predicate["call_sequence"]
                candidates = {tool} if tool is not None else tools
                if not candidates or not candidates <= tools or predicate["requires_ok"] is not True:
                    issue(tid, "result-selection-join", pid)
                    continue
                if sequence is not None and (type(sequence) is not int or sequence < 1 or any(
                    sequence > len(alt) or (tool is not None and alt[sequence-1]["tool_name"] != tool) for alt in alternatives)):
                    issue(tid, "result-call-sequence-join", pid)
                path = predicate["result_path"]
                if not isinstance(path, list) or len(path) > 32:
                    issue(tid, "result-path-bounds", pid)
                    continue
                for candidate in candidates:
                    matching = [call["arguments"] for alt in alternatives for index, call in enumerate(alt, 1)
                                if call["tool_name"] == candidate and (sequence is None or sequence == index)]
                    nodes = [_resolve(_envelope(candidate, arguments), path) for arguments in matching]
                    if not any(node is not None for node in nodes):
                        issue(tid, "unsupported-result-path-or-index", pid)
                    elif not any(node is not None and _operator_supported(node, predicate["operator"], predicate["expected"])
                                 for node in nodes):
                        issue(tid, "operator-expectation-type-or-cap", pid)
        return {"version": PREFLIGHT_VERSION,
                "status": "unsupported" if diagnostics else "unverified" if uncertain else "structurally-supported",
                "scope": "finite-source-contract-only", "diagnostics": diagnostics,
                "unverified_source_facts": uncertain,
                "runtime_facts": ["actual returned content", "capture/observer completeness", "semantic outcome truth"],
                "executes_handlers": False, "evaluates_utility": False, "runtime_verified": False}
    except (ValueError, TypeError, KeyError, UnicodeError, RecursionError, OverflowError):
        return {"version": PREFLIGHT_VERSION, "status": "unsupported", "scope": "finite-source-contract-only",
                "diagnostics": [{"code": "malformed-semantic-source-structure"}],
                "unverified_source_facts": [], "runtime_verified": False,
                "executes_handlers": False, "evaluates_utility": False}
