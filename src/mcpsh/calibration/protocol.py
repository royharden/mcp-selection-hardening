"""Full-36 public development planning and evidence-only calibration summaries."""

import random
from collections import defaultdict

from mcpsh.evaluation.statistics import paired_family_bootstrap, wilson
from mcpsh.records import typed_hash

from .models import CLASSES, DevelopmentCase, DraftPilotManifest, PilotSummary
from .protocol_models import (
    CalibrationOutcome, CalibrationSlot, DevelopmentProtocolPlan, DevelopmentSummary,
    FullDevelopmentProposal, ProtocolFailure, ProtocolSettings,
)
from .rules import repeat_rule


def _hash(record):
    return typed_hash(record.model_dump(mode="json"))


def _slots(cases, arms, settings):
    rows = []
    for case in cases:
        for arm in arms:
            for repeat in range(1, settings.repeats + 1):
                for condition in settings.conditions:
                    for cell in settings.cells:
                        rows.append(CalibrationSlot(slot_id=f"dev36-{len(rows):05d}", task_id=case.task_id,
                            arm_slot=arm.slot, selector="model", condition=condition, cell=cell, repeat=repeat))
                for selector in settings.baseline_selectors:
                    rows.append(CalibrationSlot(slot_id=f"dev36-{len(rows):05d}", task_id=case.task_id,
                        arm_slot=arm.slot, selector=selector, condition="clean", cell="control", repeat=repeat))
    random.Random(settings.seed).shuffle(rows)
    return tuple(rows)


def validate_protocol_plan(plan: DevelopmentProtocolPlan) -> None:
    # Revalidate even model_copy/construct callers, then verify all derived bytes.
    DevelopmentProtocolPlan.model_validate_json(plan.model_dump_json())
    if len(plan.cases) != 36 or len({case.task_id for case in plan.cases}) != 36:
        raise ValueError("exact 36-case public development inventory required")
    if any(sum(case.task_class == name for case in plan.cases) != 6 for name in CLASSES):
        raise ValueError("six public development cases per class required")
    if plan.arms[0].slot == plan.arms[1].slot:
        raise ValueError("arm slots must remain distinct")
    for name in ("model_id", "family"):
        values = [getattr(arm, name) for arm in plan.arms]
        if None not in values and len(set(values)) != 2:
            raise ValueError("known model/family identities must remain distinct")
    if plan.settings_sha256 != _hash(plan.settings):
        raise ValueError("settings hash mismatch")
    expected = _slots(plan.cases, plan.arms, plan.settings)
    if typed_hash([row.model_dump(mode="json") for row in expected]) != typed_hash(
        [row.model_dump(mode="json") for row in plan.slots]
    ):
        raise ValueError("derived full-development schedule differs from pinned plan")


def plan_development_calibration(*, pilot: DraftPilotManifest,
                                development_cases: tuple[DevelopmentCase, ...],
                                development_input_sha256: str,
                                pilot_summary: PilotSummary | None = None) -> DevelopmentProtocolPlan:
    if development_input_sha256 != pilot.development_input_sha256:
        raise ValueError("pilot and full-development inventory pins differ")
    inventory = {case.task_id: case for case in development_cases}
    if any(inventory.get(case.task_id) != case for case in pilot.cases):
        raise ValueError("pilot cases must be part of the same full inventory")
    if pilot_summary is not None and pilot_summary.manifest_sha256 != _hash(pilot):
        raise ValueError("pilot summary belongs to another exact pilot")
    repeats = pilot.repeats if pilot_summary is None else max(
        pilot.repeats, pilot_summary.proposed_repeats_for_both_arms)
    settings = ProtocolSettings(repeats=repeats, seed=pilot.seed)
    plan = DevelopmentProtocolPlan(
        pilot_manifest_sha256=_hash(pilot),
        pilot_summary_sha256=None if pilot_summary is None else _hash(pilot_summary),
        pilot_evidence_state="no-evidence" if pilot_summary is None else pilot_summary.evidence_state,
        pilot_execution_mode=None if pilot_summary is None else pilot_summary.execution_mode,
        pilot_requires_transport_repair=pilot_summary is not None and any(
            arm.requires_transport_repair for arm in pilot_summary.arms),
        development_input_sha256=development_input_sha256, arms=pilot.arms,
        cases=development_cases, settings=settings, settings_sha256=_hash(settings),
        slots=_slots(development_cases, pilot.arms, settings),
    )
    validate_protocol_plan(plan)
    return plan


