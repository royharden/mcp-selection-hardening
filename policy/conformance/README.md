# Conformance activation and capabilities

Conformance source is development-only and has not run. Explicit runtime and
disposable-fixture approval plus a nonempty approval ID are mandatory. Dirty Mode
does not authorize invocation. No paid model, network endpoint or external account
is part of conformance.

The fixed public fixture contains app/worker/protected IDs and two outboxes.
It is distinct from evaluation custody and never opens corpus packages. Only the
operator's explicitly supplied Linux-native fixture parent is used for POSIX;
each probe creates a UUID child with exclusive creation. Created roots are retained
for later inspection/disposition, never broadly deleted or reused.

Required checks with unavailable hooks remain unavailable. Unsupported Linux
capabilities remain unsupported. Unknown observations remain unknown. Any supported
required failure blocks its platform; missing evidence keeps it pending. Component
observer fault-channel controls are labeled and do not establish actual broker death
or filesystem conformance.

Optional D2 factory contract: `(request, track, probe) -> session`, with `call(tool,
raw_arguments) -> {event, result, wire_bytes}`, `observe() -> observer record`,
`exercise(hook) -> attributed raw evidence`, and `close()`. Boundary hook results
contain `evidence_source`, `error_code`, `outside_effect=none|observed|unknown`, and
`observation` with independent completeness. Observer fault results contain a healthy
`before` and damaged `after`. A caller-supplied passed flag is never evaluated.

Hooks needed for full platform proof: read-byte-cap, physical-line-cap, deadline,
frame-amplification, posix-symlink, posix-rename, posix-nonlocal, posix-source-change.
Each must use a trusted disposable boundary; no probe may target an arbitrary host
path. Their default absence is reported explicitly, rather than patched into a pass.

Concrete stimuli and per-scenario refusal codes are in
`src/mcpsh/conformance/boundary_controls.py`. A D2 driver may implement
`exercise_scenario(BoundaryScenario)` and inject it as LocalSession's boundary_driver.
It must apply the documented mutation timing and return actual independent evidence.
A wrong error code cannot pass a different boundary test.

Stdio activation launches only the bundled conformance host. Cancellation and
concurrency require a real independent barrier/control channel bound to that child;
the exact method contract and source orchestration are in docs/CONFORMANCE.md and
protocol_controls.py. The capability report explicitly lists missing instrumentation
and never calls a source declaration runtime detection. Required unavailable rows
keep a platform pending. Test files are authored regressions and have not run.

v3: the default stdio session now owns a bounded inherited anonymous-pipe channel
to its own bundled child. Host identity and every response bind PID, nonce, command
and sequence. D2 core session plus same-reference serve_stdio injection are required;
missing producer capabilities are not simulated. The exact bridge and source-only
limitations are documented in docs/CONFORMANCE.md.

Closed per-probe schema: evidence-v1.schema.json. D7 should use the pure
verify_evidence API with externally supplied probe/track/request/source/server/fixture
pins. JSON Schema alone does not check lineage joins, digest agreement, reply
omission, sequencing or actual credit. Source and record hashes establish identity,
not truth or product acceptance. Component/mock scopes cannot satisfy required
actual track proof. Report aggregation requires the exact expected probe set.

v4 public semantic source is fixtures/conformance/semantics-v1.json. Required
case/probe authority uses required-cases-v1.schema.json and explicit grammar/parser/
case-source pins. The pure manifest verifier needs its externally approved digest.
Evidence-v2.schema.json extends the unchanged v1 contract with closed semantic
bindings; v2 verification preserves all v1 external pin and attribution checks.
Unknown parsing coverage and pure/component diagnostics cannot complete actual
platform proof. Correct UNKNOWN-bin output remains useful diagnostic behavior.

D1 integration adds only an optional expected_semantic_manifest_sha256 keyword to
run_conformance and optional required_case_manifest report data. Missing external
authority stays pending. Source checkout fixtures need no packaging action now;
later wheel source configuration must include that canonical directory as
mcpsh/conformance/data. No generated result or measured conformance is bundled.
