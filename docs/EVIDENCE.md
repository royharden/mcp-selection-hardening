# Offline evidence editions

D7 W7 source construction, 2026-10-23. No reader, rescore, provider, DB or regression
test has been executed under Dirty Mode. The canonical evidence-gate closed-schema,
external-authority and lineage principles guide this project-specific format; this is
not a normalized-core compatibility claim or an AgentOps acceptance checker.

`mcpsh.evidence` supplies three explicit APIs:

- `build_edition_payloads(result, *, candidate_commit, revision,
  reserved_by_operation=None, oracle_package_bytes=None) -> dict[str, bytes]` adapts
  the existing runner/report object in memory. These are **private raw sidecars**,
  including argument/result/observer data. It never writes or discovers custody.
  Oracle bytes are optional and must be explicitly supplied by an authorized custodian.
  This API grants no permission to access a private oracle. Unsupported source row
  fields reject rather than being silently dropped. Missing reserve amounts remain
  unknown. Only D1's `scripts/eval.py` may publish a numeric edition, after its existing
  immutable-edition and bounded/redacted projection steps. Never place raw sidecars
  under the public report directory.
- `read_edition(root, *, authority: EditionAuthority) -> VerifiedEdition` opens only
  `EDITION.json` and its explicitly pinned artifacts. `authority` must be independently
  supplied: index SHA256, manifest SHA256, candidate commit, revision, edition ID,
  mode, platform and all nine input pins. Computing a new pin from an untrusted index
  and accepting it is not authority. The bytes are frozen and revalidated on each
  `validate()` or reproduction call. No import reads an edition.
- `inspect_edition(edition) -> dict` reports structural integrity, per-trial unknowns,
  and evidence completeness without invoking the scorer. Both empirical and product
  verdicts remain pending even when evidence completeness is true.
- `reproduce(edition, *, expected_evaluator_hash) -> dict` checks actual evaluator and
  package source hashes against the externally pinned manifest, then calls the existing
  `score_trial` and `aggregate_outcomes`. It returns the existing private report object
  shape without writing. D1 must apply its fixture-aware public projection before
  `render_bundle`. No hidden labels or raw payloads are safe merely because rendering
  escapes HTML. The exact source edition remains intact; changed inputs/scorer require
  a successor revision, not replacement of old numbers.

The index's closed v1 schema binds `MANIFEST.json`, ordered `trials.jsonl`, optional
`observers.jsonl` and optional `oracles.json` with relative forward-slash paths, exact
raw SHA256 and byte lengths. It records the explicit scheduled trial IDs in order;
duplicates, dropped rows, reordered rows and extra artifact roles reject. The public
task projection and raw oracle seal are checked when the optional oracle exists.
Empirical and product verdicts are always `pending`.

Trial rows use the existing strict `TrialOutcome`, `ToolCallEvent`, `ModelAttempt`,
`FinalAssistantResponse` and `ToolResultCapture` contracts, plus explicit attempt cost
records. Calls keep raw argument bytes and typed hashes distinct. Ordered call/result
cardinality, raw/typed hashes, trial/turn/attempt parents, global ID uniqueness, replay
provenance and live usage/settlement totals are checked.
The pinned server uses ASCII-escaped canonical JSON for typed argument and result
hashes; records use Unicode typed JSON for whole-trace hashes. The reader honors these
existing conventions and preserves JSON type distinctions in both.

Observer rows preserve the exact original observation dictionary for its outcome hash,
validate it with a closed source schema, and separately bind trial/platform/observer
code. Complete observations require reset, sequence, wire coverage and consistent
counter/outbox/wire predicates. Broker event sequence and call-parent links are checked.
Handler denial prose is never substituted for an observer. Correct hashes and coherent
journals still cannot establish that an alleged observation actually occurred.

Bounds: 128 KiB index, 32 MiB per artifact, 64 MiB total, 5,000 trial/observer rows,
1 MiB per JSONL row/string, 48 nesting levels, 100,000 JSON nodes, six calls/attempts
per trial and 1,000 broker events per observer. Duplicate JSON keys, NaN/Infinity and
overflowed finite-number exponents reject. Paths reject escapes, absolute/drive/UNC/
ADS forms, device names, ambiguous components, symlinks and Windows reparse points.
POSIX uses an anchored no-follow descriptor walk. The Windows fallback checks file
and parent identities and requires externally immutable custody; hostile rename-race
conformance remains unverified. No cross-platform race-safety claim is made.

