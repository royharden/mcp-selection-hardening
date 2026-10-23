"""Render one scored result object; views never recompute metrics."""

import csv
import html
import io
import json
from typing import Any


def _number(value: Any) -> str:
    return "N/A" if value is None else f"{value:.3f}" if isinstance(value, float) else str(value)


def _md(value: Any) -> str:
    return str(value).replace("\\", "\\\\").replace("|", "\\|").replace("\n", " ").replace("<", "&lt;")


def _lint_rows(result):
    rows = []
    labels = result.get("lint_controls", {}).get("labels", {})
    for rule, record in sorted(labels.get("per_rule", {}).items()):
        for scope in ("provisional_all_labels", "confirmed_labels"):
            metrics = record[scope]
            rows.append({"rule": rule, "review_scope": scope,
                         **{key: metrics[key] for key in ("TP", "FP", "FN", "TN")},
                         "precision": metrics["precision"]["value"],
                         "recall": metrics["recall"]["value"],
                         "unknown": record["unknown_labels"],
                         "unconfirmed": record["unreviewed_or_unconfirmed"]})
    return rows


def render_bundle(result: dict[str, Any]) -> dict[str, str]:
    """Caller must provide a redacted public projection; no raw evidence is written here."""
    summaries = result["summary"]
    heading = result["banner"]
    execution = result["execution_state"]
    columns = ["selector", "condition", "cell", "scheduled_trials", "raw_calls",
               "selection", "utility", "utility_basis", "utility_unknown_trials", "intent", "validated_prohibited_calls",
               "blocked_prohibited_calls", "gate_false_negative_calls", "effects_observed",
               "effects_unknown", "incomplete_observations", "failed_trials"]
    flat = []
    for row in summaries:
        flattened = dict(row)
        for key in ("selection", "utility", "intent"):
            metric = row[key]
            flattened[key] = f"{metric['numerator']}/{metric['denominator']}"
        flat.append(flattened)
    markdown = [f"# {_md(heading)}", "", f"Execution: {_md(execution)}. Acceptance: pending.", "",
                "Consult the manifest for live/replay provenance and platform scope.", "",
                "| " + " | ".join(columns) + " |", "| " + " | ".join("---" for _ in columns) + " |"]
    markdown.extend("| " + " | ".join(_md(row[key]) for key in columns) + " |" for row in flat)
    markdown.extend(["", "## Limits", "", *[f"- {_md(item)}" for item in result["limitations"]]])
    lint_rows = _lint_rows(result)
    lint_columns = ("rule", "review_scope", "TP", "FP", "FN", "TN", "precision", "recall",
                    "unknown", "unconfirmed")
    if lint_rows:
        markdown.extend(["", "## Public development lint controls", "",
                         "Provisional and confirmed label scopes remain separate. Bypass controls are separate diagnostics; zero denominators are N/A.", "",
                         "| " + " | ".join(lint_columns) + " |",
                         "| " + " | ".join("---" for _ in lint_columns) + " |"])
        markdown.extend("| " + " | ".join(_md(_number(row[key])) for key in lint_columns) + " |"
                        for row in lint_rows)
    pilot = result.get("pilot_summary")
    pilot_columns = ("arm_slot", "scheduled_task_runs", "supplied_task_runs", "missing_task_runs",
                     "known_utility_trials", "unknown_utility_trials", "semantic_invalid_rate",
                     "transport_failure_rate", "bernoulli_utility_variance")
    if pilot:
        markdown.extend(["", "## Supplied development pilot evidence", "",
                         "Approval-needed proposal; no dispatch or absolute utility floor is authorized.", "",
                         "| " + " | ".join(pilot_columns) + " |",
                         "| " + " | ".join("---" for _ in pilot_columns) + " |"])
        markdown.extend("| " + " | ".join(_md(_number(row[key])) for key in pilot_columns) + " |"
                        for row in pilot["arms"])
    unknown_trials = result.get("unknown_trials", [])
    if unknown_trials:
        markdown.extend(["", "## Scheduled trials with missing or incomplete evidence", "",
                         "Missing records remain unknown; an incomplete subset earns no reduced-denominator summary.", "",
                         "| trial_id | state | reasons |", "| --- | --- | --- |"])
        markdown.extend(f"| {_md(row['trial_id'])} | {_md(row['state'])} | {_md(', '.join(row['reasons']))} |"
                        for row in unknown_trials)
    acceptance = result.get("acceptance_recommendation")
    if acceptance:
        markdown.extend(["", "## Policy recommendation from supplied evidence", "",
                         f"Recommendation: {_md(acceptance['recommendation'])}. Independent product acceptance remains pending.", "",
                         "| criterion | verdict | reason |", "| --- | --- | --- |"])
        markdown.extend(f"| {_md(row['criterion_id'])} | {_md(row['verdict'])} | {_md(row['reason'])} |"
                        for row in acceptance["criteria"])
    development = result.get("development_summary")
    development_columns = ("arm_slot", "selector", "condition", "cell", "task_class", "scheduled",
        "supplied", "missing", "semantic_known", "semantic_unknown_or_proxy", "legacy_proxy_trials",
        "unknown_selection_trials", "unknown_cost_trials", "all_scheduled_utility_lower_bound")
    if development:
        markdown.extend(["", "## Supplied full36 development evidence", "",
            "All planned slots remain in the denominator; proxies and unknown evidence are disclosed. The absolute utility floor and independent approval remain pending.", "",
            "| " + " | ".join(development_columns) + " |",
            "| " + " | ".join("---" for _ in development_columns) + " |"])
        markdown.extend("| " + " | ".join(_md(_number(row[key])) for key in development_columns) + " |"
                        for row in development["groups"])
    stream = io.StringIO(newline="")
    writer = csv.writer(stream)
    writer.writerow(columns)
    for row in flat:
        # Prefix formula-looking untrusted cells for spreadsheet-safe CSV viewing.
        writer.writerow("'" + str(row[key]) if str(row[key]).startswith(("=", "+", "-", "@"))
                        else row[key] for key in columns)
    parts = ["<!doctype html><html lang='en'><meta charset='utf-8'>",
             "<meta name='viewport' content='width=device-width,initial-scale=1'>",
             "<meta http-equiv='Content-Security-Policy' content=\"default-src 'none'; style-src 'unsafe-inline'\">",
             "<title>MCP development replay report</title>",
             "<style>body{font:16px system-ui;margin:2rem;color:#17212b}table{border-collapse:collapse}",
             "th,td{border:1px solid #ccd4dc;padding:.5rem;text-align:left}pre{white-space:pre-wrap}</style>",
             f"<h1>{html.escape(heading)}</h1><p>Execution: {html.escape(execution)}. Acceptance: pending.</p>",
             "<table><thead><tr>"]
    parts.extend(f"<th>{html.escape(key)}</th>" for key in columns)
    parts.append("</tr></thead><tbody>")
    for row in flat:
        parts.append("<tr>" + "".join(f"<td>{html.escape(_number(row[key]))}</td>"
                                     for key in columns) + "</tr>")
    parts.append("</tbody></table><h2>Ordered trace projections</h2>")
    for index, row in enumerate(result["rows"]):
        trial_id = row["outcome"]["trial_id"]
        parts.append(f"<details id='trace-{index}'><summary>{html.escape(trial_id)}</summary><pre>")
        parts.append(html.escape(json.dumps(row, ensure_ascii=True, indent=2, allow_nan=False)))
        parts.append("</pre></details>")
    parts.append("<h2>Limits</h2><ul>")
    parts.extend(f"<li>{html.escape(item)}</li>" for item in result["limitations"])
    parts.append("</ul>")
    if lint_rows:
        parts.append("<h2>Public development lint controls</h2><p>Provisional and confirmed scopes are separate; N/A is not a perfect score.</p><table><thead><tr>")
        parts.extend(f"<th>{html.escape(key)}</th>" for key in lint_columns)
        parts.append("</tr></thead><tbody>")
        for row in lint_rows:
            parts.append("<tr>" + "".join(f"<td>{html.escape(_number(row[key]))}</td>"
                                         for key in lint_columns) + "</tr>")
        parts.append("</tbody></table>")
    if pilot:
        parts.append("<h2>Supplied development pilot evidence</h2><p>Approval needed; no dispatch or utility floor is authorized.</p><table><thead><tr>")
        parts.extend(f"<th>{html.escape(key)}</th>" for key in pilot_columns)
        parts.append("</tr></thead><tbody>")
        for row in pilot["arms"]:
            parts.append("<tr>" + "".join(f"<td>{html.escape(_number(row[key]))}</td>"
                                         for key in pilot_columns) + "</tr>")
        parts.append("</tbody></table>")
    if unknown_trials:
        parts.append("<h2>Scheduled trials with missing or incomplete evidence</h2><p>Unknown records are retained; an incomplete subset earns no reduced-denominator summary.</p><table><tr><th>Trial</th><th>State</th><th>Reasons</th></tr>")
        for row in unknown_trials:
            parts.append(f"<tr><td>{html.escape(row['trial_id'])}</td><td>{html.escape(row['state'])}</td><td>{html.escape(', '.join(row['reasons']))}</td></tr>")
        parts.append("</table>")
    if acceptance:
        parts.append(f"<h2>Policy recommendation from supplied evidence</h2><p>{html.escape(acceptance['recommendation'])}; independent product acceptance remains pending.</p><table><tr><th>Criterion</th><th>Verdict</th><th>Reason</th></tr>")
        for row in acceptance["criteria"]:
            parts.append(f"<tr><td>{html.escape(row['criterion_id'])}</td><td>{html.escape(row['verdict'])}</td><td>{html.escape(row['reason'])}</td></tr>")
        parts.append("</table>")
    if development:
        parts.append("<h2>Supplied full36 development evidence</h2><p>All scheduled slots remain; unknowns/proxies are explicit. No floor or independent approval is generated.</p><table><tr>")
        parts.extend(f"<th>{html.escape(key)}</th>" for key in development_columns)
        parts.append("</tr>")
        for row in development["groups"]:
            parts.append("<tr>" + "".join(f"<td>{html.escape(_number(row[key]))}</td>"
                                         for key in development_columns) + "</tr>")
        parts.append("</table>")
    parts.append("</html>")
    files = {
        "results.json": json.dumps(result, ensure_ascii=True, indent=2, allow_nan=False) + "\n",
        "trials.jsonl": "".join(json.dumps(row, ensure_ascii=True, allow_nan=False) + "\n"
                                   for row in result["rows"]),
        "summary.csv": stream.getvalue(), "REPORT.md": "\n".join(markdown) + "\n",
        "index.html": "".join(parts),
    }
    if lint_rows:
        lint_stream = io.StringIO(newline="")
        lint_writer = csv.writer(lint_stream)
        lint_writer.writerow(lint_columns)
        for row in lint_rows:
            lint_writer.writerow(_number(row[key]) for key in lint_columns)
        files["lint-controls.csv"] = lint_stream.getvalue()
        files["lint-controls.json"] = json.dumps(result["lint_controls"], ensure_ascii=True,
                                                 indent=2, allow_nan=False) + "\n"
    if pilot:
        files["pilot-summary.json"] = json.dumps(pilot, ensure_ascii=True, indent=2, allow_nan=False) + "\n"
        files["threshold-proposal.json"] = json.dumps(result["threshold_proposal"], ensure_ascii=True,
                                                       indent=2, allow_nan=False) + "\n"
    if acceptance:
        files["acceptance-recommendation.json"] = json.dumps(acceptance, ensure_ascii=True,
                                                             indent=2, allow_nan=False) + "\n"
    if development:
        files["development-summary.json"] = json.dumps(development, ensure_ascii=True,
                                                        indent=2, allow_nan=False) + "\n"
        files["development-threshold-proposal.json"] = json.dumps(
            result["development_threshold_proposal"], ensure_ascii=True, indent=2, allow_nan=False) + "\n"
        stream = io.StringIO(newline="")
        writer = csv.writer(stream)
        writer.writerow(development_columns)
        for row in development["groups"]:
            writer.writerow("'" + str(row[key]) if isinstance(row[key], str) and row[key].startswith(
                ("=", "+", "-", "@")) else row[key] for key in development_columns)
        files["development-groups.csv"] = stream.getvalue()
    return files
