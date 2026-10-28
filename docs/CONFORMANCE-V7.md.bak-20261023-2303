# V7 producer/consumer seam

D6 SOURCE contract for INT1, D1 and D7. Existing public request, run_conformance
signature, seven installed resource mappings and v1/v2/v3 JSON schemas are unchanged.
No expected pin is calculated as an approval. Registry additions prospectively
change the semantic manifest/source pins; previously measured editions stay frozen.

The six new trusted hook names are missing-source, binary-content,
unsupported-encoding, read-amplification, source-count-cap and custom-rule-count-cap.
The approved factory and exercise signatures are unchanged. Payload is absent or
empty; no external path, arbitrary fixture, command or replacement server is accepted.
Local sessions consume actual producer identity, before/after observations,
control_receipt, restoration_receipt, call, metrics and evidence_scope fields.
Missing producer/receipt is UNKNOWN or unavailable, never a synthetic pass.

Device-path is only opaque namespace rejection. Cursor controls use the real
handler, including an actually issued query-bound cursor. Input-frame-cap on a
direct handler measures raw arguments only and is component-diagnostic; the existing
stdio-input-frame exercises the full serialized transport. This deliberately leaves
the stronger local normative frame requirement pending instead of claiming equivalence.

Config caps are always component-diagnostic. Binary/encoding are POSIX-only;
nonlocal remains unavailable. Aggregate scans use the real broker metrics
aggregate_read_bytes/read_limit_bytes/completed_scans/requested_scans and the
producer's LIMIT_EXCEEDED receipt, without fabricating a public tool call.

NEXT same-child aliases control-stdio:<hook> use the existing private inherited
fixed-command channel on the exact owned stdio child. They are optional component
diagnostics because the hook call itself is not an MCP tools/call frame. Actual
stdio transport proofs continue through the existing protocol driver. No new reader,
schema version or resource is required by D1/D7. Additive result evidence metadata
producer_receipt retains the actual hook/control payload; infrastructure_failure
records only stage/type, and teardown records complete=false, owned target and
prior_status. Existing closed provenance documents are unchanged. A teardown
failure prevents credit while preserving an already observed FAIL.

Each probe creates a fresh reference/control; the receipt guard pins exact approval,
server/trial/fixture/PID, core session and broker epoch. Increasing hook sequence,
unique actual call IDs, matching raw-call/result hashes and before/after attribution
are required. Inherited envelope nonce/PID/command/sequence checks remain mandatory;
lost replies poison the channel rather than consuming a late reply for another call.
Cancellation retains actual frame/call IDs, exact JSON-RPC ID type and terminal
receipt. Incomplete cancellation is UNKNOWN. Teardown attempts remaining owned
handles after one close failure; no external child or fixture is targeted.

Dirty Mode construction only; no imports, tests, probes, runtime or exports run.

## C1 closed producer/consumer seam (D6, 2026-10-23)

D2 producer `server/conformance.py` + `broker/{__init__,posix,bounds}.py` reconciled
field-by-field against the v7 consumer (`conformance/{backend,core_bridge,stdio,
stdio_host,host_control,receipt_guard,runner}.py`). Factory and exercise signatures,
`verify_evidence_v3`, closed provenance v1/v2/v3 schemas and the seven resource mappings
are unchanged. Static source closure only; nothing imported or run.

| Hook | Tracks (normative) | Producer `evidence_scope` / `evidence_source` | Required receipt fields checked by consumer | Code |
|---|---|---|---|---|
| missing-source | filesystem-posix | actual-owned-reference / actual-owned-reference-conformance | `control_receipt.applied`, broker-dispatched captured `tail` call, `restoration_receipt.applied` | SOURCE_MISSING |
| binary-content | filesystem-posix (memory explicitly unavailable) | same | same | BINARY_CONTENT |
| unsupported-encoding | filesystem-posix (memory explicitly unavailable) | same | same | UNSUPPORTED_ENCODING |
| read-amplification | memory, posix | actual-owned-broker-budget / actual-owned-reference-conformance | `metrics.{aggregate_read_bytes,read_limit_bytes=8388608,completed_scans<requested_scans=3,requested_scan_bytes>limit}`, `validation_exception`, `restored` (memory) or `restoration_receipt.applied` (POSIX) | LIMIT_EXCEEDED |
| source-count-cap | memory, posix | component-diagnostic / actual-production-config-component | `control_receipt.attempts` AccessPolicy 100 accepted + 101 ValueError; `metrics.policy_validation_maximum=100`, `attempted_configured_sources=101`, `configured_sources<=100`; state unchanged | CONFIG_INVALID |
| custom-rule-count-cap | memory, posix | component-diagnostic / actual-production-config-component | redact-configuration 32 accepted + 33 ValueError; `metrics.validation_maximum=32`, `attempted_custom_rules=33`, `custom_rules<=32`; state unchanged | CONFIG_INVALID |

Common to all six: `ReceiptGuard` binds approval_id, server_instance_id, trial_id,
fixture_id, fixture_payload_sha256 and child_pid to the session that opened the
control, plus increasing `sequence`, fixed conformance_session_id/broker_pid/broker_epoch
and same-epoch before/after attribution. The consumer accepts only the exact per-hook
`evidence_scope` above (`receipt_guard.SCOPES`); a receipt from any other scope yields
UNKNOWN and is never relabelled. Config caps and every `control-stdio:<hook>` alias stay
component-diagnostic in the runner and never receive actual-platform credit.

Mismatches fixed in C1:

1. `stdio_host.py` reported `fixture_id = fixture_ref` (`public-conformance-v1`) while the
   producer attributes `reference.fixture_id` (broker epoch for memory). Every
   `control-stdio:<hook>` alias, and `_same_child_receipt` in the stdio cancellation and
   concurrency controls, would always have failed identity and become UNKNOWN. The host
   now reports `reference.fixture_id`. This changes the stdio provenance session
   `fixture_id` value only, not its shape.
2. Source-pin closure: the `server` pin now also digests `policy/__init__.py`
   (AccessPolicy/redact caps used by the config-cap receipts) and `catalog/schemas.py`
   (runtime validation of the stimulus call). `source_pins()` refuses to compute if any
   required producer member is missing (`broker/bounds.py`, `server/conformance.py`,
   etc.; see `evidence.REQUIRED_CLOSURE_MEMBERS`). The pin key set stays the closed five;
   values change prospectively; no measured edition exists.
3. The consumer previously ignored the producer's reported maxima, attempted counts,
   stimulus size and broker dispatch. It now requires them, against literal normative
   maxima, so drift in production constants is caught instead of silently passing.

Memory broker still implements a `missing-source` stimulus; it is not consumed, because the
normative inventory maps missing-source to POSIX only. Regressions:
`tests/conformance/test_producer_closure_c1.py` (authored, not run).

read-amplification additionally requires `refused_at_budget_boundary`: completed scans
equal `8388608 // per-scan bytes` and aggregate bytes equal completed scans times
per-scan bytes, so an earlier deadline or other LIMIT_EXCEEDED cannot pass.

Open (not closed by C1, needs an INT decision): read-amplification has no public call
packet, so its provenance `frames` are empty and `verify_evidence` reports
`frames.missing-or-cap`/`frames.response-attribution`. A genuine pass is therefore
status PASS but never creditable, and the normative `read-amplification` requirement on
memory/POSIX cannot be met as written. Options: a versioned frame rule for broker-control
receipts, or a distinct control-receipt evidence channel. C1 does not fabricate frames.
