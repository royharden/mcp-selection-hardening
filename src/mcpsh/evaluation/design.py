"""Pure exact-schedule audit. Repeats/platforms are evidence, never parsed from IDs."""

from itertools import product
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from mcpsh.records import TrialOutcome, typed_hash


class DesignRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class ScheduledTrial(DesignRecord):
    trial_id: str = Field(min_length=1)
    task_id: str = Field(min_length=1)
    model_id: str = Field(min_length=1)
    condition: Literal["clean", "ambiguous", "poisoned"]
    cell: Literal["C0", "C1", "C2"]
    repeat: int = Field(ge=1, le=5)


class ScheduleDesign(DesignRecord):
    version: Literal["exact-schedule-v1"] = "exact-schedule-v1"
    task_family_by_id: dict[str, str]
    model_family_by_id: dict[str, str]
    repeats: tuple[int, ...]
    mode: Literal["replay", "live"]
    platform_scope: Literal["synthetic-memory", "filesystem-posix"]
    seed: int = 1729
    trials: tuple[ScheduledTrial, ...]


class ObservedTrial(DesignRecord):
    outcome: TrialOutcome
    # None is intentionally representable, so an audit can disclose missing metadata.
    repeat: int | None = Field(default=None, ge=1, le=5)
    platform_scope: Literal["synthetic-memory", "filesystem-posix"] | None = None
    model_family_id: str | None = None
    outcome_sha256: str | None = None
    row_evidence_sha256: str | None = None


class FamilySupport(DesignRecord):
    schedule_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    supported_family_ids: tuple[str, ...]
    reviewer_id: str = Field(min_length=1)
    review_evidence_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class ScheduleIssue(DesignRecord):
    category: str
    severity: Literal["invalid", "incomplete"]
    trial_id: str | None = None


class ScheduleAudit(DesignRecord):
    version: Literal["exact-schedule-v1"] = "exact-schedule-v1"
    schedule_sha256: str
    scored_outcomes_sha256: str
    observed_rows_sha256: str
    status: Literal["complete", "incomplete", "invalid"]
    expected_trials: int
    supplied_schedule_slots: int
    scored_rows: int
    private_rows: int
    unique_scored_trials: int
    unique_private_trials: int
    missing_trials: int
    failed_scored_rows: int
    unknown_utility_rows: int
    incomplete_selection_rows: int
    incomplete_observation_rows: int
    utility_basis_counts: dict[str, int]
    issues: tuple[ScheduleIssue, ...]
    recommendation: Literal["repair-design-or-rows", "supply-required-evidence", "complete-for-pairing"]
    independent_product_acceptance: Literal["pending"] = "pending"


class PairedComparison(DesignRecord):
    version: Literal["paired-family-cluster-v2"] = "paired-family-cluster-v2"
    audit: ScheduleAudit
    before: str
    after: str
    metric: str
    seed: int
    resamples: Literal[10000] = 10000
    models: tuple[str, ...]
    conditions: tuple[str, ...]
    expected_pairs: int
    family_label_count: int
    supported_observable_families: int
    missing_pair_members: int
    unknown_pair_members: int
    failed_pair_members: int
    legacy_utility_pair_members: int
    support_binding: Literal["absent", "invalid", "pinned-unverified", "verified"]
    interpretation: Literal["incomplete", "legacy-proxy", "exploratory", "family-paired"]
    difference: float | None = None
    low: float | None = None
    high: float | None = None
    descriptive: dict = Field(default_factory=dict)
    independent_product_acceptance: Literal["pending"] = "pending"


def record_hash(record) -> str:
    return typed_hash(record.model_dump(mode="json"))


def slot_key(row):
    return row.task_id, row.model_id, row.condition, row.cell, row.repeat


