"""Mode-specific status views over an already projected public result.

Pure functions: no IO, no recomputation of metrics, thresholds, denominators or
acceptance, and the supplied object is never mutated. Only whitelisted fields of the
public projection (``mcpsh.evidence.public_projection``) are displayed. A missing
section or value stays explicit (pending / N/A), never zero or an empty success.
"""

import html
from typing import Any

PRESENT, PENDING, NOT_APPLICABLE = "present", "pending", "N/A"
MISSING = "not supplied"
FIELD_COLUMNS = ("field", "supplied value")

# Which status sections a public execution state is expected to carry. An expected
# but absent section is pending; an unexpected absent section is N/A.
MODE_SECTIONS = {
    "pilot-summary-draft": {"pilot_summary", "threshold_proposal", "threshold_approval_status"},
    "development-summary-draft": {"development_summary", "development_threshold_proposal",
                                  "development_paired_retention", "threshold_approval_status"},
    "acceptance-dossier-draft": {"acceptance_dossier_status", "cross_axes"},
    "ledger-audit-draft": {"ledger_audit_status"},
    "replay-only": {"replay_design", "development_input_pins"},
    "live-complete": {"token_fit_status"},
    "partial": {"token_fit_status"},
}

# (section id, title, source key, whitelisted fields, note). Order is the render order.
SECTIONS = (
    ("pilot_summary", "Development pilot status", "pilot_summary",
     ("evidence_state", "execution_mode", "proposed_repeats_for_both_arms", "absolute_utility_floor",
      "dispatch_authorized", "manifest_sha256", "input_evidence_sha256"),
     "Per-arm rows appear in the pilot table. A proposal authorizes no dispatch or utility floor."),
    ("threshold_proposal", "Pilot threshold proposal", "threshold_proposal",
     ("status", "absolute_utility_floor", "paired_retention_margin", "full_development_cases_required",
      "proposed_repeats_for_both_arms", "dispatch_authorized", "pilot_summary_sha256"),
     "Approval-needed proposal; not an approved criterion."),
    ("development_summary", "Full36 development status", "development_summary",
     ("evidence_state", "scheduled_slots", "supplied_slots", "missing_slots", "failed_slots",
      "unknown_cost_slots", "incomplete_observation_slots", "proposed_repeats_for_both_arms",
      "next_action", "absolute_utility_floor", "independent_approval", "dispatch_authorized",
      "plan_sha256", "settings_sha256", "outcomes_sha256"),
     "All planned slots stay in the supplied denominators; group rows appear in the full36 table."),
    ("development_threshold_proposal", "Development threshold proposal", "development_threshold_proposal",
     ("status", "proposal_authority", "absolute_utility_floor", "proposed_repeats_for_both_arms",
      "retention_decision", "uncertainty_rule", "independent_approval", "plan_sha256",
      "settings_sha256", "full36_summary_sha256", "outcomes_sha256"),
     "Unauthenticated proposal; the floor and uncertainty rule await independent approval."),
    ("threshold_approval_status", "Threshold approval binding", "threshold_approval_status",
     ("version", "disposition", "metadata_binding", "external_authorization", "approved_floor",
      "fresh_corpus_required", "runtime_authorized", "independent_product_acceptance", "issue_codes",
      "context_sha256", "reviewer_metadata_sha256", "integrator_metadata_sha256"),
     "A bound approval is eligible only for separate runtime admission; runtime stays unauthorized here."),
    ("acceptance_dossier_status", "Acceptance dossier status", "acceptance_dossier_status",
     ("version", "authority_binding", "authentication", "inspection_complete", "recommendation",
      "scheduled_trials", "supplied_outcomes", "missing_trials", "utility_basis_counts",
      "runtime_authorized", "independent_product_acceptance", "source_index_sha256"),
     "Pins bind metadata only; authentication stays unconfirmed unless a trusted caller confirms it."),
    ("ledger_audit_status", "Ledger audit status", "ledger_audit_status",
     ("version", "status", "complete", "snapshot_kind", "snapshot_pin_matches", "concurrent_change_observed",
      "scheduled_trials", "attempts_total", "unknown_liabilities", "unallocated_attempts", "missing_attempts",
      "operations_total", "retained_reservations", "reuse_references", "non_model_events", "billed_attempts",
      "cost_basis", "cost_bases", "freshness_claim", "database_mutated", "runtime_authorized",
      "independent_product_acceptance", "edition_index_sha256", "source_sha256", "logical_snapshot_sha256"),
     "Recorded ledger amounts are not provider billing; unknown liabilities stay unknown."),
    ("token_fit_status", "Token-fit status", "token_fit_status",
     ("version", "status", "complete", "attempts_total", "attempts_verified", "attempts_unknown",
      "trials_without_attempts", "live_admission", "billing_verified", "journal_sha256",
      "bundle_typed_sha256", "expectations_sha256"),
     "Fit verification grants no live admission and verifies no billing."),
    ("normative_v3_status", "Normative conformance status", "normative_v3_status",
     ("version", "mode", "status", "basis", "inventory_version", "authority_valid", "selected_probe_count",
      "unmapped_selected_probes", "creditable_probes", "probe_states", "required_requirements",
      "per_probe_creditable_requirements", "pending_requirements", "full_platform_credit", "suite_acceptance",
      "product_verdict", "inventory_sha256", "requirements_manifest_sha256", "semantic_manifest_sha256",
      "source_index_sha256", "authority_sha256"),
     "Copied from the evidence bridge; totals stay unset unless evaluated. Per-probe credit is not full-platform acceptance."),
    ("development_input_pins", "Development input pins", "development_input_pins",
     ("version", "scope", "cases", "episodes", "manifest_sha256", "raw_sha256"),
     "Source-data pins only; runtime unverified."),
    ("replay_design", "Replay design", "replay_design",
     ("baseline_tasks", "baseline_rows", "control_rows", "diagnostic_episodes", "diagnostic_rows"),
     "Scripted replay slots are not live samples; diagnostics are separate from the primary plan."),
)
RETENTION_COLUMNS = ("arm_slot", "decision", "family_independence", "interpretation", "metric", "difference",
                     "low", "high", "family_count", "missing_pairs", "unknown_metric_trials")
