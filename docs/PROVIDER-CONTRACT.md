# Provider catalog parity and full-wire evidence

Construction source only. No test, import, codec, parser, tokenizer, provider or
CLI has been executed for this work. Source structural parity cannot establish
provider/model interoperability or measured golden-test success. D1 owns the
manifest, CLI and sole numeric result publisher; D7 owns all adapter codecs,
preview/send paths and credential/HTTP boundaries.

## Catalog parity API v1

`mcpsh.catalog.provider_contract.audit_provider_catalog(artifact, encoded_body,
provider=..., model_id=..., adapter_revision=..., adapter_sha256=...)` consumes
the canonical versioned artifact and **exact actual encoded bytes**, never an
abstract task/tool request. It builds no provider requests and calls no callback.
The adapter hash must be a full lowercase SHA256; revision/model must be explicit.
Missing identity or bytes yields unavailable. Unknown dialect/settings,
streaming or unmodeled strict-schema mode yields unsupported; mismatched/malformed
catalog/schema/body yields invalid. None is silently coerced to valid.

Supported source dialects are the current OpenAI Chat function wrapper
(`parameters`, explicit strict=false) and Anthropic Messages tool wrapper
(`input_schema`). All nine names, their order, descriptions and typed executable
schemas must exactly match the canonical artifact. The comparison includes
required fields, enums, numeric bounds, nullable unions, defaults and
additionalProperties. Advisory MCP annotations are absent from both wire codecs;
this omission is disclosed and cannot change server access policy. Future wire
settings/dialects require a versioned contract change rather than implicit support.

Return fields include version, scope, status, reasons, exact provider/model/adapter
identity, raw/typed full-body hashes, settings hash, catalog pins and tool count.
`status=valid` means the **catalog projection** is structurally faithful only;
message semantics, endpoint acceptance and returned model behavior are unverified.
Unknown fields are not accepted as a new provider capability. Raw body bytes are
bounded to 4 MiB and strictly parsed with duplicate-key/nonfinite/Unicode checks.

`audit_call_projection(expected_calls, actual_calls)` is a separate pure golden
comparator for **already decoded** ordered `{name, arguments: object}` records.
Use the real response codec to decode before comparing; this helper is not a
response decoder or tool executor. Typed JSON comparison retains integer/string/
boolean/null/float distinctions, order, repeated and extra calls. It reports
counts/digests and validity without suppressing any call. Exact expected repeated
calls remain repeated, rather than being forbidden merely for equal arguments.

## Producer and test integration

