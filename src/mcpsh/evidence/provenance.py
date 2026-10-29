"""Pure plan projections and explicit edition-to-edition reuse joins."""

import hashlib

from mcpsh.records import typed_hash

from .reader import EvidenceRejected, VerifiedEdition, model
from .resume import ResumePlan, _retained, _same_experiment

PUBLIC_REASONS = frozenset({
    "explicit_successor_authority_missing", "successor_authority_unapproved",
    "action_receipt_missing_or_unapproved", "reused_evidence_incomplete",
    "repeat_identity_unavailable", "prior_usage_or_reservation_unreconciled",
    "positive_live_reservation_required", "one_or_more_actions_pending",
    "unattributed_usage_unknown",
})


def verify_plan_id(plan: ResumePlan, *, expected_plan_id: str) -> ResumePlan:
    parsed = model(ResumePlan, plan.model_dump(mode="json"))
    body = parsed.model_dump(mode="json")
    claimed = body.pop("plan_id")
    if claimed != expected_plan_id or typed_hash(body) != claimed:
        raise EvidenceRejected("resume proposal differs from explicit immutable plan pin")
    return parsed


def project_resume_plan(plan: ResumePlan, *, expected_plan_id: str,
                        public: bool = True) -> dict:
    """Never include raw task/model/receipt IDs, approval JSON or provider text publicly."""
    parsed = verify_plan_id(plan, expected_plan_id=expected_plan_id)
    if not public:
        return {"visibility": "private", "plan": parsed.model_dump(mode="json")}

    def identifier(value):
        return hashlib.sha256(value.encode("utf-8")).hexdigest()

    def reasons(values):
        return [value if value in PUBLIC_REASONS else "unclassified-reason" for value in values]

    return {"visibility": "public", "schema_version": 1, "plan_id": parsed.plan_id,
        "parent_index_sha256": parsed.parent_index_sha256,
        "authority_sha256": parsed.authority_sha256,
        "target_manifest_sha256": parsed.target_manifest_sha256,
        "state": parsed.state, "retained_scheduled_trials": len(parsed.retained_trials),
        "retained_failed_trials": sum(item.failed for item in parsed.retained_trials),
        "original_known_cost_microunits": parsed.original_known_cost_microunits,
        "original_unknown_cost_trials": len(parsed.original_unknown_cost_trial_ids),
        "unresolved_attempts": len(parsed.unresolved_attempt_ids),
        "unattributed_unknown_trials": len(parsed.unattributed_unknown_trial_ids),
        "proposed_new_reservation_microunits": parsed.proposed_new_reservation_microunits,
        "actions": [{"source_trial_sha256": identifier(item.source_trial_id),
            "target_trial_sha256": identifier(item.target_trial_id), "action": item.action,
            "state": item.state, "source_row_sha256": item.source_row_sha256,
            "independent_new_sample": item.independent_new_sample,
            "new_charge_microunits": item.new_charge_microunits,
            "reasons": reasons(item.reasons)} for item in parsed.actions],
        "reasons": reasons(parsed.reasons), "dispatch_performed": False,
        "publication_performed": False, "empirical_verdict": "pending", "product_verdict": "pending"}


