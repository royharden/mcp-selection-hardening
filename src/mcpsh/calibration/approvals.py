"""Pure external threshold-metadata binding, not an authorization/signing service.

No keys, accounts, files, current clock, approval generation or provider dispatch.
Pins bind bytes. External authorization must be established by a trusted caller.
"""

import hashlib
import json
from datetime import datetime
from itertools import product
from typing import Literal

from pydantic import Field, model_validator

from mcpsh.evaluation.acceptance import ApprovedThresholds
from mcpsh.records import strict_json_loads, typed_hash

from .models import CLASSES, DraftRecord
from .protocol_models import DevelopmentSummary, FullDevelopmentProposal


class ThresholdModel(DraftRecord):
    arm_slot: str = Field(min_length=1)
    provider_id: str = Field(min_length=1)
    model_id: str = Field(min_length=1)
    family_id: str = Field(min_length=1)


class ThresholdInputs(DraftRecord):
    """Actual current input digests supplied independently by the admission owner."""
    proposal_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    full36_plan_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    full36_summary_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    full36_outcomes_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    settings_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    model_configuration_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    semantic_basis: Literal["semantic-v2"] = "semantic-v2"
    semantic_definition_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    heldout_manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    corpus_seal_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    models: tuple[ThresholdModel, ThresholdModel]
    repeats: Literal[3, 5]


class ThresholdContext(DraftRecord):
    version: Literal["threshold-binding-v1"] = "threshold-binding-v1"
    inputs: ThresholdInputs
    expected_integrator_id: str = Field(min_length=1)
    source_author_ids: tuple[str, ...] = Field(min_length=1)
    proposal_author_ids: tuple[str, ...] = Field(min_length=1)
    data_author_ids: tuple[str, ...] = ()
    corpus_state: Literal["sealed-unexposed", "pending", "retired", "exposed"] = "pending"
    retired_corpus_seal_sha256s: tuple[str, ...] = ()
    corpus_sealed_at: str | None = None
    heldout_started_at: str | None = None
    prior_absolute_floor: float | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)
    prior_approval_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def prior_binding(self):
        if (self.prior_absolute_floor is None) != (self.prior_approval_sha256 is None):
            raise ValueError("a prior floor requires its externally pinned approval identity")
        return self


class ThresholdDecision(DraftRecord):
    version: Literal["threshold-decision-v1"] = "threshold-decision-v1"
    role: Literal["independent-reviewer", "integrator"]
    actor_id: str = Field(min_length=1)
    decision: Literal["approved", "pending", "rejected"]
    context_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    absolute_utility_floor: float | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)
    rationale: str = Field(min_length=1)
    uncertainty_method: Literal["paired-family-cluster-v2"] = "paired-family-cluster-v2"
    uncertainty_rule_approved: bool = False
    retention_margin: float = Field(default=0.05, ge=0.05, le=0.05)
    issued_at: str
    expires_at: str
    reviewer_metadata_sha256: str | None = None
    supersedes_approval_sha256: str | None = None
    explicitly_approves_lower_floor: bool = False


class ExternalConfirmation(DraftRecord):
    """Referenced external verification; this record does not authenticate itself."""
    context_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    reviewer_metadata_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    integrator_metadata_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    reviewer_id: str = Field(min_length=1)
    integrator_id: str = Field(min_length=1)
    external_authorization_reference: str = Field(min_length=1)
    verified_at: str


class ThresholdValidation(DraftRecord):
    version: Literal["threshold-binding-v1"] = "threshold-binding-v1"
    disposition: Literal["pending", "invalid", "eligible-for-separate-runtime-admission"]
    metadata_binding: Literal["missing", "invalid", "bound"]
    external_authorization: Literal["not-confirmed", "mismatched", "trusted-caller-confirmed"]
    context_sha256: str
    reviewer_metadata_sha256: str | None = None
    integrator_metadata_sha256: str | None = None
    approved_floor: float | None = None
    independent_reviewer_id: str | None = None
    approval_reference: str | None = None
    rationale: str | None = None
    issue_codes: tuple[str, ...]
    fresh_corpus_required: bool = False
    runtime_authorized: Literal[False] = False
    independent_product_acceptance: Literal["pending"] = "pending"


def _hash(record) -> str:
    return typed_hash(record.model_dump(mode="json"))


def model_scope_hash(models: tuple[ThresholdModel, ThresholdModel]) -> str:
    return typed_hash([model.model_dump(mode="json") for model in sorted(models, key=lambda m: m.arm_slot)])


