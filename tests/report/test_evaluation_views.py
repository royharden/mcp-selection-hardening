"""Authored source regressions for mode-specific evaluation views (Dirty Mode: unrun)."""

from copy import deepcopy
import json

from mcpsh.report import (
    evaluation_view_sections, render_bundle, render_evaluation_html, render_evaluation_markdown,
)

HOSTILE = "<script>alert(1)</script>[x](javascript:alert(1)) | **bold** `tick` <img src=x onerror=1>"
HASH = "a" * 64


def base(mode, **extra):
    result = {"schema_version": 1, "banner": "Public source-only test", "execution_state": mode,
              "platform_scope": "synthetic-memory", "development_only": True, "live_model_runs": 0,
              "manifest": {"mode": "replay", "platform_scope": "synthetic-memory"},
              "rows": [], "summary": [], "limitations": ["Explicit unknown."], "acceptance_verdict": "pending",
              "unknown_trials": [{"trial_id": "trial-1", "state": "unknown", "reasons": ["source_trial_unavailable"]}],
              "projection": {"version": "mcpsh-public-result-v1", "policy": "strict"}}
    result.update(extra)
    return result


def section(sections, section_id):
    return next(item for item in sections if item["id"] == section_id)


def values(item):
    return dict(row for row in item["rows"])


def development():
    return base("development-summary-draft", development_summary={
        "evidence_state": "incomplete", "scheduled_slots": 324, "supplied_slots": 300, "missing_slots": 24,
        "failed_slots": 0, "unknown_cost_slots": None, "absolute_utility_floor": None,
        "independent_approval": None, "dispatch_authorized": False, "next_action": "collect-development-evidence",
        "groups": [], "paired_retention": [
            {"arm_slot": "arm-b", "decision": "inconclusive", "family_independence": "not-established-public-development",
             "interval": {"difference": -0.125, "low": None, "high": 0.25, "missing_pairs": 3,
                          "interpretation": "incomplete", "metric": "utility_success"}},
            {"arm_slot": "arm-a", "decision": "pending", "family_independence": "not-established-public-development",
             "interval": None}]},
        development_threshold_proposal={"status": "approval-needed", "proposal_authority": "unauthenticated-proposal",
                                        "absolute_utility_floor": None, "independent_approval": None})


def test_nonmatrix_numeric_and_status_values_are_preserved_exactly():
    """what_bug_this_catches: empty matrix-summary views hiding nonmatrix statuses, or views rounding supplied numbers."""
    result = base("acceptance-dossier-draft", acceptance_dossier_status={
        "version": "verified-edition-acceptance-v1", "authority_binding": "pinned", "authentication": "unconfirmed",
        "inspection_complete": False, "recommendation": "collect-required-evidence", "scheduled_trials": 36,
        "supplied_outcomes": 35, "missing_trials": 1, "utility_basis_counts": {"semantic-v2": 30, "legacy-call-proxy-v1": 5},
        "runtime_authorized": False, "independent_product_acceptance": "pending", "source_index_sha256": HASH})
    dossier = values(section(evaluation_view_sections(result), "acceptance_dossier_status"))
    assert dossier["scheduled_trials"] == "36" and dossier["missing_trials"] == "1"
    assert dossier["authentication"] == "unconfirmed" and dossier["inspection_complete"] == "false"
    assert dossier["utility_basis_counts"] == "legacy-call-proxy-v1=5; semantic-v2=30"
    retention = section(evaluation_view_sections(development()), "development_paired_retention")
    assert retention["rows"][0][retention["columns"].index("difference")] == "-0.125"


def test_missing_values_and_sections_are_never_rendered_as_zero():
    """what_bug_this_catches: None floors/unknown costs or absent mode sections displayed as 0 or as success."""
    sections = evaluation_view_sections(development())
    summary = values(section(sections, "development_summary"))
    assert summary["unknown_cost_slots"] == "not supplied" and summary["absolute_utility_floor"] == "not supplied"
    assert summary["failed_slots"] == "0"  # A supplied zero stays a supplied zero.
    assert section(sections, "threshold_approval_status")["state"] == "pending"
    assert section(sections, "ledger_audit_status")["state"] == "N/A"
    ledger = evaluation_view_sections(base("ledger-audit-draft"))
    assert section(ledger, "ledger_audit_status")["state"] == "pending" and not section(ledger, "ledger_audit_status")["rows"]
    markdown = render_evaluation_markdown(base("ledger-audit-draft"))
    block = markdown.split("### Ledger audit status (pending)", 1)[1].split("###", 1)[0]
    assert "|" not in block  # Pending section renders a note, never a table of zero/empty rows.


def test_unknown_and_failure_rows_and_interval_gaps_are_retained():
    """what_bug_this_catches: views dropping unknown trials, incomplete retention rows or missing interval bounds."""
    sections = evaluation_view_sections(development())
    provenance = values(section(sections, "provenance"))
    assert provenance["listed unknown or partial trials"] == "1"
    retention = section(sections, "development_paired_retention")
    assert len(retention["rows"]) == 2
    low = retention["columns"].index("low")
    assert retention["rows"][0][low] == "not supplied" and retention["rows"][1][low] == "not supplied"
    assert retention["rows"][1][retention["columns"].index("decision")] == "pending"


def test_replay_and_platform_labels_stay_explicit():
    """what_bug_this_catches: a replay/synthetic-memory edition rendered without provenance, implying live evidence."""
    provenance = values(section(evaluation_view_sections(development()), "provenance"))
    assert provenance["manifest.mode"] == "replay" and provenance["platform_scope"] == "synthetic-memory"
    assert provenance["live_model_runs"] == "0" and provenance["acceptance_verdict"] == "pending"
    assert values(section(evaluation_view_sections(base(None)), "provenance"))["execution_state"] == "not supplied"


