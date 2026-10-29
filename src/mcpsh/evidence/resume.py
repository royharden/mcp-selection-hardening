"""Typed immutable resume proposals. No ledger mutation, model send or publication."""

import hashlib
from typing import Literal

from pydantic import Field

from mcpsh.records import ExperimentManifest, canonical_json, typed_hash
from pydantic import JsonValue
from mcpsh.records.models import Record

from .reader import EvidenceRejected, VerifiedEdition, inspect_edition, model, strict_json


class ResumeSlot(Record):
    source_trial_id: str
    target_trial_id: str
    task_id: str
    condition: str
    cell: str
    selector: str
    model_id: str | None
    repeat: int | None = Field(default=None, ge=0)
    action: Literal["reuse", "dispatch-unstarted", "successor-rerun"]


class ResumeAuthority(Record):
    schema_version: Literal[1]
    authorization_id: str = Field(min_length=1, max_length=256)
    approved: bool
    parent_index_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    candidate_commit: str = Field(pattern=r"^[0-9a-f]{40}$")
    revision: int = Field(ge=1)
    target_manifest_json: str = Field(max_length=131072)
    target_manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    schedule: tuple[ResumeSlot, ...] = Field(min_length=1, max_length=5000)
    receipt_sha256: tuple[str, ...] = Field(max_length=15000)
    max_new_reservation_microunits: int = Field(ge=0)


class ExtensionReceipt(Record):
    kind: Literal["resume-extension"]
    receipt_id: str = Field(min_length=1, max_length=256)
    approved: bool
    parent_index_sha256: str
    target_manifest_sha256: str
    source_trial_id: str
    source_row_sha256: str
    target_trial_id: str
    action: Literal["reuse", "dispatch-unstarted", "successor-rerun"]
    reason: Literal["reuse-complete-evidence", "proven-not-dispatched", "explicit-successor-experiment"]
    decision_evidence_sha256: str
    new_reservation_microunits: int = Field(ge=0)


class UsageReconciliation(Record):
    kind: Literal["usage-reconciliation"]
    receipt_id: str = Field(min_length=1, max_length=256)
    approved: bool
    applied: bool
    parent_index_sha256: str
    attempt_id: str
    source_attempt_sha256: str
    actual_usage: dict[str, JsonValue]
    usage_evidence_sha256: str
    cost_microunits: int = Field(ge=0)
    cost_basis: Literal["dated-price-estimate", "provider-billed"]
    billing_evidence_sha256: str | None
    ledger_snapshot_sha256: str | None


class RetainedTrial(Record):
    trial_id: str
    task_id: str
    condition: str
    cell: str
    selector: str
    model_id: str | None
    repeat: int | None
    source_row_sha256: str
    original_outcome_sha256: str
    selected_calls_hash: str | None
    model_attempt_ids: tuple[str, ...]
    observation_hash: str
    cost_microunits: int | None
    cost_basis: str
    failed: bool


class ResumeAction(Record):
    source_trial_id: str
    target_trial_id: str
    action: Literal["reuse", "dispatch-unstarted", "successor-rerun"]
    state: Literal["proposed", "pending"]
    source_row_sha256: str
    receipt_id: str | None
    independent_new_sample: bool
    new_reservation_microunits: int | None
    new_charge_microunits: int | None
    reasons: tuple[str, ...]


class ResumePlan(Record):
    schema_version: Literal[1] = 1
    plan_id: str
    parent_index_sha256: str
    authority_sha256: str | None
    target_manifest_sha256: str | None
    state: Literal["proposal-ready", "pending"]
    retained_trials: tuple[RetainedTrial, ...]
    actions: tuple[ResumeAction, ...]
    reconciliation_receipt_ids: tuple[str, ...]
    unresolved_attempt_ids: tuple[str, ...]
    original_known_cost_microunits: int
    original_unknown_cost_trial_ids: tuple[str, ...]
    unattributed_unknown_trial_ids: tuple[str, ...] = ()
    proposed_new_reservation_microunits: int
    dispatch_performed: Literal[False] = False
    publication_performed: Literal[False] = False
    empirical_verdict: Literal["pending"] = "pending"
    product_verdict: Literal["pending"] = "pending"
    reasons: tuple[str, ...]


def _digest(value: str | None) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(ch in "0123456789abcdef" for ch in value)