Missing oracle or raw calls/results creates an explicit unknown row and suppresses the
entire numeric summary rather than reducing denominators. Missing/incomplete observer,
usage or reservation evidence stays unknown/partial. Structural integrity, reproducible
scores, observed effects and independent empirical/product acceptance are separate
claims. Memory cannot satisfy filesystem evidence, and replay cannot count as live.

Regression source in `tests/evidence/test_edition_integrity.py` includes an honest
positive control, raw-byte tampering, externally bound revision, duplicate/nonfinite
JSON, ordered sequence and model-parent mutations, settled-without-usage rejection,
path/symlink/cap checks, missing-oracle/observer unknown handling and scorer drift.
These are authored cases, not measured results. Later activation must exercise them,
verify filesystem semantics, and integrate D1's sole publisher using an actual authorized
development edition before making any runtime claim.

Construction checks: six explicit Python AST parses and the format-description JSON
parse passed. A focused source pass checked the current evaluator/record/observer
interfaces, caught and corrected the server's distinct ASCII-canonical argument hash
convention, and added a Unicode regression source. Subsequent corrections to byte caps,
settlement linkage and semantic-unknown reporting were reparsed. New-file whitespace
was inspected directly; `git diff --check` applies only to tracked diffs and is not
evidence that untracked source ran. Fifteen regression functions are authored (some
parameterized); no tests were collected or executed. Cost totals are checked against
recorded estimates/usage, not independently verified provider bills.

## Selected journals and immutable resume proposals

The evidence trial now carries D1's canonical `SelectedCall` list,
`selection_journal_complete`, and explicit repeat identity. Ordered selected-call
count/hash/completeness, raw-wrapper and argument hashes, model/turn/provider parents,
and selection-to-server links are checked separately from the admitted server trace.
Seven or more pre-dispatch rejected selections can remain in evidence even though the
server dispatch cap is six. A capped/codec-rejected selection is not a server-policy
block. Missing capture is unknown, never an empty successful no-tool journal.

`BudgetedLiveTransport.last_selection_batch` is a read-only defensive snapshot with
`attempt_id`, `tool_calls`, and `tool_call_ids`. It resets at invocation and every
attempt, is populated only after raw provider bytes are privately journaled, and has
separate read-only `selection_batch_complete`. D1 ANDs that flag when using fallback
recovery. Wrapper objects are explicitly reconstructed; OpenAI argument strings and
Anthropic lexical input slices preserve their representations. No raw provider body
belongs in a public plan or report.

`plan_resume(edition, new_authority, receipts=(), *, expected_authority_sha256=None)`
returns a frozen `ResumePlan`. `ResumeAuthority` pins exact target-manifest JSON bytes,
the original index, candidate/revision, all source-to-target schedule slots, receipt
hashes and an extension reservation cap. The authority's canonical typed hash must
match an external approval pin. `ExtensionReceipt` approves an exact source row, target
slot and reuse/unstarted/explicit-successor action. `UsageReconciliation` separately
names the original attempt/cost hash, actual provider usage evidence, cost basis and
whether reconciliation has actually been applied with a ledger snapshot pin. Unknown
usage cannot become zero by omitting fields or starting a new controller.

All original rows, failures, source byte hashes, case/cell/model/repeat identities,
selection/observer parents and original cost bases remain in `retained_trials`.
Absent legacy repeat identity stays pending; it is not parsed from a trial ID. Source,
schema/scorer/corpus/price/settings drift forbids reuse. Semantic/model failures need
an explicitly approved successor experiment rather than an automatic favorable retry.
Mode/platform cannot change through resume. Reuse is not a new independent live sample
and has zero **new** reservation/charge; an old unknown charge remains explicitly
unknown. Proposal IDs are deterministic for crash-idempotent planning. No planner API
writes, dispatches, clears a hold, or publishes numbers. Receipt pins attest supplied
lineage, not the truth of the claimed usage or approval.

The pure wire preview is `transport.preview_request(payload, *, adapter_sha256)`.
It returns exact encoded HTTP body bytes, provider/model/settings and adapter revision
with an externally verified source pin. It never evaluates credentials/headers or
reads a source file. `encode_wire` is shared by preview, body hashing, token fit and
actual HTTP send. The approved token counter now receives those exact full-request
**bytes**, not an abstract request dict; D1's admission owns real tokenizer/source-pin
verification. Preview does not independently certify the caller-supplied adapter SHA.

