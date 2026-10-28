"""Synthetic D7 contract fixtures only; no evidence reader or dossier runs in construction."""

import hashlib
from types import SimpleNamespace

import pytest

from mcpsh.evaluation.acceptance_evidence import (
    AcceptanceSources, DossierAuthentication, DossierAuthority, assemble_acceptance_dossier,
)
from mcpsh.evidence.models import EditionAuthority, EvidenceTrial, InputPins
from mcpsh.evidence.reader import VerifiedEdition
from mcpsh.records import ExperimentManifest, TrialOutcome, typed_hash


def fixture(monkeypatch, mode="replay"):
    # Mock D7's already-validated/inspected contract, never pretend these bytes are
    # a real edition or external authority. All values are explicit test fakes.
    h = "ab" * 32
    manifest = ExperimentManifest(edition_id="fake-edition", mode=mode, platform_scope="synthetic-memory",
        code_hash=h, lock_hash=h, protocol_hash=h, task_hash=h, catalog_hash=h, policy_hash=h,
        scorer_hash=h, observer_hash=h, split_hash=h, seed=1,
        model_ids=("fake-a", "fake-b"), settings={"family_by_model": {"fake-a": "family-a", "fake-b": "family-b"}})
    manifest_raw = manifest.model_dump_json().encode()
    pins = InputPins(**{key: getattr(manifest, key) for key in InputPins.model_fields})
    authority = EditionAuthority(index_sha256=hashlib.sha256(b"fake-index").hexdigest(),
        manifest_sha256=hashlib.sha256(manifest_raw).hexdigest(), candidate_commit="a" * 40,
        revision=1, edition_id="fake-edition", mode=mode, platform_scope="synthetic-memory", input_pins=pins)
    outcomes, trials = [], []
    for index in range(2):
        failed = index == 1
        outcome = TrialOutcome(trial_id=f"fake-trial-{index}", task_id="fake-task", family_id="fake-family",
            condition="clean", cell="C1", selector="fake-selector", execution_mode=mode,
            model_id="fake-a" if mode == "live" else None,
            selection_success=False, utility_success=None if failed else True,
            utility_status="unknown" if failed else "success", utility_basis="semantic-v2",
            prohibited_intent=False, validated_prohibited_attempts=0, gate_classified_prohibited_calls=0,
            blocked_prohibited_calls=0, gate_false_negative_calls=0, effect="unknown",
            observation_complete=False, call_count=0, selected_call_count=None,
            selection_journal_complete=False, failures=("fake-scheduled-failure",) if failed else (),
            cost_microunits=None if failed or mode == "live" else 0,
            cost_status="unknown" if failed or mode == "live" else "non-model",
            trace_hash=h, observation_hash=h, latency_seconds=0.0)
        outcomes.append(outcome)
        trials.append(EvidenceTrial(outcome=outcome, repeat=1, trace=None, results=None,
            model_attempts=(), accounting=(), final_response=None, result_captures=None))
    index = SimpleNamespace(edition_id="fake-edition", mode=mode, platform_scope="synthetic-memory",
                            scheduled_trial_ids=tuple(row.trial_id for row in outcomes))
    monkeypatch.setattr(VerifiedEdition, "validate", lambda self: (index, manifest, tuple(trials), (), None))
    monkeypatch.setattr("mcpsh.evidence.reader.inspect_edition", lambda edition: {
        "structural_integrity": "verified", "evidence_complete": False,
        "unknown_trials": [{"trial_id": row.trial_id, "reasons": ["raw_trace_unavailable"]} for row in outcomes]})
    edition = VerifiedEdition(authority, b"fake-index", (("manifest", manifest_raw),))
    root = DossierAuthority(edition=authority, manifest_typed_sha256=typed_hash(manifest.model_dump(mode="json")))
    return edition, root, AcceptanceSources(), tuple(outcomes)


def dossier(edition, authority, sources, **kwargs):
    return assemble_acceptance_dossier(edition, authority=authority,
        expected_authority_sha256=typed_hash(authority.model_dump(mode="json")), sources=sources, **kwargs)


def criterion(result, code):
    return next(row for row in result.criteria if row.criterion_id == code)


def test_pinned_integrity_does_not_authenticate_custody_or_thresholds(monkeypatch):
    edition, root, sources, outcomes = fixture(monkeypatch)
    result = dossier(edition, root, sources)
    assert result.authority_binding == "pinned"
    assert result.authentication == "unconfirmed"
    assert criterion(result, "external-custody-admission").verdict == "pending"
    assert criterion(result, "external-threshold-approval-admission").verdict == "pending"
    assert result.outcomes == outcomes
    assert result.independent_product_acceptance == "pending"


@pytest.mark.parametrize("change", [{"candidate_commit": "b" * 40}, {"edition_id": "other-edition"}])
def test_wrong_external_candidate_or_edition_rejected_without_dropping_rows(monkeypatch, change):
    edition, root, sources, outcomes = fixture(monkeypatch)
    expected = root.model_copy(update={"edition": root.edition.model_copy(update=change)})
    result = dossier(edition, expected, sources)
    assert criterion(result, "external-edition-source-authority").verdict == "fail"
    assert result.outcomes == outcomes
    assert result.recommendation == "do-not-accept"