NORMATIVE_TRACKS = ("synthetic-memory", "filesystem-posix", "stdio")
NORMATIVE_REASONS = ("requirements-authority-invalid", "unselected", "missing-evidence", "invalid-evidence",
                     "component-or-nonplatform-scope", "incomplete-or-unknown-observation")
NORMATIVE_TRACK_FIELDS = ("required_scope", "required_requirements", "per_probe_creditable_requirements",
                          "pending_requirements", "selected_probe_count", "verdict")
NORMATIVE_TRACK_COLUMNS = ("track", *NORMATIVE_TRACK_FIELDS, *("pending: " + reason for reason in NORMATIVE_REASONS))
PROVENANCE_FIELDS = ("execution_state", "platform_scope", "development_only", "live_model_runs",
                     "heldout_families", "scheduled_trials", "scored_trials", "acceptance_verdict")


def _text(value: Any) -> str:
    """Display a supplied value faithfully; None is explicit, never a zero."""
    if value is None:
        return MISSING
    if value is True or value is False:
        return "true" if value else "false"
    if isinstance(value, (int, float, str)):
        return str(value)
    if isinstance(value, (list, tuple)):
        return "(none supplied)" if not value else ", ".join(_text(item) for item in value)
    if isinstance(value, dict):
        if not value:
            return "(none supplied)"
        if set(value) <= {"numerator", "denominator", "rate", "low", "high", "value", "status"}:
            return (f"{_text(value.get('numerator'))}/{_text(value.get('denominator'))}"
                    f" (value {_text(value.get('value', value.get('rate')))}; status {_text(value.get('status'))})")
        return "; ".join(f"{key}={_text(value[key])}" for key in sorted(value, key=str))
    return "unsupported value"


def _fields(record: dict, fields: tuple[str, ...]) -> list[tuple[str, str]]:
    return [(name, _text(record.get(name))) for name in fields]


def _section(section_id, title, state, note, columns=FIELD_COLUMNS, rows=()):
    return {"id": section_id, "title": title, "state": state, "note": note,
            "columns": tuple(columns), "rows": [tuple(row) for row in rows]}


def _absent(section_id, title, expected):
    if expected:
        return _section(section_id, title, PENDING, "Expected for this mode but not supplied in this public result.")
    return _section(section_id, title, NOT_APPLICABLE, "Not part of this edition's mode.")


