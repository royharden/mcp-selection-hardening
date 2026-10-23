# Live dispatch boundaries

Source constructed under Dirty Mode. Regression tests are authored, not executed;
SQLite durability, providers, real tokenizers and the joined runner remain unverified.

The runner calls `BudgetedLiveTransport.assert_dispatch_allowed() -> None` before
each model turn. It raises `LiveTransportError` for stopped admission. Controller
approval must contain the unchanged top-level receipt `expires_at` with timezone.
The controller repeats expiry, authorization, provider/model, endpoint, price,
full-wire token and request-cap checks after journaling and before **each send**,
including a transient retry. Tokenizer version correctness still requires activation
verification; the declared version is not a measurement.

`CostLedger` records prepared attempts separately from send intents. Only the exact
current reservation and its unsent prepared attempt are excluded from prior-liability
checks. Unknown costs, abandoned other reservations, cancellation, known overruns and
durable stop reasons prevent new dispatch. A send intent consumes the request cap
durably before transport entry; a crash in that gap remains conservative. The scope
is the approved per-trial `budget_reservation_id`, shared across model turns.

There is at most one explicit transient retry, counted as another request. It requires
attributable returned usage and a known dated-price estimate for attempt one. Timeout,
missing usage and ordinary HTTP errors do not imply zero billing and cannot authorize
retry. Price estimates are not provider billing receipts. Identity drift, truncation,
semantic errors and journal failures do not permit semantic retries. Unknown response
usage preserves the received response but latches a durable stop before a later turn.

Holds/stops have no automatic clear API. Later authorized reconciliation must preserve
attempt history and prove resolution; starting another controller is not reconciliation.
The schema additions preserve existing operation/attempt rows. Old `sent` NULL-cost
rows remain blocking. Counter rows cover sends admitted by this source version only;
a preexisting ledger must not be treated as complete historical request-count evidence.

Construction receipt (D7, 2026-10-23): focused source/logic inspection and five explicit
stdlib AST parses passed, then the concrete transient-overrun retry predicate found
in inspection was tightened and reparsed. Scoped `git diff --check` passed (Git reported
only its existing LF/CRLF conversion warnings). Regression source is in
`tests/adapters/test_dispatch_boundaries.py` and `tests/accounting/test_dispatch_holds.py`.
No tests, application imports, SQLite opens or provider requests were executed.

## Explicit authored replay episodes

`ReplaySelector(calls=None, *, episode=None, fixture_sha256=None,
source_file_sha256=None)` supports the existing valid embedded-call constructor and
an explicit scripted episode. It performs no file read, provider request, broker call,
model judgment or fixture execution. Construct a fresh selector per trial.

Episode v1 has exactly:

```json
{
  "schema_version": 1,
  "episode_id": "public-development-case-id",
  "provenance": "authored-development-script",
  "turns": [
    {"calls": [], "final_text": "Explicit authored fixture text.", "stop_reason": "stop"}
  ]
}
```

There are one to three turns. Each has exactly `calls`, `final_text`, `stop_reason`.
Valid explicit call wrappers use `name` and raw argument strings. Invalid JSON strings,
extra wrapper fields, malformed names, repeats and more than six selected calls remain
in their original order for the runner's pre-cap journal; they are not repaired,
deduplicated, policy-blocked or executed by the selector. The outer authored episode
remains bounded to 4 MiB JSON and 65,536 selected wrappers. Legacy valid dict arguments
retain their JSON-string convenience, and name-only legacy calls default to `{}`.

`final_text` is explicit UTF-8 fixture text or null. Null remains unavailable, even if
the task asks for refusal or the stop reason is `refusal`. Empty authored text remains
available empty text. Stop reasons are `stop`, `end_turn`, `stop_sequence`, `refusal`,
`length`, `max_tokens`, `content_filter`, or null. A complete final requires explicit
text, no selected calls and a terminal stop/refusal marker. No-call turns must be last;
later unreachable answers are rejected. Missing or exhausted scripts never synthesize
an answer, refusal or clarification from the task, oracle or prior model output.

The next episode turn requires exactly the accumulated ordered tool history, with
each `role='tool'` entry's `call` matching the prior authored wrapper. Missing/reordered
history or another task identity rejects advancement. The selector does not inspect
task requests/oracles, tool result text, or catalog descriptions to produce answers.
Runner-owned selection/call/deadline caps and admission remain unchanged.

`scripted_fixture_sha256` is `typed_hash(episode)`. An explicitly supplied
`fixture_sha256` must match it. `source_file_sha256` is a distinct caller-declared raw
PUBLIC package pin; D1's loader owns checking the package bytes and extracting the
selected episode. Neither pin implies live execution or independent correctness.

Read-only defensive snapshots:

- `scripted_final_response`: canonical `FinalAssistantResponse`, with
  `model_attempt_id=None` and `raw_response_hash=None`. Authored refusal text is present
  only when explicitly supplied with the refusal marker.
- `last_scripted_response`: private scripted provenance, authored selected calls,
  final capture, episode/turn IDs, fixture/package pins and separately labelled
  `scripted_response_sha256`. It has no provider/model/request/attempt IDs, usage or
  billed-cost fields.

D1 alone integrates these properties into the runner/demo/cases loader. The record's
scripted digest is not a provider raw-response hash; no `ModelAttempt` is fabricated.
These selectors remain replay/control provenance and cannot count as either live arm.
D5 owns public episode files/corpus data; this module contains no private-oracle loader.
All report views must use the canonical public-result projector, which omits raw final
text, raw wrappers and semantic predicate bodies.

V4 construction evidence: replay/projection source and meaningful regression source
passed stdlib AST and direct whitespace checks. Regression functions were authored,
not collected or run. No source import, selector/projection/renderer execution,
provider/DB/backend/fixture process, dependency install or runtime validation occurred.
