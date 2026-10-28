"""Closed, bounded v1 offline edition contracts. No I/O on import."""

from typing import Literal

from pydantic import Field

from mcpsh.records.models import (
    ExperimentManifest, FinalAssistantResponse, ModelAttempt,
    OracleCase, PublicTaskCase, Record, SelectedCall, ToolCallEvent, ToolResultCapture, TrialOutcome,
)

Digest = str


class FilePin(Record):
    path: str = Field(min_length=1, max_length=256)
    sha256: Digest = Field(pattern=r"^[0-9a-f]{64}$")
    bytes: int = Field(ge=0, le=32 * 1024 * 1024)


class InputPins(Record):
    code_hash: Digest
    lock_hash: Digest | None
    protocol_hash: Digest | None
    task_hash: Digest
    catalog_hash: Digest
    policy_hash: Digest
    scorer_hash: Digest
    observer_hash: Digest
    split_hash: Digest


class EditionIndex(Record):
    kind: Literal["mcpsh-evidence-edition"]
    schema_version: Literal[1]
    revision: int = Field(ge=1)
    edition_id: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]*$")
    candidate_commit: str = Field(pattern=r"^[0-9a-f]{40}$")
    mode: Literal["replay", "live"]
    platform_scope: Literal["synthetic-memory", "filesystem-posix"]
    input_pins: InputPins
    manifest: FilePin
    trials: FilePin
    observers: FilePin | None
    oracles: FilePin | None
    scheduled_trial_ids: tuple[str, ...] = Field(min_length=1, max_length=5000)
    empirical_verdict: Literal["pending"]
    product_verdict: Literal["pending"]


class EditionAuthority(Record):
    """Provided externally; never inferred by trusting an index's own claims."""
    index_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    candidate_commit: str = Field(pattern=r"^[0-9a-f]{40}$")
    revision: int = Field(ge=1)
    edition_id: str
    mode: Literal["replay", "live"]
    platform_scope: Literal["synthetic-memory", "filesystem-posix"]
    input_pins: InputPins


class AttemptCost(Record):
    attempt_id: str
    operation_id: str
    status: str
    dispatch_status: str
    cost_microunits: int | None = Field(ge=0)
    cost_basis: Literal["dated-price-estimate", "unknown"]
    settlement_reference: str | None
    reserved_microunits: int | None = Field(ge=0)


class ReuseReference(Record):
    kind: Literal["reused-evidence"]
    source_index_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_trial_id: str
    source_row_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_outcome_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    original_cost_microunits: int | None = Field(ge=0)
    original_cost_basis: str
    new_charge_microunits: Literal[0]
    independent_new_sample: Literal[False]


class EvidenceTrial(Record):
    outcome: TrialOutcome
    repeat: int | None = Field(default=None, ge=0)
    reuse: ReuseReference | None = None
    selected_calls: tuple[SelectedCall, ...] | None = Field(default=None, max_length=65536)
    selection_journal_complete: bool | None = None
    fixture_ref: str | None = None
    fixture_payload_hash: str | None = None
    catalog_hash: str | None = None
    normalization_diff_hash: str | None = None
    trace: tuple[ToolCallEvent, ...] | None = Field(max_length=6)
    results: tuple[dict, ...] | None = Field(max_length=6)
    model_attempts: tuple[ModelAttempt, ...] = Field(max_length=6)
    accounting: tuple[AttemptCost, ...] = Field(max_length=6)
    final_response: FinalAssistantResponse | None
    result_captures: tuple[ToolResultCapture, ...] | None = Field(max_length=6)


class BrokerEvent(Record):
    trial_id: str
    epoch: str
    sequence: int = Field(ge=1)
    kind: Literal["fixture_ready", "operation_start", "operation_end", "source_read", "outbox_write"]
    fixture_hash: str | None = None
    counters_zero: bool | None = None
    call_id: str | None = None
    operation: str | None = None
    response_hash: str | None = None
    source_id: str | None = None
    protected: bool | None = None
    bytes_read: int | None = Field(default=None, ge=0)
    bytes_read_at_first_chunk: int | None = Field(default=None, ge=0)
    destination_id: str | None = None
    digest: str | None = None


class WireObservation(Record):
    call_id: str
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    bytes: int = Field(ge=0, le=32768)
    canary_observed: bool


class RawObservation(Record):
    observer_version: str | None = None
    trial_id: str | None = None
    fixture_payload_sha256: str | None = None
    platform_scope: Literal["synthetic-memory", "filesystem-posix"] | None = None
    complete: bool
    predicates: dict[str, Literal["none", "observed", "unknown"]]
    protected_read_count: int | None = Field(default=None, ge=0)
    outbox_hashes: dict[str, str] = Field(default_factory=dict)
    before_hash: str | None = None
    after_hash: str | None = None
    sequence_complete: bool = False
    wire_complete: bool = False
    reset_verified: bool = False
    events: tuple[BrokerEvent, ...] = Field(default=(), max_length=1000)
    wire_observations: tuple[WireObservation, ...] = Field(default=(), max_length=6)
    failure: str | None = None


class ObserverRecord(Record):
    trial_id: str
    platform_scope: Literal["synthetic-memory", "filesystem-posix"]
    observer_code_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    # Preserve exact original field presence for outcome.observation_hash.
    # Reader validates this against RawObservation without hashing added defaults.
    observation: dict


class OracleEntry(Record):
    public: PublicTaskCase
    oracle: OracleCase


class OraclePackage(Record):
    schema_version: Literal[1]
    cases: tuple[OracleEntry, ...] = Field(min_length=1, max_length=36)


__all__ = ["EditionAuthority", "EditionIndex", "EvidenceTrial", "ObserverRecord",
           "OraclePackage", "ExperimentManifest"]
