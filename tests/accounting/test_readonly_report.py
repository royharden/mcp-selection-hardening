"""Read-only ledger audit regression SOURCE; no DB/test execution in Dirty Mode."""

from copy import deepcopy
import hashlib
import json
import sqlite3
from types import SimpleNamespace as NS

import pytest

from mcpsh.accounting import CostLedger
from mcpsh.accounting import report
from mcpsh.evidence.reader import EvidenceRejected
from mcpsh.records import typed_hash


def snapshot_pin(path):
    # Independent synthetic authority selection for source tests, not production trust.
    with sqlite3.connect(path) as db:
        return typed_hash({name: [dict(zip(columns, row, strict=True)) for row in
            db.execute(f"SELECT * FROM {name} ORDER BY 1")] for name, columns in report.TABLES.items()})


def setup(tmp_path, *, unknown=False, cancelled=False):
    path = tmp_path / "synthetic.sqlite"
    ledger = CostLedger(path, 100)
    ledger.reserve("op", 20, {"provider": "openai", "model": "fake", "price_snapshot_hash": "p" * 64,
                              "request_hash": "r" * 64})
    ledger.begin_attempt("op", "attempt", "openai", "fake")
    ledger.authorize_dispatch("op", "attempt", scope="synthetic-scope", max_requests=1)
    ledger.settle("attempt", None if unknown else 2, {"prompt_tokens": 1, "completion_tokens": 1})
    if cancelled: ledger.cancel("op")
    elif not unknown: ledger.finish("op")
    outcome = NS(trial_id="trial", task_id="task", model_id="fake", model_attempt_ids=("attempt",),
        cost_microunits=None if unknown else 2, cost_basis="unknown" if unknown else "dated-price-estimate")
    attempt = NS(attempt_id="attempt", trial_id="trial", turn_id=1, provider_id="openai",
        requested_model_id="fake", usage={"prompt_tokens": 1, "completion_tokens": 1},
        settlement_reference="attempt")
    cost = NS(attempt_id="attempt", operation_id="op", cost_microunits=outcome.cost_microunits,
        cost_basis=outcome.cost_basis, price_snapshot_hash="a" * 64, raw_request_sha256=None,
        settlement_reference="attempt")
    trial = NS(outcome=outcome, model_attempts=[attempt], accounting=[cost], reuse=None)
    # Replace non-digest synthetic metadata before pinning. No private/provider data.
    with sqlite3.connect(path) as db:
        db.execute("UPDATE operations SET metadata=?", (json.dumps({"provider": "openai", "model": "fake",
            "price_snapshot_hash": "a" * 64, "request_hash": "b" * 64}),))
    manifest = NS(code_hash="c" * 64, prices={"fake": {"snapshot_hash": "a" * 64}})
    edition = NS(authority=NS(index_sha256="d" * 64), validate=lambda: (
        NS(edition_id="experiment", scheduled_trial_ids=("trial",)), manifest, [trial], (), None))
    authority = report.LedgerAuditAuthority(experiment_id="experiment", edition_index_sha256="d" * 64,
        source_sha256="c" * 64, logical_snapshot_sha256=snapshot_pin(path),
        price_snapshot_hashes={"fake": "a" * 64}, snapshot_kind="read-transaction")
    return path, ledger, edition, authority, trial


def test_audit_reads_consistent_snapshot_without_writing_or_constructing_ledger(tmp_path, monkeypatch):
    # what_bug_this_catches: reporting calling CostLedger constructor/migrations or settlement.
    path, _, edition, authority, _ = setup(tmp_path)
    before = path.read_bytes()
    def forbidden(*args, **kwargs): raise AssertionError("audit called financial writer")
    for name in ("__init__", "reserve", "settle", "finish", "cancel", "authorize_dispatch"):
        monkeypatch.setattr(CostLedger, name, forbidden)
    result = report.audit_ledger(path, edition=edition, authority=authority)
    assert result["complete"] is True
    assert result["attempts"][0]["recorded_cost_basis"] == "dated-price-estimate"
    assert result["attempts"][0]["billed_microunits"] is None
    assert path.read_bytes() == before
    assert result["database_mutated"] is result["publication_performed"] is False


