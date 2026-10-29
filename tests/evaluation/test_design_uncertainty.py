"""Fresh synthetic analytic regressions. Not run or bootstrapped in Dirty Mode."""

from itertools import product

import pytest

from mcpsh.evaluation.design import (
    FamilySupport, ObservedTrial, ScheduledTrial, ScheduleDesign, audit_schedule, record_hash,
)
from mcpsh.evaluation.statistics import compare_paired_families, paired_family_bootstrap
from mcpsh.records import TrialOutcome


def supplied(tasks=2, repeats=(1, 2), shared_family=False):
    families = {f"public-task-{i}": "shared" if shared_family else f"public-family-{i}" for i in range(tasks)}
    models = {"public-a": "family-a", "public-b": "family-b"}
    slots = tuple(ScheduledTrial(trial_id=f"public-row-{i}", task_id=task, model_id=model,
                                condition=condition, cell=cell, repeat=repeat)
        for i, (task, model, condition, cell, repeat) in enumerate(product(
            families, models, ("clean", "ambiguous", "poisoned"), ("C0", "C1", "C2"), repeats)))
    design = ScheduleDesign(task_family_by_id=families, model_family_by_id=models, repeats=repeats,
        mode="live", platform_scope="synthetic-memory", trials=slots, seed=17)
    scored, private = [], []
    for slot in slots:
        success = slot.cell == "C2"
        outcome = TrialOutcome(trial_id=slot.trial_id, task_id=slot.task_id, family_id=families[slot.task_id],
            condition=slot.condition, cell=slot.cell, selector=slot.model_id, execution_mode="live",
            provider_id="public-provider", model_id=slot.model_id, selection_success=True,
            utility_success=success, utility_status="success" if success else "failure",
            utility_basis="semantic-v2", utility_evidence_ids=("public-result",), prohibited_intent=False,
            validated_prohibited_attempts=0, gate_classified_prohibited_calls=0, blocked_prohibited_calls=0,
            gate_false_negative_calls=0, effect="none", observation_complete=True, call_count=0,
            selected_call_count=0, selected_calls_hash="ab" * 32, selection_journal_complete=True,
            failures=(), cost_microunits=1, cost_status="settled", trace_hash="ab" * 32,
            observation_hash="ab" * 32, latency_seconds=0.0)
        scored.append(outcome)
        private.append(ObservedTrial(outcome=outcome, repeat=slot.repeat, platform_scope="synthetic-memory",
            model_family_id=models[slot.model_id], outcome_sha256=record_hash(outcome), row_evidence_sha256="cd" * 32))
    return design, tuple(scored), tuple(private)


def compare(design, scored, private, **options):
    return compare_paired_families(design, scored_outcomes=scored, observed_rows=private,
                                   before="C1", after="C2", **options)


def replace_outcome(scored, private, index, **changes):
    outcome = scored[index].model_copy(update=changes)
    scored = (*scored[:index], outcome, *scored[index + 1:])
    row = private[index].model_copy(update={"outcome": outcome, "outcome_sha256": record_hash(outcome)})
    return scored, (*private[:index], row, *private[index + 1:])


def test_constant_paired_improvement_has_analytic_degenerate_interval():
    # what_bug_this_catches: independent-call N or mixing before/after strata.
    design, scored, private = supplied()
    report = compare(design, scored, private)
    assert report.difference == report.low == report.high == 1.0
    assert report.family_label_count == 2
    assert report.supported_observable_families == 0
    assert report.expected_pairs == 24
    assert report.interpretation == "exploratory"
    assert report.independent_product_acceptance == "pending"


def test_repeats_and_tasks_do_not_inflate_shared_family_n():
    design, scored, private = supplied(tasks=4, repeats=(1, 2, 3), shared_family=True)
    report = compare(design, scored, private)
    assert report.family_label_count == 1
    assert report.expected_pairs == 72
    assert report.interpretation == "exploratory"


def test_duplicate_scored_and_private_rows_invalid_not_extra_n():
    design, scored, private = supplied()
    audit = audit_schedule(design, scored_outcomes=(*scored, scored[0]), observed_rows=(*private, private[0]))
    assert audit.status == "invalid"
    assert audit.expected_trials == len(design.trials)
    assert audit.scored_rows == len(scored) + 1
    report = compare(design, (*scored, scored[0]), (*private, private[0]))
    assert report.difference is report.low is report.high is None