def validate_calibration_outcome(plan: DevelopmentProtocolPlan, record: CalibrationOutcome) -> None:
    CalibrationOutcome.model_validate_json(record.model_dump_json())
    slot = next((slot for slot in plan.slots if slot.slot_id == record.slot_id), None)
    if slot is None or record.settings_sha256 != plan.settings_sha256:
        raise ValueError("outcome outside pinned plan/settings")
    row = record.outcome
    if _hash(row) != record.outcome_sha256:
        raise ValueError("scored outcome digest mismatch")
    if (row.trial_id, row.task_id, row.condition, row.cell) != (
        slot.slot_id, slot.task_id, slot.condition, slot.cell
    ):
        raise ValueError("outcome identity/condition/cell differs from schedule")
    arm = next(arm for arm in plan.arms if arm.slot == slot.arm_slot)
    if slot.selector == "model":
        if row.execution_mode == "live" and (
            not arm.model_id or not arm.provider_id or not arm.family
            or row.model_id != arm.model_id or row.provider_id != arm.provider_id
        ):
            raise ValueError("live calibration identity differs from pinned arm")
        if row.execution_mode == "live" and row.cost_status == "non-model":
            raise ValueError("live provider usage cannot be relabeled non-model/free")
        if row.execution_mode == "replay" and (row.provider_id is not None or row.model_id is not None):
            raise ValueError("replay model diagnostics cannot impersonate live identities")
    elif row.execution_mode != "replay" or row.selector != slot.selector or row.model_id is not None:
        raise ValueError("deterministic public baselines must remain labeled non-model replay controls")
    elif row.cost_status != "non-model" or row.cost_microunits != 0:
        raise ValueError("deterministic public baselines have no provider usage")
    if record.attempts is not None:
        counts = record.attempts
        if (counts.task_id, counts.arm_slot, counts.condition, counts.cell, counts.repeat) != (
            slot.task_id, slot.arm_slot, slot.condition, slot.cell, slot.repeat
        ) or slot.selector != "model":
            raise ValueError("attempt-counter row differs from model schedule")
        if (counts.utility_success != row.utility_success or row.utility_basis != counts.utility_basis
                or counts.execution_mode != row.execution_mode):
            raise ValueError("attempt counters cannot relabel utility/provenance")
        if row.execution_mode == "live" and (
            counts.provider_id != arm.provider_id or counts.requested_model_id != arm.model_id
        ):
            raise ValueError("attempt identity differs from calibration arm")


def retention_decision(interval: dict, *, independent_families: int | None = None) -> str:
    if interval.get("low") is None or interval.get("high") is None:
        return "pending"
    if (independent_families is None or independent_families < 20
            or interval.get("interpretation") != "family-paired"):
        return "inconclusive"
    if interval["low"] >= -0.05:
        return "pass"
    return "fail" if interval["high"] < -0.05 else "inconclusive"


