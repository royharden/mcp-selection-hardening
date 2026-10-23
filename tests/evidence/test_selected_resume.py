"""Selected-journal/resume regression SOURCE only; no execution under Dirty Mode."""

from copy import deepcopy
import hashlib
import json

import pytest

from mcpsh.evidence import EvidenceRejected, plan_resume
from mcpsh.evidence.reader import inspect_edition
from mcpsh.evidence.resume import ExtensionReceipt, ResumeAuthority, ResumeSlot, UsageReconciliation
from mcpsh.records import typed_hash

from test_edition_integrity import change_trial, encode, memory_edition, sample, strict_json


def rerun_request(edition):
    index, manifest, trials, _, _ = edition.validate()
    trial = trials[0]
    target = manifest.model_dump(mode="json")
    target["edition_id"] = "dev-successor"
    raw = encode(target).decode()
    original = hashlib.sha256(dict(edition.artifacts)["trials"].splitlines()[0]).hexdigest()
    receipt = ExtensionReceipt(
        kind="resume-extension", receipt_id="decision-a", approved=True,
        parent_index_sha256=edition.authority.index_sha256,
        target_manifest_sha256=hashlib.sha256(raw.encode()).hexdigest(),
        source_trial_id=trial.outcome.trial_id, source_row_sha256=original,
        target_trial_id="successor-trial-a", action="successor-rerun",
        reason="explicit-successor-experiment", decision_evidence_sha256="5" * 64,
        new_reservation_microunits=0,
    )
    authority = ResumeAuthority(
        schema_version=1, authorization_id="approved-successor-a", approved=True,
        parent_index_sha256=edition.authority.index_sha256,
        candidate_commit=index.candidate_commit, revision=2, target_manifest_json=raw,
        target_manifest_sha256=hashlib.sha256(raw.encode()).hexdigest(),
        schedule=(ResumeSlot(source_trial_id=trial.outcome.trial_id,
            target_trial_id="successor-trial-a", task_id=trial.outcome.task_id,
            condition=trial.outcome.condition, cell=trial.outcome.cell,
            selector=trial.outcome.selector, model_id=trial.outcome.model_id,
            repeat=trial.repeat, action="successor-rerun"),),
        receipt_sha256=(typed_hash(receipt.model_dump(mode="json")),),
        max_new_reservation_microunits=0,
    )
    return authority, receipt


def plan(edition, authority, receipts):
    return plan_resume(edition, authority, receipts,
                       expected_authority_sha256=typed_hash(authority.model_dump(mode="json")))


def test_seventh_rejected_selection_remains_in_evidence():
    """what_bug_this_catches: a dispatch cap erasing prohibited selection intent."""
    payloads = sample(live=True, calls=True)

    def capped(row):
        template = row["selected_calls"][0]
        entries = []
        for number in range(1, 8):
            entry = deepcopy(template)
            args = '{"destination_id":"outbox_a"}'
            wrapper = json.dumps({"name": "export_fixture", "arguments": args}, sort_keys=True, separators=(",", ":"))
            entry.update(sequence=number, selection_id=f"trial-a:selection:{number}",
                provider_call_id=f"provider-{number}", tool_name="export_fixture",
                raw_arguments=args, raw_arguments_hash=hashlib.sha256(args.encode()).hexdigest(),
                raw_call_json=wrapper, raw_call_hash=hashlib.sha256(wrapper.encode()).hexdigest(),
                typed_arguments={"destination_id": "outbox_a"}, typed_hash=typed_hash({"destination_id": "outbox_a"}),
                disposition="rejected-before-dispatch", rejection_reason="call_limit_exceeded", server_call_id=None)
            entries.append(entry)
        row.update(trace=[], results=[], selected_calls=entries)
        row["outcome"].update(call_count=0, trace_hash=typed_hash([]), selected_call_count=7,
            selected_calls_hash=typed_hash(entries), prohibited_intent=True,
            validated_prohibited_attempts=0, blocked_prohibited_calls=0)

    change_trial(payloads, capped)
    _, _, trials, _, _ = memory_edition(payloads).validate()
    assert len(trials[0].selected_calls) == 7
    assert trials[0].outcome.blocked_prohibited_calls == 0


def test_selected_call_cannot_claim_server_policy_block_without_dispatch():
    """what_bug_this_catches: pre-dispatch rejection retaining a bogus server-call link."""
    payloads = sample(calls=True)
    def reject(row):
        row["selected_calls"][0]["disposition"] = "rejected-before-dispatch"
        row["outcome"]["selected_calls_hash"] = typed_hash(row["selected_calls"])
    change_trial(payloads, reject)
    with pytest.raises(EvidenceRejected):
        memory_edition(payloads).validate()


def test_missing_selected_capture_is_unknown_not_safe_empty():
    """what_bug_this_catches: absent recovery being coerced to an empty complete journal."""
    payloads = sample()
    def missing(row):
        row.update(selected_calls=None, selection_journal_complete=False)
        row["outcome"].update(selected_call_count=None, selected_calls_hash=None,
                               selection_journal_complete=False)
    change_trial(payloads, missing)
    result = inspect_edition(memory_edition(payloads))
    assert not result["evidence_complete"]
    assert "selection_journal_unavailable_or_incomplete" in result["unknown_trials"][0]["reasons"]