def test_repeat_never_inferred_from_trial_id_or_expected_slot():
    design, scored, private = supplied()
    changed = (private[0].model_copy(update={"repeat": None}), *private[1:])
    report = compare(design, scored, changed)
    assert report.audit.status == "incomplete"
    assert any(item.category == "missing-explicit-repeat" for item in report.audit.issues)
    assert report.difference is None


@pytest.mark.parametrize("changes", [{"repeat": 5}, {"platform_scope": "filesystem-posix"},
                                     {"model_family_id": "another-family"}])
def test_wrong_coordinate_platform_or_family_invalidates_completeness(changes):
    design, scored, private = supplied()
    changed = (private[0].model_copy(update=changes), *private[1:])
    assert compare(design, scored, changed).audit.status == "invalid"


def test_wrong_mode_rejected_even_if_ids_and_values_match():
    design, scored, private = supplied()
    scored, private = replace_outcome(scored, private, 0, execution_mode="replay")
    assert compare(design, scored, private).audit.status == "invalid"


def test_missing_member_cannot_shrink_pair_denominator():
    design, scored, private = supplied()
    # Remove an actual C2 row, keeping every other scored failure/success visible.
    index = next(i for i, row in enumerate(scored) if row.cell == "C2")
    report = compare(design, scored[:index] + scored[index + 1:], private[:index] + private[index + 1:])
    assert report.audit.expected_trials == len(design.trials)
    assert report.audit.missing_trials == 1
    assert report.difference is None


def test_failed_scheduled_row_preserved_but_no_inference():
    design, scored, private = supplied()
    index = next(i for i, row in enumerate(scored) if row.cell == "C1")
    scored, private = replace_outcome(scored, private, index, failures=("public-runtime-failure",))
    report = compare(design, scored, private)
    assert report.audit.status == "complete"
    assert report.audit.failed_scored_rows == 1
    assert report.failed_pair_members == 1
    assert report.difference is None


def test_unknown_and_legacy_values_remain_explicit():
    design, scored, private = supplied()
    index = next(i for i, row in enumerate(scored) if row.cell == "C2")
    scored, private = replace_outcome(scored, private, index, utility_success=None, utility_status="unknown")
    report = compare(design, scored, private)
    assert report.unknown_pair_members == 1
    assert report.difference is None
    scored, private = replace_outcome(scored, private, index,
        utility_success=True, utility_status="success", utility_basis="legacy-call-proxy-v1")
    report = compare(design, scored, private)
    assert report.legacy_utility_pair_members == 1
    assert report.interpretation == "legacy-proxy"
    assert report.difference is None


def test_fixed_seed_is_deterministic_under_row_order_permutations():
    design, scored, private = supplied(tasks=3)
    for index, outcome in enumerate(scored):
        if outcome.family_id == "public-family-0" and outcome.cell == "C2":
            scored, private = replace_outcome(scored, private, index,
                                              utility_success=False, utility_status="failure")
    left = compare(design, scored, private)
    right = compare(design, tuple(reversed(scored)), tuple(reversed(private)))
    assert (left.difference, left.low, left.high) == (right.difference, right.low, right.high)
    assert left.seed == right.seed == 17
    assert left.resamples == 10000


def test_unique_labels_or_pinned_metadata_do_not_authenticate_independence():
    design, scored, private = supplied(tasks=20, repeats=(1,))
    support = FamilySupport(schedule_sha256=record_hash(design),
        supported_family_ids=tuple(sorted(set(design.task_family_by_id.values()))),
        reviewer_id="public-fake-reviewer", review_evidence_sha256="ab" * 32)
    report = compare(design, scored, private, family_support=support,
                     expected_family_support_sha256=record_hash(support))
    assert report.support_binding == "pinned-unverified"
    assert report.supported_observable_families == 0
    assert report.interpretation == "exploratory"


def test_outcome_only_legacy_entrypoint_never_bootstraps_unproven_pairs():
    _, scored, _ = supplied()
    result = paired_family_bootstrap([row.model_dump(mode="json") for row in scored],
                                     before="C1", after="C2")
    assert result["difference"] is result["low"] is result["high"] is None
    assert result["family_count"] == 0