def _time(value: str) -> datetime:
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("timezone-aware approval timestamp required")
    return result


def _read_metadata(raw: bytes | None, expected: str | None):
    if raw is None or expected is None:
        return None, None, "missing"
    if type(raw) is not bytes or len(raw) > 65536:
        return None, None, "invalid"
    digest = hashlib.sha256(raw).hexdigest()
    if digest != expected:
        return None, digest, "invalid"
    try:
        value = strict_json_loads(raw)
        result = ThresholdDecision.model_validate_json(json.dumps(value, allow_nan=False))
    except (ValueError, TypeError, UnicodeError, RecursionError, OverflowError):
        return None, digest, "invalid"
    return result, digest, "bound"


def _development_ready(summary: DevelopmentSummary, inputs: ThresholdInputs) -> tuple[bool, str]:
    if (summary.evidence_state != "supplied-complete" or summary.missing_slots or summary.failed_slots
            or summary.unknown_cost_slots or summary.incomplete_observation_slots
            or summary.supplied_slots != summary.scheduled_slots
            or summary.next_action != "request-independent-floor-review"):
        return False, "full36-evidence-or-repeat-decision-pending"
    arms = {model.arm_slot for model in inputs.models}
    expected = set(product(arms, ("model",), ("clean", "ambiguous", "poisoned"), ("C0", "C1", "C2")))
    expected |= set(product(arms, ("keyword", "abstain", "deny-all"), ("clean",), ("control",)))
    groups = [group for group in summary.groups if group.get("task_class") == "all"]
    keys = [(g.get("arm_slot"), g.get("selector"), g.get("condition"), g.get("cell")) for g in groups]
    if len(keys) != len(set(keys)) or set(keys) != expected:
        return False, "full36-control-matrix-incomplete"
    for group in summary.groups:
        for field in ("missing", "semantic_unknown_or_proxy", "legacy_proxy_trials", "failed_trials",
                      "unknown_selection_trials", "incomplete_observations", "unknown_cost_trials",
                      "scheduled_failure_records"):
            if type(group.get(field)) is not int or group.get(field) != 0:
                return False, "full36-unknown-proxy-or-failed-group"
        expected_count = (36 if group.get("task_class") == "all" else 6) * inputs.repeats
        if (group.get("scheduled") != expected_count or group.get("supplied") != expected_count
                or group.get("semantic_known") != expected_count
                or type(group.get("semantic_successes")) is not int
                or not 0 <= group["semantic_successes"] <= expected_count):
            return False, "full36-group-denominator-mismatch"
    class_keys = {(g.get("arm_slot"), g.get("selector"), g.get("condition"), g.get("cell"), g.get("task_class"))
                  for g in summary.groups if g.get("task_class") != "all"}
    if (class_keys != {(*key, name) for key in expected for name in CLASSES}
            or len([g for g in summary.groups if g.get("task_class") != "all"]) != len(class_keys)):
        return False, "full36-task-class-coverage-incomplete"
    for overall in groups:
        members = [group for group in summary.groups if group.get("task_class") != "all" and
                   all(group.get(key) == overall.get(key) for key in ("arm_slot", "selector", "condition", "cell"))]
        if sum(group["semantic_successes"] for group in members) != overall["semantic_successes"]:
            return False, "full36-class-and-overall-utility-disagreement"
    if summary.scheduled_slots != 36 * inputs.repeats * len(expected):
        return False, "full36-total-denominator-mismatch"
    if set(summary.repeat_diagnostics) != arms:
        return False, "full36-repeat-diagnostics-missing"
    for diagnostic in summary.repeat_diagnostics.values():
        if (not isinstance(diagnostic, dict) or diagnostic.get("missing_attempt_counter_rows") != 0
                or diagnostic.get("requires_transport_repair") is not False
                or (inputs.repeats == 3 and diagnostic.get("proposes_five_repeats") is not False)):
            return False, "full36-repeat-or-transport-repair-pending"
    return True, "full36-ready-for-external-review"


