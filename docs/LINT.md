# Bounded development lint evaluation

Construction source; runtime and detector results have not been verified. The
evaluator returns JSON-compatible objects to the single `scripts/eval.py`
publisher. It writes no results, README tables or reports itself. No accuracy
numbers are claimed by this document.

## Consumer API v1

```python
from mcpsh.lint_evaluation import evaluate_labels, evaluate_normalization

controls = evaluate_labels(labels, bypasses=bypasses, review=review_by_case_id)
normalization = evaluate_normalization(complete_nine_tool_catalog)
```

The publisher owns file loading and provenance. `labels` is the public
`fixtures/dev/lint-labels.json` array (48 scheduled controls); `bypasses` is the
public `fixtures/dev/lint-bypasses.json` array (12 separate diagnostics). Never
load retired/private labels through this development path. Proposed consumer
flags: `--lint-controls` and optional `--lint-review <public-review-path>`; CLI
and flags remain D1-owned until integrated. Missing files/invalid JSON must be
reported as input failures by that consumer, not replaced with empty arrays.

Each label has `case_id`, `rule_id`, boolean `expected_detection`, and `catalog`
(a list of tool fragments with `name`, `description`, `inputSchema` and optional
`annotations`). Duplicate **case** IDs yield unknown rows, preserving every
scheduled ordinal. Duplicate **tool** IDs in a fragment are diagnostic input for
L07, not suppressed or deduplicated. Fragments are not complete experiment
catalogs and need not contain canonical executable schemas.

`review` is an optional mapping by case ID. A confirmed record must contain
`status: confirmed`, the same `rule_id`, exact boolean `expected_detection`, and
`catalog_sha256` for the canonical-JSON catalog. A mismatched hash/label/rule is
stale and excluded from confirmed metrics. Pending/rejected/unreviewed cases
remain visible. Passing a review file is provenance supplied by the caller, not
proof of independent review or a security boundary.

The control return projection is:

* `version`, `lint_version`, `scope`, `scheduled`, `unknown`, `acceptance`,
  `published` (always false).
* `cases`: ordered rows, each with ordinal, kind, case ID, rule ID, status and
  review status. Valid rows add detected/expected booleans, catalog hash,
  findings, target-only classification/diagnostic and expectation agreement.
  Invalid rows retain errors and an unknown state; they are never clean TNs.
  `identical_control_count` discloses repeated rule/label/catalog templates while
  retaining every scheduled record; repeated IDs still make all copies unknown.
* `per_rule`: scheduled/unknown/unconfirmed counts, `provisional_all_labels` and
  `confirmed_labels` TP/FP/FN/TN, plus separate bypass diagnostics. Precision and
  recall contain numerator, denominator, nullable value and `N/A` at zero.

Provisional metrics are unreviewed development diagnostics. Confirmed metrics
are conditional on supplied review metadata and still do not establish held-out
generalization. One target-rule label says nothing about other co-occurring
rules. Bypasses never enter benign TN/accuracy denominators: an improved detector
may detect them without being penalized for violating an old miss expectation.
There is no single global safety score and no universal detector claim.

## Normalization audit

`evaluate_normalization` requires exactly the nine unique canonical IDs with
unchanged canonical schemas. It returns `ineligible` and issues on malformed,
duplicate/missing ID or schema-drift input; it never removes offending tools or
substitutes schemas to earn an improvement. A valid source audit returns
`verified-source-invariants`, hashes before/after, trusted-map hash, ordered IDs,
ordered schema hashes, unchanged non-description projection hashes, findings and
exact metadata diffs, plus the normalized catalog for the publisher.

Only lint-flagged descriptions may change, and each replacement must equal its
trusted canonical description. Names, order, multiplicity, schemas, annotations
and other fields stay byte-value equivalent in the JSON projection; caller input
is not mutated. `runtime_functionality: unverified` is intentional: source
identity cannot prove that a future server executes the same behavior. Residual
findings are returned; normalization is not assumed to eliminate every warning.

## Bounds and evidence