def test_unknown_cancelled_liability_preserves_hold_and_never_becomes_zero(tmp_path):
    # what_bug_this_catches: cancelled unknown requests disappearing from spent/hold audit.
    path, _, edition, authority, _ = setup(tmp_path, unknown=True, cancelled=True)
    result = report.audit_ledger(path, edition=edition, authority=authority)
    assert result["complete"] is False
    assert result["totals"]["committed_microunits"] == 20
    assert result["attempts"][0]["recorded_microunits"] is None
    assert result["attempts"][0]["unknown_liability"] is True
    assert result["operations"][0]["status"] == "cancelled"
    assert result["operations"][0]["reservation_retained"] is True


def test_missing_and_extra_attempts_stay_unallocated_and_scheduled(tmp_path):
    # what_bug_this_catches: unmatched attempts silently shrinking outcome denominators.
    path, _, edition, authority, trial = setup(tmp_path)
    trial.model_attempts[0].attempt_id = "missing"
    trial.accounting[0].attempt_id = "missing"
    trial.outcome.model_attempt_ids = ("missing",)
    result = report.audit_ledger(path, edition=edition, authority=authority)
    assert result["scheduled_trials"] == 1
    assert result["missing_attempt_ids"] == ["missing"]
    assert result["attempts"][0]["trial_id"] is None
    assert result["attempts"][0]["recorded_microunits"] == 2
    assert result["attempts"][0]["recorded_cost_basis"] == "unknown"
    assert result["trial_audit"][0]["ledger_missing_attempt_ids"] == ["missing"]


def test_scheduled_count_follows_edition_schedule_not_supplied_rows(tmp_path):
    # what_bug_this_catches: an unsupplied scheduled trial shrinking the audit's scheduled count.
    path, _, edition, authority, trial = setup(tmp_path)
    old_validate = edition.validate
    index = NS(edition_id="experiment", scheduled_trial_ids=("trial", "never-supplied"))
    edition.validate = lambda: (index, *old_validate()[1:])
    result = report.audit_ledger(path, edition=edition, authority=authority)
    assert result["scheduled_trials"] == 2 and len(result["trial_audit"]) == 1
    assert "scheduled_trial_rows_unavailable" in result["diagnostics"]
    assert result["complete"] is False


@pytest.mark.parametrize("field", ["experiment_id", "source_sha256", "edition_index_sha256", "price_snapshot_hashes"])
def test_external_authority_mismatch_rejected_before_open(tmp_path, monkeypatch, field):
    # what_bug_this_catches: self-selected source/price/edition values becoming authority.
    path, _, edition, authority, _ = setup(tmp_path)
    changed = authority.model_dump()
    changed[field] = {"fake": "e" * 64} if field == "price_snapshot_hashes" else "e" * 64
    bad = report.LedgerAuditAuthority(**changed)
    monkeypatch.setattr(sqlite3, "connect", lambda *a, **kw: (_ for _ in ()).throw(AssertionError("opened")))
    with pytest.raises(EvidenceRejected): report.audit_ledger(path, edition=edition, authority=bad)


def test_unpinned_snapshot_retains_rows_but_never_verifies(tmp_path):
    # what_bug_this_catches: database's own freshly computed digest used as expected authority.
    path, _, edition, authority, _ = setup(tmp_path)
    bad = authority.model_copy(update={"logical_snapshot_sha256": "e" * 64})
    result = report.audit_ledger(path, edition=edition, authority=bad)
    assert result["complete"] is False
    assert len(result["attempts"]) == 1
    assert result["attempts"][0]["state"] == "unknown"


def test_dated_estimate_and_pinned_invoice_amount_remain_separate(tmp_path):
    # what_bug_this_catches: estimates relabelled billed or invoices rewriting ledger amounts.
    path, _, edition, authority, _ = setup(tmp_path)
    receipt = report.BillingEvidence(attempt_id="attempt", provider="openai", model_id="fake",
        billed_microunits=9, receipt_sha256="f" * 64)
    unpinned = report.audit_ledger(path, edition=edition, authority=authority, billing_evidence=(receipt,))
    assert unpinned["attempts"][0]["billed_microunits"] is None
    approved = authority.model_copy(update={"billing_evidence_sha256": typed_hash([receipt.model_dump(mode="json")])})
    result = report.audit_ledger(path, edition=edition, authority=approved, billing_evidence=(receipt,))
    assert result["attempts"][0]["recorded_microunits"] == 2
    assert result["attempts"][0]["billed_microunits"] == 9
    assert result["totals"]["recorded_known_microunits"] == 2


