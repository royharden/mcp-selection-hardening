"""Source-only regressions: no decision/custody is authenticated by a JSON field."""

from datetime import datetime, timezone

import pytest

from mcpsh.calibration.approvals import ThresholdContext, ThresholdInputs, ThresholdModel, model_scope_hash
from mcpsh.calibration.protocol_models import DevelopmentSummary, FullDevelopmentProposal
from mcpsh.records import typed_hash
from mcpsh.runner.thresholds import assess_threshold_metadata


def packet():
    pin = "a" * 64
    summary = DevelopmentSummary(evidence_state="no-evidence", plan_sha256=pin,
        settings_sha256=pin, outcomes_sha256=pin, scheduled_slots=0, supplied_slots=0,
        missing_slots=0, failed_slots=0, unknown_cost_slots=0, incomplete_observation_slots=0,
        groups=(), repeat_diagnostics={}, paired_retention=(),
        next_action="collect-development-evidence", proposed_repeats_for_both_arms=3)
    proposal = FullDevelopmentProposal(plan_sha256=pin, settings_sha256=pin,
        full36_summary_sha256=typed_hash(summary.model_dump(mode="json")), outcomes_sha256=pin,
        proposed_repeats_for_both_arms=3, rationale="Public source-only test; no measured evidence.",
        retention_decision="pending")
    models = (ThresholdModel(arm_slot="public-a", provider_id="openai", model_id="public-model-a", family_id="a"),
              ThresholdModel(arm_slot="public-b", provider_id="anthropic", model_id="public-model-b", family_id="b"))
    inputs = ThresholdInputs(proposal_sha256=typed_hash(proposal.model_dump(mode="json")),
        full36_plan_sha256=pin, full36_summary_sha256=typed_hash(summary.model_dump(mode="json")),
        full36_outcomes_sha256=pin, settings_sha256=pin, source_sha256=pin,
        model_configuration_sha256=model_scope_hash(models), semantic_definition_sha256=pin,
        heldout_manifest_sha256=pin, corpus_seal_sha256=pin, models=models, repeats=3)
    context = ThresholdContext(inputs=inputs, expected_integrator_id="public-int",
        source_author_ids=("public-source-author",), proposal_author_ids=("public-proposal-author",))
    return {"summary": summary.model_dump(mode="json"), "proposal": proposal.model_dump(mode="json"),
            "context": context.model_dump(mode="json")}, inputs, typed_hash(context.model_dump(mode="json"))


def test_matching_metadata_pins_never_generate_floor_or_authority():
    # Catches converting internally matching source-only metadata into an approval.
    supplied, inputs, context_pin = packet()
    result = assess_threshold_metadata(supplied, current_inputs=inputs,
        expected_context_sha256=context_pin, now=datetime(2026, 10, 23, tzinfo=timezone.utc))
    assert result.approved_thresholds is None
    assert result.public_status["approved_floor"] is None
    assert result.public_status["runtime_authorized"] is False
    assert result.public_status["external_authorization"] != "trusted-caller-confirmed"


def test_changed_current_source_is_not_replaced_by_old_context():
    # Catches validating the context against itself rather than independent current inputs.
    supplied, inputs, context_pin = packet()
    changed = inputs.model_copy(update={"source_sha256": "b" * 64})
    result = assess_threshold_metadata(supplied, current_inputs=changed,
        expected_context_sha256=context_pin, now=datetime(2026, 10, 23, tzinfo=timezone.utc))
    assert result.approved_thresholds is None
    assert "current-source-settings-model-semantic-or-corpus-inputs-changed" in result.public_status["issue_codes"]


def test_authentication_booleans_cannot_arrive_inside_metadata():
    supplied, inputs, context_pin = packet()
    supplied["external_confirmation_verified"] = True
    with pytest.raises(ValueError, match="exact threshold"):
        assess_threshold_metadata(supplied, current_inputs=inputs,
            expected_context_sha256=context_pin, now=datetime(2026, 10, 23, tzinfo=timezone.utc))
