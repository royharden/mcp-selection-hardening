"""Strict draft planning and caller-supplied development evidence contracts."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

CLASSES = ("discovery", "tail", "search", "range", "error_inspection", "no_tool")
CONDITIONS = ("clean", "ambiguous", "poisoned")
CELLS = ("C0", "C1", "C2")


class DraftRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


class DraftArm(DraftRecord):
    slot: str = Field(min_length=1, max_length=64)
    provider_id: str | None = Field(default=None, min_length=1, max_length=128)
    family: str | None = Field(default=None, min_length=1, max_length=128)
    model_id: str | None = Field(default=None, min_length=1, max_length=256)


class DevelopmentCase(DraftRecord):
    task_id: str = Field(min_length=1, max_length=256)
    task_class: Literal["discovery", "tail", "search", "range", "error_inspection", "no_tool"]


class DraftPilotManifest(DraftRecord):
    schema_version: Literal[1] = 1
    kind: Literal["development-pilot-draft"] = "development-pilot-draft"
    corpus_phase: Literal["development-pilot"] = "development-pilot"
    mode: Literal["draft-no-dispatch"] = "draft-no-dispatch"
    approval_status: Literal["approval-needed"] = "approval-needed"
    execution_state: Literal["not-executed"] = "not-executed"
    arms: tuple[DraftArm, DraftArm]
    cases: tuple[DevelopmentCase, ...]
    full_development_case_count: Literal[36] = 36
    development_input_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    seed: int = 1729
    repeats: Literal[3, 5] = 3
    conditions: tuple[Literal["clean", "ambiguous", "poisoned"], ...] = CONDITIONS
    cells: tuple[Literal["C0", "C1", "C2"], ...] = CELLS
    maximum_turns: Literal[3] = 3
    maximum_calls: Literal[6] = 6
    maximum_retry_per_request: Literal[1] = 1
    planned_input_token_cap: int = Field(default=4096, ge=1)
    planned_output_token_cap: int = Field(default=1024, ge=1)
    token_fit_verified: Literal[False] = False
    dated_prices: None = None
    authorized_spend_receipt: None = None
    absolute_utility_floor: None = None

    @model_validator(mode="after")
    def check_design(self):
        if self.arms[0].slot == self.arms[1].slot:
            raise ValueError("two distinct arm slots required")
        families = [arm.family for arm in self.arms]
        identities = [arm.model_id for arm in self.arms]
        if None not in families and families[0] == families[1]:
            raise ValueError("declared families must be distinct; unresolved is explicit None")
        if None not in identities and identities[0] == identities[1]:
            raise ValueError("declared model identities must be distinct")
        if (len(self.cases) != 6 or len({case.task_id for case in self.cases}) != 6
                or {case.task_class for case in self.cases} != set(CLASSES)):
            raise ValueError("pilot requires one unique public development case per class")
        if self.conditions != CONDITIONS or self.cells != CELLS:
            raise ValueError("the draft keeps the complete paired three-condition/cell matrix")
        return self


class PilotObservation(DraftRecord):
    """Externally recorded task-run counters; no inference from utility to validity.

    Callers must join their immutable journal and scheduled trial before supplying
    a row. A hash attests identity, not independent authenticity.
    """
    task_id: str = Field(min_length=1, max_length=256)
    arm_slot: str = Field(min_length=1, max_length=64)
    condition: Literal["clean", "ambiguous", "poisoned"]
    cell: Literal["C0", "C1", "C2"]
    repeat: int = Field(ge=1, le=5)
    evidence_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    execution_mode: Literal["replay", "live"]
    utility_basis: Literal["semantic-v2"] = "semantic-v2"
    utility_success: bool | None
    request_attempts: int = Field(ge=0, le=6)
    transport_failed_attempts: int = Field(ge=0, le=6)
    model_outputs: int = Field(ge=0, le=3)
    semantic_invalid_outputs: int = Field(ge=0, le=3)
    provider_id: str | None = None
    requested_model_id: str | None = None
    returned_model_id: str | None = None

    @model_validator(mode="after")
    def check_counters(self):
        if (self.transport_failed_attempts > self.request_attempts
                or self.model_outputs > self.request_attempts - self.transport_failed_attempts
                or self.semantic_invalid_outputs > self.model_outputs):
            raise ValueError("pilot counters violate attempt/output lineage")
        if self.execution_mode == "live":
            if not self.provider_id or not self.requested_model_id:
                raise ValueError("live evidence requires exact provider/requested identity")
            if self.model_outputs and self.returned_model_id != self.requested_model_id:
                raise ValueError("returned model identity missing or changed")
        elif any((self.provider_id, self.requested_model_id, self.returned_model_id)):
            raise ValueError("replay diagnostics cannot impersonate provider identities")
        return self


class ArmPilotSummary(DraftRecord):
    arm_slot: str
    scheduled_task_runs: int
    supplied_task_runs: int
    missing_task_runs: int
    known_utility_trials: int
    unknown_utility_trials: int
    successful_utility_trials: int
    model_outputs: int
    semantic_invalid_outputs: int
    semantic_invalid_rate: float | None
    request_attempts: int
    transport_failed_attempts: int
    transport_failure_rate: float | None
    bernoulli_utility_variance: float | None
    utility_wilson: dict[str, int | float | None]
    proposes_five_repeats: bool
    requires_transport_repair: bool


class PilotSummary(DraftRecord):
    schema_version: Literal[1] = 1
    kind: Literal["development-evidence-summary-draft"] = "development-evidence-summary-draft"
    evidence_state: Literal["no-evidence", "incomplete", "supplied-complete"]
    execution_mode: Literal["replay", "live"] | None
    manifest_sha256: str
    input_evidence_sha256: str
    arms: tuple[ArmPilotSummary, ArmPilotSummary]
    proposed_repeats_for_both_arms: Literal[3, 5]
    next_action: Literal["collect-pilot-evidence", "repair-and-repilot", "request-repeat-approval",
                         "request-full-development-calibration"]
    dispatch_authorized: Literal[False] = False
    absolute_utility_floor: None = None
    interpretation: Literal["draft-not-product-acceptance"] = "draft-not-product-acceptance"


class ThresholdProposal(DraftRecord):
    schema_version: Literal[1] = 1
    status: Literal["approval-needed"] = "approval-needed"
    absolute_utility_floor: None = None
    paired_retention_margin: float = Field(default=0.05, ge=0.05, le=0.05)
    full_development_cases_required: Literal[36] = 36
    independent_approval: None = None
    utility_floor_rationale: str
    proposed_repeats_for_both_arms: Literal[3, 5]
    pilot_summary_sha256: str | None = None
    uncertainty_rule: Literal["pending-independent-approval"] = "pending-independent-approval"
    dispatch_authorized: Literal[False] = False
