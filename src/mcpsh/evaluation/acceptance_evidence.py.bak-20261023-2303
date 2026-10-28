"""D7 verified bytes -> attributable acceptance inputs. No reader, I/O or dispatch.

External pins and authorization are separate. Every authentication defaults false;
an edition's self-seal cannot establish reviewer, custody, prices or probe authority.
"""

from datetime import datetime
from typing import TYPE_CHECKING, Literal

from pydantic import Field

from mcpsh.evidence.models import EditionAuthority
from mcpsh.records import TrialOutcome, typed_hash

from .acceptance import (
    AcceptanceRecord, AcceptanceReport, ConformanceEvidence, ControlEvidence,
    Criterion, CustodyProvenance, MatrixDesign, evaluate_acceptance,
)
from .design import FamilySupport, ObservedTrial, ScheduleDesign, record_hash
from mcpsh.calibration.approvals import ThresholdContext, ThresholdInputs, ExternalConfirmation
from mcpsh.calibration.protocol_models import FullDevelopmentProposal, DevelopmentSummary

if TYPE_CHECKING:
    from mcpsh.evidence.reader import VerifiedEdition


class DossierAuthority(AcceptanceRecord):
    edition: EditionAuthority
    manifest_typed_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    design_sha256: str | None = None
    schedule_sha256: str | None = None
    family_support_sha256: str | None = None
    custody_sha256: str | None = None
    conformance_sha256: str | None = None
    conformance_report_sha256: str | None = None
    requirements_report_sha256: str | None = None
    requirements_inventory_sha256: str | None = None
    producer_authority_sha256: str | None = None
    probe_raw_sha256: dict[str, str] = Field(default_factory=dict)
    controls_sha256: str | None = None
    prices_sha256: str | None = None
    settlements_sha256: str | None = None
    threshold_context_sha256: str | None = None
    threshold_current_inputs_sha256: str | None = None
    reviewer_metadata_sha256: str | None = None
    integrator_metadata_sha256: str | None = None
    semantic_definition_sha256: str | None = None


class DossierAuthentication(AcceptanceRecord):
    edition_authority_confirmed: bool = False
    custody_confirmed: bool = False
    family_independence_confirmed: bool = False
    conformance_confirmed: bool = False
    controls_confirmed: bool = False
    prices_confirmed: bool = False
    settlement_receipts_confirmed: bool = False
    threshold_external_confirmation_verified: bool = False


class ModelPrice(AcceptanceRecord):
    snapshot_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    dated_at: str = Field(min_length=1)
    input_microunits_per_million: int = Field(ge=0)
    output_microunits_per_million: int = Field(ge=0)
    cached_read_microunits_per_million: int | None = Field(default=None, ge=0)
    cache_creation_microunits_per_million: int | None = Field(default=None, ge=0)


class PriceAuthority(AcceptanceRecord):
    manifest_typed_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    prices: dict[str, ModelPrice]
    basis: Literal["dated-price-estimate"] = "dated-price-estimate"


class SettlementWitness(AcceptanceRecord):
    attempt_id: str
    settlement_reference: str
    usage_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    accounting_row_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class SettlementAuthority(AcceptanceRecord):
    source_index_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    witnesses: tuple[SettlementWitness, ...]


class ConformanceAttachment(AcceptanceRecord):
    evidence: ConformanceEvidence
    producer_report: dict
    requirements_report: dict


class AcceptanceSources(AcceptanceRecord):
    design: MatrixDesign | None = None
    schedule: ScheduleDesign | None = None
    family_support: FamilySupport | None = None
    custody: CustodyProvenance | None = None
    conformance: ConformanceAttachment | None = None
    controls: tuple[ControlEvidence, ...] = ()
    prices: PriceAuthority | None = None
    settlements: SettlementAuthority | None = None


class ThresholdAttachment(AcceptanceRecord):
    """Use keyword arguments from calibration.approvals; bytes stay private.

    A plain immutable argument bundle avoids another definition of D4's approval
    schema. The exact closed records are validated by the existing approval API.
    """
    proposal: FullDevelopmentProposal
    summary: DevelopmentSummary
    context: ThresholdContext
    current_inputs: ThresholdInputs
    reviewer_metadata: bytes | None = None
    integrator_metadata: bytes | None = None
    external_confirmation: ExternalConfirmation | None = None


