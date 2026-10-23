# Public semantic development corpus v2

Source-authored, tuning-known development data. No fixture, model, selector,
handler, evaluator or test ran during authoring. There are no observed outputs,
measured accuracy, live-model traces or independently held-out families here.

## Canonical files and consumer contract

* `fixtures/dev/tasks.json`: 36 wrappers with public (the exact four-field
  PublicTaskCase), scripted_calls, development_only, corpus_version and task_class.
* `gold/dev/oracles.json`: the canonical sealed-loader shape
  `{schema_version: 1, cases: [{public, oracle}]}`. Every oracle is a complete
  semantic-v2 OracleCase JSON projection; D1 owns actual model loading.
* `fixtures/dev/fixtures.json`: 36 exact D2 trusted synthetic payloads, each with
  fixture_ref, pinned clock, source_lines, allowed_source_ids, the two outboxes
  and a source-authored/unexecuted loader_status.
* `fixtures/dev/treatments.json`: exact sealed-loader treatment joins with all
  three conditions, only description overlays, no executable schema change and
  a per-task deterministic order seed. Mechanism annotations are public,
  author-known development metadata; the sealed consumer strips them before
  selector input.
* `fixtures/dev/corpus-manifest-v2.json`: raw file hashes, producer-source pins,
  counts, author/lineage and authored expectations. It is source provenance,
  not an execution or acceptance receipt.

D1 must replace the legacy call-proxy development loader: read the canonical
paired oracle package and preserve utility_version/spec when instantiating
OracleCase via JSON. Its original array-of-legacy-labels reader is incompatible
with this deliberately versioned v2 shape. Keep the public projection confined
to PublicTaskCase; never serialize a task wrapper, oracle, manifest or treatment
lineage into provider requests. D4 calibration consumes the same semantic pairs.
D1 alone owns runner/demo/CLI and result publication. These files do not execute
or publish a study.

## Semantic evidence

Thirty result cases require independently captured actual returned content:
source listings; exact bounded line counts/order/text; match order; grouped error
occurrences; or error totals under the public parser/coverage contract. Successful
call shape cannot replace those predicates. Eight timestamped physical lines
per public source provide known ERROR/FATAL groups and sufficient tail/range
windows. Source policy remains task-specific; protected synthetic sentinels never
occur in public lines. The two canonical disposable outboxes are retained.

Six no-call cases distinguish two ordinary no-tool responses, two explicit
refusals and two clarification questions. They require available, complete final
assistant content plus no selected calls. Refusal/clarification predicates use
bounded case-insensitive content tokens; exact response tasks require their
requested text. Authored expected/scripted text is not an observed response.
Missing final content must stay unknown, never be invented from abstention.

The 36 task IDs, typed expected selections, accepted alternatives, ordering,
multiplicity and forbidden source/tool policies are retained from the public
legacy data. Fixture references and two clarification requests are deliberately
updated. Cases remain six development template clusters, six variants per class;
variants are not independent novel families. Public poison descriptions are the
already-known prerequisite/substitution controls, never private retired cases.

## Preservation and static receipt

Original public v1 tasks and legacy oracles are preserved under their respective
`legacy-v1/` directories, with raw hashes in the v2 manifest. Local `.bak-*`
copies preceded edits and remain uncommitted. No immutable executed evidence
edition was rewritten. The canonical manifest pins the exact changed source
inputs; a later implementation change needs a new source manifest/edition.

CURRENT D5 static inspection, 2026-10-23: standard JSON/count/bounds/join checking
and AST comparison with shared record field sets passed for all 36 pairs,
fixtures and treatments. Coverage is six classes x six; semantic modes are 30
result, two no-tool, two refusal and two clarification. No application import,
model instantiation, handler/parser/fixture execution or test run occurred.
Actual semantic outcomes and replay integration remain unverified.

## Pure preflight/projection API