def test_wrong_source_pin_cannot_become_new_authority(monkeypatch):
    edition, root, sources, outcomes = fixture(monkeypatch)
    pins = root.edition.input_pins.model_copy(update={"code_hash": "ff" * 32})
    expected = root.model_copy(update={"edition": root.edition.model_copy(update={"input_pins": pins})})
    result = dossier(edition, expected, sources)
    assert criterion(result, "external-edition-source-authority").verdict == "fail"
    assert result.outcomes == outcomes


def test_replay_cannot_be_promoted_even_with_authentication_flags(monkeypatch):
    edition, root, sources, _ = fixture(monkeypatch)
    result = dossier(edition, root, sources, authentication=DossierAuthentication(
        edition_authority_confirmed=True, custody_confirmed=True, family_independence_confirmed=True,
        prices_confirmed=True, settlement_receipts_confirmed=True))
    assert criterion(result, "live-evidence-provenance").verdict == "pending"
    assert criterion(result, "actual-usage-settlement-evidence").verdict == "pending"
    assert result.runtime_authorized is False


def test_failed_unknown_usage_rows_never_turn_into_zero_cost_or_disappear(monkeypatch):
    edition, root, sources, outcomes = fixture(monkeypatch, mode="live")
    result = dossier(edition, root, sources)
    assert len(result.outcomes) == 2
    assert result.outcomes[1].failures == outcomes[1].failures
    assert result.outcomes[1].cost_microunits is None
    assert result.outcomes[1].utility_success is None
    assert criterion(result, "actual-usage-settlement-evidence").verdict == "pending"


def test_missing_external_pin_not_replaced_by_edition_self_seal(monkeypatch):
    edition, root, sources, outcomes = fixture(monkeypatch)
    result = assemble_acceptance_dossier(edition, authority=root, expected_authority_sha256=None, sources=sources)
    assert result.authority_binding == "missing"
    assert result.outcomes == outcomes
    assert result.acceptance is None


def test_caller_narrative_is_not_a_verified_edition():
    with pytest.raises(TypeError, match="VerifiedEdition"):
        assemble_acceptance_dossier(SimpleNamespace(), authority=None,
                                    expected_authority_sha256=None, sources=AcceptanceSources())


def test_d7_rejection_of_missing_scheduled_failure_is_not_an_empty_pass(monkeypatch):
    from mcpsh.evidence.reader import EvidenceRejected

    edition, root, sources, _ = fixture(monkeypatch)

    def reject(self):
        raise EvidenceRejected("synthetic missing scheduled row")

    monkeypatch.setattr(VerifiedEdition, "validate", reject)
    with pytest.raises(EvidenceRejected):
        dossier(edition, root, sources)


def test_altered_threshold_source_does_not_reach_approval_projection(monkeypatch):
    from datetime import datetime, timezone
    from mcpsh.calibration.approvals import ThresholdContext, ThresholdInputs, ThresholdModel, model_scope_hash
    from mcpsh.calibration.protocol_models import DevelopmentSummary, FullDevelopmentProposal
    from mcpsh.evaluation.acceptance_evidence import ThresholdAttachment

    edition, root, sources, _ = fixture(monkeypatch)
    h = "ab" * 32
    summary = DevelopmentSummary(evidence_state="no-evidence", plan_sha256=h, settings_sha256=h,
        outcomes_sha256=h, scheduled_slots=0, supplied_slots=0, missing_slots=0, failed_slots=0,
        unknown_cost_slots=0, incomplete_observation_slots=0, groups=(), repeat_diagnostics={},
        paired_retention=(), next_action="collect-development-evidence", proposed_repeats_for_both_arms=3)
    proposal = FullDevelopmentProposal(plan_sha256=h, settings_sha256=h, full36_summary_sha256=typed_hash(
        summary.model_dump(mode="json")), outcomes_sha256=h, proposed_repeats_for_both_arms=3,
        rationale="Synthetic test metadata only", retention_decision="pending")
    models = (ThresholdModel(arm_slot="a", provider_id="fake-a", model_id="fake-a", family_id="family-a"),
              ThresholdModel(arm_slot="b", provider_id="fake-b", model_id="fake-b", family_id="family-b"))
    inputs = ThresholdInputs(proposal_sha256=typed_hash(proposal.model_dump(mode="json")),
        full36_plan_sha256=h, full36_summary_sha256=typed_hash(summary.model_dump(mode="json")),
        full36_outcomes_sha256=h, settings_sha256=h, source_sha256="ff" * 32,
        model_configuration_sha256=model_scope_hash(models), semantic_definition_sha256=h,
        heldout_manifest_sha256=root.manifest_typed_sha256, corpus_seal_sha256=h, models=models, repeats=3)
    context = ThresholdContext(inputs=inputs, expected_integrator_id="fake-int",
        source_author_ids=("fake-author",), proposal_author_ids=("fake-author",))
    root = root.model_copy(update={"threshold_current_inputs_sha256": typed_hash(inputs.model_dump(mode="json")),
                                  "semantic_definition_sha256": h})
    called = []
    monkeypatch.setattr("mcpsh.calibration.approvals.project_approved_thresholds", lambda **kwargs: called.append(kwargs))
    result = dossier(edition, root, sources, threshold_attachment=ThresholdAttachment(
        proposal=proposal, summary=summary, context=context, current_inputs=inputs),
        authentication=DossierAuthentication(threshold_external_confirmation_verified=True),
        now=datetime(2030, 1, 1, tzinfo=timezone.utc))
    assert called == []
    assert criterion(result, "external-threshold-approval-admission").verdict == "pending"
