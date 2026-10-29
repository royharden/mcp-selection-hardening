"""Public full-development protocol, observations and explicit future admission."""

from typing import Literal

from pydantic import Field, JsonValue, model_validator

from mcpsh.records import TrialOutcome

from .models import DevelopmentCase, DraftArm, DraftRecord, PilotObservation


class ProtocolSettings(DraftRecord):
    repeats: Literal[3, 5] = 3
    seed: int = 1729
    conditions: tuple[Literal["clean", "ambiguous", "poisoned"], ...] = ("clean", "ambiguous", "poisoned")
    cells: tuple[Literal["C0", "C1", "C2"], ...] = ("C0", "C1", "C2")
    maximum_turns: Literal[3] = 3
    maximum_calls: Literal[6] = 6
    maximum_retry_per_request: Literal[1] = 1
    utility_basis: Literal["semantic-v2"] = "semantic-v2"
    baseline_selectors: tuple[Literal["keyword", "abstain", "deny-all"], ...] = ("keyword", "abstain", "deny-all")

    @model_validator(mode="after")
    def fixed_core(self):
        if (self.conditions != ("clean", "ambiguous", "poisoned") or self.cells != ("C0", "C1", "C2")
                or self.baseline_selectors != ("keyword", "abstain", "deny-all")):
            raise ValueError("full paired matrix and declared public baselines required")
        return self


class CalibrationSlot(DraftRecord):
    slot_id: str
    task_id: str
    arm_slot: str
    selector: Literal["model", "keyword", "abstain", "deny-all"]
    condition: Literal["clean", "ambiguous", "poisoned"]
    cell: Literal["C0", "C1", "C2", "control"]
    repeat: int = Field(ge=1, le=5)


class DevelopmentProtocolPlan(DraftRecord):
    schema_version: Literal[1] = 1
    kind: Literal["full36-development-protocol-draft"] = "full36-development-protocol-draft"
    approval_status: Literal["approval-needed"] = "approval-needed"
    corpus_phase: Literal["public-development"] = "public-development"
    pilot_manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    pilot_summary_sha256: str | None = None
    pilot_evidence_state: Literal["no-evidence", "incomplete", "supplied-complete"] = "no-evidence"
    pilot_execution_mode: Literal["live", "replay"] | None = None
    pilot_requires_transport_repair: bool = False
    development_input_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    arms: tuple[DraftArm, DraftArm]
    cases: tuple[DevelopmentCase, ...]
    settings: ProtocolSettings
    settings_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    slots: tuple[CalibrationSlot, ...]
    dispatch_authorized: Literal[False] = False


class CalibrationOutcome(DraftRecord):
    slot_id: str
    settings_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    evidence_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    outcome_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    outcome: TrialOutcome
    attempts: PilotObservation | None = None


class ProtocolFailure(DraftRecord):
    slot_id: str
    category: str


class ProtocolAdmission(DraftRecord):
    """Future explicit runtime grant; not a threshold approval or experiment grant."""
    plan_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    settings_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    pilot_summary_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    receipt_id: str = Field(min_length=1)
    expires_at: str
    authorized: bool = False
    dirty_mode_closed: bool = False
    execution_mode: Literal["live", "replay"]
    model_dispatch_approval_id: str | None = None


class ProtocolRun(DraftRecord):
    plan_sha256: str
    outcomes: tuple[CalibrationOutcome, ...]
    failures: tuple[ProtocolFailure, ...]
    state: Literal["partial", "collected-not-accepted"]
    independent_acceptance: Literal["pending"] = "pending"


class DevelopmentSummary(DraftRecord):
    schema_version: Literal[1] = 1
    evidence_state: Literal["no-evidence", "incomplete", "supplied-complete"]
    plan_sha256: str
    settings_sha256: str
    outcomes_sha256: str
    scheduled_slots: int
    supplied_slots: int
    missing_slots: int
    failed_slots: int
    unknown_cost_slots: int
    incomplete_observation_slots: int
    groups: tuple[dict[str, JsonValue], ...]
    repeat_diagnostics: dict[str, JsonValue]
    paired_retention: tuple[dict[str, JsonValue], ...]
    next_action: Literal["collect-development-evidence", "repair-and-repilot", "request-repeat-approval",
                         "request-independent-floor-review"]
    proposed_repeats_for_both_arms: Literal[3, 5]
    absolute_utility_floor: None = None
    independent_approval: None = None
    dispatch_authorized: Literal[False] = False


class FullDevelopmentProposal(DraftRecord):
    status: Literal["approval-needed"] = "approval-needed"
    plan_sha256: str
    settings_sha256: str
    full36_summary_sha256: str
    outcomes_sha256: str
    absolute_utility_floor: None = None
    proposed_repeats_for_both_arms: Literal[3, 5]
    independent_approval: None = None
    rationale: str
    retention_decision: Literal["pending", "inconclusive", "fail", "pass"]
    uncertainty_rule: Literal["pending-independent-approval"] = "pending-independent-approval"
