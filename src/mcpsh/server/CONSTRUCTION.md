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
returns a plain dictionary `{"root": "absolute POSIX path", "fixture_id": "32 hex characters"}`.
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
