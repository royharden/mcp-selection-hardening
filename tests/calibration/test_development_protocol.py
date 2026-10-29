"""Public synthetic protocol regressions; not executed during construction."""

from datetime import datetime, timezone

import pytest

from mcpsh.calibration import (
    CalibrationOutcome, DevelopmentCase, ProtocolAdmission, execute_development_protocol,
    plan_development_calibration, plan_pilot, propose_full36_thresholds,
    retention_decision, summarize_development, validate_protocol_plan,
)
from mcpsh.calibration.models import CLASSES, PilotObservation
from mcpsh.records import TrialOutcome, typed_hash


def planned():
    cases = tuple(DevelopmentCase(task_id=f"public-{name}-{index}", task_class=name)
                  for name in CLASSES for index in range(6))
    pilot = plan_pilot(development_cases=cases, development_input_sha256="ab" * 32)
    return plan_development_calibration(pilot=pilot, development_cases=cases,
                                        development_input_sha256="ab" * 32)


def recorded(plan, slot=None, basis="semantic-v2", utility=True):
    slot = plan.slots[0] if slot is None else slot
    outcome = TrialOutcome(
        trial_id=slot.slot_id, task_id=slot.task_id, family_id="public-development-template",
        condition=slot.condition, cell=slot.cell,
        selector="public-script" if slot.selector == "model" else slot.selector,
        execution_mode="replay", selection_success=True, utility_success=utility,
        utility_status="unknown" if utility is None else "success" if utility else "failure",
        utility_basis=basis, utility_evidence_ids=("public-capture",), prohibited_intent=False,
        validated_prohibited_attempts=0, gate_classified_prohibited_calls=0,
        blocked_prohibited_calls=0, gate_false_negative_calls=0,
        effect="none", observation_complete=True, call_count=0, selected_call_count=0,
        selected_calls_hash="cd" * 32, selection_journal_complete=True, failures=(),
        cost_microunits=0, cost_status="non-model", trace_hash="cd" * 32,
        observation_hash="cd" * 32, latency_seconds=0.0,
    )
    counts = None
    if slot.selector == "model" and basis == "semantic-v2":
        counts = PilotObservation(task_id=slot.task_id, arm_slot=slot.arm_slot, condition=slot.condition,
            cell=slot.cell, repeat=slot.repeat, evidence_sha256="cd" * 32, execution_mode="replay",
            utility_success=utility, request_attempts=1, transport_failed_attempts=0,
            model_outputs=1, semantic_invalid_outputs=0)
    return CalibrationOutcome(slot_id=slot.slot_id, settings_sha256=plan.settings_sha256,
        evidence_sha256="cd" * 32, outcome_sha256=typed_hash(outcome.model_dump(mode="json")),
        outcome=outcome, attempts=counts)


def test_all36_and_controls_are_planned_without_measurements():
    plan = planned()
    assert len(plan.cases) == 36
    assert len(plan.slots) == 2592
    assert sum(row.selector == "model" for row in plan.slots) == 1944
    assert sum(row.selector == "deny-all" for row in plan.slots) == 216
    assert plan.pilot_evidence_state == "no-evidence"
    assert plan.dispatch_authorized is False


def test_settings_tamper_and_missing_slot_rejected():
    plan = planned()
    with pytest.raises(ValueError, match="settings"):
        validate_protocol_plan(plan.model_copy(update={"settings_sha256": "ff" * 32}))
    with pytest.raises(ValueError, match="schedule"):
        validate_protocol_plan(plan.model_copy(update={"slots": plan.slots[:-1]}))


def test_missing_observations_do_not_create_full36_results():
    plan = planned()
    summary = summarize_development(plan, ())
    assert summary.evidence_state == "no-evidence"
    assert summary.missing_slots == summary.scheduled_slots == 2592
    assert summary.next_action == "collect-development-evidence"
    assert all(group["known_semantic_utility"]["rate"] is None for group in summary.groups)
    proposal = propose_full36_thresholds(summary)
    assert proposal.status == "approval-needed"
    assert proposal.absolute_utility_floor is None
    assert proposal.independent_approval is None