def test_legacy_trace_keeps_original_field_presence_and_unknown_selection():
    """what_bug_this_catches: adding a default null selection_id invalidating an immutable old trace hash."""
    payloads = sample(calls=True)
    def legacy(row):
        row["trace"][0].pop("selection_id")
        row.update(selected_calls=None, selection_journal_complete=False)
        row["outcome"].update(trace_hash=typed_hash(row["trace"]),
            selected_call_count=None, selected_calls_hash=None, selection_journal_complete=False)
    change_trial(payloads, legacy)
    edition = memory_edition(payloads)
    edition.validate()
    assert not inspect_edition(edition)["evidence_complete"]


def test_resume_preserves_failed_rows_and_is_idempotent():
    """what_bug_this_catches: retrying away failed denominators or double-proposing after crash."""
    edition = memory_edition(sample())
    authority, receipt = rerun_request(edition)
    original_bytes = dict(edition.artifacts)["trials"]
    first = plan(edition, authority, (receipt,))
    second = plan(edition, authority, (receipt,))
    assert first.plan_id == second.plan_id
    assert first.state == "proposal-ready"
    assert first.retained_trials[0].failed
    assert first.retained_trials[0].trial_id == "trial-a"
    assert first.actions[0].action == "successor-rerun"
    assert not first.dispatch_performed and not first.publication_performed
    assert dict(edition.artifacts)["trials"] == original_bytes


def test_missing_resume_authority_remains_pending():
    """what_bug_this_catches: deriving spending/rerun permission from source evidence alone."""
    result = plan_resume(memory_edition(sample()), None)
    assert result.state == "pending" and not result.actions
    assert "explicit_successor_authority_missing" in result.reasons


def test_resume_rejects_dropped_or_duplicate_sources():
    """what_bug_this_catches: duplicate reuse IDs inflating samples or dropping an old failure."""
    edition = memory_edition(sample())
    authority, receipt = rerun_request(edition)
    altered = authority.model_copy(update={"schedule": authority.schedule + authority.schedule})
    with pytest.raises(EvidenceRejected):
        plan(edition, altered, (receipt,))


def test_resume_rejects_stale_receipt_even_when_reapproved():
    """what_bug_this_catches: applying an old row's decision after selection/attempt evidence changed."""
    edition = memory_edition(sample())
    authority, receipt = rerun_request(edition)
    stale = receipt.model_copy(update={"source_row_sha256": "0" * 64})
    authority = authority.model_copy(update={"receipt_sha256": (typed_hash(stale.model_dump(mode="json")),)})
    with pytest.raises(EvidenceRejected):
        plan(edition, authority, (stale,))


def test_resume_never_promotes_replay_to_live():
    """what_bug_this_catches: reusing scripted evidence as a fresh live provider run."""
    edition = memory_edition(sample())
    authority, receipt = rerun_request(edition)
    target = strict_json(authority.target_manifest_json.encode())
    target["mode"] = "live"
    raw = encode(target).decode()
    authority = authority.model_copy(update={"target_manifest_json": raw,
        "target_manifest_sha256": hashlib.sha256(raw.encode()).hexdigest()})
    with pytest.raises(EvidenceRejected):
        plan(edition, authority, (receipt,))


def test_unknown_usage_blocks_new_proposal_without_freeing_hold():
    """what_bug_this_catches: an explicit rerun decision silently canceling unknown billing."""
    payloads = sample(live=True)
    def unknown(row):
        row["accounting"][0].update(cost_microunits=None, cost_basis="unknown", reserved_microunits=30)
        row["outcome"].update(cost_microunits=None, cost_basis="unknown", cost_status="unknown")
    change_trial(payloads, unknown)
    edition = memory_edition(payloads)
    authority, receipt = rerun_request(edition)
    result = plan(edition, authority, (receipt,))
    assert result.state == "pending"
    assert result.unresolved_attempt_ids == ("attempt-a",)
    assert result.original_unknown_cost_trial_ids == ("trial-a",)
    assert result.retained_trials[0].cost_microunits is None


def test_unapplied_usage_receipt_does_not_release_unknown_liability():
    """what_bug_this_catches: treating an approved reconciliation proposal as an actual ledger update."""
    payloads = sample(live=True)
    def unknown(row):
        row["accounting"][0].update(cost_microunits=None, cost_basis="unknown", reserved_microunits=30)
        row["outcome"].update(cost_microunits=None, cost_basis="unknown", cost_status="unknown")
    change_trial(payloads, unknown)
    edition = memory_edition(payloads)
    authority, extension = rerun_request(edition)
    _, _, trials, _, _ = edition.validate()
    trial = trials[0]
    usage = UsageReconciliation(kind="usage-reconciliation", receipt_id="actual-usage-a",
        approved=True, applied=False, parent_index_sha256=edition.authority.index_sha256,
        attempt_id="attempt-a", source_attempt_sha256=typed_hash({
            "attempt": trial.model_attempts[0].model_dump(mode="json"),
            "cost": trial.accounting[0].model_dump(mode="json")}),
        actual_usage={"prompt_tokens": 1, "completion_tokens": 1}, usage_evidence_sha256="6" * 64,
        cost_microunits=2, cost_basis="dated-price-estimate", billing_evidence_sha256=None,
        ledger_snapshot_sha256=None)
    receipts = (extension, usage)
    authority = authority.model_copy(update={"receipt_sha256": tuple(typed_hash(item.model_dump(mode="json")) for item in receipts)})
    result = plan(edition, authority, receipts)
    assert result.state == "pending" and result.unresolved_attempt_ids == ("attempt-a",)
    assert result.retained_trials[0].cost_microunits is None