def audit_schedule(design: ScheduleDesign, *, scored_outcomes: tuple[TrialOutcome, ...],
                   observed_rows: tuple[ObservedTrial, ...]) -> ScheduleAudit:
    """Audit every supplied row, including failures; do not execute any statistics."""
    issues = []

    def issue(category, severity="invalid", trial_id=None):
        issues.append(ScheduleIssue(category=category, severity=severity, trial_id=trial_id))

    tasks, models = design.task_family_by_id, design.model_family_by_id
    if (not tasks or any(not key or not value for key, value in tasks.items())
            or len(models) != 2 or len(set(models.values())) != 2
            or any(not key or not value for key, value in models.items())):
        issue("invalid-task-or-two-family-declaration")
    if (not design.repeats or len(set(design.repeats)) != len(design.repeats)
            or any(type(n) is not int or not 1 <= n <= 5 for n in design.repeats)):
        issue("invalid-explicit-repeat-set")
    expected_keys = set(product(tasks, models, ("clean", "ambiguous", "poisoned"),
                                ("C0", "C1", "C2"), design.repeats))
    ids = {}
    keys = set()
    for slot in design.trials:
        if slot.trial_id in ids:
            issue("duplicate-scheduled-trial-id", trial_id=slot.trial_id)
        if slot_key(slot) in keys:
            issue("duplicate-scheduled-coordinate", trial_id=slot.trial_id)
        ids[slot.trial_id] = slot
        keys.add(slot_key(slot))
    if keys != expected_keys:
        issue("schedule-not-exact-cartesian-design")
    scored = {}
    for outcome in scored_outcomes:
        if outcome.trial_id in scored:
            issue("duplicate-scored-trial-id", trial_id=outcome.trial_id)
        scored[outcome.trial_id] = outcome
        if outcome.trial_id not in ids:
            issue("unexpected-scored-trial", trial_id=outcome.trial_id)
        if outcome.scheduled is not True:
            issue("scheduled-row-reclassified-unscheduled", trial_id=outcome.trial_id)
    observed = {}
    actual_keys = set()
    for row in observed_rows:
        outcome = row.outcome
        trial_id = outcome.trial_id
        if trial_id in observed:
            issue("duplicate-private-trial-id", trial_id=trial_id)
        observed[trial_id] = row
        slot = ids.get(trial_id)
        if slot is None:
            issue("unexpected-private-trial", trial_id=trial_id)
        if row.repeat is None:
            issue("missing-explicit-repeat", "incomplete", trial_id)
        if row.platform_scope is None:
            issue("missing-explicit-platform", "incomplete", trial_id)
        elif row.platform_scope != design.platform_scope:
            issue("wrong-platform", trial_id=trial_id)
        if row.model_family_id is None:
            issue("missing-model-family", "incomplete", trial_id)
        elif row.model_family_id != models.get(outcome.model_id):
            issue("wrong-model-family", trial_id=trial_id)
        if outcome.execution_mode != design.mode:
            issue("wrong-execution-mode", trial_id=trial_id)
        if outcome.family_id != tasks.get(outcome.task_id):
            issue("wrong-task-family", trial_id=trial_id)
        key = (outcome.task_id, outcome.model_id, outcome.condition, outcome.cell, row.repeat)
        if key in actual_keys:
            issue("duplicate-observed-coordinate", trial_id=trial_id)
        actual_keys.add(key)
        if slot is not None and key != slot_key(slot):
            # Missing repeat is unavailable, not an inferred ordinal from trial ID.
            if row.repeat is None and key[:-1] == slot_key(slot)[:-1]:
                pass
            else:
                issue("wrong-task-model-condition-cell-or-repeat", trial_id=trial_id)
        digest = record_hash(outcome)
        if row.outcome_sha256 is None:
            issue("missing-outcome-binding", "incomplete", trial_id)
        elif row.outcome_sha256 != digest:
            issue("wrong-outcome-binding", trial_id=trial_id)
        if not row.row_evidence_sha256 or len(row.row_evidence_sha256) != 64 or any(
            value not in "0123456789abcdef" for value in row.row_evidence_sha256
        ):
            issue("missing-private-row-evidence-pin", "incomplete", trial_id)
        if trial_id not in scored:
            issue("private-row-without-scored-row", "incomplete", trial_id)
        elif record_hash(scored[trial_id]) != digest:
            issue("scored-private-outcome-disagreement", trial_id=trial_id)
    for trial_id in set(ids) - set(scored):
        issue("missing-scored-trial", "incomplete", trial_id)
    for trial_id in set(ids) - set(observed):
        issue("missing-private-trial", "incomplete", trial_id)
    bases = {}
    for outcome in scored_outcomes:
        bases[outcome.utility_basis] = bases.get(outcome.utility_basis, 0) + 1
    status = "invalid" if any(item.severity == "invalid" for item in issues) else "incomplete" if issues else "complete"
    # Sort findings for stable audit identity regardless of set iteration order.
    issues.sort(key=lambda item: (item.category, item.trial_id or "", item.severity))
    return ScheduleAudit(schedule_sha256=record_hash(design),
        scored_outcomes_sha256=typed_hash([o.model_dump(mode="json") for o in scored_outcomes]),
        observed_rows_sha256=typed_hash([r.model_dump(mode="json") for r in observed_rows]), status=status,
        expected_trials=len(expected_keys), supplied_schedule_slots=len(design.trials),
        scored_rows=len(scored_outcomes), private_rows=len(observed_rows),
        unique_scored_trials=len(scored), unique_private_trials=len(observed),
        missing_trials=len(set(ids) - (set(scored) & set(observed))),
        failed_scored_rows=sum(bool(row.failures) for row in scored_outcomes),
        unknown_utility_rows=sum(row.utility_success is None for row in scored_outcomes),
        incomplete_selection_rows=sum(row.selection_journal_complete is not True for row in scored_outcomes),
        incomplete_observation_rows=sum(not row.observation_complete or row.effect == "unknown" for row in scored_outcomes),
        utility_basis_counts=bases, issues=tuple(issues), recommendation="repair-design-or-rows"
        if status == "invalid" else "supply-required-evidence" if status == "incomplete" else "complete-for-pairing")


