"""Explicit semantic extension to the unchanged closed evidence-v1 contract."""

from .evidence import ROOT_FIELDS, digest, verify_evidence
from .manifest import verify_semantic_manifest

SEMANTIC_FIELDS = frozenset({"manifest_sha256", "manifest_version", "case_source_sha256",
    "grammar_version", "parser_version", "grammar_source_sha256", "parser_source_sha256",
    "case_id", "case_call_sha256", "case_expectation_sha256", "actual_raw_arguments_sha256",
    "handler_result_sha256", "coverage_sha256", "coverage_kind"})


def build_evidence_v2(base, *, manifest, case_id, result, actual_raw_arguments_sha256,
                      actual_case_source_sha256):
    cases = {case["case_id"]: case for case in manifest["cases"]}
    case = cases.get(case_id)
    coverage = result.get("coverage", {}) if type(result) is dict else {}
    if case is None:
        coverage_kind = "not-applicable-control"
    elif result.get("ok") is False:
        coverage_kind = "validation-refusal"
    elif coverage.get("complete") is True and coverage.get("semantic_complete") is True:
        coverage_kind = "parsed"
    else:
        coverage_kind = "unknown"
    semantic = {key: manifest[key] for key in ("manifest_sha256", "manifest_version", "case_source_sha256",
        "grammar_version", "parser_version", "grammar_source_sha256", "parser_source_sha256")}
    semantic["case_source_sha256"] = actual_case_source_sha256
    semantic.update(case_id=case_id, case_call_sha256=case["call_sha256"] if case else None,
        case_expectation_sha256=case["expectation_sha256"] if case else None,
        actual_raw_arguments_sha256=actual_raw_arguments_sha256 if case else None,
        handler_result_sha256=digest(result), coverage_sha256=digest(coverage), coverage_kind=coverage_kind)
    document = {**base, "schema_version": 2, "semantic": semantic}
    document["record_sha256"] = digest({key: value for key, value in document.items() if key != "record_sha256"})
    return document


def verify_evidence_v2(document, *, semantic_manifest, expected_manifest_sha256, **v1_selection):
    issues = []
    if type(document) is not dict or set(document) != ROOT_FIELDS | {"semantic"} or type(document.get("schema_version")) is not int or document["schema_version"] != 2:
        return {"valid": False, "creditable": False, "violations": ["evidence-v2.fields"], "scope": "unknown", "predicates": {}}
    authority = verify_semantic_manifest(semantic_manifest, expected_manifest_sha256=expected_manifest_sha256)
    if not authority["valid"]:
        issues.extend(authority["violations"])
    try:
        semantic = document["semantic"]
        if type(semantic) is not dict or set(semantic) != SEMANTIC_FIELDS:
            raise ValueError("semantic fields differ")
        for key in ("manifest_sha256", "manifest_version", "case_source_sha256", "grammar_version",
                    "parser_version", "grammar_source_sha256", "parser_source_sha256"):
            if semantic[key] != semantic_manifest[key]:
                issues.append("semantic.version-or-pin")
        track = v1_selection["expected_track"]
        probe_id = v1_selection["expected_probe_id"]
        if probe_id not in semantic_manifest["required_probe_ids"].get(track, []):
            issues.append("semantic.required-probe")
        case_id = semantic["case_id"]
        matching_ids = {"semantic-" + case["case_id"]: case["case_id"] for case in semantic_manifest["cases"]}
        matching_ids.update({"semantic-stdio-" + case["case_id"]: case["case_id"] for case in semantic_manifest["cases"]})
        if matching_ids.get(probe_id) != case_id:
            issues.append("semantic.case-attribution")
        cases = {case["case_id"]: case for case in semantic_manifest["cases"]}
        if case_id is not None:
            case = cases[case_id]
            if semantic["case_call_sha256"] != case["call_sha256"] or semantic["case_expectation_sha256"] != case["expectation_sha256"]:
                issues.append("semantic.case-pins")
            if semantic["actual_raw_arguments_sha256"] != case["raw_arguments_sha256"]:
                issues.append("semantic.actual-raw-call")
        elif any(semantic[key] is not None for key in ("case_call_sha256", "case_expectation_sha256", "actual_raw_arguments_sha256")):
            issues.append("semantic.unexpected-case")
        if semantic["coverage_kind"] not in {"parsed", "validation-refusal", "unknown", "not-applicable-control"}:
            issues.append("semantic.coverage-kind")
        if case_id is not None and semantic["coverage_kind"] == "not-applicable-control":
            issues.append("semantic.coverage-suppressed")
        for key in ("handler_result_sha256", "coverage_sha256"):
            value = semantic[key]
            if type(value) is not str or len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
                issues.append("semantic.result-pin")
        unsigned = {key: value for key, value in document.items() if key != "record_sha256"}
        if digest(unsigned) != document["record_sha256"]:
            issues.append("evidence-v2.digest")
        # Validate every v2-only field before translating the closed v1 subset.
        base = {key: value for key, value in document.items() if key != "semantic"}
        base["schema_version"] = 1
        base["record_sha256"] = digest({key: value for key, value in base.items() if key != "record_sha256"})
        result = verify_evidence(base, **v1_selection)
        issues.extend(result["violations"])
        return {**result, "valid": not issues, "creditable": result["creditable"] and not issues and semantic["coverage_kind"] != "unknown",
                "violations": sorted(set(issues))}
    except (ValueError, TypeError, KeyError, UnicodeError, RecursionError):
        return {"valid": False, "creditable": False, "violations": sorted(set(issues + ["semantic.ill-shaped"])), "scope": "unknown", "predicates": {}}
