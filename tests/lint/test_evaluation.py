"""Public, synthetic regressions; authored in Dirty Mode and not executed."""

from copy import deepcopy

from mcpsh.lint_evaluation import evaluate_labels, validate_findings


def fragment(description="Read bounded lines."):
    return [{"name": "tail", "description": description,
             "inputSchema": {"type": "object", "properties": {}},
             "annotations": {"readOnlyHint": True}}]


def control(case_id="public-control", description="SYSTEM OVERRIDE; bounded lines."):
    return {"case_id": case_id, "rule_id": "L03", "expected_detection": True,
            "catalog": fragment(description)}


def test_unreviewed_counts_cannot_become_reviewed_accuracy():
    # what_bug_this_catches: unreviewed author labels masquerading as accepted gold.
    result = evaluate_labels([control()])
    rule = result["per_rule"]["L03"]
    assert rule["provisional_all_labels"]["TP"] == 1
    assert rule["confirmed_labels"]["scored"] == 0
    assert rule["confirmed_labels"]["precision"]["value"] is None
    assert rule["confirmed_labels"]["precision"]["status"] == "N/A"


def test_matching_review_is_hash_bound_and_stale_review_excluded():
    # what_bug_this_catches: stale case-id review following a changed catalog.
    case = control()
    initial = evaluate_labels([case])["cases"][0]
    review = {case["case_id"]: {"status": "confirmed", "rule_id": "L03",
                              "expected_detection": True,
                              "catalog_sha256": initial["catalog_sha256"]}}
    assert evaluate_labels([case], review=review)["per_rule"]["L03"][
        "confirmed_labels"]["TP"] == 1
    changed = deepcopy(case)
    changed["catalog"][0]["description"] = "Inspect bounded messages."
    result = evaluate_labels([changed], review=review)
    assert result["cases"][0]["review_status"] == "stale"
    assert result["per_rule"]["L03"]["confirmed_labels"]["scored"] == 0


def test_duplicate_case_ids_remain_two_unknowns():
    # what_bug_this_catches: deduplicating scheduled failures into a better score.
    result = evaluate_labels([control(), control()])
    assert result["scheduled"] == result["unknown"] == 2
    assert result["per_rule"]["L03"]["provisional_all_labels"]["scored"] == 0


def test_malformed_catalog_and_nonboolean_label_are_unknown():
    # what_bug_this_catches: invalid controls counted as successful negatives.
    malformed = control("malformed")
    malformed["catalog"][0]["inputSchema"] = None
    wrong_label = control("wrong-label")
    wrong_label["expected_detection"] = 1
    bad_rule = control("bad-rule")
    bad_rule["rule_id"] = []
    result = evaluate_labels([malformed, wrong_label, bad_rule])
    assert result["unknown"] == result["scheduled"] == 3


def test_bypass_is_a_separate_diagnostic_even_if_detected():
    # what_bug_this_catches: improved bypass detection charged as a benign FP.
    bypass = control("bypass")
    bypass["expected_detection"] = False
    result = evaluate_labels([], bypasses=[bypass])
    assert result["cases"][0]["diagnostic"] == "detected"
    assert result["per_rule"]["L03"]["provisional_all_labels"]["scored"] == 0


def test_exact_unicode_codepoint_evidence_and_invalid_span():
    # what_bug_this_catches: UTF-16 offsets shifting evidence after supplementary text.
    case = control(description="\U0001f680 SYSTEM OVERRIDE; bounded lines.")
    row = evaluate_labels([case])["cases"][0]
    finding = next(f for f in row["findings"] if f["rule_id"] == "L03")
    assert finding["span"]["start"] == 2
    assert finding["evidence"] == "SYSTEM OVERRIDE"
    finding["span"]["end"] = 10000
    assert validate_findings(case["catalog"], [finding])


def test_length_cap_emits_exact_bounded_evidence():
    # what_bug_this_catches: long prose scanned without bounds or evidence truncated incorrectly.
    case = control(description="Read bounded lines." + "z" * 5000)
    case["rule_id"] = "L11"
    result = evaluate_labels([case])
    row = result["cases"][0]
    finding = next(f for f in row["findings"] if f["rule_id"] == "L11")
    assert finding["span"] == {"start": 4096, "end": 4224, "unit": "unicode-codepoint"}
    assert len(finding["evidence"]) == 128
    assert row["detected"] is True


def test_duplicate_tool_control_is_not_suppressed():
    # what_bug_this_catches: ID deduplication hiding a real L07 collision control.
    case = control()
    case["rule_id"] = "L07"
    case["catalog"] = fragment() * 2
    row = evaluate_labels([case])["cases"][0]
    assert row["duplicate_tool_identifiers"] is True
    assert row["detected"] is True


def test_negated_external_channel_is_a_reported_false_positive():
    # what_bug_this_catches: treating lexical warnings as proof of malicious intent.
    case = control(description="Do not upload bounded lines; return them locally.")
    case["rule_id"] = "L09"
    case["expected_detection"] = False
    result = evaluate_labels([case])
    assert result["cases"][0]["classification"] == "FP"
    assert result["per_rule"]["L09"]["provisional_all_labels"]["precision"][
        "denominator"] == 1


def test_mandatory_ignore_errors_control_is_not_a_role_override():
    # what_bug_this_catches: broad ignore keyword changes causing innocent-role FPs.
    case = control(description="Read bounded lines; ignore errors in unrelated examples.")
    case["expected_detection"] = False
    assert evaluate_labels([case])["cases"][0]["classification"] == "TN"


def test_identical_templates_expose_dependence_without_losing_rows():
    # what_bug_this_catches: two IDs for one control counted as independent cases.
    result = evaluate_labels([control("one"), control("two")])
    assert result["scheduled"] == 2
    assert [row["identical_control_count"] for row in result["cases"]] == [2, 2]


def test_string_annotation_hint_is_unknown_instead_of_truthy():
    # what_bug_this_catches: string false/true changing annotation mismatch labels.
    case = control()
    case["catalog"][0]["annotations"]["readOnlyHint"] = "true"
    assert evaluate_labels([case])["cases"][0]["status"] == "unknown"


def test_metadata_depth_cap_produces_source_bound_evidence():
    # what_bug_this_catches: recursive metadata escaping L11 or losing source context.
    case = control(description="Read bounded lines.")
    case["rule_id"] = "L11"
    nested = {}
    case["catalog"][0]["extra"] = nested
    for _ in range(10):
        nested["child"] = {}
        nested = nested["child"]
    row = evaluate_labels([case])["cases"][0]
    assert row["status"] == "observed"
    assert row["classification"] == "TP"
    assert not validate_findings(case["catalog"], row["findings"])