def evaluation_view_sections(public_result: dict) -> list[dict]:
    """Ordered display sections; every value is a string copy of supplied data."""
    if not isinstance(public_result, dict):
        raise TypeError("a projected public result dictionary is required")
    mode = public_result.get("execution_state")
    expected = MODE_SECTIONS.get(mode, set())
    manifest = public_result.get("manifest") if isinstance(public_result.get("manifest"), dict) else {}
    projection = public_result.get("projection") if isinstance(public_result.get("projection"), dict) else {}
    rows = public_result.get("rows")
    unknown = public_result.get("unknown_trials")
    provenance = _fields(public_result, PROVENANCE_FIELDS) + [
        ("manifest.mode", _text(manifest.get("mode"))),
        ("manifest.platform_scope", _text(manifest.get("platform_scope"))),
        ("projection.version", _text(projection.get("version"))),
        ("projection.policy", _text(projection.get("policy"))),
        ("rows in public result", _text(len(rows)) if isinstance(rows, list) else MISSING),
        ("listed unknown or partial trials", _text(len(unknown)) if isinstance(unknown, list) else MISSING)]
    sections = [_section("provenance", "Edition mode and provenance", PRESENT if mode is not None else PENDING,
                         "Replay and live, memory and filesystem provenance stay distinct; acceptance is pending.",
                         rows=provenance)]
    for section_id, title, key, fields, note in SECTIONS:
        record = public_result.get(key)
        if isinstance(record, dict):
            sections.append(_section(section_id, title, PRESENT, note, rows=_fields(record, fields)))
        else:
            sections.append(_absent(section_id, title, section_id in expected))
        if section_id == "normative_v3_status" and isinstance(record, dict):
            tracks = record.get("tracks")
            tracks_title = "Normative conformance tracks"
            if isinstance(tracks, dict):
                table = []
                for track in NORMATIVE_TRACKS:
                    item = tracks.get(track) if isinstance(tracks.get(track), dict) else {}
                    reasons = item.get("pending_reason_counts") if isinstance(item.get("pending_reason_counts"), dict) else {}
                    table.append((track, *(_text(item.get(name)) for name in NORMATIVE_TRACK_FIELDS),
                                  *(_text(reasons.get(reason)) for reason in NORMATIVE_REASONS)))
                sections.append(_section("normative_v3_tracks", tracks_title, PRESENT,
                    "Per-track counts as supplied; every track verdict stays pending.", NORMATIVE_TRACK_COLUMNS, table))
            else:
                sections.append(_section("normative_v3_tracks", tracks_title, PENDING,
                    "Track counts are supplied only for an evaluated status with a valid authority."))
        if section_id == "development_summary":
            retention = record.get("paired_retention") if isinstance(record, dict) else None
            retention_title = "Paired retention decisions"
            if isinstance(retention, list):
                table = []
                for item in retention:
                    item = item if isinstance(item, dict) else {}
                    interval = item.get("interval") if isinstance(item.get("interval"), dict) else {}
                    table.append(tuple(_text(item.get(name) if name in ("arm_slot", "decision", "family_independence")
                                             else interval.get(name)) for name in RETENTION_COLUMNS))
                sections.append(_section("development_paired_retention", retention_title, PRESENT,
                    "Supplied decisions and intervals only; public development families are not independent.",
                    RETENTION_COLUMNS, table))
            else:
                sections.append(_absent("development_paired_retention", retention_title,
                                        "development_paired_retention" in expected))
    # Projection mcpsh-public-result-v1 defines no aliased cross-axis block, so any
    # `cross_axes` key is ignored rather than displayed with unaliased identifiers.
    if "cross_axes" in expected:
        sections.append(_section("cross_axes", "Cross-axis diagnostics", PENDING,
            "Cross-axis diagnostics are in the private dossier; this public projection carries no cross-axis block."))
    else:
        sections.append(_absent("cross_axes", "Cross-axis diagnostics", False))
    return sections


def _md_cell(value: str) -> str:
    """Inline code span: inert to links, emphasis and HTML; pipes stay escaped for tables."""
    value = "".join(" " if ord(char) < 32 or ord(char) == 127 else char for char in value)
    run = longest = 0
    for char in value:
        run = run + 1 if char == "`" else 0
        longest = max(longest, run)
    fence = "`" * (longest + 1)
    pad = " " if value.startswith("`") or value.endswith("`") or not value.strip() else ""
    return fence + pad + value.replace("|", "\\|") + pad + fence


def render_evaluation_markdown(public_result: dict) -> str:
    lines = ["## Evaluation views", "",
             "Status views from the same public result object. Missing data is shown as pending or not supplied, never as zero."]
    for section in evaluation_view_sections(public_result):
        lines.extend(["", f"### {section['title']} ({section['state']})", "", section["note"]])
        if section["rows"]:
            columns = section["columns"]
            lines.extend(["", "| " + " | ".join(columns) + " |", "| " + " | ".join("---" for _ in columns) + " |"])
            lines.extend("| " + " | ".join(_md_cell(cell) for cell in row) + " |" for row in section["rows"])
    return "\n".join(lines) + "\n"


def render_evaluation_html(public_result: dict) -> str:
    """HTML fragment; ids are fixed constants and every data value is escaped."""
    parts = ["<section id='evaluation-views'><h2>Evaluation views</h2>",
             "<p>Status views from the same public result object. Missing data is shown as pending or not supplied, never as zero.</p>"]
    for section in evaluation_view_sections(public_result):
        parts.append(f"<section id='view-{section['id']}'><h3>{html.escape(section['title'])} "
                     f"({html.escape(section['state'])})</h3><p>{html.escape(section['note'])}</p>")
        if section["rows"]:
            parts.append("<table><thead><tr>" + "".join(f"<th>{html.escape(name)}</th>" for name in section["columns"])
                         + "</tr></thead><tbody>")
            parts.extend("<tr>" + "".join(f"<td>{html.escape(cell)}</td>" for cell in row) + "</tr>"
                         for row in section["rows"])
            parts.append("</tbody></table>")
        parts.append("</section>")
    parts.append("</section>")
    return "".join(parts)
