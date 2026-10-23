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


def render_bundle(result: dict[str, Any]) -> dict[str, str]:
    """Caller must provide a redacted public projection; no raw evidence is written here."""
    summaries = result["summary"]
    heading = result["banner"]
    execution = result["execution_state"]
    columns = ["selector", "condition", "cell", "scheduled_trials", "raw_calls",
               "selection", "utility", "intent", "validated_prohibited_calls",
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
    parts.append("</ul></html>")
    return {
        "results.json": json.dumps(result, ensure_ascii=True, indent=2, allow_nan=False) + "\n",
        "trials.jsonl": "".join(json.dumps(row, ensure_ascii=True, allow_nan=False) + "\n"
                                   for row in result["rows"]),
        "summary.csv": stream.getvalue(), "REPORT.md": "\n".join(markdown) + "\n",
        "index.html": "".join(parts),
    }
