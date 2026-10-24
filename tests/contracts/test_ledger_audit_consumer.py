"""Source regressions only: no SQLite connection/CostLedger constructor is run."""

from types import SimpleNamespace
import csv
import io
import json

import pytest

from mcpsh.runner.ledger_audit import admit_ledger_authority, assemble_ledger_audit
from mcpsh.report import render_bundle


def test_malformed_ledger_authority_never_becomes_default_authority():
    with pytest.raises(ValueError):
        admit_ledger_authority(b'{"experiment_id":"public-test","snapshot_kind":"auto"}')
    with pytest.raises(ValueError, match="duplicate"):
        admit_ledger_authority(b'{"experiment_id":"a","experiment_id":"b"}')


def test_missing_or_rejected_snapshot_has_no_empty_successful_report(monkeypatch):
    import mcpsh.accounting.report as producer

    def rejected(*args, **kwargs):
        raise ValueError("public source test: snapshot pin mismatch")

    monkeypatch.setattr(producer, "audit_ledger", rejected)
    with pytest.raises(ValueError, match="snapshot pin mismatch"):
        assemble_ledger_audit("explicit-public-test.sqlite", edition=None, authority=None)


def test_unknown_unallocated_reused_liability_survives_existing_read_only_api(monkeypatch):
    import mcpsh.accounting.report as producer
    import mcpsh.accounting

    report = {"scope": "read-only-authoritative-ledger-snapshot", "complete": False,
              "source_sha256": "a" * 64, "edition_index_sha256": "b" * 64,
              "logical_snapshot_sha256": "c" * 64, "snapshot_pin_matches": True,
              "snapshot_kind": "immutable-file", "concurrent_change_observed": False,
              "scheduled_trials": 1,
              "totals": {"budget_microunits": 90, "recorded_known_microunits": 10,
                         "committed_microunits": 100, "available_microunits": 0,
                         "unknown_attempts": 1, "cost_basis": "recorded-ledger-amounts-not-provider-billing"},
              "attempts": [{"recorded_cost_basis": "dated-price-estimate", "unknown_liability": False,
                            "trial_id": "public-existing", "billing_basis": "unknown"},
                           {"recorded_cost_basis": "unknown", "unknown_liability": True,
                            "trial_id": None, "billing_basis": "unknown"}],
              "operations": [{"reservation_retained": True}], "missing_attempt_ids": ["missing"],
              "unallocated_dispatch_attempt_ids": ["unallocated"], "reuse": [{"parent": "private-parent"}],
              "non_model": [{"category": "replay"}], "dispatch_stops": [{"reason": "private-unknown"}]}
    supplied = {}

    def audit(path, **kwargs):
        supplied.update(path=path, **kwargs)
        return report

    def forbidden_constructor(*args, **kwargs):
        raise AssertionError("consumer must never create/migrate/reconcile a ledger")

    monkeypatch.setattr(producer, "audit_ledger", audit)
    monkeypatch.setattr(mcpsh.accounting, "CostLedger", forbidden_constructor)
    outcome = SimpleNamespace(trial_id="public-existing", model_dump=lambda **options: {"trial_id": "public-existing"})
    trial = SimpleNamespace(outcome=outcome, repeat=1, model_dump=lambda **options: {"original": True})
    index = SimpleNamespace(platform_scope="synthetic-memory", scheduled_trial_ids=("public-existing", "missing-trial"))
    manifest = SimpleNamespace(model_dump=lambda **options: {"mode": "replay"})
    edition = SimpleNamespace(validate=lambda: (index, manifest, (trial,), (), None))
    view = assemble_ledger_audit("explicit-public-test.sqlite", edition=edition, authority=None)
    assert supplied["path"] == "explicit-public-test.sqlite" and supplied["billing_evidence"] == ()
    assert view.private_report is report
    assert view.result["ledger_audit"] is report  # Canonical projector owns this closed safe report schema.
    status = view.result["ledger_audit_status"]
    assert view.result["ledger_audit"]["totals"] == report["totals"]
    assert status["unknown_liabilities"] == status["unallocated_attempts"] == status["reuse_references"] == 1
    assert status["retained_reservations"] == status["missing_attempts"] == 1
    assert len(view.result["ledger_audit"]["unallocated_dispatch_attempt_ids"]) == 1
    assert status["cost_bases"] == ["dated-price-estimate", "unknown"]
    assert status["billed_attempts"] == 0
    assert len(view.result["rows"]) == view.result["scheduled_trials"] == 2


def test_all_ledger_views_copy_same_unknown_values_and_escape_text():
    # Catches HTML omitting ledger-only numbers, CSV dropping unknown rows or
    # a renderer replacing an unknown amount with free/zero budget.
    report = {"totals": {"budget_microunits": 90, "recorded_known_microunits": 10,
                          "committed_microunits": 100, "available_microunits": None,
                          "unknown_attempts": 1, "cost_basis": "<source-only-test>"},
              "attempts": [{"attempt_id": "=public-test", "recorded_microunits": None,
                            "recorded_cost_basis": "unknown", "unknown_liability": True}],
              "operations": [{"id": "public-operation", "reserved": 100,
                              "unknown_attempts": 1, "reservation_retained": True}]}
    result = {"summary": [], "rows": [], "banner": "Public source-only test", "execution_state": None,
              "limitations": ["Explicit unknown."], "ledger_audit": report}
    files = render_bundle(result)
    assert json.loads(files["ledger-audit.json"]) == json.loads(files["results.json"])["ledger_audit"] == report
    attempts = list(csv.DictReader(io.StringIO(files["ledger-attempts.csv"])))
    assert len(attempts) == 1 and attempts[0]["recorded_microunits"] == "N/A"
    assert attempts[0]["attempt_id"] == "'=public-test"
    assert "available_microunits | N/A" in files["REPORT.md"]
    assert "&lt;source-only-test&gt;" in files["index.html"]
    assert "<source-only-test>" not in files["index.html"]