def pairing_inputs(design: ScheduleDesign, rows: tuple[ObservedTrial, ...], *, before: str,
                   after: str, metric: str, models: tuple[str, ...] | None = None,
                   conditions: tuple[str, ...] | None = None) -> dict:
    """Called only after a complete audit; all selected strata remain in each family."""
    if before == after or before not in ("C0", "C1", "C2") or after not in ("C0", "C1", "C2"):
        raise ValueError("two distinct declared cells required")
    if metric not in ("utility_success", "selection_success", "prohibited_intent", "effect_observed"):
        raise ValueError("unsupported paired metric")
    models = tuple(design.model_family_by_id) if models is None else models
    conditions = ("clean", "ambiguous", "poisoned") if conditions is None else conditions
    if (not models or len(set(models)) != len(models) or set(models) - set(design.model_family_by_id)
            or not conditions or len(set(conditions)) != len(conditions)
            or set(conditions) - {"clean", "ambiguous", "poisoned"}):
        raise ValueError("explicit nonempty model/condition subset of the design required")
    by_key = {(r.outcome.task_id, r.outcome.model_id, r.outcome.condition, r.outcome.cell, r.repeat): r.outcome
              for r in rows}
    families = {}
    missing = unknown = failed = legacy = 0
    values = {before: [], after: []}
    unobservable_families = set()
    for task, model, condition, repeat in product(design.task_family_by_id, models, conditions, design.repeats):
        family = design.task_family_by_id[task]
        pair = []
        for cell in (before, after):
            outcome = by_key.get((task, model, condition, cell, repeat))
            if outcome is None:
                missing += 1
                unobservable_families.add(family)
                pair.append(None)
                continue
            failed += bool(outcome.failures)
            if outcome.failures:
                unobservable_families.add(family)
            value = getattr(outcome, metric, None)
            if metric == "utility_success":
                legacy += outcome.utility_basis != "semantic-v2"
                if outcome.utility_basis != "semantic-v2" or outcome.utility_status != (
                    "unknown" if value is None else "success" if value else "failure"):
                    value = None
            elif metric in ("selection_success", "prohibited_intent"):
                if outcome.selection_journal_complete is not True:
                    value = None
            else:
                value = outcome.effect == "observed" if outcome.observation_complete and outcome.effect != "unknown" else None
            if value is None:
                unknown += 1
                unobservable_families.add(family)
            pair.append(value)
            values[cell].append(value)
        families.setdefault(family, [])
        if all(value is not None for value in pair):
            families[family].append(int(pair[1]) - int(pair[0]))
    return {"families": families, "values": values, "missing_pair_members": missing,
            "unknown_pair_members": unknown, "failed_pair_members": failed,
            "legacy_utility_pair_members": legacy,
            "unobservable_families": unobservable_families,
            "expected_pairs": len(design.task_family_by_id) * len(models) * len(conditions) * len(design.repeats),
            "models": models, "conditions": conditions}
