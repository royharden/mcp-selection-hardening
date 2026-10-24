# Mode-specific report views

The base report tables (matrix summary, lint controls, pilot arms, full36 groups,
ledger totals) are empty for most nonmatrix editions, even though the projected
result object carries their statuses. `mcpsh.report.evaluation_views` adds status
views for those modes. They are built from the same object as `results.json`.

## API

```python
from mcpsh.report import (
    evaluation_view_sections,   # (public_result: dict) -> list[dict]
    render_evaluation_markdown, # (public_result: dict) -> str, a "## Evaluation views" block
    render_evaluation_html,     # (public_result: dict) -> str, a <section> fragment
)
```

Each section is `{"id", "title", "state", "note", "columns", "rows"}`. `state` is
`present`, `pending` (expected for this `execution_state` but absent) or `N/A` (not part
of this mode). Every row cell is a string copy of a supplied value. The functions do
no IO and never mutate their input. `render_bundle` places the Markdown block at the
end of `REPORT.md` and the HTML fragment at the end of `index.html`, and it writes the
sections as `evaluation-views.json`. Because `scripts/eval.py` already calls
`render_bundle` on the canonical projection, it needs no change.

## Input contract

Pass only the output of `mcpsh.evidence.project_public_result(...).public`. The views
read a fixed whitelist of fields from these blocks: `pilot_summary`,
`threshold_proposal`, `development_summary` (including `paired_retention`),
`development_threshold_proposal`, `threshold_approval_status`,
`acceptance_dossier_status`, `ledger_audit_status`, `token_fit_status`,
`normative_v3_status` (version `m5-normative-v3-status-1`), `development_input_pins`
and `replay_design`. They also read these root provenance
scalars: `execution_state`, `platform_scope`, `development_only`, `live_model_runs`,
`heldout_families`, `scheduled_trials`, `scored_trials`, `acceptance_verdict`,
`manifest.mode`, `manifest.platform_scope`, `projection.version` and
`projection.policy`, plus the counts of rows and listed unknown trials. Other keys are
never shown. Neither are nested metadata, raw authority, bodies or final text.

Cross-axis diagnostics are produced inside the private acceptance dossier.
Projection `mcpsh-public-result-v1` defines no aliased `cross_axes` block, so dossier
editions show that section as `pending`. Any `cross_axes` key on the input is
ignored. That way unaliased model IDs or per-trial diagnostics cannot be displayed.
Before it can be shown, the projector owner must add an aliased schema and this
module must add a whitelist.

| `execution_state` | Sections expected (pending when absent) |
| --- | --- |
| `pilot-summary-draft` | pilot status, pilot threshold proposal, threshold approval binding |
| `development-summary-draft` | full36 status, paired retention, development threshold proposal, threshold approval binding |
| `acceptance-dossier-draft` | acceptance dossier status, cross-axis diagnostics (pending until projected) |
| `ledger-audit-draft` | ledger audit status |
| `replay-only` | replay design, development input pins |
| `live-complete`, `partial` | token-fit status |

Any section that is present is shown whatever the mode.

The **Normative conformance status** section copies D7's bridge status as supplied. It
is `N/A` when the edition carries no block. Totals, probe states and tracks are null
unless the status is `evaluated` with a valid authority. They then show as
`not supplied`, and the **Normative conformance tracks** section shows as `pending`;
none of them shows as zero. When tracks are supplied, the table always lists the
synthetic-memory, filesystem-posix and stdio tracks. It shows each track's counts and
one column per pending reason, and a track that is absent shows `not supplied`. Track
verdicts, `suite_acceptance` and `product_verdict` stay `pending`.
`full_platform_credit` can only be false.

## Display rules

- `None` is shown as `not supplied`, never as `0`. A supplied `0` stays `0`. An empty
  supplied list or map is shown as `(none supplied)`.
- Numbers are shown exactly as supplied. Nothing is rounded, and no rate, threshold,
  denominator, interval or acceptance outcome is recomputed or inferred.
- Metric records show `numerator/denominator (value …; status …)` exactly as supplied.
- Order is fixed: sections follow a constant order, fields follow the whitelist order,
  map keys are sorted, and list rows keep their supplied order.
- Markdown data cells are inline code spans whose backtick fence is longer than any
  run inside the value. Pipes are escaped and control characters become spaces. Links,
  emphasis and HTML in supplied data are therefore inert. In HTML, every value is
  passed through `html.escape`. Element ids are fixed constants. The fragment has no
  scripts or external resources, and the page CSP stays `default-src 'none'`.

## Status

These views were built under Dirty Mode and have not been run. Nine regressions were
written in `tests/report/test_evaluation_views.py` and have not been run: value
preservation, missing versus zero, retained unknown and gap rows, replay and platform
labels, hostile cells, the shared object left unchanged, deterministic order,
normative-v3 pending versus evaluated, and cross-axis staying pending with unprojected
data ignored. A rendering pass over real projected editions
still needs to happen.