def validate_threshold_approval(*, proposal: FullDevelopmentProposal, summary: DevelopmentSummary,
        context: ThresholdContext, current_inputs: ThresholdInputs, now: datetime,
        expected_context_sha256: str | None = None, reviewer_metadata: bytes | None = None,
        expected_reviewer_sha256: str | None = None, integrator_metadata: bytes | None = None,
        expected_integrator_sha256: str | None = None,
        external_confirmation: ExternalConfirmation | None = None,
        external_confirmation_verified: bool = False,
        fresh_custody_confirmed: bool = False) -> ThresholdValidation:
    """Validate actual supplied bytes; a matched pin alone never grants authority."""
    scope = _hash(context)
    review, review_pin, review_state = _read_metadata(reviewer_metadata, expected_reviewer_sha256)
    approval, approval_pin, approval_state = _read_metadata(integrator_metadata, expected_integrator_sha256)
    problems, pending = [], []
    fresh = context.corpus_state in ("retired", "exposed") or (
        context.inputs.corpus_seal_sha256 in context.retired_corpus_seal_sha256s)
    if fresh:
        problems.append("retired-or-author-exposed-corpus-needs-fresh-custody")
    elif context.corpus_state != "sealed-unexposed":
        pending.append("fresh-custody-state-pending")
    if not fresh_custody_confirmed or context.corpus_sealed_at is None:
        pending.append("fresh-custody-not-confirmed-by-owner")
    if expected_context_sha256 is None:
        pending.append("external-context-pin-missing")
    elif scope != expected_context_sha256:
        problems.append("external-context-pin-mismatch")
    if context.inputs != current_inputs:
        problems.append("current-source-settings-model-semantic-or-corpus-inputs-changed")
    binding = context.inputs
    expected = (binding.proposal_sha256 == _hash(proposal)
        and binding.full36_plan_sha256 == proposal.plan_sha256 == summary.plan_sha256
        and binding.settings_sha256 == proposal.settings_sha256 == summary.settings_sha256
        and binding.full36_outcomes_sha256 == proposal.outcomes_sha256 == summary.outcomes_sha256
        and binding.full36_summary_sha256 == proposal.full36_summary_sha256 == _hash(summary))
    if not expected:
        problems.append("proposal-summary-plan-settings-outcome-binding-mismatch")
    if (model_scope_hash(binding.models) != binding.model_configuration_sha256
            or len({m.arm_slot for m in binding.models}) != 2
            or len({m.model_id for m in binding.models}) != 2
            or len({m.family_id for m in binding.models}) != 2):
        problems.append("model-scope-or-two-family-binding-invalid")
    ready, development_reason = _development_ready(summary, binding)
    if not ready:
        pending.append(development_reason)
    if proposal.proposed_repeats_for_both_arms != binding.repeats:
        pending.append("repeat-proposal-not-reconciled-with-approved-settings")
    if review_state == "missing" or approval_state == "missing":
        pending.append("external-reviewer-or-integrator-metadata-missing")
    if review_state == "invalid" or approval_state == "invalid":
        problems.append("external-metadata-pin-or-schema-invalid")
    try:
        if now.tzinfo is None:
            raise ValueError("aware caller time required")
        if context.corpus_sealed_at and _time(context.corpus_sealed_at) > now:
            problems.append("corpus-seal-timestamp-in-future")
        start = _time(context.heldout_started_at) if context.heldout_started_at else None
        if start is not None and start > now:
            problems.append("claimed-execution-start-in-future")
        if review is not None and approval is not None:
            authors = {value.casefold().strip() for value in
                       (*context.source_author_ids, *context.proposal_author_ids, *context.data_author_ids)}
            review_id, int_id = review.actor_id.casefold().strip(), approval.actor_id.casefold().strip()
            if (not review_id or not int_id or review.role != "independent-reviewer" or review_id in authors
                    or approval.role != "integrator" or approval.actor_id != context.expected_integrator_id
                    or int_id in {value.casefold().strip() for value in context.proposal_author_ids}
                    or review_id == int_id):
                problems.append("self-authored-dependent-or-wrong-role-approval")
            for decision in (review, approval):
                issued, expires = _time(decision.issued_at), _time(decision.expires_at)
                if issued > now or issued >= expires or expires <= now:
                    problems.append("stale-or-future-dated-approval")
                if start is not None and issued >= start:
                    problems.append("approval-not-frozen-before-heldout-execution")
                if decision.context_sha256 != scope:
                    problems.append("decision-context-mismatch")
                if decision.decision == "rejected":
                    problems.append("external-decision-rejected")
                elif decision.decision != "approved" or decision.absolute_utility_floor is None:
                    pending.append("external-floor-or-decision-pending")
                if not decision.uncertainty_rule_approved:
                    pending.append("uncertainty-rule-approval-pending")
            if _time(approval.issued_at) < _time(review.issued_at):
                problems.append("integrator-approval-precedes-review")
            if approval.reviewer_metadata_sha256 != review_pin:
                problems.append("integrator-not-bound-to-exact-reviewer-bytes")
            floor = review.absolute_utility_floor
            if floor != approval.absolute_utility_floor:
                problems.append("reviewer-integrator-floor-disagreement")
            if floor is not None:
                deny = [g for g in summary.groups if g.get("task_class") == "all"
                        and g.get("selector") == "deny-all"]
                if len(deny) != 2 or any(type(g.get("scheduled")) is not int or g["scheduled"] <= 0
                        or type(g.get("semantic_successes")) is not int
                        or g["semantic_successes"] / g["scheduled"] >= floor for g in deny):
                    problems.append("deny-all-does-not-fail-explicit-approved-floor")
                if context.prior_absolute_floor is not None and floor < context.prior_absolute_floor:
                    if any(not d.explicitly_approves_lower_floor or
                           d.supersedes_approval_sha256 != context.prior_approval_sha256
                           for d in (review, approval)):
                        problems.append("automatic-or-unapproved-floor-lowering")
    except (ValueError, TypeError, OverflowError):
        problems.append("approval-temporal-metadata-invalid")
    authorization = "not-confirmed"
    if external_confirmation_verified:
        proof = external_confirmation
        if (proof is None or review is None or approval is None or proof.context_sha256 != scope
                or proof.reviewer_metadata_sha256 != review_pin or proof.integrator_metadata_sha256 != approval_pin
                or proof.reviewer_id != review.actor_id or proof.integrator_id != approval.actor_id):
            authorization = "mismatched"
            problems.append("external-confirmation-does-not-bind-these-actors-and-bytes")
        else:
            try:
                verified = _time(proof.verified_at)
                if (verified > now or verified < max(_time(review.issued_at), _time(approval.issued_at))
                        or (context.heldout_started_at and verified >= _time(context.heldout_started_at))):
                    raise ValueError("confirmation timing invalid")
                authorization = "trusted-caller-confirmed"
            except (ValueError, TypeError):
                authorization = "mismatched"
                problems.append("external-confirmation-timing-invalid")
    else:
        pending.append("external-authorization-not-authenticated-by-trusted-caller")
    eligible = not problems and not pending and authorization == "trusted-caller-confirmed"
    return ThresholdValidation(disposition="invalid" if problems else
        "eligible-for-separate-runtime-admission" if eligible else "pending",
        metadata_binding="invalid" if problems else "missing" if review_state == "missing"
        or approval_state == "missing" else "bound", external_authorization=authorization,
        context_sha256=scope, reviewer_metadata_sha256=review_pin, integrator_metadata_sha256=approval_pin,
        approved_floor=review.absolute_utility_floor if eligible else None,
        independent_reviewer_id=review.actor_id if eligible else None,
        approval_reference=external_confirmation.external_authorization_reference if eligible else None,
        rationale=review.rationale if eligible else None, issue_codes=tuple(dict.fromkeys((*problems, *pending))),
        fresh_corpus_required=fresh)