class AcceptanceDossier(AcceptanceRecord):
    version: Literal["verified-edition-acceptance-v1"] = "verified-edition-acceptance-v1"
    edition_id: str
    source_index_sha256: str
    authority_binding: Literal["missing", "mismatched", "pinned"]
    authentication: Literal["unconfirmed", "trusted-caller-confirmed"]
    outcomes: tuple[TrialOutcome, ...]
    observed_rows: tuple[ObservedTrial, ...]
    inspection_complete: bool
    criteria: tuple[Criterion, ...]
    acceptance: AcceptanceReport | None
    cross_axes: dict | None = None
    recommendation: Literal["do-not-accept", "collect-required-evidence", "eligible-for-independent-review"]
    independent_product_acceptance: Literal["pending"] = "pending"
    runtime_authorized: Literal[False] = False


def _bound(value, pin):
    return value is not None and pin is not None and record_hash(value) == pin


def assemble_acceptance_dossier(edition: "VerifiedEdition", *, authority: DossierAuthority,
        expected_authority_sha256: str | None, sources: AcceptanceSources,
        authentication: DossierAuthentication | None = None,
        threshold_attachment: ThresholdAttachment | None = None,
        now: datetime | None = None) -> AcceptanceDossier:
    """Consume D7 validation/inspection; never discover/read another edition or rescore."""
    from mcpsh.evidence.reader import VerifiedEdition, inspect_edition, usage_known

    if type(edition) is not VerifiedEdition:
        raise TypeError("D7 VerifiedEdition required; caller narrative is not an edition")
    # D7 owns all raw evidence parsing and structural joins. Rejected input stays a
    # D7 rejection; no second parser or fabricated zero-row edition is substituted.
    index, manifest, trials, observers, oracles = edition.validate()
    inspection = inspect_edition(edition)
    unknown_trials = inspection.get("unknown_trials")
    inspection_complete = (inspection.get("structural_integrity") == "verified"
        and inspection.get("evidence_complete") is True and type(unknown_trials) is list and not unknown_trials)
    auth = authentication or DossierAuthentication()
    criteria = []

    def add(key, verdict, reason, **counts):
        criteria.append(Criterion(criterion_id=key, verdict=verdict, reason=reason, counts=counts))

    authority_state = "missing" if expected_authority_sha256 is None else (
        "pinned" if record_hash(authority) == expected_authority_sha256 else "mismatched")
    root_ok = (authority_state == "pinned" and edition.authority == authority.edition
               and record_hash(manifest) == authority.manifest_typed_sha256)
    add("external-edition-source-authority", "fail" if authority_state == "mismatched" or
        (authority_state == "pinned" and not root_ok) else "pass" if root_ok else "pending",
        "External edition/candidate/revision/source/raw-manifest and typed-manifest pins are separate from its self-seal.")
    add("external-edition-authorization", "pass" if root_ok and auth.edition_authority_confirmed else "pending",
        "Structural integrity does not authenticate the external authority or truthful execution.")
    add("original-evidence-completeness", "pass" if inspection_complete else "pending",
        "All D7 unknown/missing evidence remains scheduled; no rescore or replacement rows.",
        scheduled=len(index.scheduled_trial_ids), supplied=len(trials),
        unknown=len(unknown_trials) if type(unknown_trials) is list else None)
    original = tuple(row.outcome for row in trials)
    observer_map = {row.trial_id: row for row in observers}
    observed = []
    family_map = manifest.settings.get("family_by_model", {})
    invalid_repeats = 0
    for trial in trials:
        outcome = trial.outcome
        observer = observer_map.get(outcome.trial_id)
        if type(trial.repeat) is int and not 1 <= trial.repeat <= 5:
            invalid_repeats += 1
        family = family_map.get(outcome.model_id) if type(family_map) is dict else None
        observed.append(ObservedTrial(outcome=outcome,
            repeat=trial.repeat if type(trial.repeat) is int and 1 <= trial.repeat <= 5 else None,
            platform_scope=observer.platform_scope if observer is not None else None,
            model_family_id=family if type(family) is str and family else None,
            outcome_sha256=record_hash(outcome), row_evidence_sha256=record_hash(trial)))
    add("actual-repeat-domain", "fail" if invalid_repeats else "pass",
        "Out-of-domain actual repeats remain original evidence and cannot be guessed/rebased into the primary design.",
        invalid=invalid_repeats)
    design_ok = root_ok and _bound(sources.design, authority.design_sha256)
    schedule_ok = root_ok and _bound(sources.schedule, authority.schedule_sha256)
    if design_ok and schedule_ok:
        design_ok = (sources.design.task_family_by_id == sources.schedule.task_family_by_id
            and sources.design.model_family_by_id == sources.schedule.model_family_by_id
            and sources.design.public_task_hash == manifest.task_hash
            and sources.schedule.mode == index.mode and sources.schedule.platform_scope == index.platform_scope
            and sources.schedule.seed == manifest.seed
            and sources.schedule.repeats == tuple(range(1, sources.design.repeats + 1))
            and [r.model_dump(mode="json") for r in sources.design.trials] ==
                [r.model_dump(mode="json") for r in sources.schedule.trials]
            and tuple(r.trial_id for r in sources.schedule.trials) == index.scheduled_trial_ids)
        schedule_ok = design_ok
    add("external-design-and-schedule", "pass" if design_ok and schedule_ok else "pending",
        "Both externally pinned schedules must cover the original ordered edition, with actual repeats retained.")
    if index.mode != "live":
        add("live-evidence-provenance", "pending", "Replay/diagnostics cannot acquire live, heldout or paid-usage credit.")
    else:
        add("live-evidence-provenance", "pass", "Live label retained; actual evidence and authorization are checked separately.")
    reuse = sum(row.reuse is not None for row in trials)
    add("independent-new-samples", "pending" if reuse else "pass",
        "Reused parent evidence is not a new independent sample; D7 owns explicit parent lineage.", reused=reuse)
    custody_ok = root_ok and _bound(sources.custody, authority.custody_sha256) and auth.custody_confirmed
    add("external-custody-admission", "pass" if custody_ok else "pending",
        "Custody/label authorship requires an external pin and separate trusted confirmation.")
    retired = sources.custody is not None and sources.custody.retired_or_exposed or (
        oracles is not None and any(entry.oracle.split == "retired" for entry in oracles.cases))
    heldout_ok = (index.mode == "live" and manifest.settings.get("corpus_phase") == "heldout"
                  and oracles is not None and all(entry.oracle.split == "heldout" for entry in oracles.cases)
                  and custody_ok and not retired and sources.custody.label_adjudication == "pass"
                  and sources.custody.lineage_adjudication == "pass"
                  and sources.custody.data_author_id not in sources.custody.source_author_ids
                  and sources.custody.label_reviewer_id not in (
                      *sources.custody.source_author_ids, sources.custody.data_author_id)
                  and bool(sources.custody.label_reviewer_id))
    add("heldout-sample-admission", "fail" if retired else "pass" if heldout_ok else "pending",
        "Replay, development, retired or unconfirmed custody cannot become heldout samples by relabeling an edition.")
    family_ok = root_ok and _bound(sources.family_support, authority.family_support_sha256)
    add("external-family-support", "pass" if family_ok and auth.family_independence_confirmed else "pending",
        "A label count or supplied family-support hash is not independent-family authentication.")
    conformance = None
    attachment = sources.conformance
    try:
        if root_ok and attachment is not None:
            producer, requirements = attachment.producer_report, attachment.requirements_report
            platform = requirements.get("platforms", {}).get(index.platform_scope, {})
            required = set(platform.get("required_probe_ids", ()))
            probe_rows = producer.get("conformance", ())
            probes = {row.get("probe_id"): row for row in probe_rows if type(row) is dict}
            checks = {check.check_id: check for check in attachment.evidence.checks}
            conform_ok = (_bound(attachment.evidence, authority.conformance_sha256)
                and type(producer.get("schema_version")) is int and producer.get("schema_version") == 1
                and type(requirements.get("schema_version")) is int and requirements.get("schema_version") == 1
                and typed_hash(producer) == authority.conformance_report_sha256
                and typed_hash(requirements) == authority.requirements_report_sha256
                and producer.get("authority_sha256") == authority.producer_authority_sha256
                and producer.get("source_index_sha256") == edition.authority.index_sha256
                and producer.get("bindings_complete") is True and producer.get("all_selected_probes_creditable") is True
                and requirements.get("inventory_sha256") == authority.requirements_inventory_sha256
                and requirements.get("authority_valid") is True and requirements.get("audit_valid") is True
                and platform.get("verdict") == "passed" and bool(required)
                and type(platform.get("required_requirements")) is int and platform["required_requirements"] > 0
                and platform.get("covered_requirements") == platform["required_requirements"]
                and len(platform.get("requirements", ())) == platform["required_requirements"]
                and all(item.get("covered") is True and not item.get("violations")
                        for item in platform["requirements"])
                and (index.platform_scope != "filesystem-posix" or platform.get("filesystem_proof") is True)
                and set(attachment.evidence.required_check_ids) == required
                and len(attachment.evidence.required_check_ids) == len(required)
                and len(checks) == len(attachment.evidence.checks)
                and len(probes) == len(probe_rows) and required <= set(probes)
                and required <= set(checks) and required <= set(authority.probe_raw_sha256)
                and all(probes[key].get("state") == "verified" and probes[key].get("creditable") is True
                        and checks[key].state == "executed" and checks[key].verdict == "pass"
                        and len(authority.probe_raw_sha256[key]) == 64
                        and all(c in "0123456789abcdef" for c in authority.probe_raw_sha256[key])
                        and checks[key].evidence_sha256 == authority.probe_raw_sha256[key] for key in required)
                and attachment.evidence.platform_scope == index.platform_scope
                and attachment.evidence.manifest_sha256 == record_hash(manifest))
            if conform_ok and auth.conformance_confirmed:
                conformance = attachment.evidence
    except (ValueError, TypeError, KeyError, AttributeError, OverflowError):
        conformance = None
    add("attributable-full-conformance", "pass" if conformance is not None else "pending",
        "D7 per-probe reports alone cannot establish D6 normative whole-suite conformance.")
    controls = sources.controls if root_ok and authority.controls_sha256 is not None and auth.controls_confirmed and (
        typed_hash([control.model_dump(mode="json") for control in sources.controls]) == authority.controls_sha256) else ()
    add("external-controls-admission", "pass" if controls else "pending",
        "Independent control records require external pins/confirmation; no roles are inferred from observed effects.")
    prices_ok = root_ok and _bound(sources.prices, authority.prices_sha256)
    if prices_ok:
        prices_ok = (sources.prices.manifest_typed_sha256 == record_hash(manifest)
                     and set(sources.prices.prices) == set(manifest.model_ids))
        if prices_ok:
            for model, quote in sources.prices.prices.items():
                actual = manifest.prices.get(model)
                if type(actual) is not dict or any(typed_hash(actual.get(key)) != typed_hash(value)
                                                 for key, value in quote.model_dump(mode="json").items()):
                    prices_ok = False
    add("external-price-admission", "pass" if index.mode == "live" and prices_ok and auth.prices_confirmed else "pending",
        "Pinned dated estimates are not paid/provider billing receipts; missing price authority stays pending.")
    receipts_ok = (root_ok and _bound(sources.settlements, authority.settlements_sha256)
                   and sources.settlements.source_index_sha256 == edition.authority.index_sha256)
    witnesses = {row.attempt_id: row for row in sources.settlements.witnesses} if receipts_ok else {}
    if receipts_ok and len(witnesses) != len(sources.settlements.witnesses):
        receipts_ok = False
    usage_unknown = 0
    all_attempt_ids = []
    for row in trials:
        if index.mode != "live":
            continue
        if row.outcome.cost_status != "settled" or row.outcome.cost_microunits is None or not row.model_attempts:
            usage_unknown += 1
        accounting = {item.attempt_id: item for item in row.accounting}
        for attempt in row.model_attempts:
            all_attempt_ids.append(attempt.attempt_id)
            cost, witness = accounting.get(attempt.attempt_id), witnesses.get(attempt.attempt_id)
            if (not usage_known(attempt) or cost is None or witness is None or cost.reserved_microunits is None
                    or cost.cost_microunits is None or not cost.settlement_reference
                    or witness.settlement_reference != cost.settlement_reference
                    or witness.settlement_reference != attempt.settlement_reference
                    or witness.usage_sha256 != typed_hash(attempt.usage)
                    or witness.accounting_row_sha256 != record_hash(cost)):
                usage_unknown += 1
    if set(all_attempt_ids) != set(witnesses) or len(all_attempt_ids) != len(set(all_attempt_ids)):
        receipts_ok = False
    add("actual-usage-settlement-evidence", "pass" if index.mode == "live" and receipts_ok
        and not usage_unknown and auth.settlement_receipts_confirmed else "pending",
        "Unknown usage/reservation/receipts are not zero-cost successes; original rows remain unchanged.", unknown=usage_unknown)
    thresholds = None
    if root_ok and threshold_attachment is not None and now is not None:
        from mcpsh.calibration.approvals import project_approved_thresholds

        inputs = threshold_attachment.current_inputs
        models = {model.model_id: model for model in inputs.models}
        actual_families = manifest.settings.get("family_by_model", {})
        threshold_scope_ok = (heldout_ok and _bound(inputs, authority.threshold_current_inputs_sha256)
            and inputs.heldout_manifest_sha256 == record_hash(manifest)
            and inputs.source_sha256 == manifest.code_hash
            and inputs.corpus_seal_sha256 == manifest.split_hash
            and inputs.semantic_definition_sha256 == authority.semantic_definition_sha256
            and set(models) == set(manifest.model_ids)
            and type(actual_families) is dict
            and all(actual_families.get(model) == body.family_id for model, body in models.items())
            and all(row.model_attempts and all(attempt.requested_model_id in models and
                    attempt.provider_id == models[attempt.requested_model_id].provider_id
                    for attempt in row.model_attempts) for row in trials))
        if threshold_scope_ok:
            thresholds = project_approved_thresholds(proposal=threshold_attachment.proposal,
                summary=threshold_attachment.summary, context=threshold_attachment.context, current_inputs=inputs,
                now=now, expected_context_sha256=authority.threshold_context_sha256,
                reviewer_metadata=threshold_attachment.reviewer_metadata,
                expected_reviewer_sha256=authority.reviewer_metadata_sha256,
                integrator_metadata=threshold_attachment.integrator_metadata,
                expected_integrator_sha256=authority.integrator_metadata_sha256,
                external_confirmation=threshold_attachment.external_confirmation,
                external_confirmation_verified=auth.threshold_external_confirmation_verified,
                fresh_custody_confirmed=auth.custody_confirmed)
    add("external-threshold-approval-admission", "pass" if thresholds is not None else "pending",
        "Only the existing raw-pinned external approval validator can supply a floor; source drift blocks old metadata.")
    acceptance = None
    if design_ok and schedule_ok:
        acceptance = evaluate_acceptance(manifest=manifest, design=sources.design, outcomes=original,
            observed_rows=tuple(observed), thresholds=thresholds,
            custody=sources.custody if custody_ok else None, conformance=conformance, controls=controls,
            family_support=sources.family_support if family_ok else None,
            expected_family_support_sha256=authority.family_support_sha256,
            independence_authenticated=auth.family_independence_confirmed and auth.edition_authority_confirmed)
    verdicts = {criterion.verdict for criterion in criteria}
    recommendation = "do-not-accept" if "fail" in verdicts or acceptance is not None and (
        acceptance.recommendation == "do-not-accept") else "collect-required-evidence"
    if (auth.edition_authority_confirmed and verdicts == {"pass"} and acceptance is not None
            and acceptance.recommendation == "eligible-for-independent-review"):
        recommendation = "eligible-for-independent-review"
    from .diagnostics import axis_evidence_from_trial, summarize_cross_axes

    axes = tuple(axis_evidence_from_trial(trial, observer=observer_map.get(trial.outcome.trial_id),
                                         platform_scope=index.platform_scope) for trial in trials)
    policy = {entry.oracle.task_id: entry.oracle for entry in oracles.cases} if oracles else None
    cross_axes = summarize_cross_axes(axes, expected_schedule=sources.schedule if schedule_ok else None,
                                     oracle_by_task=policy).model_dump(mode="json")
    return AcceptanceDossier(edition_id=index.edition_id, source_index_sha256=edition.authority.index_sha256,
        authority_binding=authority_state, authentication="trusted-caller-confirmed" if
        root_ok and auth.edition_authority_confirmed else "unconfirmed", outcomes=original,
        observed_rows=tuple(observed), inspection_complete=inspection_complete,
        criteria=tuple(criteria), acceptance=acceptance, cross_axes=cross_axes, recommendation=recommendation)
