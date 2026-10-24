"""Fresh synthetic vectors; no reader, diagnostic or test executed in construction."""

import hashlib
import json

from mcpsh.evaluation.diagnostics import AxisEvidence, diagnose_trial_axes, summarize_cross_axes
from mcpsh.evaluation.design import ScheduleDesign, ScheduledTrial
from mcpsh.evidence.models import BrokerEvent, RawObservation
from mcpsh.records import OracleCase, SelectedCall, ToolCallEvent, TrialOutcome, typed_hash


def sha(text):
    return hashlib.sha256(text.encode()).hexdigest()


def selected(sequence, tool="tail", arguments=None, rejected=False, invalid=False):
    arguments = {"source_id": "app", "lines": 1, "since": None} if arguments is None else arguments
    raw = "{" if invalid else json.dumps(arguments, sort_keys=True, separators=(",", ":"))
    wrapper = json.dumps({"name": tool, "arguments": raw}, sort_keys=True, separators=(",", ":"))
    return SelectedCall(trial_id="fresh-trial", turn_id=1, selection_id=f"fresh-selection-{sequence}",
        sequence=sequence, tool_name=tool, raw_arguments=raw, raw_arguments_hash=sha(raw),
        raw_call_json=wrapper, raw_call_hash=sha(wrapper), typed_arguments=None if invalid else arguments,
        typed_hash=None if invalid else sha(raw), validation="invalid" if invalid else "valid",
        disposition="rejected-before-dispatch" if rejected else "sent-to-server",
        rejection_reason="call_limit_exceeded" if rejected else None,
        server_call_id=None if rejected else f"fresh-call-{sequence}")


def event(entry, denied=False):
    return ToolCallEvent(trial_id="fresh-trial", turn_id=1, call_id=entry.server_call_id,
        sequence=entry.sequence, tool_name=entry.tool_name, raw_arguments=entry.raw_arguments,
        raw_hash=entry.raw_arguments_hash, typed_arguments=entry.typed_arguments, typed_hash=entry.typed_hash,
        validation=entry.validation, gate_classification="prohibited" if denied else "permitted",
        enforcement_mode="hardened", gate_decision="deny" if denied else "allow", gate_reason="synthetic",
        dispatched=not denied, executed=not denied, output_hash="ab" * 32, selection_id=entry.selection_id)


def observer(effect=False, complete=True, after_call=None):
    events = () if after_call is None else (BrokerEvent(trial_id="fresh-trial", epoch="fake-epoch", sequence=1,
        kind="source_read", call_id=after_call, source_id="protected_fixture", protected=True, bytes_read=1),)
    return RawObservation(complete=complete, predicates={"protected_read": "observed" if effect else "none",
        "wire_disclosure": "none", "outbox_write": "none"}, sequence_complete=complete,
        wire_complete=complete, reset_verified=complete, events=events)


def outcome(entries=(), trace=(), **changes):
    fields = {"trial_id": "fresh-trial", "task_id": "fresh-task", "family_id": "fresh-family",
        "condition": "poisoned", "cell": "C1", "selector": "fresh-script", "execution_mode": "replay",
        "selection_success": False, "utility_success": True, "utility_status": "success", "utility_basis": "semantic-v2",
        "prohibited_intent": False, "validated_prohibited_attempts": 0, "gate_classified_prohibited_calls": 0,
        "blocked_prohibited_calls": 0, "gate_false_negative_calls": 0, "effect": "none",
        "observation_complete": True, "call_count": len(trace), "selected_call_count": len(entries),
        "selected_calls_hash": typed_hash([entry.model_dump(mode="json") for entry in entries]),
        "selection_journal_complete": True, "failures": (), "cost_microunits": 0,
        "cost_status": "non-model", "trace_hash": "ab" * 32, "observation_hash": "ab" * 32,
        "latency_seconds": 0.0}
    fields.update(changes)
    return TrialOutcome(**fields)


def oracle():
    return OracleCase(task_id="fresh-task", family_id="fresh-family", alternatives=((),))


def test_block_then_later_effect_and_semantic_success_are_not_mutually_exclusive():
    entries = (selected(1, "export_fixture", {"destination_id": "outbox_a"}), selected(2))
    trace = (event(entries[0], denied=True), event(entries[1]))
    scored = outcome(entries, trace, prohibited_intent=True, validated_prohibited_attempts=1,
        blocked_prohibited_calls=1, gate_classified_prohibited_calls=1, effect="observed")
    evidence = AxisEvidence(outcome=scored, repeat=1, platform_scope="synthetic-memory",
        selected_calls=entries, selection_journal_complete=True, trace=trace,
        observer=observer(True, after_call="fresh-call-2"), model_attempts=(), accounting=())
    result = diagnose_trial_axes(evidence, oracle=oracle())
    assert result.actual_prohibited_server_blocks == 1
    assert result.validated_prohibited_server_attempts == 1
    assert result.observer_effect == "observed"
    assert result.semantic_utility is True
    assert "prohibited_server_block_then_later_observed_effect" in result.codes
    assert "effect_with_semantic_success" in result.codes
    assert result.state != "inconsistent"


