# MCP selection and independent enforcement

**development/replay-only; live-model and filesystem acceptance pending**

This research harness separates a selector choosing a prohibited call from a server allowing its effect. It contains a fixed nine-tool synthetic catalog, clean/ambiguous/poisoned metadata, bounded lint and trusted-description normalization, a server-owned policy boundary, a separate fixture broker/observer, ordered replay, scorer-only labels, local cost-accounting source and escaped static reports.

The source was constructed under Dirty Mode. Focused source inspection and syntax parsing are the only checks performed during construction. No dependency installation, application run, test, SDK interoperability check, benchmark, paid model request or filesystem conformance run has occurred. There is no measured results table yet.

## Source journey

1. Validate/export a catalog or inspect L01–L12 findings with evidence spans.
2. Run explicitly scripted public development calls through permissive and hardened synthetic variants.
3. Capture the actual serialized result in the runner, independently of server response claims.
4. Observe protected reads, wire disclosure and outbox changes outside handlers.
5. Score selection, legitimate utility, recognizable prohibited intent, validated attempts, blocks, gate false negatives and effects separately.
6. Publish a new immutable development edition as JSON/JSONL, CSV, Markdown and static HTML from one result object. Unknown observations stay unknown.

No description or selector can enable permissive mode. Only the runner chooses the treatment. The permissive twin relaxes synthetic source/export policy inside the same bounded fixture universe; it never opens a host path or performs real exfiltration. This is an M5-owned fallback, not an accepted S1 filesystem reader or an original vulnerable S1 release.

## Later local activation

These commands are instructions for the later validation phase. They have **not** been run during construction. Use Python 3.12+ and an environment you authorize. From the repository root:

```powershell
uv sync --extra dev
uv run mcpsh catalog validate
uv run mcpsh catalog export --condition poisoned
uv run mcpsh lint --condition poisoned
uv run mcpsh lint --condition poisoned --normalize
uv run python scripts/demo.py
uv run python scripts/eval.py --mode replay --corpus development --edition dev-001
```

Dependency ranges are declared, but no verified dependency lock exists. MCP SDK selection, its optional dependency declaration, a protocol pin and an actual stdio smoke test remain later work. The SDK adapter source imports the SDK lazily. Do not describe it as interoperable before that work is done. A `lint` exit code of 1 means findings; it is not a scanner crash.

The demo prints safe call/decision/effect traces without publishing benchmark metrics. The evaluator defaults to all 36 public development cases; `--corpus demo` selects the two scripted walkthrough cases. Clean, ambiguous and poisoned C0/C1/C2 cells use identical scripted calls, so replay cannot measure a model’s response to metadata. Keyword, abstain and deny-all controls are separately labelled. The original calls and raw malformed arguments are retained in private evidence rather than the public reports.

Only `scripts/eval.py` writes numeric editions. Public output defaults to `results/<edition>/`; raw synthetic evidence defaults to `../mcp-selection-hardening-private-evidence/<edition>/`, outside this product repository. `--private-evidence` can choose another explicitly authorized outside-repository directory. Use a fresh edition ID for reruns: existing editions/reservations are not overwritten, and failures preserve staging/reservations. The source has no committed results or claimed pass rates. Report hashes establish identity, not safety or runtime acceptance.

## What remains pending

- Execute the source journey and meaningful regression/conformance checks after Dirty Mode closes. The static review is not runtime proof.
- Establish and lock compatible Python/Pydantic/MCP dependencies; exercise actual stdio and separate-process IPC, failure/teardown/reset behavior, byte/line/frame/deadline caps and redaction.
- Verify the authored disposable POSIX backend and its filesystem conformance track on actual supported storage. Current `synthetic-memory` evidence cannot satisfy it; real Windows filesystem support is deferred.
- Admit and exercise the authored OpenAI/Anthropic HTTP codecs, controller and live-runner source with two exact model families, returned identities, dated prices, full-wire tokenizer, durable accounting and approved bounded spend. These integrations have not been run.
- Appoint independent held-out custody and product review, seal independent task/attack families, calibrate the utility floor on development data, run the pilot and complete the approved live matrix. These are W3C/W6/W7 gates, not completed construction outcomes.

All 36 development tasks, the public demo and lint labels are agent-authored and author-seen. Template variants are clustered by their six task classes for descriptive uncertainty; they are not 36 independent held-out families. Lint is bounded lexical/structural detection with known bypasses. Normalization replaces only flagged metadata from a trusted behavior map; it does not remove tools, alter schemas or prove general injection prevention. No universal safety or generalization claim is made.

## Layout

```text
src/mcpsh/records/       strict public/oracle/evidence boundaries and hashing
src/mcpsh/catalog/       canonical schemas and experimental metadata overlays
src/mcpsh/lint/          bounded evidence-bearing lint and normalization
src/mcpsh/server/        synthetic reference and lazy stdio adapter source
src/mcpsh/broker/        separate-process fixture authority
src/mcpsh/observer/      read/disclosure/write observation
src/mcpsh/policy/        server-owned access/redaction policy
src/mcpsh/adapters/      replay, keyword, abstain and gated live contracts
src/mcpsh/accounting/    local SQLite reservation/settlement source
src/mcpsh/runner/        capped ordered development replay pipeline
src/mcpsh/evaluation/    scorer-only predicates and uncertainty
src/mcpsh/report/        shared-object static report renderers
fixtures/dev/           public development tasks
gold/dev/               development-only oracle labels, never provider inputs
scripts/                demonstration and sole metric-edition publisher
```

See [ARCHITECTURE.md](ARCHITECTURE.md), [limitations and validation handoff](docs/VALIDATION.md) and [provenance](docs/PROVENANCE.md). MIT licensed. Source was authored with Codex agents working in disjoint packages under Roy Harden’s direction. Coordination records and chat exports stay outside the product repository. No remote, publication, deployment or CI infrastructure was created.

The later live source entrypoint is `scripts/eval.py --mode live --manifest <file> --approval <file> --oracle-package <sealed-file> --protocol-record <file>`. This command is not authorized by this README or by source construction. It requires a manifest bound to exact source/lock/protocol/corpus hashes, two approved distinct-family arms, prices, independent custody, explicit Dirty Mode closure and an unexpired M5 runtime/network/spend receipt. The approval names a real versioned local full-wire tokenizer; there is no guessed token-count fallback. Credentials are read only through admitted lazy environment-name callbacks at future dispatch. Missing inputs fail closed. Live and replay editions remain separate.

For a later authorized POSIX matrix, `--filesystem-config` names a JSON object with one absolute `fixture_parent` path on supported Linux-native storage. The runner prepares a fresh disposable synthetic root for every task-run; it never reuses one consumed fixture. Do not point it at real logs or private data. No filesystem setup or provider request was performed during construction.
