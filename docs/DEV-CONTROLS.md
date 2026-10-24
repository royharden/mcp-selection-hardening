# Authored scripted-control expectations

`fixtures/dev/control-expectations.json` version
`m5-scripted-control-expectations-1` maps all fifteen existing diagnostic episodes,
including the original ten plus five implemented-producer protocol boundaries.
These are EXPECTED source declarations, not observed outcomes, evaluation results
or extra primary/paired/family/live samples. No control was executed during construction.

## API and identity

`catalog.dev_controls.parse_control_expectations(raw, package=...,
expected_sha256=...)` accepts at most 1 MiB strict UTF-8 JSON. The external raw
pin must agree with the externally pinned corpus manifest's `control_contract`:
path, version, raw_sha256 and diagnostic_controls. The six-file main corpus API
does not change; load this optional diagnostic sidecar separately.

The sidecar root has version, corpus_version, scope, expected_only=true,
episode_source_sha256, controls and source-only provenance. Every control has
episode_id, task_id, role=diagnostic, conditions, cells, script_sha256,
planned_raw_argument_sha256, expected, required_evidence and limitations. Script
identity, raw argument strings/null pins and role/design join the exact episode
source. Missing/duplicate/primary controls and extra observed/result fields fail.

`control_expectation_projection(package, controls, episode_id)` returns only an
authored-expected namespace with expected_control, required_actual_evidence and
source pins, paired_design=false and live_eligible=false.
`diagnostic_control_plan(package, controls)` returns these separate entries.
Neither function accepts real observations, computes scores, compares outcomes,
dispatches or publishes. D1 owns demo/eval consumption; D4 owns actual scoring.

## Independent axes and evidence requirements

* Selection records authored relation and planned wrapper count/order/multiplicity.
  A planned wrapper is not an actually captured selected call, especially when
  execution stops before selection.
* Intent predicts recognizable prohibited intent separately from schema-valid
  prohibited attempts. Malformed export arguments do not imply a validated attempt.
* Dispatch distinguishes allowed processing, argument validation, malformed batch,
  pre-dispatch call-cap rejection, policy-dependent cells and unsupported hooks.
  Only an actual admitted server-policy denial can substantiate a policy block.
* Effect carries conditional expected-by-cell labels. Permissive synthetic export
  is predicted only for valid export controls. No-effect credit requires a complete
  independent observer; unknown is never replaced by none.
* Utility retains null where actual semantic evaluation is required and labels
  expected wrong/missing/incomplete final content separately. A successful expected
  read may coexist with an extra prohibited call/effect or a selection error.
* Observer faults retain the request, current source support and expected unknown.
  The inspected runner rejects the unsupported hook before constructing the server.
  A declarative request is not actual fault injection; report unsupported with no
  fault/conformance/effect-free credit until a real admitted hook exists.

Required actual evidence is explicit: source/script pins, ordered selected journal,
selection-to-server links, validation/policy events, independent reset/sequence,
protected-read counters, separate wire-disclosure/outbox observations, semantic
result-capture availability and final-assistant availability/completeness captures.
Availability records may explicitly be missing/incomplete; their presence does not
make the underlying content available or complete. Only actual complete evidence
can support a claim that requires it.
Fault controls additionally require actual hook evidence or explicit unsupported.
The source sidecar supplies none of those execution records. Nulls remain null;
there are no fabricated provider parents, usage/billing, utility flags or effects.

The sidecar schema is deliberately closed under expected. It cannot be extended
with observed_outcome or utility_success and accepted merely by recomputing a hash.
It checks supplied source lineage, not the truth of an author's forecast or approval.
Expected/observed comparison and independent product acceptance remain outside it.

## Construction validation

Focused source review checked the current runner's selection journaling, pre-cap
batch rejection, server-call validation and explicit unsupported observer-fault
path. Standard JSON/count/hash inspection checked all fifteen diagnostic joins,
six-axis separation and the exact episode source pin. Source AST checks and
meaningful schema/failure regressions were authored; no parser, projection,
selector, scorer, fixture, test, model import, provider or backend was executed.
Runtime effect/utility/observer behavior remains unverified.

V6 final construction receipt, D5 2026-10-23: seven scoped Python files parsed
with stdlib AST after concrete source repairs. Fourteen new v6 regression
functions were authored (six role/semantic, eight control-contract); none ran.
Standard JSON/hash inspection checked all 15 control/script/raw-argument/planned-
count joins, five main data pins and preserved prior-source archives. Structural
response caps include each declared call's own limits, not only global maxima.
Parsed control dictionaries carry a typed digest and source pins; post-parse
mutation is rejected before diagnostic projection. No actual evidence checker,
semantic preflight, parser, projection, handler, selector, fixture or test was run.

Current source manifest (version 3 at the existing corpus-manifest-v2 filename)
raw SHA256: `2ca6bf0807f14f12e3abb16182f0598c14326f65532b7c0055a5e1451f47d646`
(C1 oracle prohibited-source closure re-pin, 2026-10-23; the previous pin
`f78646ecff932d3810130bf1d590daf18c6bcd32ec2332b69d010f15fa6a92af` is superseded,
see `docs/DEV-CORPUS.md`).
Control sidecar raw SHA256:
`fee1bc68622bd27eb3c1c8fbd36c6017b109afe4c493cbcfc419df242923db49`.
The primary source has 36 scripts/324 planned design slots; diagnostics remain
15 separate source plans, never paired or live samples. Runtime outcomes, actual
semantic correctness and real evidence completeness remain unverified.
