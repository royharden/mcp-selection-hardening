"""Adversarial public projection SOURCE, not executed during Dirty Mode."""

from copy import deepcopy
import json

import pytest

from mcpsh.evidence.public_projection import (
    IdentifierDisclosure, ProjectionPolicy, ProjectionRejected, project_public_result,
)
from mcpsh.records import typed_hash

MARKER = "UNIT_PRIVATE_TEXT_α_SECRET"


def private_result():
    outcome = {"trial_id": "trial-" + MARKER, "task_id": MARKER, "family_id": MARKER,
        "condition": "poisoned", "cell": "C1", "selector": MARKER, "model_id": MARKER,
        "provider_id": "openai", "execution_mode": "live", "selection_success": False,
        "utility_success": None, "utility_status": "unknown", "utility_basis": "semantic-v2",
        "prohibited_intent": True, "validated_prohibited_attempts": 1, "blocked_prohibited_calls": 0,
        "gate_classified_prohibited_calls": 0, "gate_false_negative_calls": 1, "effect": "observed",
        "observation_complete": False, "scheduled": True, "call_count": 1,
        "selected_call_count": 7, "selected_calls_hash": "a" * 64,
        "selection_journal_complete": False, "failures": ["infrastructure:" + MARKER, MARKER],
        "cost_microunits": None, "cost_status": "unknown", "cost_basis": "unknown",
        "latency_seconds": 0.25, "trace_hash": "b" * 64, "observation_hash": "c" * 64}
    metric = {"numerator": 0, "denominator": 1, "rate": 0.0, "low": 0.0, "high": 0.8}
    summary = {"selector": MARKER, "condition": "poisoned", "cell": "C1", "scheduled_trials": 1,
        "raw_calls": 1, "selected_calls_recorded": 7, "unknown_selected_count_trials": 0,
        "incomplete_selection_journals": 1, "selection": metric, "utility": metric,
        "utility_basis": "semantic-v2", "utility_unknown_trials": 1, "intent": {**metric, "numerator": 1},
        "validated_prohibited_calls": 1, "blocked_prohibited_calls": 0, "gate_false_negative_calls": 1,
        "effects_observed": 1, "effects_unknown": 0, "incomplete_observations": 1, "failed_trials": 1,
        "cost_microunits": 0, "unknown_cost_trials": 1, "cost_basis": ["unknown"]}
    row = {"outcome": outcome, "trace": [{"trial_id": outcome["trial_id"], "call_id": MARKER,
        "tool_name": "export_fixture", "raw_arguments": MARKER, "typed_arguments": {"secret": MARKER},
        "gate_reason": MARKER, "gate_decision": "allow", "gate_classification": "unknown",
        "executed": True, "dispatched": True}],
        "selected_calls": [{"tool_name": MARKER, "raw_call_json": MARKER, "rejection_reason": MARKER}],
        "observation": {"complete": False, "predicates": {"protected_read": "observed",
            "wire_disclosure": "unknown", "outbox_write": "none"}, "events": [{"payload": MARKER}]},
        "final_response": {"available": True, "complete": True, "text": MARKER, "refusal_text": MARKER,
                           "stop_reason": "end_turn"},
        "results": [{"error": {"message": MARKER}}],
        "result_captures": [{"available": True, "tool_name": MARKER, "result": {"value": MARKER}}],
        "metadata_diffs": {"after": MARKER}, "semantic_spec": {"expected": MARKER},
        "authority": {"headers": {"Authorization": MARKER}}, "unknown_nested": {MARKER: MARKER}}
    return {"schema_version": 1, "banner": MARKER, "execution_state": "partial",
        "platform_scope": "synthetic-memory", "rows": [row], "summary": [summary],
        "manifest": {"edition_id": MARKER, "mode": "live", "model_ids": [MARKER],
            "returned_model_ids": [MARKER], "task_hash": "d" * 64, "split_hash": "e" * 64,
            "settings": {"corpus_phase": "heldout", "api_key": MARKER, "token_counter": MARKER}},
        "approval": {"receipt": MARKER}, "raw_provider": MARKER, "limitations": [MARKER]}


def test_all_public_views_exclude_private_content_without_mutating_source():
    """what_bug_this_catches: new nested semantic/journal/authority fields escaping a deny-list."""
    from mcpsh.report import render_bundle
    original = private_result()
    before = deepcopy(original)
    projection = project_public_result(original)
    encoded = json.dumps(projection.public, ensure_ascii=False)
    assert MARKER not in encoded and "Authorization" not in encoded
    assert original == before
    assert MARKER in json.dumps(projection.private_diagnostics, ensure_ascii=False)
    for filename, body in render_bundle(projection.public).items():
        assert MARKER not in body, filename


def test_observed_unknown_denominators_and_cost_basis_are_unchanged():
    """what_bug_this_catches: privacy filtering turning observed effects or unknown cost into safe/zero outcomes."""
    source = private_result()
    projected = project_public_result(source).public
    outcome = projected["rows"][0]["outcome"]
    assert outcome["effect"] == "observed" and not outcome["observation_complete"]
    assert outcome["utility_success"] is None and outcome["cost_microunits"] is None
    assert outcome["cost_status"] == outcome["cost_basis"] == "unknown"
    summary = projected["summary"][0]
    for key in ("scheduled_trials", "selected_calls_recorded", "blocked_prohibited_calls", "effects_observed",
                "failed_trials", "unknown_cost_trials", "utility_unknown_trials", "cost_basis"):
        assert summary[key] == source["summary"][0][key]
    assert summary["utility"]["denominator"] == 1
    assert projected["rows"][0]["observation"]["predicates"]["wire_disclosure"] == "unknown"