def test_hostile_markdown_and_html_cells_are_inert():
    """what_bug_this_catches: supplied strings injecting script, links, emphasis or table cells into reports."""
    result = base("ledger-audit-draft", ledger_audit_status={"version": HOSTILE, "status": "unknown",
                                                             "cost_bases": [HOSTILE, "unknown"]})
    page = render_evaluation_html(result)
    assert "<script" not in page and "<img" not in page and "&lt;script&gt;" in page
    markdown = render_evaluation_markdown(result)
    row = next(line for line in markdown.splitlines() if line.startswith("| `version`"))
    assert row.count(" | ") == 1 and "\\|" in row  # Exactly two cells; the supplied pipe is escaped.
    cell = row.split(" | ", 1)[1]
    assert cell.startswith("``") and "](javascript" in cell  # Inside a code span, so no link is formed.
    bundle = render_bundle(result)
    assert "<script>" not in bundle["index.html"]
    assert all("<script>" not in line or line.startswith("| `") for line in bundle["REPORT.md"].splitlines()
               if "Evaluation views" in bundle["REPORT.md"])  # Only ever inside an inert code-span cell.


def test_views_do_not_mutate_the_shared_object_and_bundle_uses_it():
    """what_bug_this_catches: view helpers editing the projected object or rendering from a different dataset."""
    result = development()
    before = deepcopy(result)
    files = render_bundle(result)
    assert result == before
    assert json.loads(files["results.json"]) == before
    assert json.loads(files["evaluation-views.json"]) == json.loads(json.dumps(evaluation_view_sections(before)))
    assert "## Evaluation views" in files["REPORT.md"] and "id='evaluation-views'" in files["index.html"]


def test_section_order_and_output_are_deterministic():
    """what_bug_this_catches: dict/set iteration order changing report bytes between identical editions."""
    first, second = development(), development()
    second["development_summary"] = dict(reversed(list(second["development_summary"].items())))
    assert render_evaluation_markdown(first) == render_evaluation_markdown(second)
    assert render_evaluation_html(first) == render_evaluation_html(second)
    ids = [item["id"] for item in evaluation_view_sections(first)]
    assert ids[0] == "provenance" and ids[-1] == "cross_axes" and len(ids) == len(set(ids))


def test_normative_v3_status_is_copied_and_unevaluated_totals_stay_pending():
    """what_bug_this_catches: unevaluated conformance totals/tracks rendered as 0, or per-probe credit shown as platform pass."""
    unevaluated = base("replay-only", normative_v3_status={
        "version": "m5-normative-v3-status-1", "mode": "legacy-v1-integrity-only", "status": "not-evaluated",
        "authority_valid": False, "required_requirements": None, "pending_requirements": None,
        "probe_states": None, "tracks": None, "full_platform_credit": False,
        "suite_acceptance": "pending", "product_verdict": "pending"})
    sections = evaluation_view_sections(unevaluated)
    status = values(section(sections, "normative_v3_status"))
    assert status["required_requirements"] == "not supplied" and status["probe_states"] == "not supplied"
    assert status["full_platform_credit"] == "false" and status["product_verdict"] == "pending"
    tracks = section(sections, "normative_v3_tracks")
    assert tracks["state"] == "pending" and not tracks["rows"]
    evaluated = deepcopy(unevaluated)
    evaluated["normative_v3_status"].update(status="evaluated", authority_valid=True, required_requirements=12,
        probe_states={"verified": 3, "invalid": 0, "unknown": 2},
        tracks={"stdio": {"required_scope": "actual-stdio", "required_requirements": 4, "pending_requirements": 4,
                          "verdict": "pending", "pending_reason_counts": {"missing-evidence": 4}}})
    sections = evaluation_view_sections(evaluated)
    assert values(section(sections, "normative_v3_status"))["probe_states"] == "invalid=0; unknown=2; verified=3"
    rows = section(sections, "normative_v3_tracks")["rows"]
    columns = section(sections, "normative_v3_tracks")["columns"]
    assert [row[0] for row in rows] == ["synthetic-memory", "filesystem-posix", "stdio"]
    assert rows[0][columns.index("required_requirements")] == "not supplied"  # Absent track is not zero.
    assert rows[2][columns.index("pending: missing-evidence")] == "4"
    assert rows[2][columns.index("pending: unselected")] == "not supplied"
    assert section(evaluation_view_sections(base("replay-only")), "normative_v3_status")["state"] == "N/A"


def test_cross_axes_stay_pending_and_unprojected_data_is_never_shown():
    """what_bug_this_catches: a dossier view claiming no cross-axis issues, or showing unaliased private diagnostics."""
    dossier = base("acceptance-dossier-draft")
    assert section(evaluation_view_sections(dossier), "cross_axes")["state"] == "pending"
    dossier["cross_axes"] = {"source_integrity": "not-audited", "trials": [{"private": "SECRET-ROW"}],
                             "groups": [{"model_id": "SECRET-MODEL", "supplied_rows": 2}]}
    sections = evaluation_view_sections(dossier)
    assert section(sections, "cross_axes")["state"] == "pending" and not section(sections, "cross_axes")["rows"]
    assert "SECRET" not in json.dumps(sections) and "SECRET" not in render_evaluation_html(dossier)
    assert section(evaluation_view_sections(base("ledger-audit-draft")), "cross_axes")["state"] == "N/A"
