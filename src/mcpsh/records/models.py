"""Version-one contracts. Frozen records reject extra fields and type coercion."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue

from .hashing import typed_hash

EffectState = Literal["none", "observed", "unknown"]


class Record(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class PublicTaskCase(Record):
    task_id: str
    user_request: str
    allowed_source_ids: tuple[str, ...]
    fixture_ref: str


def public_task_projection(task: PublicTaskCase) -> dict[str, JsonValue]:
    """No oracle labels, split, family, canary, logging context or exceptions escape."""
    if type(task) is not PublicTaskCase:
        raise TypeError("provider input must be an exact PublicTaskCase")
    return {
        "task_id": task.task_id,
        "user_request": task.user_request,
        "allowed_source_ids": list(task.allowed_source_ids),
        "fixture_ref": task.fixture_ref,
    }


class CallPredicate(Record):
    tool_name: str
    arguments: dict[str, JsonValue]


class OracleCase(Record):
    task_id: str
    alternatives: tuple[tuple[CallPredicate, ...], ...]
    utility_alternatives: tuple[tuple[CallPredicate, ...], ...] = ()
    required_output_text: tuple[str, ...] = ()
    prohibited_source_ids: tuple[str, ...] = ("protected_fixture",)
    prohibited_tools: tuple[str, ...] = ("export_fixture",)
    family_id: str
    split: Literal["development", "heldout", "retired"] = "development"
    attack_family: str | None = None


class ExperimentManifest(Record):
    schema_version: Literal[1] = 1
    edition_id: str
    mode: Literal["replay", "live"]
    platform_scope: Literal["synthetic-memory", "filesystem-posix"]
    code_hash: str
    lock_hash: str | None
    protocol_hash: str | None
    task_hash: str
    catalog_hash: str
    policy_hash: str
    scorer_hash: str
    observer_hash: str
    split_hash: str
    seed: int
    model_ids: tuple[str, ...] = ()
    returned_model_ids: tuple[str, ...] = ()
    settings: dict[str, JsonValue] = Field(default_factory=dict)
    matrix: tuple[str, ...] = ("C0", "C1", "C2")
    max_turns: int = Field(default=3, ge=1, le=3)
    max_calls: int = Field(default=6, ge=1, le=6)
    prices: dict[str, JsonValue] = Field(default_factory=dict)
    budget_receipt: str | None = None


class CatalogArtifact(Record):
    server_instance_id: str
    tool_names: tuple[str, ...]
    executable_schema_hash: str
    presented_metadata_hash: str
    overlay_version: str
    normalizer_version: str
    ordering_seed: int


class ModelAttempt(Record):
    attempt_id: str
    request_id: str | None
    response_id: str | None
    raw_response_hash: str | None
    provider_id: str
    requested_model_id: str
    returned_model_id: str | None
    started_at: str
    finished_at: str | None
    status: str
    usage: dict[str, JsonValue]
    settlement_reference: str | None


class ToolCallEvent(Record):
    trial_id: str
    turn_id: int
    call_id: str
    sequence: int
    tool_name: str
    raw_arguments: str
    raw_hash: str
    typed_arguments: dict[str, JsonValue] | None
    typed_hash: str | None
    validation: str
    gate_classification: str
    enforcement_mode: str
    gate_decision: str
    gate_reason: str
    dispatched: bool
    executed: bool
    output_hash: str
    model_attempt_id: str | None = None


class EffectObservation(Record):
    observer_version: str
    complete: bool
    predicates: dict[str, EffectState]
    before_hash: str | None = None
    after_hash: str | None = None
    protected_read_count: int | None = None
    sequence_complete: bool = False
    fixture_reset_verified: bool = False
    failures: tuple[str, ...] = ()


class TrialOutcome(Record):
    trial_id: str
    task_id: str
    family_id: str
    condition: str
    cell: str
    selector: str
    selection_success: bool
    utility_success: bool
    prohibited_intent: bool
    validated_prohibited_attempts: int
    gate_classified_prohibited_calls: int
    blocked_prohibited_calls: int
    gate_false_negative_calls: int
    effect: EffectState
    observation_complete: bool
    scheduled: bool = True
    call_count: int
    failures: tuple[str, ...]
    cost_microunits: int | None
    cost_status: Literal["non-model", "settled", "unknown", "reserved"]
    trace_hash: str
    observation_hash: str
    latency_seconds: float


def record_digest(record: Record) -> str:
    return typed_hash(record.model_dump(mode="json"))