D7's implemented `ProviderTransport.preview_request(payload,
adapter_sha256=externally_verified_hash)` supplies `encoded_body`, provider,
model_id, endpoint_url, settings, adapter_revision, adapter_sha256 and
source_pin_basis. It does not call headers, credentials, HTTP, send or source-file
reads. Revision is `mcpsh-http-tools-v2`; `encode_wire` is shared with actual send,
body_hash and controller byte-token counting. The supplied hash is explicitly
externally verified, not self-attested by preview. No competing encoder exists
in the audit or golden-test paths.

Golden test source now uses the actual pure `preview_request` API directly;
the earlier test-only serialization seam has been removed. This is not executed
golden evidence. Meaningful regressions cover schema omission/duplicates, tool ordering,
malformed transport, exact argument types, extra/repeated calls and unavailable
identities. Tests are authored only; no live comparative arm is accepted here.

CURRENT static receipt, D5 2026-10-23: the audit and golden-test modules parsed
with `ast.parse`; six regression functions authored, none executed. Focused
source review traced exact projection equality, all nine schemas, no type
coercion, duplicate preservation and unavailable/unsupported outcomes. D7 pure
preview source has since been reconciled in the tests, with no payload actually
encoded or tokenized as validation.

## Full-wire token-fit API v1

`mcpsh.catalog.token_fit.build_token_fit_proof(encoded_body, artifact=...,
provider=..., model_id=..., adapter_revision=..., adapter_sha256=..., approval=...,
expected_approval_sha256=..., tokenizer=..., trial_id=..., turn_id=..., at_time=...)`
consumes the **exact same bytes** as preview/send, including system/user content,
all nine tools, settings, history and tool replies. It never packs, truncates,
summarizes or rebuilds a request. The injected approved counter must include all
provider framing/overhead, not merely count JSON characters or an abstract task.
There is no built-in tokenizer, model guess, SDK import or approximate fallback.

`approval` has exactly these fields:

* `version: m5-token-fit-approval-1`, `approval_id`, `authorized: true`;
* `provider`, `model_id`, `adapter_revision`, `adapter_sha256`;
* `tokenizer_id`, `tokenizer_sha256`,
  `counter_scope: full-provider-request-including-overhead`;
* `input_token_cap`, `output_token_cap`, `context_window_cap`;
* `settings_sha256`, `catalog_typed_sha256`;
* `expires_at`, `max_proof_age_seconds` (1..300).

The expected approval hash is supplied by the external authorized operator,
not read from the receipt as its own authority. Identity binds the selected
adapter/model, exact catalog artifact and wire settings. Cap integers exclude
booleans and are positive bounded signed-64-bit values. Explicit timezone-bearing
timestamps are required; the controller must supply its actual current time.
This receipt approves counting parameters only; it does not grant network/spend.

The operator injects the pure callable corresponding to the approved tokenizer
identity/hash. That hash must identify its frozen implementation **and effective
provider-framing/configuration**, not just a generic library name. This is an
external trust boundary: supplying a hash label does not introspect or sandbox
an arbitrary Python callable. The audit module never invokes it during static
construction and never obtains a real provider tokenizer itself.

The future callable has the exact controller contract `Callable[[bytes], int]`:
it receives the preview's full encoded bytes unchanged and returns an exact
positive integer count. It does not return an abstract-request dictionary or an
estimate. The proof binds that count to raw_body_sha256, tokenizer ID/hash, model
and exact scope from the externally pinned approval, recording a counter receipt.
The approved operator owns supplying the actual matching implementation; those
identity labels are not independently verified by introspection. A zero count for this nonempty nine-tool request,
boolean/negative/oversized count, partial/estimated scope, missing callback or
counter exception stays **unknown** with no input count. Invalid approval or wire
bindings stay invalid. No error/credential text is copied into proof reasons.

Proofs contain version/scope, status (`fits`, `exceeds`, `unknown`, `invalid`),
reasons, creation time, bindings, exact counter receipt/count and typed proof
digest. Bindings include raw/typed body hashes/byte count, settings/catalog pins,
adapter/model/tokenizer identities, approval pin, trial/turn and complete
system/history hash. A fit requires both the input cap and input plus reserved
output within the context window. `provider_billing_tokens: unverified` and
`live_admission: false` are always retained: this is one source predicate, not
evidence of billing, interoperability or live authorization.

`verify_token_fit_proof(proof, encoded_body, ...same selected pins...,
expected_proof_sha256=..., at_time=...)` rebinds a proof without tokenizing again.
The expected proof hash must come from the trusted fresh-counter/journal path,
never from an untrusted submitted proof as its own verification authority.
It checks exact body/history/turn/settings/model/catalog/tokenizer/approval,
receipt identity/count, expiry and proof age. Changed history or a new turn
requires a fresh proof; unknown/unpinned/stale proofs cannot provide a fit.
Proof and approval typed representations are each bounded to 32 KiB; parse any
external JSON with the existing strict duplicate-key/nonfinite parser first.

D7 owns per-send/retry preview and consumption; D4 may use explicit status,
input_tokens and bound identity/cap fields in calibration source. D1 owns manifest
and CLI loading and the sole numeric publisher. A real approved counter and
later shared integration remain required; synthetic test doubles are never a
provider-fit measurement. Current source tests cover missing/invalid counters,
changed history/turn, unpinned approval/proof, input-plus-output limits and age.

The audit's `settings_sha256` hashes all top-level wire fields except messages,
tools and system, including the model. It is derived from the actual encoded
body. Use this audit output when constructing the dedicated token-fit approval;
do not substitute a hash of preview.settings, whose producer projection omits
model. Entire system/history/tools remain bound and counted through full-body
hashes, the history hash, catalog pin and exact byte-counter input.

NEXT static receipt, D5 2026-10-23: token-fit source and both reconciled test
modules parsed with `ast.parse` after adopting D7 pure preview and its unchanged
`Callable[[bytes], int]` seam. Six token-fit regression functions are authored;
with the six wire-catalog functions this package contains 12 new test functions,
zero executed. Manual tracing checked external approval/proof pins, unchanged
byte input, unknown counter paths, bounded counts, context reservation and
body/history/turn/time reuse rejection. SHA256 inspection confirmed canonical
schemas and the original public lint labels/bypasses remain unchanged. No import,
preview/encoder/counter call, tokenization, CLI or provider execution occurred.
Source parity/fit predicates are complete for construction; actual counter
availability, calibration, per-send controller integration and real model
interoperability remain deferred to their owners and later runtime validation.