## Resume projections and producer joins

`project_resume_plan(plan, *, expected_plan_id, public=True)` validates the immutable
plan hash, then emits only allowlisted fields. Public output hashes source/target
identifiers, counts retained failures and unknown charges separately, and includes no
raw approval JSON, request/selection content, oracle labels or receipt text. Private
output retains the typed proposal. Neither projection writes or publishes anything.

`validate_resume_lineage(parent, successor, plan, *, expected_plan_id)` explicitly
joins both verified editions. The successor's manifest bytes and full ordered schedule
must match the proposal. Originals retain byte-pinned failure rows and original cost
bases. A reused successor row carries `ReuseReference` pins to the parent index,
manifest, trial, raw row and outcome, and carries no copied attempt/selection/trace/
observer data. Parent outcome values may not change except the successor's row ID.
Reuse contributes zero new billing and zero independent live samples. Changed fixture,
catalog/treatment, source/schema/scorer/corpus/price settings cannot earn reuse credit.
Fresh rows cannot reuse original attempt/call/selection IDs. Standalone reading or
rescoring a reuse reference without the explicit parent join remains unknown.

Original unknown cost with no attributable attempt journal is separately pending,
not a free zero balance. Actual-usage receipts require provider token fields, usage
evidence and an applied ledger snapshot; dated-price reconciliations are checked against
the **original** approved price basis, including supported cache usage. Billed claims
need a separate billing-evidence pin. Missing original prices or unapplied receipts
cannot release a hold. These are pure planning checks; no API clears a ledger hold.

`verify_producer_bindings(edition, authority: ProducerAuthority, *,
expected_authority_sha256, catalog_documents, conformance_documents)` consumes explicit
public producer document bytes under externally selected expectations. It calls D5's
`catalog.artifacts.artifact_pins(value, raw=...)`, checks exact raw/schema/metadata/order/
qualified tool pins and the trial's catalog-content hash, then calls D6's
`conformance.evidence.verify_evidence` with expected probe/track/request/source/server
**and fixture payload** pins. It never discovers files, launches a probe or claims that
a generated narrative occurred. Missing required documents remain unknown.

D6 component/mock scope cannot earn actual memory/stdio/POSIX credit. Mixed observed
and unknown predicates retain the observed effect while denying full credit. This
adapter always returns `full_platform_credit=False`: complete supported-probe coverage
and independent platform/product acceptance remain outside a per-probe structural join.
Producer verification output is private; it does not publish artifact descriptions.

V3 construction receipt: fourteen owned Python sources parsed with stdlib AST and
passed direct whitespace inspection. Forty-five regression functions are present in
that checked source scope, including meaningful selected-cap, codec recovery, exact
wire preview/byte counter, immutable/crash-idempotent resume, stale/duplicate/wrong-mode,
unknown/unapplied cost, reuse-charge, projection and D5/D6 attribution cases. They were
not collected or run. Later concrete price/unknown-liability corrections were reparsed.
No application imports, provider calls, real evidence reads/rescore, SQLite opens,
backend/probe processes, installs, CI or hidden-corpus reads occurred.

Legacy trace hashes retain original JSON field presence instead of inserting new null
defaults before hashing; missing legacy selection capture remains explicitly unknown.

## Canonical public-result projection (v4)

`project_public_result(result, *, policy=None, fixture_map=None) -> PublicProjection`
is the single pure producer-side projection for D1. `.public` is the object supplied
unchanged to all JSON/CSV/Markdown/HTML renderers; `.private_diagnostics` contains
bounded alias links, private dropped-field paths and provenance counts and must remain
beside the original private evidence. No original object is mutated. This helper is
not a scorer, evidence authenticator, publisher or universal confidentiality guarantee.

Version `mcpsh-public-result-v1` defines explicit record/field/value allowlists for
outcomes, traces, selected calls, observations, semantic capture metadata, attempts,
usage/cost basis, manifests, summary/paired metrics, lint/pilot/acceptance views and
resume actions. Raw arguments/wrappers, result bodies, final/refusal text, semantic
predicates, oracle/family labels, poison descriptions/diffs, approval/credential/header
records and raw provider responses are never copied into public output. Known tool
names remain canonical; arbitrary tool/model/private IDs become stable namespace hash
aliases. Freeform failures become safe codes plus fingerprints, never exception text.