def test_duplicate_or_tampered_observation_is_rejected():
    plan = planned()
    record = recorded(plan)
    with pytest.raises(ValueError, match="duplicate"):
        summarize_development(plan, (record, record))
    with pytest.raises(ValueError, match="digest"):
        summarize_development(plan, (record.model_copy(update={"outcome_sha256": "ff" * 32}),))


def test_legacy_success_preserved_but_not_counted_as_semantic():
    plan = planned()
    summary = summarize_development(plan, (recorded(plan, basis="legacy-call-proxy-v1"),))
    overall = [g for g in summary.groups if g["task_class"] == "all" and g["supplied"]]
    assert len(overall) == 1
    assert overall[0]["legacy_proxy_successes"] == 1
    assert overall[0]["semantic_successes"] == 0
    assert summary.evidence_state == "incomplete"


def test_unknown_utility_stays_unknown_with_full_scheduled_denominator():
    plan = planned()
    summary = summarize_development(plan, (recorded(plan, utility=None),))
    group = next(g for g in summary.groups if g["task_class"] == "all" and g["supplied"])
    assert group["semantic_known"] == 0
    assert group["semantic_unknown_or_proxy"] == group["scheduled"]


def test_runtime_grant_required_before_any_injected_runner():
    # what_bug_this_catches: fake/injected callback bypassing Dirty Mode/admission.
    plan = planned()
    called = []
    admission = ProtocolAdmission(plan_sha256=typed_hash(plan.model_dump(mode="json")),
        settings_sha256=plan.settings_sha256, pilot_summary_sha256="ab" * 32,
        receipt_id="public-fake-receipt", expires_at="2099-01-01T00:00:00Z", execution_mode="replay")
    with pytest.raises(ValueError, match="before any callback"):
        execute_development_protocol(plan, runner=lambda slot: called.append(slot), admission=admission,
                                      clock=lambda: datetime(2030, 1, 1, tzinfo=timezone.utc))
    assert called == []


def admission_fixture():
    # Explicit fake caller attestation for future pure protocol regression only.
    plan = planned().model_copy(update={"pilot_evidence_state": "supplied-complete",
        "pilot_summary_sha256": "ef" * 32, "pilot_execution_mode": "replay"})
    admission = ProtocolAdmission(plan_sha256=typed_hash(plan.model_dump(mode="json")),
        settings_sha256=plan.settings_sha256, pilot_summary_sha256="ef" * 32,
        receipt_id="public-fake-scope", expires_at="2035-01-01T00:00:00Z", execution_mode="replay",
        authorized=True, dirty_mode_closed=True)
    return plan, admission


def test_injected_runner_cannot_substitute_another_valid_slot():
    plan, admission = admission_fixture()
    result = execute_development_protocol(plan, runner=lambda slot: recorded(plan, plan.slots[1]),
        admission=admission, clock=lambda: datetime(2030, 1, 1, tzinfo=timezone.utc))
    assert not result.outcomes
    assert result.failures[0].category == "ValueError"
    assert len(result.failures) == len(plan.slots)


def test_expiry_rechecked_before_next_callback():
    # what_bug_this_catches: one initial timestamp authorizing all later slots.
    plan, admission = admission_fixture()
    moments = iter((datetime(2030, 1, 1, tzinfo=timezone.utc),
                    datetime(2040, 1, 1, tzinfo=timezone.utc)))
    called = []

    def runner(slot):
        called.append(slot.slot_id)
        return recorded(plan, slot)

    result = execute_development_protocol(plan, runner=runner, admission=admission,
                                          clock=lambda: next(moments))
    assert len(called) == len(result.outcomes) == 1
    assert result.state == "partial"
    assert len(result.failures) == len(plan.slots) - 1


@pytest.mark.parametrize("interval,independent,expected", [
    ({"low": None, "high": None}, None, "pending"),
    ({"low": 0.0, "high": 0.1, "interpretation": "family-paired"}, None, "inconclusive"),
    ({"low": -0.04, "high": 0.1, "interpretation": "family-paired"}, 24, "pass"),
    ({"low": -0.1, "high": -0.06, "interpretation": "family-paired"}, 24, "fail"),
    ({"low": -0.1, "high": 0.0, "interpretation": "family-paired"}, 24, "inconclusive"),
])
def test_retention_separates_unapproved_independence_and_crossing_intervals(interval, independent, expected):
    assert retention_decision(interval, independent_families=independent) == expected
