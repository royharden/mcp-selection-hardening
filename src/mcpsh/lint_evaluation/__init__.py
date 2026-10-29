"""Development-only lint/control evidence returned to the single eval publisher.

No files, providers, fixtures or reports are executed/published by this module.
Counts are target-rule observations, never safety or unseen-family acceptance.
"""

from copy import deepcopy
from hashlib import sha256
import json
from typing import Any

from mcpsh.catalog import CANONICAL_DESCRIPTIONS, validate_catalog
from mcpsh.catalog.spans import enrich_finding
from mcpsh.lint import LIMITS, LINT_VERSION, NORMALIZER_VERSION, lint_catalog, normalize_catalog

EVALUATION_VERSION = "m5-lint-evaluation-1"
MAX_CASES = 4096


def _hash(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False,
                     separators=(",", ":")).encode("utf-8")
    return sha256(raw).hexdigest()


def _ratio(numerator: int, denominator: int) -> dict[str, Any]:
    return {"numerator": numerator, "denominator": denominator,
            "value": numerator / denominator if denominator else None,
            "status": "available" if denominator else "N/A"}


def _counts(rows: list[dict[str, Any]]) -> dict[str, Any]:
    counts = {key: sum(row.get("classification") == key for row in rows)
              for key in ("TP", "FP", "FN", "TN")}
    return {**counts, "scored": sum(counts.values()),
            "precision": _ratio(counts["TP"], counts["TP"] + counts["FP"]),
            "recall": _ratio(counts["TP"], counts["TP"] + counts["FN"])}


def validate_findings(catalog: list[dict[str, Any]], findings: Any) -> list[str]:
    """Verify exact Unicode-codepoint slices; invalid findings become unknown."""
    errors = []
    if not isinstance(catalog, list) or any(not isinstance(tool, dict) for tool in catalog):
        return ["catalog must contain tool objects"]
    if not isinstance(findings, list):
        return ["findings must be a list"]
    for position, finding in enumerate(findings):
        if not isinstance(finding, dict):
            errors.append(f"finding {position}: not an object")
            continue
        index, field, span = (finding.get(key) for key in ("tool_index", "field", "span"))
        if type(index) is not int or not 0 <= index < len(catalog):
            errors.append(f"finding {position}: invalid tool index")
            continue
        if (not isinstance(field, str) or field not in {"name", "description"}
                or not isinstance(span, dict)):
            errors.append(f"finding {position}: invalid field/span")
            continue
        text = catalog[index].get(field)
        if not isinstance(text, str):
            errors.append(f"finding {position}: source field is not text")
            continue
        start, end = span.get("start"), span.get("end")
        if (type(start) is not int or type(end) is not int
                or not 0 <= start < end <= len(text)
                or span.get("unit") != "unicode-codepoint"):
            errors.append(f"finding {position}: invalid codepoint bounds")
        elif finding.get("evidence") != text[start:end]:
            errors.append(f"finding {position}: evidence differs from source slice")
        if not isinstance(finding.get("rule_id"), str) or finding["rule_id"] not in LIMITS:
            errors.append(f"finding {position}: unknown rule")
    return errors


