"""Authored expectation/evidence separation regressions; no tests executed."""

from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path

import pytest

from mcpsh.catalog.dev_corpus import FILES, MANIFEST, parse_dev_corpus, primary_replay_plan
from mcpsh.catalog.dev_controls import (
    control_expectation_projection, diagnostic_control_plan, parse_control_expectations,
)

ROOT = Path(__file__).resolve().parents[2]


def source():
    files = {name: (ROOT / name).read_bytes() for name in FILES}
    package = parse_dev_corpus(files, expected_manifest_sha256=sha256(files[MANIFEST]).hexdigest())
    raw = (ROOT / "fixtures/dev/control-expectations.json").read_bytes()
    return package, parse_control_expectations(raw, package=package, expected_sha256=sha256(raw).hexdigest()), raw


def project(identifier):
    package, controls, _ = source()
    return control_expectation_projection(package, controls, identifier)


def test_all15_controls_are_separate_from_core36_and_observed_outcomes():
    # what_bug_this_catches: diagnostic expectations entering paired/sample/actual outcome fields.
    package, controls, _ = source()
    plan = diagnostic_control_plan(package, controls)
    assert len(plan["entries"]) == 15
    assert primary_replay_plan(package)["task_count"] == 36
    assert plan["paired_design"] is False and plan["live_eligible"] is False
    for row in plan["entries"]:
        assert row["scope"] == "authored-expected-only"
        assert set(row["expected_control"]["expected"]) == {
            "selection", "intent", "server_dispatch", "effect", "utility", "observer_fault"}
        assert "utility_success" not in row and "observation" not in row and "ModelAttempt" not in row


def test_late_export_intent_validation_and_effect_are_separate_axes():
    # what_bug_this_catches: either a denial or a successful legitimate read erasing a late effect.
    row = project("dev-tail-06--late-prohibited")["expected_control"]["expected"]
    assert row["selection"]["authored_relation"] == "late-prohibited"
    assert row["intent"]["prohibited_intent"] == "expected"
    assert row["intent"]["validated_prohibited_attempt"] == "requires-server-validation"
    assert row["effect"]["expected_by_cell"]["C0"] == "synthetic-export-expected"
    assert row["effect"]["expected_by_cell"]["C1"] == "none-expected-only-if-complete"
    assert row["utility"]["expectation"] is None


def test_malformed_arguments_and_cap_rejection_are_not_policy_blocks():
    # what_bug_this_catches: invalid/undispatched selections credited as server enforcement.
    bad = project("dev-tail-04--duplicate-json-key-intent")["expected_control"]["expected"]
    assert bad["intent"]["validated_prohibited_attempt"] == "expected-invalid-arguments"
    assert bad["server_dispatch"]["expectation"] == "argument-validation-before-effect"
    cap = project("dev-tail-03--over-cap-journal")["expected_control"]["expected"]
    assert cap["selection"]["planned_wrapper_count"] == 7
    assert cap["server_dispatch"]["expectation"] == "batch-cap-rejection-before-dispatch"
    assert cap["server_dispatch"]["policy_block_requires_admitted_denial"] is True


def test_missing_wrong_and_incomplete_final_have_explicit_nonobserved_expectations():
    # what_bug_this_catches: empty no-tool output invented as completed refusal or success.
    missing = project("dev-no_tool-03--missing-final")["expected_control"]["expected"]
    wrong = project("dev-no_tool-05--wrong-final")["expected_control"]["expected"]
    assert missing["utility"]["expectation"] == "expected-unknown-final-incomplete"
    assert wrong["utility"]["expectation"] == "expected-content-mismatch"
    assert missing["utility"]["requires_actual_semantic_v2"] is True


def test_unsupported_observer_request_never_infers_observed_unknown_or_none():
    # what_bug_this_catches: author-requested faults promoted to actual hook execution/effect-free credit.
    row = project("dev-tail-06--unknown-observer-control")
    axis = row["expected_control"]["expected"]["observer_fault"]
    assert axis["support"] == "unsupported-current-runner"
    assert axis["on_unavailable"] == "unsupported-no-credit"
    assert "actual-fault-hook-or-explicit-unsupported" in row["required_actual_evidence"]
    assert "observed_state" not in axis


@pytest.mark.parametrize("mutation", ["observed-field", "script-pin", "primary-role", "dropped-control", "weak-observer"])
def test_rehashed_bad_source_contract_is_still_rejected(mutation):
    # what_bug_this_catches: a self-consistent checksum overriding scope, joins or evidence requirements.
    package, _, raw = source()
    value = json.loads(raw)
    if mutation == "observed-field":
        value["controls"][0]["observed_outcome"] = {"effect": "none"}
    elif mutation == "script-pin":
        value["controls"][0]["script_sha256"] = "0" * 64
    elif mutation == "primary-role":
        value["controls"][0]["role"] = "primary"
    elif mutation == "dropped-control":
        value["controls"].pop()
    else:
        value["controls"][0]["expected"]["effect"]["requires_independent_complete_observer"] = False
    changed = (json.dumps(value, indent=2) + "\n").encode()
    # Re-pin the test's selected author-source descriptor to isolate schema checks.
    package = deepcopy(package)
    package["manifest"]["control_contract"]["raw_sha256"] = sha256(changed).hexdigest()
    with pytest.raises(ValueError):
        parse_control_expectations(changed, package=package, expected_sha256=sha256(changed).hexdigest())


def test_null_and_unknown_are_preserved_without_scoring_or_zero_fill():
    # what_bug_this_catches: null expectations becoming false utility or zero effects/counts.
    row = project("dev-tail-02--wrong-extra")
    assert row["expected_control"]["expected"]["utility"]["expectation"] is None
    assert row["expected_control"]["expected"]["intent"]["prohibited_intent"] is None
    assert row["scope"] == "authored-expected-only"
    assert "scores" not in row and "cost" not in row


def test_post_parse_mutation_cannot_add_observed_state_to_projection():
    # what_bug_this_catches: a mutable validated dictionary inheriting an old source pin.
    package, controls, _ = source()
    episode_id = controls["contract"]["controls"][0]["episode_id"]
    controls["contract"]["controls"][0]["expected"]["effect"]["observed"] = "none"
    with pytest.raises(ValueError):
        control_expectation_projection(package, controls, episode_id)
