# Server conformance source

Built under Dirty Mode; no conformance, tests, backend, SDK, syscall or process has
run. This implements the library behind future `mcpsh server-check`; D1 owns CLI
wiring. Memory cannot satisfy filesystem proof. No measured results are included.

## Frozen consumer API v1

```python
from mcpsh.conformance import ConformanceRequest, run_conformance

request = ConformanceRequest(
    tracks=("synthetic-memory",),
    runtime_authorized=False,
    disposable_authorized=False,
    approval_id="",
    posix_fixture_parent=None,
    probe_ids=(),
    timeout_seconds=5.0,
)
# Future approved activation only; these defaults deliberately reject invocation.
# report = run_conformance(request, backend_factory=None)
# json_payload = report.to_dict()
```

Request tracks: synthetic-memory, filesystem-posix, stdio. `probe_ids=()` selects
the full suite. A nonempty selection is diagnostic and cannot earn a full-suite
pass unless it selects all definitions. CLI must expose explicit runtime/disposable
approval and approval ID; `--mode` alone cannot authorize conformance. Invalid
request or missing activation raises ValueError before backend creation. No SDK
or application import occurs merely by importing this package.

Projection: schema_version=1, kind=conformance, approval_id, full_suite,
selected_probe_ids, platforms, results, product_acceptance=pending, limitations.
Per platform: verdict=blocked|pending|passed; counts for pass/fail/unknown/
unavailable/unsupported; filesystem_proof true only for a passing complete POSIX
suite. Each result has probe_id, track, status, required, reason and bounded
hash-based evidence. Raw fixture/response/error strings are not public evidence.

## Current controls

Fresh local fixture per probe; configured-source and export denial, strict duplicate/
nonfinite/boolean/extra-field validation before broker I/O, allowed-read negative,
protected read/wire/export positives, trusted relative clock, built-in/custom
redaction, forged cursor, unknown source, line/range/input-frame caps and opaque
path-ID controls. Observer failure controls execute the observer component against
explicit fault-channel copies of a healthy broker snapshot. They are distinct from
actual IPC/process-failure proof. Runtime source hooks for deep read/physical-line/
deadline/frame and POSIX no-follow/rename/source-change cases are defined in
policy/conformance/README.md; unavailable hooks never pass.

## Later validation

After authorized Dirty Mode closure, pin dependencies/SDK and run authored
regressions, then activate disposable memory/POSIX/stdio tracks. Confirm actual
IPC isolation, platform semantics, every required hook and complete frames. A
supported failure blocks that platform even when other checks pass. Hidden-corpus
retirement/adjudication and benchmark product acceptance are separate work.

Protocol references for the next stdio source: official MCP tools specification
https://modelcontextprotocol.io/specification/2025-11-25/server/tools and official
Python SDK https://github.com/modelcontextprotocol/python-sdk (read 2026-10-23).
SDK compatibility remains provisional until an exact lock and real smoke pass.

## Stdio and capability package

`capability_report()` is a pure source declaration with execution=not-run. It is
available independently of activation. Runtime reports use actual frames only.
The stdio adapter launches only `python -m mcpsh.conformance.stdio_host`, with a
small OS bootstrap environment and the package source path. It accepts no command,
shell, provider environment, URL or arbitrary server target. All imports of server
and SDK functionality are lazy. Missing SDK modules produce unavailable; an
unrecognized negotiated protocol version also produces unavailable. The authored
probe version is explicitly 2025-11-25, not a claim about an installed SDK lock.

The fixed child receives only a public synthetic fixture. Exact UTF-8 newline
frames have bounded reads, write/response deadlines, a maximum 64-frame queue and
hash/byte evidence. Each probe starts a separate child and closes only its own
Popen handle. Raw response payloads are excluded from the public report.

The stdio track now defines catalog/schema, successful result, policy execution
error, unknown-method protocol error, escaping, duplicate/nonfinite input, input
frame limit and output amplification checks. A dead/disconnected/unresponsive child
is unknown, not a fabricated structured rejection. The text and structured result
must agree, and `isError` must match the M5 execution status.

Cancellation and concurrency source is in protocol_controls.py. An injected D2
control channel must bind to the same disposable child and implement hold_execution,
release_execution, wait_for_occupancy(active, queued, timeout),
wait_for_cancellation(request_id, timeout), and observe. The harness first witnesses
one in-flight call before cancelling, or four active plus sixteen queued before
sending the overflow call. It checks independent effects after release. Genuine
same-reference D2 instrumentation is required before those rows become available.
The default inherited channel is authored in v3 below; genuine D2 core instrumentation
remains required before those rows become available. Generic quick parallel calls cannot prove occupancy; a post-completion cancellation
cannot prove cancellation. Source orchestration is built; instrumentation is a
named D2 reconciliation seam, not an assumed successful integration.

