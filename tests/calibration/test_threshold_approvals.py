"""Synthetic external-metadata protocol regressions; no real approval/run/floor.

All actors, hashes, counts and numeric decisions below are explicit test fakes.
Tests are authored only and remain unexecuted while Dirty Mode is open.
"""

import hashlib
from datetime import datetime, timezone
from itertools import product

import pytest

from mcpsh.calibration.approvals import (
    ExternalConfirmation, ThresholdContext, ThresholdDecision, ThresholdInputs, ThresholdModel,
    model_scope_hash, project_approved_thresholds, project_threshold_status, validate_threshold_approval,
)
from mcpsh.calibration.models import CLASSES
from mcpsh.calibration.protocol import propose_full36_thresholds
from mcpsh.calibration.protocol_models import DevelopmentSummary
from mcpsh.records import typed_hash

NOW = datetime(2030, 2, 1, tzinfo=timezone.utc)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def record_hash(record):
    return typed_hash(record.model_dump(mode="json"))


def packet(*, floor=0.8, context_updates=None, review_updates=None, integrator_updates=None,
           deny_all_successes=0, legacy=False):
    models = (ThresholdModel(arm_slot="fake-arm-a", provider_id="fake-provider-a",
                             model_id="fake-model-a", family_id="fake-family-a"),
              ThresholdModel(arm_slot="fake-arm-b", provider_id="fake-provider-b",
                             model_id="fake-model-b", family_id="fake-family-b"))
    cells = list(product(("model",), ("clean", "ambiguous", "poisoned"), ("C0", "C1", "C2")))
    cells += list(product(("keyword", "abstain", "deny-all"), ("clean",), ("control",)))
    groups = []
    for model, (selector, condition, cell), task_class in product(models, cells, ("all", *CLASSES)):
        size = 108 if task_class == "all" else 18
        success = (deny_all_successes if task_class == "all" else 0) if selector == "deny-all" else (
            96 if task_class == "all" else 16)
        groups.append({"arm_slot": model.arm_slot, "selector": selector, "condition": condition, "cell": cell,
            "task_class": task_class, "scheduled": size, "supplied": size, "missing": 0,
            "semantic_known": size, "semantic_successes": success, "semantic_unknown_or_proxy": 0,
            "legacy_proxy_trials": int(legacy), "failed_trials": 0, "unknown_selection_trials": 0,
            "incomplete_observations": 0, "unknown_cost_trials": 0, "scheduled_failure_records": 0})
    summary = DevelopmentSummary(evidence_state="supplied-complete", plan_sha256="11" * 32,
        settings_sha256="22" * 32, outcomes_sha256="33" * 32, scheduled_slots=2592, supplied_slots=2592,
        missing_slots=0, failed_slots=0, unknown_cost_slots=0, incomplete_observation_slots=0, groups=tuple(groups),
        repeat_diagnostics={model.arm_slot: {"missing_attempt_counter_rows": 0,
            "requires_transport_repair": False, "proposes_five_repeats": False} for model in models},
        paired_retention=({"decision": "inconclusive"}, {"decision": "inconclusive"}),
        next_action="request-independent-floor-review", proposed_repeats_for_both_arms=3)
    proposal = propose_full36_thresholds(summary)
    inputs = ThresholdInputs(proposal_sha256=record_hash(proposal), full36_plan_sha256=summary.plan_sha256,
        full36_summary_sha256=record_hash(summary), full36_outcomes_sha256=summary.outcomes_sha256,
        settings_sha256=summary.settings_sha256, source_sha256="44" * 32,
        model_configuration_sha256=model_scope_hash(models), semantic_definition_sha256="55" * 32,
        heldout_manifest_sha256="66" * 32, corpus_seal_sha256="77" * 32, models=models, repeats=3)
    context_fields = {"inputs": inputs, "expected_integrator_id": "fake-int",
        "source_author_ids": ("fake-source-author",), "proposal_author_ids": ("fake-proposal-author",),
        "data_author_ids": ("fake-data-author",), "corpus_state": "sealed-unexposed",
        "corpus_sealed_at": "2029-01-01T00:00:00Z"}
    context_fields.update(context_updates or {})
    context = ThresholdContext(**context_fields)
    scope = record_hash(context)
    fields = {"role": "independent-reviewer", "actor_id": "fake-reviewer", "decision": "approved",
        "context_sha256": scope, "absolute_utility_floor": floor, "rationale": "Explicit synthetic test decision.",
        "uncertainty_rule_approved": True, "issued_at": "2030-01-02T00:00:00Z",
        "expires_at": "2031-01-01T00:00:00Z"}
    fields.update(review_updates or {})
    review = ThresholdDecision(**fields)
    review_raw = review.model_dump_json().encode()
    fields = {**fields, "role": "integrator", "actor_id": "fake-int",
              "issued_at": "2030-01-03T00:00:00Z", "reviewer_metadata_sha256": sha(review_raw)}
    fields.update(integrator_updates or {})
    approval = ThresholdDecision(**fields)
    approval_raw = approval.model_dump_json().encode()
    confirmation = ExternalConfirmation(context_sha256=scope, reviewer_metadata_sha256=sha(review_raw),
        integrator_metadata_sha256=sha(approval_raw), reviewer_id=review.actor_id, integrator_id=approval.actor_id,
        external_authorization_reference="fake-external-reference", verified_at="2030-01-04T00:00:00Z")
    return {"proposal": proposal, "summary": summary, "context": context, "current_inputs": inputs,
        "now": NOW, "expected_context_sha256": scope, "reviewer_metadata": review_raw,
        "expected_reviewer_sha256": sha(review_raw), "integrator_metadata": approval_raw,
        "expected_integrator_sha256": sha(approval_raw), "external_confirmation": confirmation,
        "external_confirmation_verified": True, "fresh_custody_confirmed": True}


