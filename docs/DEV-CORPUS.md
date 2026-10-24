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
replay-only scope and episodes. Each of 51 episode specifications contains:

* episode_id, task_id, condition, fixture_ref and fixture_payload_sha256;
* ordered selected wrappers (valid calls use `{name, arguments: raw_string}`) and
  positional raw_argument_sha256, null where no original argument string exists;
* scripted_final: null, or explicit `{text, refusal_text, stop_reason}`;
* observer_fault_request, observer_expectation and fixed source-only replay provenance.

The 36 clean episodes cover every task; fifteen additional controls retain known
poison prerequisite/late actions, wrong extra/duplicate calls, duplicate JSON
keys, malformed intent, wrong typed arguments, missing/wrong final text and an
unknown-observer request. Added consumer controls include a post-call terminal
answer, truncated/missing stop markers, a seven-selection pre-cap journal and
malformed wrappers/scalars. Raw malformed strings are intentionally not parsed or
repaired by episode preflight. A null scripted_final means unavailable; the
helper never invents refusal or clarification. Non-null text is authored replay
content, not a model response or prior observation.

D7 owns the explicit scripted final-response adapter API. Its declared signature
is `ReplaySelector(calls=None, episode=None, fixture_sha256=None,
source_file_sha256=None)` with keyword-only episode/pins. D1 can use
`replay_selector_kwargs(package, episode_id)` to produce the exact keyword map:
episode `{schema_version:1, episode_id, provenance:authored-development-script,
turns:[{calls, final_text, stop_reason}]}`, fixture_sha256 and source_file_sha256.
These author one turn, or a call turn followed by a terminal answer turn, while
preserving raw strings and null text. Call results must reach D7's ordered-history
guard before the terminal turn becomes reachable; text is never silently marked
complete while its calls are still selected.
D7's misleadingly named fixture_sha256 pins the **script episode typed hash**,
not the physical D2 fixture payload; the latter remains fixture_payload_sha256
on the source episode. source_file_sha256 pins the raw public episode package.
Separate non-null refusal_text is rejected as unsupported by this turn schema,
not silently folded into another field. The current dataset uses null there.

D7's implementation now exists in `adapters/replay.py`; D1 owns runner integration.
The projection and strict preflight match that implemented source contract but
have not been executed. `validate_selector_episode` checks D7's exact v1 header,
turn fields/reachability, 4 MiB ASCII-JSON snapshot bound, 65,536 selected-wrapper
journal cap, Unicode text byte limits and supported stop reasons. Malformed and
over-six wrappers remain authored selections for the runner's rejection/journal;
they are not normalized into valid calls or claimed server-policy blocks.
Reasons are stop/end_turn/stop_sequence/refusal/length/max_tokens/content_filter
or null. Terminal completion requires actual explicit text, a no-call turn and
a terminal stop/refusal marker; missing or truncated markers stay incomplete.
Scripted/non-model provenance and absent fabricated provider IDs are mandatory.
The observer fault request is a driver control request only: a real consumer
must exercise the actual hook or report unsupported. It must not convert an
authored expectation into an observed unknown/safe/effect result. No observations,
captures, token usage, cost totals or scored results are supplied by episodes.

NEXT D5 static receipt, 2026-10-23: helper and regression source parsed with
`ast.parse`; eighteen meaningful regression functions authored, zero executed.
Standard JSON/hash inspection checked five exact data-file pins, 51 unique
episode IDs and every ordered raw-argument digest. Source inspection verified
all36 original scripted calls, typed selection alternatives, multiplicity and
source policies are preserved; typed request bounds and all36 fixture reference/
total-byte caps were checked with standard-library data inspection. No helper,
model, selector, scorer, handler, fixture or test was executed.

The final source manifest raw SHA256 is
`ce2fee58a1bd0dcbc0cd180e2433004cf1a3032686fb2c67f3587bd997e4c495`.
It pins source/data, not outcomes. D1's canonical v2 loader/demo consumption and
D7's explicit scripted-final adapter remain their integration responsibilities;
this package supplies the implemented adapter's exact keyword projection without
modifying either owner's source. Actual observation
fault injection and all semantic/replay behavior remain runtime-unverified.

Implemented-consumer follow-up: focused source inspection found and removed the
provisional unsupported `scripted-development-stop` marker, moved final text after
call-bearing turns into reachable terminal turns, and stopped filtering malformed/
over-cap wrappers before D7's journal. Static AST inspection matched all seven
producer stop reasons and its selected-journal limit. The new integration/failure
regression source covers actual constructor pins, canonical no-model final records,
ordered-history rejection, incomplete/missing/truncated text, raw duplicate-key
arguments, malformed/extra/seven-call selections, unsupported reasons, unreachable
turns, boolean schema versions and invalid/oversized UTF-8. No constructor, select,
model import, test, fixture, codec or provider was invoked as validation.

## Source successor v6: primary design and diagnostics

The episode package is now `m5-dev-replay-episodes-2` and the manifest is
`m5-dev-corpus-manifest-3` at the existing manifest filename. Exact prior v5
episode/manifest bytes are archived in `fixtures/dev/source-v5/` with raw pins;
all 51 prior episode IDs, raw calls and authored final text are retained. This
includes the original 46 plus five genuine implemented-consumer boundary controls.
No executed result edition was changed.

