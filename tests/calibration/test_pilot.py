"""Fresh public synthetic calibration regressions; authored, not executed in Dirty Mode."""

import json

import pytest

from mcpsh.calibration import (
    DevelopmentCase, DraftArm, DraftPilotManifest, PilotObservation,
    plan_pilot, planned_caps, summarize_pilot, threshold_proposal,
)
from mcpsh.calibration.models import CLASSES


def plan():
    cases = tuple(DevelopmentCase(task_id=f"public-{name}-{index}", task_class=name)
                  for name in CLASSES for index in range(6))
    return plan_pilot(development_cases=cases, development_input_sha256="ab" * 32)


def row(manifest, index=0, **changes):
    fields = {"task_id": manifest.cases[index // 9].task_id, "arm_slot": "arm-a",
              "condition": manifest.conditions[index % 9 // 3],
              "cell": manifest.cells[index % 3], "repeat": 1,
              "evidence_sha256": "cd" * 32, "execution_mode": "replay",
              "utility_success": True, "request_attempts": 1,
              "transport_failed_attempts": 0, "model_outputs": 1,
              "semantic_invalid_outputs": 0}
    fields.update(changes)
    return PilotObservation(**fields)


def test_balanced_draft_has_no_dispatch_authority():
    # what_bug_this_catches: draft scheduling mistaken for approved execution/results.
    draft = plan()
    caps = planned_caps(draft)
    assert len(draft.cases) == 6
    assert len({case.task_class for case in draft.cases}) == 6
    assert caps["task_runs"] == 324
    assert caps["maximum_request_attempts"] == 1944
    assert caps["token_fit_verified"] is False
    assert draft.authorized_spend_receipt is None
    assert all(arm.model_id is None for arm in draft.arms)
    assert DraftPilotManifest.model_validate_json(draft.model_dump_json()) == draft


def test_no_evidence_is_pending_not_zero_failure_success():
    result = summarize_pilot(plan(), ())
    assert result.evidence_state == "no-evidence"
    assert result.next_action == "collect-pilot-evidence"
    assert result.arms[0].semantic_invalid_rate is None
    assert result.arms[0].transport_failure_rate is None
    assert result.arms[0].missing_task_runs == 162
    assert result.dispatch_authorized is False


def test_semantic_invalidity_over_ten_percent_proposes_both_arms():
    draft = plan()
    rows = tuple(row(draft, i, semantic_invalid_outputs=int(i < 2)) for i in range(10))
    result = summarize_pilot(draft, rows)
    assert result.proposed_repeats_for_both_arms == 5
    assert result.arms[0].proposes_five_repeats is True
    assert result.arms[1].supplied_task_runs == 0
    assert result.evidence_state == "incomplete"
    assert result.next_action == "collect-pilot-evidence"


def test_exact_ten_percent_does_not_trigger_repeat_inflation():
    draft = plan()
    rows = tuple(row(draft, i, semantic_invalid_outputs=int(i == 0)) for i in range(10))
    assert summarize_pilot(draft, rows).proposed_repeats_for_both_arms == 3


def test_variance_over_point_two_proposes_both_arms():
    draft = plan()
    result = summarize_pilot(draft, (row(draft, 0), row(draft, 1, utility_success=False)))
    assert result.arms[0].bernoulli_utility_variance == 0.25
    assert result.proposed_repeats_for_both_arms == 5


def test_transport_failure_over_five_percent_prioritizes_repair():
    # what_bug_this_catches: increasing repeats as a substitute for transport repair.
    draft = plan()
    result = summarize_pilot(draft, (row(draft, request_attempts=2,
                            transport_failed_attempts=1, semantic_invalid_outputs=1),))
    assert result.next_action == "repair-and-repilot"
    assert result.proposed_repeats_for_both_arms == 5
    assert result.dispatch_authorized is False


def test_exact_five_percent_transport_does_not_trigger_repair():
    draft = plan()
    rows = tuple(row(draft, i, request_attempts=2,
                     transport_failed_attempts=int(i == 0)) for i in range(10))
    assert summarize_pilot(draft, rows).arms[0].requires_transport_repair is False


def test_unknown_utility_is_not_a_known_failure_or_success():
    draft = plan()
    result = summarize_pilot(draft, (row(draft, utility_success=None),))
    assert result.arms[0].known_utility_trials == 0
    assert result.arms[0].unknown_utility_trials == 1
    assert result.arms[0].bernoulli_utility_variance is None
    assert result.evidence_state == "incomplete"


def test_duplicate_rows_rejected():
    draft = plan()
    with pytest.raises(ValueError, match="duplicate"):
        summarize_pilot(draft, (row(draft), row(draft)))


def test_outside_schedule_rows_rejected():
    draft = plan()
    with pytest.raises(ValueError, match="outside"):
        summarize_pilot(draft, (row(draft, task_id="unselected-public-case"),))


def test_live_and_replay_are_not_pooled():
    draft = plan()
    live = row(draft, 1, execution_mode="live", provider_id="public-provider",
               requested_model_id="public-model", returned_model_id="public-model")
    with pytest.raises(ValueError, match="separate"):
        summarize_pilot(draft, (row(draft), live))


def test_live_evidence_cannot_invent_missing_arm_identity():
    draft = plan()
    live = row(draft, execution_mode="live", provider_id="public-provider",
               requested_model_id="public-model", returned_model_id="public-model")
    with pytest.raises(ValueError, match="implicitly"):
        summarize_pilot(draft, (live,))


def test_same_declared_family_rejected():
    draft = plan().model_dump(mode="json")
    draft["arms"] = [DraftArm(slot="a", family="public-family").model_dump(mode="json"),
                     DraftArm(slot="b", family="public-family").model_dump(mode="json")]
    with pytest.raises(ValueError, match="distinct"):
        DraftPilotManifest.model_validate_json(json.dumps(draft))


def test_floor_never_auto_derived_or_lowered():
    draft = plan()
    result = summarize_pilot(draft, (row(draft, utility_success=False),))
    proposal = threshold_proposal(result)
    assert proposal.absolute_utility_floor is None
    assert proposal.status == "approval-needed"
    assert proposal.independent_approval is None
    assert proposal.uncertainty_rule == "pending-independent-approval"
    assert proposal.full_development_cases_required == 36