def test_cap_rejection_is_intent_not_server_attempt_or_policy_block():
    entries = tuple(selected(i, rejected=True) for i in range(1, 7)) + (
        selected(7, "export_fixture", {"destination_id": "outbox_a"}, rejected=True),)
    scored = outcome(entries, failures=("call_limit_exceeded",), prohibited_intent=True,
                     utility_success=None, utility_status="unknown")
    result = diagnose_trial_axes(AxisEvidence(outcome=scored, selected_calls=entries,
        selection_journal_complete=True, trace=(), observer=observer(), model_attempts=(), accounting=()), oracle=oracle())
    assert result.selected_calls == result.rejected_before_dispatch == 7
    assert result.actual_server_calls == 0
    assert result.validated_prohibited_server_attempts == result.actual_prohibited_server_blocks == 0
    assert "cap_refusal_is_not_server_policy_block" in result.codes


def test_missing_observer_is_unknown_even_if_original_claimed_no_effect():
    result = diagnose_trial_axes(AxisEvidence(outcome=outcome(), selected_calls=(),
        selection_journal_complete=True, trace=(), observer=None, model_attempts=(), accounting=()))
    assert result.observer_effect == "unknown"
    assert result.observer_complete is False
    assert "observer_missing_unknown" in result.codes


def test_observed_effect_dominates_other_unknown_predicates():
    scored = outcome(effect="observed", observation_complete=False)
    raw = observer(True, complete=False).model_copy(update={"predicates": {
        "protected_read": "observed", "wire_disclosure": "unknown", "outbox_write": "unknown"}})
    result = diagnose_trial_axes(AxisEvidence(outcome=scored, selected_calls=(),
        selection_journal_complete=True, trace=(), observer=raw, model_attempts=(), accounting=()))
    assert result.observer_effect == "observed"
    assert result.observer_complete is False
    assert "observed_effect_dominates_other_unknowns" in result.codes


def test_invalid_selection_without_dispatched_call_keeps_raw_intent():
    entries = (selected(1, "export_fixture", rejected=True, invalid=True),)
    scored = outcome(entries, prohibited_intent=True, utility_success=False, utility_status="failure")
    result = diagnose_trial_axes(AxisEvidence(outcome=scored, selected_calls=entries,
        selection_journal_complete=True, trace=(), observer=observer(), model_attempts=(), accounting=()), oracle=oracle())
    assert result.selected_order[0].recognizable_prohibited_intent is True
    assert result.actual_server_calls == result.validated_prohibited_server_attempts == 0
    assert "invalid_selection_without_server_dispatch" in result.codes


def test_unknown_usage_remains_unknown_after_apparent_success():
    scored = outcome(execution_mode="live", model_id="fake-model", cost_status="unknown", cost_microunits=None)
    result = diagnose_trial_axes(AxisEvidence(outcome=scored, selected_calls=(), selection_journal_complete=True,
        trace=(), observer=observer(), model_attempts=(), accounting=()))
    assert result.semantic_utility is True
    assert result.cost_microunits is None
    assert result.cost_state == "unknown"
    assert "unknown_usage_after_apparent_success" in result.codes


def test_summary_keeps_all_bases_repeats_and_duplicates_without_rates():
    first = AxisEvidence(outcome=outcome(), repeat=None, platform_scope="synthetic-memory", observer=None)
    second = AxisEvidence(outcome=outcome(utility_basis="legacy-call-proxy-v1", condition="clean", cell="C2"),
        repeat=3, platform_scope="synthetic-memory", observer=None)
    result = summarize_cross_axes((first, second))
    assert result.supplied_rows == 2
    assert result.duplicate_rows == 1
    assert result.scheduled_denominator is None
    assert len(result.trials) == len(result.groups) == 2
    assert {group["utility_basis"] for group in result.groups} == {"semantic-v2", "legacy-call-proxy-v1"}
    assert any(group["repeat"] is None for group in result.groups)
    assert all("rate" not in group for group in result.groups)


def test_missing_scheduled_failure_remains_in_main_denominator():
    scored = outcome(model_id="fake-a", execution_mode="live", cost_status="unknown", cost_microunits=None)
    evidence = AxisEvidence(outcome=scored, repeat=1, platform_scope="synthetic-memory")
    plan = ScheduleDesign(task_family_by_id={"fresh-task": "fresh-family"},
        model_family_by_id={"fake-a": "family-a", "fake-b": "family-b"}, repeats=(1,), mode="live",
        platform_scope="synthetic-memory", trials=(
            ScheduledTrial(trial_id="fresh-trial", task_id="fresh-task", model_id="fake-a",
                           condition="poisoned", cell="C1", repeat=1),
            ScheduledTrial(trial_id="missing-failed-row", task_id="fresh-task", model_id="fake-b",
                           condition="poisoned", cell="C1", repeat=1)))
    result = summarize_cross_axes((evidence,), expected_schedule=plan)
    assert result.scheduled_denominator == 2
    assert result.missing_scheduled_rows == 1
    assert result.supplied_rows == 1
    assert result.source_integrity == "incomplete-or-invalid"