def _retained(edition, trials):
    raw_lines = dict(edition.artifacts)["trials"].splitlines()
    return tuple(RetainedTrial(
        trial_id=row.outcome.trial_id, task_id=row.outcome.task_id,
        condition=row.outcome.condition, cell=row.outcome.cell,
        selector=row.outcome.selector, model_id=row.outcome.model_id,
        repeat=row.repeat,
        source_row_sha256=hashlib.sha256(raw).hexdigest(),
        original_outcome_sha256=typed_hash(row.outcome.model_dump(mode="json")),
        selected_calls_hash=row.outcome.selected_calls_hash,
        model_attempt_ids=row.outcome.model_attempt_ids, observation_hash=row.outcome.observation_hash,
        cost_microunits=row.outcome.cost_microunits, cost_basis=row.outcome.cost_basis,
        failed=bool(row.outcome.failures),
    ) for row, raw in zip(trials, raw_lines, strict=True))


def _same_experiment(old, new) -> bool:
    fields = ("mode", "platform_scope", "code_hash", "lock_hash", "protocol_hash", "task_hash",
              "catalog_hash", "policy_hash", "scorer_hash", "observer_hash", "split_hash",
              "model_ids", "returned_model_ids", "prices", "matrix", "max_turns", "max_calls", "seed")
    # Budget authority may change, but experimental settings cannot drift during reuse.
    settings_old, settings_new = dict(old.settings), dict(new.settings)
    for key in ("resume_parent_index_sha256", "resume_authorization_id"):
        settings_old.pop(key, None)
        settings_new.pop(key, None)
    return all(getattr(old, key) == getattr(new, key) for key in fields) and settings_old == settings_new