Every scheduled/error row and every supplied summary row remains in order, including
duplicates and malformed-row placeholders. Actual numeric values, booleans, unknown
utility/cost states, effects and original denominators are copied rather than scored
again. Absent/invalid numeric values stay unknown, never zero. A declared size limit
rejects the projection rather than publishing a truncated subset. This does not make
an internally inconsistent supplied summary valid; D1's evidence validation still owns
that check. No public projection grants product or empirical acceptance.

Strict projection is the default, including active held-out and retired phases.
`ProjectionPolicy(scope='qualified-development', qualification='public-development',
input_pins=(('task_hash', <exact-public-pin>),), identifiers=(IdentifierDisclosure(...),))`
can disclose only explicitly granted bounded labels after matching supplied development
manifest pins. The publisher must independently know those pins are public; equality
alone does not prove publication authority. Missing/mismatched qualification or a
held-out phase falls back to strict aliases. It never authorizes freeform response or
oracle text. Trusted fixture payloads use the same `protected_sentinels` and hardened
`policy.redact` semantics as the server. Missing/invalid supplied fixture semantics or
public-schema-key/enum conflicts fail closed, retaining the private edition rather
than rewriting observed/unknown categories into redaction markers.

Adversarial regression source is in `tests/evidence/test_public_projection.py`. AST and
direct whitespace inspection passed; no projection, renderer or regression was executed
under Dirty Mode. Known limits include deliberate numeric/enum producer-field covert
channels and inference from stable hashes; the source/input trust boundary still matters.

Scripted-final consumer contract for D5/D1: `ReplaySelector(calls=None,
*, episode=None, fixture_sha256=None, source_file_sha256=None)` uses exact episode fields
`schema_version: 1`, `episode_id`, `provenance: 'authored-development-script'`, and 1–3
`turns` with exactly `calls`, `final_text`, `stop_reason`. Explicit valid calls use raw
argument strings; malformed/extra/repeated/over-cap wrappers remain authored data.
`fixture_sha256` pins `typed_hash(episode)`, distinct from optional raw public package
`source_file_sha256`. `scripted_final_response` is the canonical record with no model
parent or raw provider-response hash; `last_scripted_response` carries a separately
labelled scripted-response digest and fixture provenance. Missing text is unavailable,
never an invented refusal. Implementation is in `adapters/replay.py`; see
`docs/LIVE-BOUNDARIES.md` for history and raw-call semantics. The canonical public
projection retains only scripted availability/provenance metadata and hashes.

v5 token-fit lineage consumes D1's actual private request/proof events. The pure
`capture_token_fit_bundle(journal_events, *, expectations)` adapter adds source
sequence positions, retains every proof event (including legacy/unattributed), and
never opens or writes a journal. `build_edition_payloads(..., token_fit_bundle=...)`
adds optional private `token-fit.json`. Its serialization preserves wire dictionary
order: actual request bytes are reproduced with the transport's sole `encode_wire`.
The sidecar participates in the edition's external byte pin, bounded reader and
closed schema; it is never a public artifact.

`EditionAuthority.token_fit_expectations_sha256` is an independently selected
`typed_hash` of the ordered expectations array, not a submitted proof's own hash.
Each expectation selects trial, turn, attempt, operation, checked-at, exact request
and proof hashes plus D5 verifier arguments (catalog artifact, exact closed approval
and its independent hash, provider/model/adapter source revision and hash). The
approval binds counter identity/source, settings, catalog, caps, expiry and maximum
proof age. Callers must authenticate those pins through authorized custody; merely
copying submitted values into an authority does not provide independent evidence.

`verify_token_fit_lineage(edition)` reuses D5's verifier without counting or building
proofs. Pre-send events must uniquely follow their prepared request and match the
actual attempt/operation/trial/turn. Missing/duplicate/legacy/unbound/retry evidence
stays unknown or invalid. Preflight entries remain diagnostic and cannot cover a
send. All reports retain `live_admission=False`, `billing_verified=False`: fit is
neither paid dispatch approval nor financial settlement. Inspection exposes missing
lineage; reproduction suppresses live numeric summaries for incomplete lineage.
The canonical public projection permits only safe status/hash/aliased parent data;
raw approval, catalog body, request/history and proof receipt remain private.
Authored regressions cover mutated/stale/expired/wrong-parent/missing/retry evidence;
none was executed in Dirty Mode.