`mcpsh.catalog.dev_corpus.parse_dev_corpus(files,
expected_manifest_sha256=...)` takes a map from the six exact relative filenames
above (including `fixtures/dev/replay-episodes.json`) to authorized raw bytes.
It opens no paths, imports no application models and executes no fixtures or
callbacks. Input is bounded to 8 MiB per file and 16 MiB total. It checks strict
JSON, an external raw manifest pin, exact data-file hashes, all36/six-class joins,
semantic content gates, source policy, description-only treatments, episode raw
argument identity and replay-only provenance. D1 still owns full shared-model,
server argument and fixture-normalizer admission; preflight is not a replacement
runtime loader or proof that expected results occur.

Clean task-wrapper calls must reproduce the first typed selection alternative;
intentional malformed/wrong controls live in episodes instead. This preserves
legacy selection truth without treating a scripted successful call as utility.

Returns version, tasks, oracle_package, fixtures, treatments, episodes, manifest,
raw_sha256 and manifest_sha256. `public_task_projection(package, task_id)` emits
only the four public fields. `replay_episode_projection(package, episode_id)`
returns public task plus the explicit authored episode for the driver;
`corpus_pins(package)` returns source identity/counts with runtime-unverified
scope. Never pass the combined package/episode to a live selector.

## Scripted episode schema v1

`fixtures/dev/replay-episodes.json` has version, corpus_version, public-development-
replay-only scope and episodes. Each of 46 episode specifications contains:

* episode_id, task_id, condition, fixture_ref and fixture_payload_sha256;
* ordered calls as `{name, arguments: raw_string}` and ordered raw_argument_sha256;
* scripted_final: null, or explicit `{text, refusal_text, stop_reason}`;
* observer_fault_request, observer_expectation and fixed source-only replay provenance.

The 36 clean episodes cover every task; ten additional controls retain known
poison prerequisite/late actions, wrong extra/duplicate calls, duplicate JSON
keys, malformed intent, wrong typed arguments, missing/wrong final text and an
unknown-observer request. Raw malformed strings are intentionally not parsed or
repaired by episode preflight. A null scripted_final means unavailable; the
helper never invents refusal or clarification. Non-null text is authored replay
content, not a model response or prior observation.

D7 owns the explicit scripted final-response adapter API. Its declared signature
is `ReplaySelector(calls=None, episode=None, fixture_sha256=None,
source_file_sha256=None)` with keyword-only episode/pins. D1 can use
`replay_selector_kwargs(package, episode_id)` to produce the exact keyword map:
episode `{schema_version:1, episode_id, provenance:authored-development-script,
turns:[{calls, final_text, stop_reason}]}`, fixture_sha256 and source_file_sha256.
These author one scripted turn while preserving raw strings and null text.
D7's misleadingly named fixture_sha256 pins the **script episode typed hash**,
not the physical D2 fixture payload; the latter remains fixture_payload_sha256
on the source episode. source_file_sha256 pins the raw public episode package.
Separate non-null refusal_text is rejected as unsupported by this turn schema,
not silently folded into another field. The current dataset uses null there.

D7's implementation and D1's runner integration remain their responsibility;
the projection matches the declared source contract and has not been executed.
Scripted/non-model provenance and absent fabricated provider IDs are mandatory.
The observer fault request is a driver control request only: a real consumer
must exercise the actual hook or report unsupported. It must not convert an
authored expectation into an observed unknown/safe/effect result. No observations,
captures, token usage, cost totals or scored results are supplied by episodes.

NEXT D5 static receipt, 2026-10-23: helper and regression source parsed with
`ast.parse`; ten meaningful regression functions authored, zero executed.
Standard JSON/hash inspection checked five exact data-file pins, 46 unique
episode IDs and every ordered raw-argument digest. Source inspection verified
all36 original scripted calls, typed selection alternatives, multiplicity and
source policies are preserved; typed request bounds and all36 fixture reference/
total-byte caps were checked with standard-library data inspection. No helper,
model, selector, scorer, handler, fixture or test was executed.

The final source manifest raw SHA256 is
`ce2fee58a1bd0dcbc0cd180e2433004cf1a3032686fb2c67f3587bd997e4c495`.
It pins source/data, not outcomes. D1's canonical v2 loader/demo consumption and
D7's explicit scripted-final adapter remain their integration responsibilities;
this package supplies the declared adapter's exact keyword projection without
modifying either owner's source. Actual observation
fault injection and all semantic/replay behavior remain runtime-unverified.
