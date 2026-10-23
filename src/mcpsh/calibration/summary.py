"""Summarize explicitly supplied pilot counters; never run or synthesize trials."""

from mcpsh.evaluation.statistics import wilson
from mcpsh.records import typed_hash

from .models import ArmPilotSummary, DraftPilotManifest, PilotObservation, PilotSummary
from .rules import repeat_rule


def summarize_pilot(manifest: DraftPilotManifest,
                    observations: tuple[PilotObservation, ...]) -> PilotSummary:
    slots = {arm.slot: arm for arm in manifest.arms}
    task_ids = {case.task_id for case in manifest.cases}
    seen = set()
    modes = {row.execution_mode for row in observations}
    if len(modes) > 1:
        raise ValueError("live evidence and replay diagnostics must remain separate")
    expected_per_arm = len(task_ids) * len(manifest.conditions) * len(manifest.cells) * manifest.repeats
    for row in observations:
        key = (row.arm_slot, row.task_id, row.condition, row.cell, row.repeat)
        if key in seen:
            raise ValueError("duplicate scheduled pilot row")
        seen.add(key)
        if (row.arm_slot not in slots or row.task_id not in task_ids
                or row.repeat > manifest.repeats):
            raise ValueError("observation outside the pinned development pilot schedule")
        arm = slots[row.arm_slot]
        if row.execution_mode == "live":
            if not arm.provider_id or not arm.model_id or not arm.family:
                raise ValueError("live evidence cannot resolve draft identities implicitly")
            if row.provider_id != arm.provider_id or row.requested_model_id != arm.model_id:
                raise ValueError("recorded identity differs from draft arm")
    summaries = []
    for arm in manifest.arms:
        rows = [row for row in observations if row.arm_slot == arm.slot]
        known = [row.utility_success for row in rows if row.utility_success is not None]
        success = sum(value is True for value in known)
        outputs = sum(row.model_outputs for row in rows)
        invalid = sum(row.semantic_invalid_outputs for row in rows)
        attempts = sum(row.request_attempts for row in rows)
        transport = sum(row.transport_failed_attempts for row in rows)
        diagnostic = repeat_rule(invalid=invalid, outputs=outputs, failures=transport,
                                 attempts=attempts, successes=success, known_utility=len(known))
        summaries.append(ArmPilotSummary(
            arm_slot=arm.slot, scheduled_task_runs=expected_per_arm, supplied_task_runs=len(rows),
            missing_task_runs=expected_per_arm - len(rows), known_utility_trials=len(known),
            unknown_utility_trials=sum(row.utility_success is None for row in rows),
            successful_utility_trials=success, model_outputs=outputs,
            semantic_invalid_outputs=invalid,
            request_attempts=attempts, transport_failed_attempts=transport,
            utility_wilson=wilson(success, len(known)),
            **diagnostic,
        ))
    proposed = 5 if any(arm.proposes_five_repeats for arm in summaries) else manifest.repeats
    complete = all(not arm.missing_task_runs and not arm.unknown_utility_trials for arm in summaries)
    # Transport faults take priority over repeat inflation. Partial evidence can
    # trigger repair/proposals but can never establish pilot completion.
    if any(arm.requires_transport_repair for arm in summaries):
        action = "repair-and-repilot"
    elif not complete:
        action = "collect-pilot-evidence"
    elif proposed > manifest.repeats:
        action = "request-repeat-approval"
    else:
        action = "request-full-development-calibration"
    return PilotSummary(
        evidence_state="no-evidence" if not observations else
                       "supplied-complete" if complete else "incomplete",
        execution_mode=next(iter(modes)) if modes else None,
        manifest_sha256=typed_hash(manifest.model_dump(mode="json")),
        input_evidence_sha256=typed_hash([row.model_dump(mode="json") for row in observations]),
        arms=tuple(summaries), proposed_repeats_for_both_arms=proposed, next_action=action,
    )
