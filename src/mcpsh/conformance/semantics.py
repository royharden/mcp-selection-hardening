"""Fresh public semantic gold; actual handlers supply the measured outcomes."""

import copy
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from .models import CallSpec, Status

CASE_SOURCE_VERSION = "m5-public-semantics-v1"
GRAMMAR_VERSION = "m5-literal-pattern-v1"
PARSER_VERSION = "m5-log-fields-v1"
REQUIRED_CASE_IDS = ("literal-dot", "escaped-reserved", "escaped-backslash", "anchors-alternatives",
    "case-sensitive", "unsupported-repetition", "unsupported-escape", "alternative-cap", "utf8-byte-cap",
    "structured-code-groups", "plain-code-groups", "warning-alias", "timestamp-boundaries",
    "unknown-code-bin", "conflicting-json-fields", "bounded-scan-counts")


@dataclass(frozen=True)
class SemanticCase:
    case_id: str
    kind: str
    lines: tuple[str, ...]
    call: CallSpec
    expected_json: str
    source_sha256: str

    def expected(self):
        return json.loads(self.expected_json)


def public_case_source():
    path = Path(__file__).resolve().parents[3] / "fixtures/conformance/semantics-v1.json"
    if not path.is_file():
        path = Path(__file__).resolve().parent / "data/semantics-v1.json"
    try:
        with path.open("rb") as handle:
            raw = handle.read(128 * 1024 + 1)
    except OSError as exc:
        from .backend import BackendUnavailable

        raise BackendUnavailable("required public conformance case source is not packaged") from exc
    if len(raw) > 128 * 1024:
        raise ValueError("public semantic case-source cap")
    return raw


def semantic_cases(raw: bytes) -> tuple[SemanticCase, ...]:
    """Pure bounded projection; rejects an omitted/extra public required case."""
    from mcpsh.records import strict_json_loads

    if type(raw) is not bytes or len(raw) > 128 * 1024:
        raise ValueError("bounded public case bytes required")
    package = strict_json_loads(raw)
    if type(package) is not dict or set(package) != {"schema_version", "case_source_version", "cases"} or type(package["schema_version"]) is not int or package["schema_version"] != 1 or package["case_source_version"] != CASE_SOURCE_VERSION:
        raise ValueError("public semantic source contract differs")
    entries = package["cases"]
    if type(entries) is not list or len(entries) != len(REQUIRED_CASE_IDS):
        raise ValueError("public semantic case count differs")
    cases = []
    seen = set()
    for entry in entries:
        if type(entry) is not dict or set(entry) != {"id", "kind", "lines", "repeat_lines", "tool", "arguments", "expansions", "expect"}:
            raise ValueError("public semantic case fields differ")
        case_id = entry["id"]
        if type(case_id) is not str or case_id not in REQUIRED_CASE_IDS or case_id in seen or entry["kind"] not in {"matching", "parsing"}:
            raise ValueError("public semantic case identity differs")
        seen.add(case_id)
        lines = entry["lines"]
        if type(lines) is not list or len(lines) > 500 or any(type(line) is not str or any(char in line for char in "\n\r\x00") or len(line.encode("utf-8")) > 4096 for line in lines):
            raise ValueError("invalid public semantic physical lines")
        repeat = entry["repeat_lines"]
        if type(repeat) is not int or not 0 <= repeat <= 500 or (repeat and len(lines) != 1):
            raise ValueError("invalid bounded public line expansion")
        lines = lines * repeat if repeat else lines
        arguments = copy.deepcopy(entry["arguments"])
        if type(arguments) is not dict or arguments.get("source_id") != "app":
            raise ValueError("semantic calls use only the public app source")
        expansions = entry["expansions"]
        if type(expansions) is not dict or set(expansions) - {"pattern"}:
            raise ValueError("unknown argument expansion")
        for key, expansion in expansions.items():
            if type(expansion) is not dict or set(expansion) != {"text", "count"} or type(expansion["text"]) is not str or len(expansion["text"].encode("utf-8")) > 4 or type(expansion["count"]) is not int or not 1 <= expansion["count"] <= 600:
                raise ValueError("invalid bounded argument expansion")
            arguments[key] = expansion["text"] * expansion["count"]
        if entry["tool"] not in {"search", "tail", "error_counts", "errors", "recent_lines"} or type(entry["expect"]) is not dict or set(entry["expect"]) - {"ok", "error_code", "no_io", "matches", "levels", "groups", "coverage"}:
            raise ValueError("unsupported public semantic expectation")
        cases.append(SemanticCase(case_id, entry["kind"], tuple(lines),
            CallSpec(entry["tool"], json.dumps(arguments, ensure_ascii=True, allow_nan=False)),
            json.dumps(entry["expect"], ensure_ascii=True, allow_nan=False), hashlib.sha256(raw).hexdigest()))
    if seen != set(REQUIRED_CASE_IDS):
        raise ValueError("required public case omitted")
    return tuple(cases)


def get_case(case_id):
    return next(case for case in semantic_cases(public_case_source()) if case.case_id == case_id)


def semantic_fixture(case_id):
    from .backend import development_fixture

    case = get_case(case_id)
    fixture = development_fixture()
    fixture["fixture_ref"] = "public-semantic-" + case_id
    fixture["source_lines"]["app"] = list(case.lines)
    return fixture


def _subset(expected, actual):
    if type(expected) is dict:
        return type(actual) is dict and all(key in actual and _subset(value, actual[key]) for key, value in expected.items())
    return type(actual) is type(expected) and actual == expected


def evaluate_semantic(case_id, result, observation):
    case = get_case(case_id)
    expected = case.expected()
    if observation.get("complete") is not True:
        return Status.UNKNOWN, "semantic handler observation incomplete"
    quiet = all(observation.get("predicates", {}).get(key) == "none" for key in ("protected_read", "outbox_write", "wire_disclosure"))
    checks = [quiet, result.get("ok") is expected.get("ok")]
    if "error_code" in expected:
        checks.append((result.get("error") or {}).get("code") == expected["error_code"])
    if expected.get("no_io"):
        checks.append(not any(event.get("kind") == "operation_start" for event in observation.get("events", [])))
    if "matches" in expected:
        checks.append([match.get("line_no") for match in result.get("matches", [])] == expected["matches"])
    if "levels" in expected:
        checks.append([line.get("level") for line in result.get("lines", [])] == expected["levels"])
    if "groups" in expected:
        checks.append({group.get("key"): group.get("count_in_coverage") for group in result.get("groups", [])} == expected["groups"])
    if "coverage" in expected:
        checks.append(_subset(expected["coverage"], result.get("coverage")))
    if result.get("ok") is True:
        checks.append(result.get("data", {}).get("parser_version") == PARSER_VERSION)
        if case.call.tool == "search":
            checks.append(result.get("data", {}).get("pattern_grammar_version") == GRAMMAR_VERSION)
    return (Status.PASS, "public semantic handler and independent receipts agree") if all(checks) else (Status.FAIL, "public semantic handler differs from golden contract")