def validate_resume_lineage(parent: VerifiedEdition, successor: VerifiedEdition,
                            plan: ResumePlan, *, expected_plan_id: str) -> dict:
    """References, not cloned attempts: original costs and failures remain distinct."""
    plan = verify_plan_id(plan, expected_plan_id=expected_plan_id)
    old_index, old_manifest, old_rows, _, _ = parent.validate()
    new_index, new_manifest, new_rows, _, _ = successor.validate()
    if plan.parent_index_sha256 != parent.authority.index_sha256 or plan.retained_trials != _retained(parent, old_rows):
        raise EvidenceRejected("resume altered the original immutable rows/failures/cost bases")
    if plan.target_manifest_sha256 != successor.authority.manifest_sha256:
        raise EvidenceRejected("successor manifest differs from approved resume target")
    if old_manifest.mode != new_manifest.mode or old_manifest.platform_scope != new_manifest.platform_scope:
        raise EvidenceRejected("successor changes execution provenance")
    if new_index.edition_id == old_index.edition_id or new_index.revision <= old_index.revision:
        raise EvidenceRejected("successor overwrites original edition/revision")
    actions = {item.source_trial_id: item for item in plan.actions}
    if len(actions) != len(plan.actions) or set(actions) != {row.outcome.trial_id for row in old_rows}:
        raise EvidenceRejected("plan omits/duplicates original denominators")
    if tuple(item.target_trial_id for item in plan.actions) != new_index.scheduled_trial_ids:
        raise EvidenceRejected("successor drops/reorders/duplicates the planned schedule")
    old_attempts = {item.attempt_id for row in old_rows for item in row.model_attempts}
    old_calls = {item.call_id for row in old_rows for item in row.trace or ()}
    old_selections = {item.selection_id for row in old_rows for item in row.selected_calls or ()}
    by_new = {row.outcome.trial_id: row for row in new_rows}
    reused, independent, new_cost, new_unknown = 0, 0, 0, []
    retained = {item.trial_id: item for item in plan.retained_trials}
    for old in old_rows:
        action = actions[old.outcome.trial_id]
        new = by_new[action.target_trial_id]
        if (old.outcome.task_id, old.outcome.condition, old.outcome.cell, old.outcome.selector, old.outcome.model_id, old.repeat) != (new.outcome.task_id, new.outcome.condition, new.outcome.cell, new.outcome.selector, new.outcome.model_id, new.repeat):
            raise EvidenceRejected("successor changes case/cell/repeat/model identity")
        if action.action == "reuse":
            if not _same_experiment(old_manifest, new_manifest) or old_index.candidate_commit != new_index.candidate_commit:
                raise EvidenceRejected("reused execution cannot cross changed source/schema/scorer/price inputs")
            if any(getattr(old, field) != getattr(new, field) for field in (
                    "fixture_ref", "fixture_payload_hash", "catalog_hash", "normalization_diff_hash")):
                raise EvidenceRejected("reuse changes per-trial fixture/catalog/treatment pins")
            ref = new.reuse
            original = retained[old.outcome.trial_id]
            if ref is None or (ref.source_index_sha256, ref.source_manifest_sha256, ref.source_trial_id, ref.source_row_sha256, ref.source_outcome_sha256) != (
                    parent.authority.index_sha256, parent.authority.manifest_sha256,
                    original.trial_id, original.source_row_sha256, original.original_outcome_sha256):
                raise EvidenceRejected("reused evidence has stale/unbound parent pins")
            expected = old.outcome.model_dump(mode="json")
            expected["trial_id"] = new.outcome.trial_id
            if new.outcome.model_dump(mode="json") != expected:
                raise EvidenceRejected("reuse relabels a failed outcome, intent, cost or observation")
            if action.independent_new_sample or action.new_charge_microunits != 0:
                raise EvidenceRejected("reuse claims a fresh sample or duplicates billing")
            reused += 1
        else:
            if new.reuse is not None:
                raise EvidenceRejected("fresh dispatch action was replaced with reused evidence")
            if any(item.attempt_id in old_attempts for item in new.model_attempts) or any(item.call_id in old_calls for item in new.trace or ()) or any(item.selection_id in old_selections for item in new.selected_calls or ()):
                raise EvidenceRejected("successor duplicates original execution/attempt/selection identity")
            cost_records = {item.attempt_id: item for item in new.accounting}
            independent += int(new_manifest.mode == "live" and any(
                attempt.status in {"completed", "completed_usage_unknown"}
                and attempt.returned_model_id == attempt.requested_model_id
                and attempt.raw_response_hash is not None
                and cost_records[attempt.attempt_id].dispatch_status == "response_received"
                for attempt in new.model_attempts))
            if new.outcome.cost_microunits is None:
                new_unknown.append(new.outcome.trial_id)
            else:
                new_cost += new.outcome.cost_microunits
    pending = plan.state != "proposal-ready" or bool(plan.unresolved_attempt_ids)
    return {"structural_integrity": "verified", "resume_disposition": "pending" if pending else "linked",
        "original_scheduled_trials": len(old_rows), "original_failed_trials": sum(bool(row.outcome.failures) for row in old_rows),
        "successor_scheduled_trials": len(new_rows), "reused_evidence_trials": reused,
        "independent_new_live_samples": independent, "new_known_cost_microunits": new_cost,
        "new_unknown_cost_trial_ids": new_unknown,
        "original_known_cost_microunits": plan.original_known_cost_microunits,
        "original_unknown_cost_trial_ids": list(plan.original_unknown_cost_trial_ids),
        "reused_new_charge_microunits": 0, "dispatch_performed": False,
        "empirical_verdict": "pending", "product_verdict": "pending",
        "limitation": "Verified lineage does not attest truthful execution, real billing, or independent acceptance."}