def project_approved_thresholds(**validation_inputs) -> ApprovedThresholds | None:
    """Revalidate raw external metadata; never trust a caller-created 'ready' report."""
    report = validate_threshold_approval(**validation_inputs)
    if report.disposition != "eligible-for-separate-runtime-admission":
        return None
    scope = validation_inputs["current_inputs"]
    return ApprovedThresholds(manifest_sha256=scope.heldout_manifest_sha256,
        approval_status="approved", absolute_utility_floor=report.approved_floor,
        independent_reviewer_id=report.independent_reviewer_id, approval_receipt_id=report.approval_reference,
        full36_calibration_sha256=scope.full36_summary_sha256, rationale=report.rationale,
        frozen_before_heldout_execution=True, uncertainty_rule_approved=True)


def project_threshold_status(report: ThresholdValidation) -> dict:
    """Status projection only; no transcript, raw decisions or hidden corpus content."""
    return {"version": report.version, "disposition": report.disposition,
            "metadata_binding": report.metadata_binding, "external_authorization": report.external_authorization,
            "context_sha256": report.context_sha256, "reviewer_metadata_sha256": report.reviewer_metadata_sha256,
            "integrator_metadata_sha256": report.integrator_metadata_sha256,
            "issue_codes": list(report.issue_codes), "approved_floor": report.approved_floor,
            "fresh_corpus_required": report.fresh_corpus_required, "runtime_authorized": False,
            "independent_product_acceptance": "pending"}
