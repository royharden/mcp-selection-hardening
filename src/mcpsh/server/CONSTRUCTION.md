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
Actual POSIX path/handle/race safety and Windows filesystem support are not
implemented by memory fixtures. No filesystem conformance or universal injection
prevention claim follows from this source.
