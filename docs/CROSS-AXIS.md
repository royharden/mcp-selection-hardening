# Cross-axis diagnostics

`evaluation.diagnostics` exposes `AxisEvidence`, `diagnose_trial_axes(evidence,
oracle=None)` and `summarize_cross_axes(evidence, expected_schedule=None,
oracle_by_task=None)`. Optional arguments are keyword-only. The acceptance dossier
includes the summary as `cross_axes`; D1 owns report publication. These pure
consumers perform no filesystem reads, dispatch, rescoring or statistical analysis.
The typed adapter delegates validation of D7 observer dictionaries to D7's model
helper. Callers must supply the existing verified edition, not arbitrary payloads.

Each output retains the full selected order with validation and dispatch disposition,
actual server attempts and blocks, independent observer effects, existing utility
projection and usage/accounting basis. A cap rejection does not become a server
policy block. Recognizable invalid intent can exist without any dispatched call.
A prohibited block followed by a later independently observed effect is reported
when call-order evidence supports it. An effect may coexist with semantic success.

Missing observers remain unknown. Observed predicates dominate unknown predicates,
while incompleteness remains explicit. Missing usage after apparent success remains
unknown cost. Replay non-model cost cannot grant live usage or billing credit;
recorded dated estimates remain estimates. Unjoined reused evidence grants neither
a new independent sample nor free usage.

Summaries retain all supplied rows, including duplicates, failures, unknowns and
legacy proxies. The externally supplied scheduled denominator, missing rows,
unexpected rows and duplicate rows are separate fields. Group counts preserve
model, selector, condition, cell, repeat, execution mode, platform and utility/cost
bases. A group's shared scheduled-coordinate denominator does not represent a new
denominator for acceptance. No rates, uncertainty interval, independent sample size
or new acceptance metric are produced. Missing metadata is not inferred from IDs.

Outputs contain fixed diagnostic codes, counts, hashes and metadata. Raw selected
arguments, oracle predicates, assistant text and provider payloads are excluded.
Independent product acceptance remains pending. Diagnostic schedule identity checks
do not authenticate external authority or replace the dossier admission criteria.

## Public status (D7 C3)

`project_cross_axis_status(summary_dict)` turns `CrossAxisSummary.model_dump(mode="json")`
into the finite `cross-axis-status-v1` block. `runner.dossier` carries it as the result's
`cross_axes`, and `public_projection` allowlists it (`CROSS_AXES`). Fields:

- `version`, `source_version`, `interpretation`, `source_integrity`
- `scheduled_denominator`, `supplied_rows`, `missing_scheduled_rows`, `duplicate_rows`,
  `unexpected_rows`
- per-axis counts: `trial_states` (mixed-axes-recorded, incomplete, inconsistent),
  `observer_effect` (none, observed, unknown), `cost_state` (non-model,
  recorded-estimate, unknown), `utility_basis` (semantic-v2, legacy-call-proxy-v1),
  `semantic_utility` (success, failure, unknown)
- `mixed_failure_categories`: trials, not codes, per category. The categories are
  effect_with_apparent_utility, effect_without_reported_intent, block_then_effect,
  intent_without_server_attempt, selection_not_server_policy and
  unknown_usage_after_success.
- `code_counts`: every code in the closed `CROSS_AXIS_CODES` vocabulary, zero-filled.
  A code outside that vocabulary is added to `unlisted_code_count`, never dropped.
- `groups`: the summary's coordinate groups. Model IDs and selectors are aliased by
  the projection; condition, cell, repeat, mode, platform and bases appear with all
  nine counts.
- `independent_product_acceptance: pending`

No per-trial rows, selected-call order, outcome hashes, arguments or text are included.
The full summary stays in the private dossier. Parity tests pin the projection's
copies of the code and category vocabularies.

Construction receipt, D4 source-v5: scoped AST parses passed for the two new source
modules and both regression files. Seventeen regression functions were authored
(nine admission, eight cross-axis), covering source drift, unknown costs, missing
scheduled failures, mixed effects, cap refusal, invalid intent and denominator
retention. Source contract inspection covered D7 typed evidence and existing scorer
recognizers. No product import, reader, dossier, evaluator, statistics, bootstrap,
test or runtime execution occurred. Dirty Mode construction only; runtime unverified.
