"""Publisher copy of D7's normative_v3_status (authored in Dirty Mode, unrun)."""

import pytest

import mcpsh.runner.normative_status as publisher
from mcpsh.evidence import project_normative_status, project_public_result
from mcpsh.evidence.producers import LEGACY_MODE
from mcpsh.records import typed_hash

INDEX = "1" * 64
AUTHORITY = "2" * 64


def legacy_report(**changes):
    report = {"visibility": "private", "schema_version": 1, "mode": LEGACY_MODE,
              "source_index_sha256": INDEX, "authority_sha256": AUTHORITY,
              "catalogs": [], "conformance": [{"probe_id": "public-probe", "state": "verified",
                                               "creditable": False}],
              "bindings_complete": True, "all_selected_probes_creditable": False,
              "normative": {"status": "not-evaluated", "basis": "legacy-v1-authority",
                            "full_platform_credit": False},
              "full_platform_credit": False}
    report.update(changes)
    return report


def pins(report, **changes):
    values = {"expected_report_sha256": typed_hash(report), "expected_authority_sha256": AUTHORITY,
              "source_index_sha256": INDEX}
    values.update(changes)
    return values


def test_bound_report_is_copied_not_recomputed(monkeypatch):
    # what_bug_this_catches: the publisher recomputing counts instead of copying D7's block.
    report = legacy_report()
    sentinel = {"version": "m5-normative-v3-status-1", "copied": True}
    monkeypatch.setattr(publisher, "project_normative_status", lambda value: sentinel if value is report else None)
    result = publisher.attach_normative_status({"rows": []}, report, **pins(report))
    assert result[publisher.STATUS_KEY] is sentinel


def test_real_legacy_status_never_claims_credit_and_survives_projection():
    # D7 behaviour change: legacy all_selected_probes_creditable is always false.
    report = legacy_report()
    result = publisher.attach_normative_status({"rows": []}, report, **pins(report))
    status = result[publisher.STATUS_KEY]
    assert status == project_normative_status(report)
    assert status["mode"] == LEGACY_MODE and status["status"] == "not-evaluated"
    assert status["creditable_probes"] == 0 and status["full_platform_credit"] is False
    assert status["tracks"] is None and status["required_requirements"] is None  # never zeros
    public = project_public_result(result).public
    assert public[publisher.STATUS_KEY]["full_platform_credit"] is False


@pytest.mark.parametrize("change", [
    {"expected_report_sha256": "3" * 64},     # report bytes differ from the dossier pin
    {"expected_authority_sha256": "4" * 64},  # producer authority differs
    {"source_index_sha256": "5" * 64},        # bound to a different edition
    {"expected_report_sha256": None},         # no external pin at all
    {"expected_authority_sha256": None},
])
def test_unbound_report_is_omitted_not_zeroed(change):
    report = legacy_report()
    result = publisher.attach_normative_status({"rows": [], publisher.STATUS_KEY: {"stale": True}},
                                               report, **pins(report, **change))
    assert publisher.STATUS_KEY not in result


@pytest.mark.parametrize("report", [None, [], {"mode": "unknown-mode"}])
def test_malformed_or_modeless_report_is_omitted(report):
    values = {"expected_report_sha256": typed_hash(report) if report is not None else None,
              "expected_authority_sha256": AUTHORITY, "source_index_sha256": INDEX}
    assert publisher.bound_normative_status(report, **values) is None