def test_duplicate_reuse_never_double_counts_original_billing_or_sample_credit(tmp_path):
    # what_bug_this_catches: resumed references counted as two newly billed independent samples.
    path, _, edition, authority, trial = setup(tmp_path)
    reference = NS(source_index_sha256="f" * 64, source_trial_id="original",
        original_cost_microunits=2, original_cost_basis="dated-price-estimate")
    reused = [NS(outcome=NS(trial_id=name, task_id="task", model_id="fake", model_attempt_ids=(),
        cost_microunits=2, cost_basis="dated-price-estimate"), reuse=reference, model_attempts=[], accounting=[])
        for name in ("reuse1", "reuse2")]
    old_validate = edition.validate
    index = NS(edition_id="experiment", scheduled_trial_ids=("trial", "reuse1", "reuse2"))
    edition.validate = lambda: (index, old_validate()[1], [trial, *reused], (), None)
    result = report.audit_ledger(path, edition=edition, authority=authority)
    assert result["scheduled_trials"] == 3
    assert "scheduled_trial_rows_unavailable" not in result["diagnostics"]
    assert result["totals"]["recorded_known_microunits"] == 2
    assert all(row["new_charge_microunits"] == 0 and row["independent_new_sample"] is False for row in result["reuse"])
    assert result["complete"] is False


@pytest.mark.parametrize("kind", ["corrupt", "missing-table", "missing-file", "finished-unknown"])
def test_corrupt_partial_or_inconsistent_snapshots_never_silently_pass(tmp_path, kind):
    # what_bug_this_catches: partial reader/migration recovering a false clean financial report.
    path, _, edition, authority, _ = setup(tmp_path, unknown=kind == "finished-unknown")
    if kind == "corrupt": path.write_bytes(b"not sqlite")
    elif kind == "missing-file": path = tmp_path / "never-created.sqlite"
    elif kind == "missing-table":
        with sqlite3.connect(path) as db: db.execute("DROP TABLE dispatches")
    else:
        with sqlite3.connect(path) as db: db.execute("UPDATE operations SET status='finished'")
        authority = authority.model_copy(update={"logical_snapshot_sha256": snapshot_pin(path)})
    if kind == "finished-unknown":
        result = report.audit_ledger(path, edition=edition, authority=authority)
        assert result["complete"] is False
        assert "finished_operation_hides_unknown_liability" in result["operations"][0]["reasons"]
    else:
        with pytest.raises(EvidenceRejected): report.audit_ledger(path, edition=edition, authority=authority)


def test_concurrent_wal_commit_cannot_mix_old_rows_with_new_totals(tmp_path, monkeypatch):
    # what_bug_this_catches: separate SELECT transactions observing incompatible balances/rows.
    path, _, edition, authority, _ = setup(tmp_path)
    writer = sqlite3.connect(path)
    try:
        writer.execute("PRAGMA journal_mode=WAL")
        original = report._snapshot
        def concurrent_snapshot(db):
            result = original(db)
            writer.execute("UPDATE budget SET amount=200")
            writer.commit()
            return result
        monkeypatch.setattr(report, "_snapshot", concurrent_snapshot)
        result = report.audit_ledger(path, edition=edition, authority=authority)
        assert result["totals"]["budget_microunits"] == 100
        assert result["concurrent_change_observed"] is True
        assert result["freshness_claim"] is False
    finally:
        writer.close()


def test_immutable_snapshot_requires_sealed_no_sidecar_file(tmp_path):
    # what_bug_this_catches: immutable=1 discarding live WAL rows while claiming full ledger identity.
    path, _, edition, authority, _ = setup(tmp_path)
    sealed = authority.model_copy(update={"snapshot_kind": "immutable-file",
        "immutable_file_sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    result = report.audit_ledger(path, edition=edition, authority=sealed)
    assert result["snapshot_pin_matches"] is True
    wal = type(path)(str(path) + "-wal")
    wal.write_bytes(b"synthetic-uncheckpointed")
    with pytest.raises(EvidenceRejected): report.audit_ledger(path, edition=edition, authority=sealed)


def test_status_helper_reports_unknown_without_another_financial_calculator(tmp_path):
    # what_bug_this_catches: safe CLI status deriving a second cost total or exposing metadata.
    path, _, edition, authority, _ = setup(tmp_path, unknown=True, cancelled=True)
    audit = report.audit_ledger(path, edition=edition, authority=authority)
    status = report.project_ledger_audit_status(audit)
    assert status["status"] == "unknown"
    assert status["unknown_liabilities"] == status["retained_reservations"] == 1
    assert status["cost_bases"] == ["unknown"]
    assert status["runtime_authorized"] is status["database_mutated"] is False
    assert "metadata" not in json.dumps(status)