def evaluate_labels(labels: list[dict[str, Any]], *,
                    bypasses: list[dict[str, Any]] | None = None,
                    review: dict[str, dict[str, Any]] | None = None) -> dict[str, Any]:
    """Evaluate public fragments; never silently discard malformed scheduled rows.

    ``review`` maps case_id to {status: confirmed|pending|rejected, rule_id,
    expected_detection, catalog_sha256}. Only a matching confirmed review enters
    reviewed metrics. An unreviewed diagnostic is always visibly provisional.
    Bypass controls are separate diagnostics, never credited as benign TNs.
    """
    bypasses = [] if bypasses is None else bypasses
    review = {} if review is None else review
    if not isinstance(labels, list) or not isinstance(bypasses, list):
        raise ValueError("labels and bypasses must be lists")
    if len(labels) + len(bypasses) > MAX_CASES:
        raise ValueError("too many scheduled controls")
    if not isinstance(review, dict):
        raise ValueError("review must be an object")
    scheduled = [(case, False) for case in labels] + [(case, True) for case in bypasses]
    ids: dict[str, int] = {}
    for case, _ in scheduled:
        if isinstance(case, dict) and isinstance(case.get("case_id"), str):
            ids[case["case_id"]] = ids.get(case["case_id"], 0) + 1
    rows = []
    for ordinal, (case, bypass) in enumerate(scheduled):
        row: dict[str, Any] = {"ordinal": ordinal, "kind": "bypass" if bypass else "label",
                               "status": "unknown", "review_status": "unreviewed"}
        rows.append(row)
        if not isinstance(case, dict):
            row["errors"] = ["case must be an object"]
            continue
        case_id, rule, expected = (case.get(key) for key in
                                  ("case_id", "rule_id", "expected_detection"))
        row.update(case_id=case_id, rule_id=rule)
        if (not isinstance(case_id, str) or not case_id or ids.get(case_id) != 1
                or not isinstance(rule, str) or rule not in LIMITS
                or type(expected) is not bool):
            row["errors"] = ["missing/duplicate case ID, unknown rule or nonboolean label"]
            continue
        catalog = case.get("catalog")
        try:
            catalog_hash = _hash(catalog)
            findings = lint_catalog(catalog)
            errors = validate_findings(catalog, findings)
            if errors:
                row["errors"] = errors
                continue
            findings = [enrich_finding(catalog, finding) for finding in findings]
        except (ValueError, TypeError, KeyError, RecursionError, OverflowError) as exc:
            row["errors"] = [f"invalid catalog: {type(exc).__name__}"]
            continue
        detected = any(finding["rule_id"] == rule for finding in findings)
        names = [tool["name"] for tool in catalog]
        row.update(status="observed", expected_detection=expected, detected=detected,
                   catalog_sha256=catalog_hash, findings=findings,
                   duplicate_tool_identifiers=len(names) != len(set(names)),
                   target_only=True, matches_declared_expectation=detected == expected)
        decision = review.get(case_id, {})
        if isinstance(decision, dict) and decision.get("status") == "confirmed":
            matches = (decision.get("rule_id") == rule
                       and type(decision.get("expected_detection")) is bool
                       and decision["expected_detection"] == expected
                       and decision.get("catalog_sha256") == catalog_hash)
            row["review_status"] = "confirmed" if matches else "stale"
        elif isinstance(decision, dict) and decision.get("status") in {"pending", "rejected"}:
            row["review_status"] = decision["status"]
        if bypass:
            row["diagnostic"] = "detected" if detected else "documented_miss"
        else:
            row["classification"] = ("TP" if detected else "FN") if expected else (
                "FP" if detected else "TN")
            row["diagnostic"] = "positive" if expected else "benign_near_miss"
    # Repeated templates remain scheduled observations, with dependence exposed.
    # Do not silently deduplicate favorable or unfavorable cases.
    repeated: dict[tuple[str, bool, str], int] = {}
    for row in rows:
        if row["status"] == "observed":
            key = (row["rule_id"], row["expected_detection"], row["catalog_sha256"])
            repeated[key] = repeated.get(key, 0) + 1
    for row in rows:
        if row["status"] == "observed":
            key = (row["rule_id"], row["expected_detection"], row["catalog_sha256"])
            row["identical_control_count"] = repeated[key]
    per_rule = {}
    for rule in LIMITS:
        subset = [row for row in rows if row.get("rule_id") == rule]
        label_rows = [row for row in subset if row["kind"] == "label"]
        per_rule[rule] = {
            "scheduled_labels": len(label_rows),
            "unknown_labels": sum(row["status"] == "unknown" for row in label_rows),
            "unreviewed_or_unconfirmed": sum(row["review_status"] != "confirmed"
                                             for row in label_rows),
            "provisional_all_labels": _counts(label_rows),
            "confirmed_labels": _counts([row for row in label_rows
                                         if row["review_status"] == "confirmed"]),
            "bypass_diagnostics": [row for row in subset if row["kind"] == "bypass"],
        }
    return {"version": EVALUATION_VERSION, "lint_version": LINT_VERSION,
            "scope": "public-development-only; publisher must supply execution provenance",
            "scheduled": len(rows), "unknown": sum(row["status"] == "unknown" for row in rows),
            "per_rule": per_rule, "cases": rows,
            "acceptance": "not-evaluated", "published": False}


def evaluate_normalization(catalog: list[dict[str, Any]]) -> dict[str, Any]:
    """Audit metadata-only repair of a complete nine-tool catalog without dispatch.

    The unchanged non-description projection establishes source contract identity;
    it cannot prove runtime functionality. Invalid catalogs are ineligible, never
    silently repaired by dropping tools or replacing executable schemas.
    """
    result: dict[str, Any] = {"version": EVALUATION_VERSION,
                              "normalizer_version": NORMALIZER_VERSION,
                              "status": "ineligible", "runtime_functionality": "unverified"}
    try:
        result["before_sha256"] = _hash(catalog)
        issues = validate_catalog(catalog)
        if issues:
            result["issues"] = issues
            return result
        findings = lint_catalog(catalog)
        errors = validate_findings(catalog, findings)
        if errors:
            result["issues"] = errors
            return result
        findings = [enrich_finding(catalog, finding) for finding in findings]
        before = deepcopy(catalog)
        after, diffs = normalize_catalog(catalog)
        immutable_before = [{k: v for k, v in tool.items() if k != "description"}
                            for tool in before]
        immutable_after = [{k: v for k, v in tool.items() if k != "description"}
                           for tool in after]
        affected = {finding["tool_index"] for finding in findings
                    if finding["field"] == "description"}
        changes = {index for index in range(len(before))
                   if before[index]["description"] != after[index]["description"]}
        unchanged = (_hash(immutable_before) == _hash(immutable_after)
                     and _hash(catalog) == _hash(before))
        trusted = all(after[index]["description"] == CANONICAL_DESCRIPTIONS[
            before[index]["name"]] for index in changes)
        exact_diffs = {item["tool_index"] for item in diffs} == changes
        after_findings = lint_catalog(after)
        after_errors = validate_findings(after, after_findings)
        if not after_errors:
            after_findings = [enrich_finding(after, finding) for finding in after_findings]
        invariants = (unchanged and changes <= affected and trusted and exact_diffs
                      and not after_errors)
        result.update(status="verified-source-invariants" if invariants else "invalid-repair",
                      after_sha256=_hash(after),
                      immutable_before_sha256=_hash(immutable_before),
                      immutable_after_sha256=_hash(immutable_after),
                      trusted_map_sha256=_hash(CANONICAL_DESCRIPTIONS),
                      schema_before_sha256=_hash([tool["inputSchema"] for tool in before]),
                      schema_after_sha256=_hash([tool["inputSchema"] for tool in after]),
                      ids_before=[tool["name"] for tool in before],
                      ids_after=[tool["name"] for tool in after],
                      no_suppression=len(before) == len(after) == 9,
                      input_unmutated=catalog == before, metadata_only=unchanged,
                      before_findings=findings, after_findings=after_findings,
                      after_evidence_errors=after_errors,
                      diffs=diffs, catalog=after)
    except (ValueError, TypeError, KeyError, RecursionError, OverflowError) as exc:
        result["issues"] = [f"invalid normalization input: {type(exc).__name__}"]
    return result