Official references, read 2026-10-23:

- [MCP lifecycle](https://modelcontextprotocol.io/specification/2025-11-25/basic/lifecycle)
- [MCP stdio transport](https://modelcontextprotocol.io/specification/2025-11-25/basic/transports)
- [MCP cancellation](https://modelcontextprotocol.io/specification/2025-11-25/basic/utilities/cancellation)

Dirty Mode construction validation: the current package's eight Python files passed
stdlib AST parsing, with no application imports or test/probe execution. Follow-up
protocol/regression source is checked statically at handoff. No measured conformance,
filesystem proof, installed SDK compatibility or product acceptance is claimed.

## v3 same-child control source

The bundled host now uses two inherited anonymous pipes beside its actual stdio
transport. Parent-generated handles, nonce and child PID bind a fixed, closed
command set to that owned Popen child. No listener, arbitrary PID, command, remote
target or caller-selected control endpoint exists. Request/reply limits, monotonic
sequences and deadlines reject stale or mismatched replies. Windows uses an explicit
inherited handle list; POSIX uses pass_fds. These platform mechanisms are authored,
not executed. Parent cleanup terminates/waits only for its own Popen child and
closes the inherited control handles; disposable POSIX fixture roots remain retained.

D2 producer bridge used by core_bridge.py is the actual public factory
`mcpsh.server.conformance.create_conformance_session(reference,
runtime_authorized=..., disposable_authorized=..., approval_id=...)`. It returns
a control on that exact reference, exposing the methods documented above;
`serve_stdio(reference=reference, conformance_session=attached_session)` serves
that same reference with its exact attached D2 session. The host never
substitutes a separately constructed server for occupancy or observation. Identity
returns actual host PID, reference trial ID, fixture digest and explicit control/
injection capability flags. Local memory/POSIX sessions prefer the genuine D2
session.exercise hook. Absence of either producer API remains unavailable. This
is an explicitly named source reconciliation seam, not assumed interoperability.
The actual factory and core hook source have been read and adapted. Its
ConformanceHookUnavailable is mapped to unavailable. The producer's stdio
same-reference injection/cancellation forwarding source has also been read and
reconciled, including its exact attached-session argument. The
core's server instance ID and trial ID are retained as separate identities.

## v3 evidence projection and D7 verifier

The D1 request signature and top-level report keys are unchanged. Each successful
probe collection adds `evidence.provenance` and `evidence.verification`. Closed JSON
schema: `policy/conformance/evidence-v1.schema.json`. Python typed frame/session/
observation bindings and the verifier live in conformance/evidence.py.

```python
# Pure verification API; the expected selection/pins come from the scope owner.
# verify_evidence(document,
#     expected_probe_id=...,
#     expected_track=...,
#     expected_request_sha256=...,
#     expected_source_pins=...,
#     expected_server_instance_id=...,
#     expected_fixture_payload_sha256=...)
```

The optional fixture-pin keyword preserves the initial callable shape; omitting it
does not earn credit. The result has valid, creditable, violations, scope and
predicates. Validity checks structure and identity; creditability means the evidence
can support that track's probe evaluation, not that a protocol check succeeded or
that a product/release was accepted. Source pins have exactly server/broker/observer/
stdio/conformance keys and bind bounded public source bytes at activation and probe
completion. server/broker/observer/conformance pins cover each directory's bounded
Python source closure, including admission/control modules; stdio pins its exact
adapter source. The caller supplies expected pins externally; record self-hashes alone
do not authorize a different selection or prove an observation narrative true.

Records bind each actual request/reply byte hash, byte count, sequence and response
expectation, plus server/fixture/platform/child identity and broker trial/epoch/
sequence/reset/observer version. Omitted required replies, stale attribution,
changed source pins, extra raw fields and incomplete/unknown observations cannot
earn actual proof. Notifications and proven cancellation have explicit reply
expectations. Component fault-channel controls and injected mock factories remain
diagnostics. Known observed effects survive alongside unknown predicates.

Platform aggregation accounts for the exact required probe IDs for that track;
missing or duplicate rows cannot be hidden by a full_suite flag. All required rows
must pass AND have creditable actual evidence. A supported failure still blocks;
missing instrumentation, unknowns, partial selection and diagnostics leave pending.
Memory and stdio remain separate from POSIX filesystem proof.

This is a versioned M5 project evaluator. It does not claim equivalence to the
portable evidence-gate normalized schema, independent review, execution or product
acceptance. Dirty Mode prohibits running either the authored regressions or a case
generator; validation here is focused source inspection and syntax/JSON parsing.

## v4 public semantic controls and required-case manifest

Fresh public source is `fixtures/conformance/semantics-v1.json`, version
m5-public-semantics-v1. It contains 16 cases and no retired/private benchmark data.
The fixed required IDs are a separate scope authority, so deleting a difficult
case does not reduce the denominator. Each case has a bounded public source fixture,
actual tool/argument bytes and explicit expected matches/groups/coverage or refusal.
Deterministic expansions cover 257 two-byte pattern characters and 500 physical
source lines without an unbounded fixture generator.

Actual memory and POSIX ReferenceServer calls and same-child stdio requests drive
the semantic probes. The stdio host accepts only a fixed public case ID; it never
loads a caller-selected fixture path. Pure matching/parsing output cannot satisfy
those probes. The cases distinguish literal dot/reserved punctuation/backslashes,
case sensitivity, anchors/alternatives, invalid grammar before broker I/O, UTF-8
byte caps, structured/plain codes, warning normalization, inclusive time bounds,
UNKNOWN bins/conflicting fields and bounded scan counts. Actual server parser/
grammar versions are checked in successful response data. Correct UNKNOWN reporting
may pass its diagnostic case while its unknown semantic coverage remains uncreditable
for full platform proof.

Consumer APIs, all source-only here:

- `semantics.semantic_cases(raw: bytes)` is a pure bounded parser returning immutable
  public SemanticCase values. `evaluate_semantic(case_id, result, observation)`
  evaluates actual handler data against public gold; no provider/oracle is involved.
- `manifest.semantic_manifest(raw, grammar_source_sha256=..., parser_source_sha256=...)`
  is pure. Its closed manifest binds exact required probe IDs per track, capability
  scope, grammar/parser/case-source versions, source-byte hashes and per-case call,
  raw-argument, fixture-line and expectation hashes. `verify_semantic_manifest`
  requires an externally supplied expected_manifest_sha256. Self-updating a digest
  cannot approve an omitted required ID or changed version.
- `evidence_v2.verify_evidence_v2(document, semantic_manifest=...,
  expected_manifest_sha256=..., **v1_selection)` first validates every v2 field,
  then checks the exact v1 subset with every unchanged external request/source/
  server/fixture pin. Closed schemas are evidence-v2.schema.json and
  required-cases-v1.schema.json in policy/conformance/. V1 verifier/schema remain
  available and unchanged. V2 adds semantic authority, actual raw-call, result and
  coverage hashes; mismatched arguments, wrong versions, missing cases and unknown
  parse coverage cannot finish actual proof. Component/mock restrictions and mixed
  observed/unknown effects survive v2 translation.

Backward-compatible D1 seam: `run_conformance(request, backend_factory=None,
expected_semantic_manifest_sha256=None)` adds an optional keyword. ConformanceRequest
is unchanged. Without the externally approved manifest pin, v2 evidence remains
uncreditable and platforms pending. A generated manifest never authorizes itself.
The existing report root keys remain; optional `required_case_manifest` exposes the
public authority. ConformanceReport adds a final default-None semantic_manifest
field, preserving earlier positional constructors. Per-probe provenance explicitly
uses schema_version=2 after this source change.

Runtime source capture reads bounded grammar/parser bytes and extracts their version
constants by AST, without importing those application modules for manifest creation.
The source checkout reads the canonical fixtures file; an installed wheel may read
the generated package-data destination `mcpsh/conformance/data/semantics-v1.json`.
D1 owns wheel configuration and must include the canonical fixture directory there.
Missing public fixture data is unavailable, not an empty successful suite. No wheel,
dependency install, test, probe, backend or process was run during this authoring.

Frozen D2 bridge confirmation: the actual validated request approval flags/ID reach
create_conformance_session; the bundled host passes that session's exact underlying
control to serve_stdio alongside the same reference. Cancellation preserves actual
JSON-RPC integer OR string IDs, rejects bool and forwards request_id/payload without
coercion. No approval-free reference shortcut or replacement server is used.