Producer reconciliation v5 also retains `development-summary-draft`, closed
`development_summary` scheduled/supplied/missing/class groups, repeat and retention
diagnostics, and raw input SHA pins. `development_threshold_proposal` omits rationale
text and is explicitly labelled `unauthenticated-proposal`; it cannot carry an
independent approval. Replay rows retain `replay_role`, aliased episode ID and bounded
`scripted_responses` provenance/hash/availability only. Raw scripted final text stays
in the private edition. `replay_design` preserves baseline/control/diagnostic counts;
`observer_fault_status` and `observer_fault_unsupported` remain explicit.

Final v5 producer reconciliation: safe `token_fit_status` exactly follows D1's
`m5-token-fit-status-1` counters/hashes; no raw expectations or proof body. Root
`threshold_approval_status` follows D4 `project_threshold_status` status/hash/floor
fields while discarding reviewer/approval/rationale plaintext. Runtime authority
flags accept false only. Per-row platform scope is bound to edition scope and
model family is always aliased, never disclosed. Both fields survive rescore.
Development corpus pins follow actual public `corpus_pins` source, retaining fixed
public file hash slots and full case/episode counts. No corpus contents are read.

## Retrospective fit successor (v6)

`plan_fit_reverification(parent, *, authority, expected_authority_sha256,
expectations, parent_journal_bytes, receipt=None, expected_receipt_sha256=None)`
prepares in-memory candidate bytes. `FitReverificationAuthority` pins original
index/manifest/capture/journal/candidate/input/source/settings/prices, the complete
external expectation set, verifier source/candidate, new edition ID/revision and
independent retrospective selection provenance. Authentication defaults false.
It never changes the original edition or self-selects expectations from events.
Missing original capture/journal/authority or incomplete attempt selection stays
pending. Changed original bytes, source, candidate, settings or prices are rejected.
The caller supplies exact original journal bytes explicitly; no new reader or
journal writer is introduced.

The successor's `fit_parent` byte archive contains exact original index/artifact/
journal bytes in bounded base64 chunks. Active trial rows remain byte-identical;
observers/oracles remain byte-identical; only successor identity/revision and the
new externally selected expectation set change. Original manifest bytes remain
archived, with original execution source/cost/settings preserved in the active
manifest. Orphan requests, failed attempts, unknown costs and duplicate reuse rows
survive. New expectations must cover every original model/request attempt, never
just successes. Archive and index participate in existing edition bounds and pins.
Nested retrospective successors require separately granted scope.

A separate `FitReverificationReceipt` must externally pin plan ID, selected
authority, proposed successor index and verifier source, with authentication and
independent-selection confirmation false by default. Receipt metadata does not
itself authenticate custody; independently trusted callers must confirm it and
select the expected pin. The receipt resides in externally supplied successor
`EditionAuthority.fit_reverification_receipt` plus its independent typed SHA,
outside the indexed artifacts, avoiding circular index/receipt hashes. Supplying
this receipt on an original index is rejected. D1 separately authorizes the writer
and destination; `build_fit_reverification_payloads(plan)` only returns bytes after
receipt checks and full existing-reader validation. It never writes anything.

This is `RETROSPECTIVE-FIT-EVIDENCE-ONLY`, not a new experiment or pre-send approval.
It reuses D5's verifier through the existing fit lineage consumer, never a counter
or proof builder. Reports use `retrospective-fit-only`, no pre-send admission claim,
zero new attempts/charges, no dispatch authority and no billing/usage/product
acceptance claim. Existing costs and unresolved reservations stay unchanged. Actual
verifier execution source and external custody must be established by the caller;
metadata/source hashes alone cannot establish truthful execution. No helper,
parser, counter, proof, reader or test was executed during Dirty construction.

Safe canonical views additionally cover `acceptance-dossier-draft` /
`acceptance_dossier_status`, and `ledger-audit-draft` / `ledger_audit_status`.
The latter follows `accounting.report.project_ledger_audit_status(audit)`, a pure
status/count/hash/basis projection of the existing private audit. It performs no
financial arithmetic, publication or database calls. Original scheduled and unknown
counts remain; raw dossiers, authorities, DB metadata and corpus text stay private.