def test_missing_decisions_cannot_invent_floor_or_approval():
    args = packet()
    args.update(reviewer_metadata=None, integrator_metadata=None)
    report = validate_threshold_approval(**args)
    assert report.disposition != "eligible-for-separate-runtime-admission"
    assert report.approved_floor is None
    assert project_approved_thresholds(**args) is None


def test_raw_pins_and_confirmation_record_do_not_authenticate_themselves():
    args = packet()
    args["external_confirmation_verified"] = False
    report = validate_threshold_approval(**args)
    assert report.metadata_binding == "bound"
    assert report.external_authorization == "not-confirmed"
    assert report.disposition == "pending"
    assert report.approved_floor is None


def test_explicit_fake_external_confirmation_allows_projection_only():
    args = packet()
    report = validate_threshold_approval(**args)
    assert report.disposition == "eligible-for-separate-runtime-admission"
    assert report.approved_floor == 0.8
    projected = project_approved_thresholds(**args)
    assert projected.absolute_utility_floor == 0.8
    assert projected.full36_calibration_sha256 == args["current_inputs"].full36_summary_sha256
    assert report.runtime_authorized is False
    assert report.independent_product_acceptance == "pending"


@pytest.mark.parametrize("field", ["source_sha256", "settings_sha256", "model_configuration_sha256",
                                    "semantic_definition_sha256", "full36_outcomes_sha256"])
def test_changed_actual_inputs_invalidate_old_metadata(field):
    args = packet()
    args["current_inputs"] = args["current_inputs"].model_copy(update={field: "ff" * 32})
    assert validate_threshold_approval(**args).disposition == "invalid"


def test_stale_metadata_invalid_even_when_pins_match():
    args = packet(review_updates={"expires_at": "2030-01-10T00:00:00Z"})
    report = validate_threshold_approval(**args)
    assert "stale-or-future-dated-approval" in report.issue_codes
    assert project_approved_thresholds(**args) is None


def test_source_author_cannot_review_own_threshold():
    args = packet(review_updates={"actor_id": "fake-source-author"})
    report = validate_threshold_approval(**args)
    assert report.disposition == "invalid"
    assert "self-authored-dependent-or-wrong-role-approval" in report.issue_codes


@pytest.mark.parametrize("state", ["retired", "exposed"])
def test_retired_or_author_exposed_corpus_needs_fresh_custody(state):
    report = validate_threshold_approval(**packet(context_updates={"corpus_state": state}))
    assert report.disposition == "invalid"
    assert report.fresh_corpus_required is True


def test_sealing_before_review_is_allowed_but_late_approval_is_not():
    assert validate_threshold_approval(**packet()).disposition == "eligible-for-separate-runtime-admission"
    late = packet(context_updates={"heldout_started_at": "2030-01-02T00:00:00Z"})
    report = validate_threshold_approval(**late)
    assert "approval-not-frozen-before-heldout-execution" in report.issue_codes
    assert report.disposition == "invalid"


def test_missing_floor_and_failed_deny_all_contrast_do_not_pass():
    missing = validate_threshold_approval(**packet(floor=None))
    assert missing.disposition == "pending"
    assert missing.approved_floor is None
    wrong = validate_threshold_approval(**packet(deny_all_successes=108))
    assert wrong.disposition == "invalid"
    assert "deny-all-does-not-fail-explicit-approved-floor" in wrong.issue_codes


def test_floor_is_never_automatically_lowered():
    context = {"prior_absolute_floor": 0.9, "prior_approval_sha256": "ee" * 32}
    report = validate_threshold_approval(**packet(context_updates=context))
    assert "automatic-or-unapproved-floor-lowering" in report.issue_codes
    assert report.approved_floor is None


def test_proxy_development_summary_keeps_approval_pending():
    report = validate_threshold_approval(**packet(legacy=True))
    assert report.disposition == "pending"
    assert "full36-unknown-proxy-or-failed-group" in report.issue_codes


def test_duplicate_json_keys_rejected_after_raw_pin_match():
    args = packet()
    raw = b'{"role":"independent-reviewer",' + args["reviewer_metadata"][1:]
    args.update(reviewer_metadata=raw, expected_reviewer_sha256=sha(raw))
    report = validate_threshold_approval(**args)
    assert "external-metadata-pin-or-schema-invalid" in report.issue_codes
    assert report.disposition == "invalid"


def test_unconfirmed_fresh_custody_cannot_project_approval():
    args = packet()
    args["fresh_custody_confirmed"] = False
    report = validate_threshold_approval(**args)
    assert report.disposition == "pending"
    assert "fresh-custody-not-confirmed-by-owner" in report.issue_codes
    public = project_threshold_status(report)
    assert public["approved_floor"] is None
    assert public["runtime_authorized"] is False