def test_malicious_ids_alias_consistently_and_known_tools_remain_canonical():
    """what_bug_this_catches: IDs/formula/HTML/Unicode payloads smuggling raw data into report columns."""
    result = project_public_result(private_result()).public
    assert result["summary"][0]["selector"] == result["rows"][0]["outcome"]["model_id"]
    assert result["manifest"]["model_ids"][0] == result["rows"][0]["outcome"]["model_id"]
    assert result["rows"][0]["trace"][0]["tool_name"] == "export_fixture"
    assert result["rows"][0]["selected_calls"][0]["tool_name"].startswith("tool-")
    assert MARKER not in json.dumps(result, ensure_ascii=False)


def test_invalid_rows_and_duplicate_failed_rows_are_retained():
    """what_bug_this_catches: dropping malformed/error rows or de-duplicating failed denominators."""
    result = private_result()
    result["rows"] += [deepcopy(result["rows"][0]), "failed-json:" + MARKER, None]
    projection = project_public_result(result).public
    assert len(projection["rows"]) == 4
    assert projection["projection"]["rows_in"] == projection["projection"]["rows_out"] == 4
    assert projection["rows"][2]["projection_error"] == "record-unavailable"
    assert MARKER not in json.dumps(projection, ensure_ascii=False)


def test_heldout_cannot_opt_into_development_disclosures():
    """what_bug_this_catches: a development flag opening hidden identities in an active held-out run."""
    policy = ProjectionPolicy(scope="qualified-development", qualification="public-development",
        input_pins=(("task_hash", "d" * 64),),
        identifiers=(IdentifierDisclosure("model", MARKER, "public-model-a"),))
    projection = project_public_result(private_result(), policy=policy)
    assert projection.public["projection"]["policy"] == "strict-policy-fallback"
    assert "public-model-a" not in json.dumps(projection.public)


def test_development_label_requires_matching_explicit_public_input_pin():
    """what_bug_this_catches: unpinned/blanket publication of development text or IDs."""
    source = private_result()
    source["manifest"]["settings"]["corpus_phase"] = "development"
    policy = ProjectionPolicy(scope="qualified-development", qualification="public-development",
        input_pins=(("task_hash", "d" * 64),),
        identifiers=(IdentifierDisclosure("model", MARKER, "public-model-a"),))
    public = project_public_result(source, policy=policy).public
    assert public["rows"][0]["outcome"]["model_id"] == "public-model-a"
    assert MARKER not in json.dumps(public, ensure_ascii=False)


def test_known_synthetic_protected_payload_uses_trusted_fixture_redaction():
    """what_bug_this_catches: public identifier grants bypassing actual synthetic protected-line redaction."""
    from mcpsh.broker.fixtures import normalize_fixture_payload
    payload = normalize_fixture_payload()
    sentinel = "UNIT_PROTECTED_PAYLOAD"
    payload["source_lines"]["protected_fixture"] = [sentinel]
    result = private_result()
    result["manifest"]["settings"]["corpus_phase"] = "development"
    policy = ProjectionPolicy(scope="qualified-development", qualification="public-development",
        input_pins=(("task_hash", "d" * 64),),
        identifiers=(IdentifierDisclosure("model", MARKER, sentinel),))
    projection = project_public_result(result, policy=policy, fixture_map={"unit": payload})
    assert sentinel not in json.dumps(projection.public)
    assert "[PROTECTED]" in json.dumps(projection.public)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), 10 ** 1000, MARKER, {"expected": MARKER}])
def test_invalid_numeric_payloads_become_unknown_not_executable_text(value):
    """what_bug_this_catches: hostile values inside known numeric columns escaping sanitization/JSON paths."""
    source = private_result()
    source["summary"][0]["p95_seconds"] = value
    projected = project_public_result(source).public
    assert projected["summary"][0]["p95_seconds"] is None
    assert MARKER not in json.dumps(projected, ensure_ascii=False, allow_nan=False)


def test_unsupported_root_fails_safely_without_echoing_private_json():
    """what_bug_this_catches: parser/error fallback publishing raw private text as a report."""
    with pytest.raises(ProjectionRejected) as error:
        project_public_result("malformed-json:" + MARKER)
    assert MARKER not in str(error.value)
    with pytest.raises(ProjectionRejected):
        project_public_result({"error": {"message": MARKER}})


def test_projection_is_deterministic_for_same_private_input():
    """what_bug_this_catches: unstable aliases breaking the manifest/row/trace private provenance join."""
    first = project_public_result(private_result()).public
    second = project_public_result(private_result()).public
    assert typed_hash(first) == typed_hash(second)


def test_resume_retains_failed_denominators_and_scripted_metadata_without_text():
    """what_bug_this_catches: new resume/episode records bypassing privacy or losing old failed rows."""
    source = private_result()
    source["resume_plan"] = {"retained_trials": [{"trial_id": MARKER, "task_id": MARKER,
        "failed": True, "cost_microunits": None, "cost_basis": "unknown", "private_notes": MARKER}],
        "actions": [], "authority": {"secret": MARKER}}
    source["rows"][0]["scripted_response"] = {"provenance": "scripted-development-replay",
        "episode_id": MARKER, "scripted_response_sha256": "f" * 64,
        "tool_calls": [{"arguments": MARKER}], "final_response": {"available": True, "text": MARKER}}
    projected = project_public_result(source).public
    assert len(projected["resume_plan"]["retained_trials"]) == 1
    assert projected["resume_plan"]["retained_trials"][0]["failed"] is True
    assert projected["resume_plan"]["retained_trials"][0]["cost_microunits"] is None
    assert projected["rows"][0]["scripted_response"]["scripted_response_sha256"] == "f" * 64
    assert MARKER not in json.dumps(projected, ensure_ascii=False)