Description scanning stops at 4096 Unicode codepoints; length excess is an L11
finding with a bounded evidence slice. Maximum metadata depth is eight. Names
are limited to 1024 codepoints, descriptions to 1 Mi codepoints and fragment
catalogs to 256 tools for processing; exceeding these outer limits is invalid,
not a clean lint outcome. An evaluation accepts at most 4096 scheduled controls.
Non-text/empty descriptions, malformed schemas/annotations and invalid Unicode
scalars produce explicit errors. Named bidi/zero-width characters are data.

Every emitted finding is checked against its original `name`/`description`
Unicode-codepoint slice, including supplementary characters; out-of-bounds or
inexact evidence makes the case unknown. Label spans and lexical-match spans
are different concepts. Matching text, not a claim of malicious intent, is the
bounded rule's observation. Negation and harmless mentions can be false
positives; paraphrases without lexical triggers can bypass both lint and repair.

## Deferred validation

Meaningful regression source lives under `tests/lint/` and `tests/catalog/`.
Dirty Mode permits authoring and syntax inspection only; these tests have not
run. Later activation must execute the public controls, validate CLI/publisher
provenance, inspect all positive/benign/bypass diagnostics, and exercise server
semantics separately. No retired held-out examples are embedded in source/tests.

## Construction receipt — current package

D5, 2026-10-23: authored evaluator/control API, malformed-input handling,
source-only normalization invariants and eight regression functions. Focused
manual control/logic review and AST parsing of the lint, catalog, evaluator and
regression modules completed successfully (four files). No application import,
test or study ran. Catalog search prose now declares the server's existing finite
literal-alternatives/anchors subset; schemas were not changed. Schema comparison
uses typed JSON identity so booleans cannot substitute for numeric bounds.
Backups preceded the two edits to pre-existing source files.

## Public review metadata and follow-up receipt

`fixtures/dev/lint-review.json` version `m5-public-lint-review-1` supplies a
`cases` mapping for the API (`review=sidecar["cases"]`). Its 48 confirmations are
D5's static target-control adjudications, not independent review and not
executed detector observations. Input hashes bind it to the original public
files, which remain unchanged. The 12 `bypasses` entries are diagnostic-only:
some document missing features rather than a proven semantic attack. Do not
interpret target non-detection as evidence of exploitation. Two L07 positive
records contain the same catalog template; dependence is reported without
silently removing either record.

The follow-up adds normalization regression source under `tests/catalog/` and
false-positive, innocent-ignore-errors and repeated-template controls under
`tests/lint/`. It leaves rule patterns and frozen executable schemas intact.
All tests are authored only. A future study must include all scheduled failures
and unknowns, state the supplied review lineage, and run the public controls
before making any numeric lint-effectiveness assertion. D1 owns loading,
CLI/provenance and the sole result publisher; no results are published here.

Follow-up static receipt, 2026-10-23: four changed/new Python modules parsed
successfully with `ast.parse` (lint, evaluator, lint tests and catalog tests).
The two test modules contain 19 authored test functions; zero ran. Standard
JSON parsing inspected 48 public label records, 12 bypass diagnostics and 48
sidecar review entries. SHA256 inspection confirmed the original public label,
bypass and canonical-schema files retain their pre-package identities. Manual
source tracing checked unknown/provisional/confirmed denominators, separate
bypasses, duplicate-template disclosure and metadata-only invariants. CLI,
publisher integration, actual detector outcomes and server functionality remain
unverified until authorized runtime validation.

The versioned catalog/treatment API is described in `docs/CATALOG.md`.
`evaluate_labels` and `evaluate_normalization` additionally enrich findings with
`byte_span` (`utf-8-byte`) and `field_sha256` while retaining canonical
Unicode-codepoint `span` and exact evidence. Character and byte positions are
different for non-ASCII text. These reference original decoded field text,
not escaped JSON transport or a normalized Unicode representation. Mismatched
evidence is unknown/invalid, never silently corrected. Original label schemas
and the evaluator's existing consumer return keys remain compatible.