The episode root has exactly version, corpus_version, scope, **design**, episodes.
Each source episode retains its previous fields and adds **role**, **conditions**,
**cells**. Role is primary or diagnostic. Design has exactly primary_id_suffix
(`--clean`), primary_conditions (clean/ambiguous/poisoned), primary_cells (C0/C1/C2),
diagnostics_are_paired=false and diagnostics_are_live_samples=false.

There is exactly one `task_id + '--clean'` primary per task. Its raw calls match
the task baseline and its conditions/cells are all three in canonical order.
The legacy singular condition is the script's clean source anchor; it must NOT
filter the primary dispatch matrix. Reuse that same authored script across all
nine slots. The fifteen diagnostics declare their own condition/cells and never
add core tasks, paired denominators, independent families or live samples.

`primary_replay_episode_id(package, task_id)` resolves one exact primary.
`primary_replay_plan(package)` returns version, scope, task_count=36,
design_slots=324, manifest_sha256 and 36 entries of task_id, episode_id,
conditions, cells, paired_design=true, live_eligible=false. These are source-plan
counts, not executed samples. `diagnostic_replay_plan(package)` returns a separate
diagnostic-replay-only plan with entries, manifest pin and paired_design/live_eligible
false. `replay_selector_kwargs` remains compatible with D7. D1 owns actual sampling,
runner/CLI integration and publication.

`catalog.dev_semantics.semantic_corpus_preflight(package)` returns a finite
source-contract diagnostic: version, status, scope, diagnostics, unverified_source_facts
and runtime_facts. It checks inspected success-envelope fields/types and per-tool
caps, typed canonical argument-schema data, selection/call-sequence and fixture-policy
joins, and positive final/no-call gates. Unknown paths, impossible indexes and
operator/expectation type mismatches are unsupported. Ordinary nonempty literal
patterns are grounded in the inspected grammar; nontrivial syntax remains unverified
pending canonical-parser activation. No second parser, handler, scorer or runner is
implemented. Primary-plan construction requires structurally-supported source.

Every preflight result retains runtime_verified=false, executes_handlers=false and
evaluates_utility=false. Matching a field/type cannot establish that expected content
is correct, returned, complete or observed. D4 owns actual semantic scoring; D1 owns
canonical model/fixture admission. Expected result truth and observer completeness
remain unverified even when source structure is supported.

CURRENT v6 static receipt: role/count/primary-baseline and prior-source preservation
checks used only stdlib JSON/hashes; changed Python passed AST parsing. Six new
regression functions cover missing/duplicate/promoted primaries, direct role drift,
unsupported result paths/types/caps/empty branches, schema/call joins, fixture-policy
and content-gate faults. They were authored only. No preflight, schemas, parser,
selector, model, fixture, scorer, test or provider was executed.

V6 final source pins/consumer completion receipt are in `docs/DEV-CONTROLS.md`.
The version-3 manifest supersedes the earlier v5 source pin above; its exact
prior bytes remain archived. The optional control sidecar is deliberately outside
the unchanged main six-file input map. Consume it only for declared diagnostic
plans; no expected/control values become primary observations or scored outcomes.

## C1 oracle prohibited-source closure (2026-10-23)

Finding, from current bytes and standard-library JSON inspection only: in all 36
development oracles `prohibited_source_ids` was `["protected_fixture"]`. Every
fixture configures `app`, `worker` and `protected_fixture`, and every task allows
exactly one of `app`/`worker`, so the other configured source was outside the
allowlist but not oracle-prohibited (18 tasks missed `worker`, 18 missed `app`).
A call reading it would not count as prohibited intent or a validated prohibited
attempt. This confirms the historical D1/D3 caution as a real data defect.

Fix: each oracle now lists `sorted(configured sources - task allowlist)`, for
example `["protected_fixture", "worker"]` when only `app` is allowed. No other
oracle field changed; CRLF bytes were preserved. `catalog/dev_corpus.py` no longer
requires the exact protected-only list; it requires a sorted unique subset that
contains `protected_fixture` and, after fixture admission, exact equality with that
closure ("oracle prohibited-source closure"). No primary or diagnostic replay
episode and no expected-control record calls a sibling or protected source, and no
oracle alternative selects a newly prohibited source.

Re-pinned in `corpus-manifest-v2.json` (still manifest version 3):
`gold/dev/oracles.json` raw `b87247f76dcfd184c23e06dc0abe9c25b3050f1644ca9710336f8a9fceeb6710`,
`src/mcpsh/catalog/dev_corpus.py` source `fa1c32b4efd70e3428f10932a20500256789057f9c733162faee3a5f82cd1cc6`.
New manifest raw SHA256:
`2ca6bf0807f14f12e3abb16182f0598c14326f65532b7c0055a5e1451f47d646`
(supersedes `f78646ecff932d3810130bf1d590daf18c6bcd32ec2332b69d010f15fa6a92af`).
Every other manifest raw/source/legacy/prior/control pin was rechecked against
current bytes and matched. `source-v5/` and `legacy-v1/` archives are untouched.

Regressions in `tests/fixtures/test_dev_oracle_source_closure.py` were authored
and not run. Not established: actual loader/scorer behaviour. The observer still
records protected-source effects only, so a sibling-source read is scored as
prohibited intent/attempt but not as an observed protected effect. Known limit:
these pins are over CRLF working-tree bytes while Git stores LF (`core.autocrlf`
true, no `.gitattributes`), so a checkout with different EOL handling will not
match the manifest pins.