def summarize_development(plan: DevelopmentProtocolPlan,
                          records: tuple[CalibrationOutcome, ...], *,
                          failures: tuple[ProtocolFailure, ...] = ()) -> DevelopmentSummary:
    validate_protocol_plan(plan)
    by_id = {}
    for record in records:
        validate_calibration_outcome(plan, record)
        if record.slot_id in by_id:
            raise ValueError("duplicate observed calibration slot")
        by_id[record.slot_id] = record
    failure_ids = [failure.slot_id for failure in failures]
    if len(set(failure_ids)) != len(failure_ids) or set(failure_ids) - {slot.slot_id for slot in plan.slots}:
        raise ValueError("duplicate or out-of-schedule failure record")
    model_records = [r for r in records if next(s for s in plan.slots if s.slot_id == r.slot_id).selector == "model"]
    modes = {record.outcome.execution_mode for record in model_records}
    if len(modes) > 1:
        raise ValueError("live model evidence and replay model diagnostics cannot be pooled")
    classes = {case.task_id: case.task_class for case in plan.cases}
    buckets = defaultdict(list)
    for slot in plan.slots:
        for task_class in ("all", classes[slot.task_id]):
            buckets[(slot.arm_slot, slot.selector, slot.condition, slot.cell, task_class)].append(slot)
    groups = []
    pending_semantics = 0
    for key, slots in sorted(buckets.items()):
        actual = [by_id[slot.slot_id].outcome for slot in slots if slot.slot_id in by_id]
        known = [row for row in actual if row.utility_basis == "semantic-v2"
                 and row.utility_success is not None and row.utility_status == (
                     "success" if row.utility_success else "failure")]
        success = sum(row.utility_success is True for row in known)
        if key[-1] == "all":
            pending_semantics += len(slots) - len(known)
        groups.append({"arm_slot": key[0], "selector": key[1], "condition": key[2],
            "cell": key[3], "task_class": key[4], "scheduled": len(slots), "supplied": len(actual),
            "missing": len(slots) - len(actual), "semantic_known": len(known),
            "semantic_successes": success, "semantic_unknown_or_proxy": len(slots) - len(known),
            "legacy_proxy_trials": sum(row.utility_basis != "semantic-v2" for row in actual),
            "legacy_proxy_successes": sum(row.utility_basis != "semantic-v2" and row.utility_success is True
                                           for row in actual),
            "failed_trials": sum(bool(row.failures) for row in actual),
            "scheduled_failure_records": sum(slot.slot_id in set(failure_ids) for slot in slots),
            "unknown_cost_trials": sum(row.cost_microunits is None
                                       or row.cost_status in ("unknown", "reserved") for row in actual),
            "incomplete_observations": sum(not row.observation_complete or row.effect == "unknown"
                                           for row in actual),
            "unknown_selection_trials": sum(row.selection_journal_complete is not True for row in actual),
            "all_scheduled_utility_lower_bound": success / len(slots),
            "known_semantic_utility": wilson(success, len(known))})
    diagnostics = {}
    counters_missing = 0
    for arm in plan.arms:
        subset = [r for r in model_records if next(s for s in plan.slots if s.slot_id == r.slot_id).arm_slot == arm.slot]
        counts = [r.attempts for r in subset if r.attempts is not None]
        counters_missing += len(subset) - len(counts)
        known = [r.outcome for r in subset if r.outcome.utility_basis == "semantic-v2"
                 and r.outcome.utility_success is not None and r.outcome.utility_status == (
                     "success" if r.outcome.utility_success else "failure")]
        diagnostics[arm.slot] = {
            **repeat_rule(invalid=sum(r.semantic_invalid_outputs for r in counts),
                outputs=sum(r.model_outputs for r in counts), failures=sum(r.transport_failed_attempts for r in counts),
                attempts=sum(r.request_attempts for r in counts), successes=sum(r.utility_success is True for r in known),
                known_utility=len(known)), "missing_attempt_counter_rows": len(subset) - len(counts),
        }
    failed_rows = sum(bool(record.outcome.failures) for record in records)
    unknown_journals = sum(record.outcome.selection_journal_complete is not True
        or record.outcome.selected_call_count is None or not record.outcome.selected_calls_hash
        or not record.outcome.utility_evidence_ids for record in records)
    unknown_cost = sum(record.outcome.cost_microunits is None
                      or record.outcome.cost_status in ("unknown", "reserved") for record in records)
    unknown_observation = sum(not record.outcome.observation_complete or record.outcome.effect == "unknown"
                              for record in records)
    complete = (len(records) == len(plan.slots) and not failures and not failed_rows
                and not pending_semantics and not unknown_journals and not counters_missing
                and not unknown_cost and not unknown_observation)
    retained = []
    for arm in plan.arms:
        clean = [r.outcome.model_dump(mode="json") for r in model_records
                 if r.outcome.condition == "clean" and next(
                     s for s in plan.slots if s.slot_id == r.slot_id).arm_slot == arm.slot]
        if complete:
            interval = paired_family_bootstrap(clean, before="C1", after="C2", seed=plan.settings.seed)
        else:
            interval = {"low": None, "high": None, "difference": None,
                        "interpretation": "incomplete", "family_count": None}
        retained.append({"arm_slot": arm.slot, "interval": interval,
                         "decision": retention_decision(interval),
                         "family_independence": "not-established-public-development"})
    proposed = 5 if any(item["proposes_five_repeats"] for item in diagnostics.values()) else plan.settings.repeats
    if any(item["requires_transport_repair"] for item in diagnostics.values()):
        action = "repair-and-repilot"
    elif not complete or modes != {"live"}:
        action = "collect-development-evidence"
    elif proposed > plan.settings.repeats:
        action = "request-repeat-approval"
    else:
        action = "request-independent-floor-review"
    ordered = [by_id[slot.slot_id].model_dump(mode="json") for slot in plan.slots if slot.slot_id in by_id]
    return DevelopmentSummary(evidence_state="no-evidence" if not records and not failures else
        "supplied-complete" if complete else "incomplete", plan_sha256=_hash(plan),
        settings_sha256=plan.settings_sha256,
        outcomes_sha256=typed_hash({"records": ordered, "failures": [f.model_dump(mode="json") for f in failures]}),
        scheduled_slots=len(plan.slots), supplied_slots=len(records), missing_slots=len(plan.slots) - len(records),
        failed_slots=len(set(failure_ids) | {r.slot_id for r in records if r.outcome.failures}),
        unknown_cost_slots=unknown_cost, incomplete_observation_slots=unknown_observation,
        groups=tuple(groups), repeat_diagnostics=diagnostics, paired_retention=tuple(retained),
        next_action=action, proposed_repeats_for_both_arms=proposed)


def propose_full36_thresholds(summary: DevelopmentSummary) -> FullDevelopmentProposal:
    decisions = {row["decision"] for row in summary.paired_retention}
    decision = ("fail" if "fail" in decisions else "pending" if "pending" in decisions else
                "inconclusive" if "inconclusive" in decisions else "pass")
    return FullDevelopmentProposal(plan_sha256=summary.plan_sha256, settings_sha256=summary.settings_sha256,
        full36_summary_sha256=_hash(summary), outcomes_sha256=summary.outcomes_sha256,
        proposed_repeats_for_both_arms=summary.proposed_repeats_for_both_arms, retention_decision=decision,
        rationale="Review all scheduled semantic utility and baselines by class/model, missing evidence and controls. "
                  "Public variants do not establish independent families. Absolute floor and uncertainty approval "
                  "remain independent decisions; poor utility never lowers a floor automatically.")