def plan_resume(edition: VerifiedEdition, new_authority: ResumeAuthority | None,
                receipts: tuple[ExtensionReceipt | UsageReconciliation, ...] = (), *,
                expected_authority_sha256: str | None = None) -> ResumePlan:
    """Propose a successor without rewriting failures, spending, or freeing holds.

    Receipt hashes must be separately pinned in the approved authority. Applied usage
    receipts attest actual reconciliation; this planner cannot establish their truth.
    Originals remain immutable even when a successor explicitly authorizes reruns.
    """
    index, manifest, trials, _, _ = edition.validate()
    retained = _retained(edition, trials)
    held = {cost.attempt_id: (trial, cost) for trial in trials for cost in trial.accounting
            if cost.cost_microunits is None or cost.reserved_microunits is None}
    unattributed = {trial.outcome.trial_id for trial in trials
                    if trial.outcome.cost_microunits is None and not trial.accounting}
    reasons, actions, reconciled = [], [], set()
    authority_hash = typed_hash(new_authority.model_dump(mode="json")) if new_authority else None
    if new_authority is None or expected_authority_sha256 is None:
        reasons.append("explicit_successor_authority_missing")
    elif not _digest(expected_authority_sha256) or authority_hash != expected_authority_sha256:
        raise EvidenceRejected("successor authority differs from external pin")
    if new_authority is not None:
        if new_authority.parent_index_sha256 != edition.authority.index_sha256:
            raise EvidenceRejected("resume parent edition differs")
        if hashlib.sha256(new_authority.target_manifest_json.encode()).hexdigest() != new_authority.target_manifest_sha256:
            raise EvidenceRejected("successor manifest byte pin mismatch")
        target = model(ExperimentManifest, strict_json(new_authority.target_manifest_json.encode()))
        if target.mode != manifest.mode or target.platform_scope != manifest.platform_scope:
            raise EvidenceRejected("resume cannot promote replay/live or memory/filesystem provenance")
        if target.edition_id == index.edition_id or new_authority.revision <= index.revision:
            raise EvidenceRejected("resume requires a distinct immutable successor edition/revision")
        if not new_authority.approved:
            reasons.append("successor_authority_unapproved")
        by_source = {slot.source_trial_id: slot for slot in new_authority.schedule}
        targets = [slot.target_trial_id for slot in new_authority.schedule]
        if len(by_source) != len(new_authority.schedule) or set(by_source) != {row.trial_id for row in retained}:
            raise EvidenceRejected("resume drops/duplicates original scheduled denominators")
        if len(set(targets)) != len(targets) or set(targets) & {row.trial_id for row in retained}:
            raise EvidenceRejected("successor trial identities duplicate or overwrite originals")
        receipt_ids = [receipt.receipt_id for receipt in receipts]
        receipt_hashes = [typed_hash(receipt.model_dump(mode="json")) for receipt in receipts]
        if len(set(receipt_ids)) != len(receipt_ids) or len(set(receipt_hashes)) != len(receipt_hashes):
            raise EvidenceRejected("duplicate receipt/reuse/reconciliation")
        if set(receipt_hashes) != set(new_authority.receipt_sha256) or len(set(new_authority.receipt_sha256)) != len(new_authority.receipt_sha256):
            raise EvidenceRejected("receipts differ from explicitly pinned authority")
        extensions, usages = {}, {}
        for receipt in receipts:
            if receipt.parent_index_sha256 != index_hash(edition):
                raise EvidenceRejected("receipt has wrong immutable parent")
            if isinstance(receipt, ExtensionReceipt):
                if receipt.source_trial_id in extensions:
                    raise EvidenceRejected("duplicate reuse/extension for original trial")
                extensions[receipt.source_trial_id] = receipt
            else:
                if receipt.attempt_id in usages or receipt.attempt_id not in held:
                    raise EvidenceRejected("duplicate/unbound usage reconciliation")
                usages[receipt.attempt_id] = receipt
                trial, cost = held[receipt.attempt_id]
                attempt = next(item for item in trial.model_attempts if item.attempt_id == receipt.attempt_id)
                expected = typed_hash({"attempt": attempt.model_dump(mode="json"), "cost": cost.model_dump(mode="json")})
                if receipt.source_attempt_sha256 != expected or not _digest(receipt.usage_evidence_sha256):
                    raise EvidenceRejected("usage receipt is stale or lacks actual usage evidence")
                strict_json(canonical_json(receipt.actual_usage).encode())
                if not receipt.actual_usage:
                    raise EvidenceRejected("reconciliation cannot assume missing usage is zero")
                required_usage = ({"prompt_tokens", "completion_tokens"} if attempt.provider_id == "openai"
                                  else {"input_tokens", "output_tokens"} if attempt.provider_id == "anthropic" else set())
                if not required_usage or not required_usage <= set(receipt.actual_usage) or any(
                        type(receipt.actual_usage[key]) is not int or receipt.actual_usage[key] < 0 for key in required_usage):
                    raise EvidenceRejected("actual reconciliation usage lacks provider token fields")
                if receipt.cost_basis == "provider-billed" and not _digest(receipt.billing_evidence_sha256):
                    raise EvidenceRejected("billed-cost assertion requires explicit billing evidence")
                priced = receipt.cost_basis == "provider-billed"
                if receipt.cost_basis == "dated-price-estimate":
                    original_prices = manifest.prices.get(attempt.requested_model_id)
                    if isinstance(original_prices, dict):
                        from mcpsh.adapters.live import DatedTokenPrices
                        try:
                            keys = (("prompt_tokens", "completion_tokens") if attempt.provider_id == "openai"
                                    else ("input_tokens", "output_tokens"))
                            expected_cost = DatedTokenPrices(**original_prices).estimate(attempt.provider_id,
                                {"usage": receipt.actual_usage, "input_tokens": receipt.actual_usage[keys[0]],
                                 "output_tokens": receipt.actual_usage[keys[1]]})
                        except (ValueError, TypeError, KeyError, AttributeError):
                            expected_cost = None
                        if expected_cost is None or expected_cost != receipt.cost_microunits:
                            raise EvidenceRejected("usage reconciliation disagrees with original approved price basis")
                        priced = True
                if receipt.approved and receipt.applied and priced and _digest(receipt.ledger_snapshot_sha256):
                    reconciled.add(receipt.attempt_id)
        same = _same_experiment(manifest, target)
        incomplete = {item["trial_id"]: set(item["reasons"]) for item in inspect_edition(edition)["unknown_trials"]}
        for original, trial in zip(retained, trials, strict=True):
            slot = by_source[original.trial_id]
            if (slot.task_id, slot.condition, slot.cell, slot.selector, slot.model_id, slot.repeat) != (original.task_id, original.condition, original.cell, original.selector, original.model_id, original.repeat):
                raise EvidenceRejected("resume changes original case/cell/model identity")
            receipt = extensions.get(original.trial_id)
            pending = []
            if original.repeat is None:
                pending.append("repeat_identity_unavailable")
            if receipt is None or not receipt.approved:
                pending.append("action_receipt_missing_or_unapproved")
            else:
                if (receipt.target_trial_id, receipt.action, receipt.source_row_sha256, receipt.target_manifest_sha256) != (slot.target_trial_id, slot.action, original.source_row_sha256, new_authority.target_manifest_sha256):
                    raise EvidenceRejected("extension receipt input/action lineage mismatch")
                if not _digest(receipt.decision_evidence_sha256):
                    raise EvidenceRejected("action has no explicit decision evidence pin")
                if slot.action == "reuse":
                    if not same or new_authority.candidate_commit != index.candidate_commit:
                        raise EvidenceRejected("changed source/schema/scorer/corpus/price inputs cannot earn reuse")
                    if receipt.reason != "reuse-complete-evidence" or receipt.new_reservation_microunits != 0:
                        raise EvidenceRejected("reuse must have zero new reservation, not duplicate billing")
                    missing = incomplete.get(original.trial_id, set())
                    trial_held = {cost.attempt_id for cost in trial.accounting if cost.attempt_id in held}
                    if missing and not (missing <= {"usage_or_reservation_incomplete"} and trial_held and trial_held <= reconciled):
                        pending.append("reused_evidence_incomplete")
                elif slot.action == "dispatch-unstarted":
                    if not same or not original.failed or trial.model_attempts or trial.trace or trial.selected_calls:
                        raise EvidenceRejected("unstarted resume cannot erase existing attempts/selections/effects")
                    if receipt.reason != "proven-not-dispatched":
                        raise EvidenceRejected("new dispatch requires explicit non-dispatch proof")
                elif receipt.reason != "explicit-successor-experiment":
                    raise EvidenceRejected("bad semantic/model outcomes require an explicit successor experiment")
                if slot.action != "reuse" and target.mode == "live" and receipt.new_reservation_microunits <= 0:
                    pending.append("positive_live_reservation_required")
                if slot.action == "dispatch-unstarted" and receipt.reason == "proven-not-dispatched":
                    unattributed.discard(original.trial_id)
            if held.keys() - reconciled:
                pending.append("prior_usage_or_reservation_unreconciled")
            if reasons:
                pending.extend(reasons)
            actions.append(ResumeAction(source_trial_id=slot.source_trial_id,
                target_trial_id=slot.target_trial_id, action=slot.action,
                state="pending" if pending else "proposed", source_row_sha256=original.source_row_sha256,
                receipt_id=receipt.receipt_id if receipt else None,
                independent_new_sample=target.mode == "live" and slot.action != "reuse",
                new_reservation_microunits=receipt.new_reservation_microunits if receipt else None,
                new_charge_microunits=0 if slot.action == "reuse" else None,
                reasons=tuple(dict.fromkeys(pending))))
        if set(extensions) - set(by_source):
            raise EvidenceRejected("extension receipt is outside the approved schedule")
        reservation = sum(item.new_reservation_microunits or 0 for item in actions)
        if reservation > new_authority.max_new_reservation_microunits:
            raise EvidenceRejected("resume reservation proposal exceeds approved extension budget")
    else:
        reservation = 0
    if held.keys() - reconciled:
        reasons.append("prior_usage_or_reservation_unreconciled")
    if unattributed:
        reasons.append("unattributed_usage_unknown")
    if any(item.state == "pending" for item in actions):
        reasons.append("one_or_more_actions_pending")
    body = dict(schema_version=1, parent_index_sha256=index_hash(edition), authority_sha256=authority_hash,
        target_manifest_sha256=new_authority.target_manifest_sha256 if new_authority else None,
        state="pending" if reasons else "proposal-ready", retained_trials=retained, actions=tuple(actions),
        reconciliation_receipt_ids=tuple(sorted(receipt.receipt_id for receipt in receipts if isinstance(receipt, UsageReconciliation))),
        unresolved_attempt_ids=tuple(sorted(held.keys() - reconciled)),
        original_known_cost_microunits=sum(row.cost_microunits or 0 for row in retained),
        original_unknown_cost_trial_ids=tuple(row.trial_id for row in retained if row.cost_microunits is None),
        unattributed_unknown_trial_ids=tuple(sorted(unattributed)),
        proposed_new_reservation_microunits=reservation, reasons=tuple(dict.fromkeys(reasons)))
    provisional = ResumePlan(plan_id="0" * 64, **body)
    digest_body = provisional.model_dump(mode="json")
    digest_body.pop("plan_id")
    return provisional.model_copy(update={"plan_id": typed_hash(digest_body)})


def index_hash(edition: VerifiedEdition) -> str:
    return edition.authority.index_sha256
