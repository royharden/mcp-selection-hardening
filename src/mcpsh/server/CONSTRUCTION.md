# Synthetic server construction boundary

This is an M5-owned synthetic-memory fallback. It implements the nine selected
request shapes, policy variants, bounded fixture operations, independent broker
read/write counters and runner-captured wire observation. No S1 implementation
or ErrorCode enum is vendored. The first five request shapes were transcribed
from the supplied S1 snapshot at `0abc5d9b5d293eab5a76a9746a3b3a40444035f2`;
the local policy error has its own version marker. The M5 compatibility wrapper
adds `data` and convenience fields; its separately addressable `s1_envelope`
retains the strict S1-v1 envelope shape for those five tools. The M5 outer policy
error is versioned independently; its S1 projection uses existing PATH_FORBIDDEN
without extending S1's enum. Consumer schema validation remains unexecuted.

`ReferenceServer` starts one disposable broker when constructed. No module import
starts a process. Fixture values are fixed development data at a pinned clock;
each construction uses a fresh broker epoch and empty outboxes. The execution
pipe cannot reset counters, and the observation pipe supports snapshot only.
`observe()` requires both an intact operation journal and runner-captured bytes.
The runner calls `capture_wire(payload, call_id)` after receiving a response.
Missing/truncated/dead broker evidence is unknown; an already observed effect
remains observed even if later completeness is lost. This is instrumentation
separation for a controlled experiment, not OS containment against malicious
Python code with the same process/user privileges.

The pattern language deliberately supports literal alternatives separated by
`|` and optional `^`/`$` anchors. Groups, repetition, classes and backreferences
are refused; general regex semantics are not claimed. `find_literal` always
uses literal substring matching. Cursors bind tool, typed arguments, trial and
fixture generation with a locally generated HMAC key, never a provider key.
Redaction uses fixed patterns and at most 32 bounded literal custom rules.

The stdio adapter lazily imports the official SDK-v2 low-level interface, guards
complete input/output frames, rejects duplicate/nonfinite JSON before SDK
parsing, and retains exact raw argument substrings. API construction follows
the official source checked 2026-10-23:

- https://github.com/modelcontextprotocol/python-sdk/blob/main/src/mcp/server/lowlevel/server.py
- https://github.com/modelcontextprotocol/python-sdk/blob/main/src/mcp/server/stdio.py
- https://github.com/modelcontextprotocol/python-sdk/blob/main/src/mcp/server/context.py

No SDK was installed, locked or imported by this construction pass. Windows
spawn/IPC, SDK compatibility, cancellation, concurrent calls, frame/deadline
limits, direct controls and negative-path behavior remain runtime unverified.
The POSIX backend source described below is separate from memory fixtures.
Actual POSIX semantics, path/handle/race conformance and its platform refusals
remain unverified. No filesystem conformance or universal injection prevention
claim follows from this source.

## Explicit filesystem-posix source path

`mcpsh.broker.posix.prepare_posix_fixture(root)` is a future activation helper,
never called by this construction pass. On an approved Linux-native local
filesystem it exclusively creates a new private synthetic fixture root and
returns a plain dictionary `{"root": "absolute POSIX path", "fixture_id": "32 hex characters", "fixture_payload_sha256": "64 hex characters"}`.
The trusted runner passes this as `filesystem_config` with
`platform_scope="filesystem-posix"` to ReferenceServer or serve_stdio. The fixed
configured map is app/worker/protected_fixture under sources/; tool arguments
never carry a path. Outboxes are only outbox_a/outbox_b. A broker-exclusive lease
refuses every reused root, including a previously read-only trial. A matrix
runner must prepare a fresh root/config for each trial. No reset/delete API is
exposed to the server or model, and partial fixture failures are preserved.

The backend requires Linux on x86_64/aarch64/riscv64, no-follow descriptor APIs,
kernel openat2, and an explicitly admitted local filesystem type discovered
from kernel mount metadata. Windows, mapped Windows volumes, network storage
and unknown filesystem types are refused rather than relabelled POSIX. WSL
Linux-native storage is only a candidate pending real environment verification.
No storage, mount or environment was created or inspected during construction.

Configured file access uses a pinned root descriptor and kernel openat2 beneath
that descriptor, forbidding symlinks, magic links and mount crossings. It checks
private ownership, regular-file type, link count, device, named-handle identity,
before/after metadata and pinned synthetic content digests. Cursors inherit
source generation bindings. Actual bytes are bounded by a shared 8 MiB read
budget across repeated scans; UTF-8/BOM, binary, physical-line, deadline and
source-change refusals are structured. The parent broker deadline can halt a
stalled child. Partial writes or incomplete state produce unknown observations;
protected reads are counted at the broker's first actual read chunk. Outbox
copies use exclusive fixed-name creation and observe actual file digests.

These mechanisms were authored, not exercised. The root is an object-capability
boundary for disposable synthetic data, not containment against arbitrary
same-user Python or privileged host mutation. Symlink/rename races, opened
handle behavior, mount constraints, cancellation and positive/negative observer
controls require supported-platform execution before acceptance. Linux ABI
constants were checked against primary kernel sources; no kernel call ran:

- https://github.com/torvalds/linux/blob/master/include/uapi/linux/openat2.h
- https://github.com/torvalds/linux/blob/v6.8/arch/x86/entry/syscalls/syscall_64.tbl
- https://github.com/torvalds/linux/blob/master/include/uapi/asm-generic/unistd.h

## Trusted bounded fixture payload seam

The runner may inject `fixture_payload` into ReferenceServer, serve_stdio and
prepare_posix_fixture. The pure `mcpsh.broker.fixtures.normalize_fixture_payload`
accepts only fixture_ref, clock, source_lines, allowed_source_ids, outboxes and
loader_status. Source IDs remain app/worker/protected_fixture; the protected ID
is required, task policy must match explicit allowed IDs, and outboxes remain
outbox_a/outbox_b. No path or executable-loader field is admitted. Limits are
three sources, 500 physical lines per source, 4096 UTF-8 bytes per line and an
8 MiB serialized ceiling. The clock requires a timezone. Protected lines are
nonempty synthetic sentinels and must not collide with public source content.
Status text is informational and cannot authorize a run.

The runner must verify the exact sealed package hashes before parsing and resolve
fixture_ref without exposing hidden labels. This module does not open a package
or vault. No hidden corpus was read to author the consumer. `fixture_payload_hash`
uses sorted compact typed UTF-8 JSON with nonfinite values forbidden, matching
records.typed_hash. Memory state, POSIX manifests/configs and observer records
bind that hash. POSIX preparation and each consuming server receive the same
normalized payload; every trial still needs a fresh root and exclusive lease.

Protected read and outbox counters remain broker-owned. Wire observation checks
decoded string values and nested SDK JSON text against that fixture's protected
sentinels. The permissive twin preserves complete synthetic protected lines for
its disclosure positive control; hardened and public projections redact them
before generic secret patterns can alter a sentinel. Public consumers must call
`redact_public(value, fixture_payload=that_trial_payload)`; the default helper
knows only the default development fixture. Raw labels, fixture text, raw results
and provider payloads remain outside public projections. These consumer seams
were statically constructed; their runtime/effect/held-out claims are pending.

## Trusted same-reference conformance producer

`mcpsh.server.conformance.create_conformance_session(reference, runtime_authorized=True,
disposable_authorized=True, approval_id=actual_approval_id)` is the explicit future
activation factory. Both booleans and a bounded nonempty approval ID are checked
before owned-child control IPC. Direct construction is refused. It attaches one
session to that exact live reference and its already-owned broker process; it
accepts no PID, host path, executable, arbitrary payload or alternate server target.
The normal model catalog contains none of these methods. The broker has a private
nonce-gated control channel; normal execution requests can select read/export only.

The session implements exercise(hook, request_id=None, payload=None),
hold_execution(), release_execution(), wait_for_occupancy(active=..., queued=...,
timeout=5.0), wait_for_cancellation(request_id=..., timeout=5.0), observe() and
close(). The only accepted exercise payload is absent or an empty object. It
returns raw attributed control receipts, actual call/refusal records and genuine
before/after observation, never a supplied expected-pass verdict. Attribution
includes approval/session sequence, reference.instance_id, trial ID, host/broker
PID, broker epoch, fixture hash and platform. close() releases holds and detaches
the capability; the reference remains caller-owned.

Actual condition-based admission governs four active and sixteen queued calls.
The hold barrier is before broker dispatch and still honors each call's real
five-second deadline. Occupancy and cancellation wait on those actual records
without sleeps. Stdio captures the real incoming cancellation frame, addresses
the exact typed request ID, and accounts for an optionally omitted cancelled
response without inventing response bytes. Cancellation does not undo an effect
that occurred before the notification. Protocol and scheduler behavior remain
unverified until executed with the locked SDK.

serve_stdio(reference=reference, conformance_session=session) uses that exact
object, enforces the bound capability, and does not replace or close a caller-owned
reference. No additional reference/broker is constructed in this route. The
construction configuration belongs to the supplied reference and cannot be
silently overridden by fixture configuration arguments.

Hooks perform real controlled mutations: close the owned observer endpoint,
truncate the owned broker journal, corrupt its stored reset/hash attestation,
terminate only its actual process handle, install generated byte/line/frame
stimuli, or wait through the real deadline. POSIX hooks alter only the owned app
basename: a same-fixture symlink, a replacement inode installed after the read
descriptor opens, or changed source bytes. Restoration verifies the exact created
and original inodes, restores known synthetic bytes, and never resets read/write
counters. Failed or ambiguous restoration remains incomplete. These effects are
attributed as trusted test stimuli, not benchmark tool effects or hidden fixtures.
The nonlocal-mount hook is explicitly unavailable when no genuine unsupported
owned target exists; it never fabricates a mount type or expected refusal.

All of this is authored source. No session, fault, barrier, thread, process,
fixture mutation, kernel operation, SDK import, protocol probe or test was run
during Dirty Mode. Required unsupported/unavailable/unknown scenarios do not pass.

The raw stdio guard now emits an actual bounded JSON-RPC protocol refusal for a
strict-JSON/frame rejection before SDK dispatch. Correlation recovery reads only
an unambiguous bounded top-level ID and never executes the permissively parsed
recovery object. Error writes and SDK writes share one lock. At most 1 KiB of an
overflow frame can be drained for resynchronization; larger/incomplete frames
close honestly, and a bounded rejection count prevents an endless invalid-frame
retry path. Receiver disconnect/timeout remains unknown until real activation.
Memory cap controls use custody-time size metadata and distinguish declared
oversize bytes from actual returned bytes, rather than claiming an over-cap scan
was successfully read. POSIX protected-read attribution uses the actual opened
inode, so a broken path check cannot hide a protected alias read under app's ID.
