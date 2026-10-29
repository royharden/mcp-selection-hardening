# MCP selection and independent enforcement

**development/replay-only; live-model and filesystem acceptance pending**

This research harness separates a selector choosing a prohibited call from a server allowing its effect. It contains a fixed nine-tool synthetic catalog, clean/ambiguous/poisoned metadata, bounded lint and trusted-description normalization, a server-owned policy boundary, a separate fixture broker/observer, ordered replay, scorer-only labels, local cost-accounting source and escaped static reports.

Validation update, 2026-10-25, run PB-M5-R03: the project has moved from source construction to Normal-mode keyless validation. `uv.lock` exists; Python 3.12.13, Pydantic 2.14.1 and MCP SDK 2.3.0 have been installed and exercised. At source commit `a1f61c1320166cc68f14b3bfebc5dfac634514ef`, the Windows local runner reports **877 tests passed, 3 Linux-only skips, no failures or errors**, plus a passing public CLI journey. Fresh installed-wheel checks also ran. Independent High-effort review approved the bounded public synthetic-memory joined source with notes. Docker evaluation ran, but the full POSIX gate is blocked by the required unavailable `posix-nonlocal` probe. These results are not product, live-model or filesystem acceptance. See the scoped evidence and open gates in [VALIDATION.md](docs/VALIDATION.md).

## Source journey

1. Validate/export a catalog or inspect L01–L12 findings with evidence spans.
2. Run explicitly scripted public development calls through permissive and hardened synthetic variants.
3. Capture the actual serialized result in the runner, independently of server response claims.
4. Observe protected reads, wire disclosure and outbox changes outside handlers.
5. Score selection, legitimate utility, recognizable prohibited intent, validated attempts, blocks, gate false negatives and effects separately.
6. Publish a new immutable development edition as JSON/JSONL, CSV, Markdown and static HTML from one result object. Unknown observations stay unknown.

No description or selector can enable permissive mode. Only the runner chooses the treatment. The permissive twin relaxes synthetic source/export policy inside the same bounded fixture universe; it never opens a host path or performs real exfiltration. This is an M5-owned fallback, not an accepted S1 filesystem reader or an original vulnerable S1 release.

Utility records distinguish explicit `semantic-v2` predicates from `legacy-call-proxy-v1`. The latter is a declared call-sequence proxy, not proof that a result, refusal or clarification met the user’s request. The runner captures tool-result envelopes and a terminal assistant response as private scorer evidence, preserving attempt parents and availability; missing semantic evidence remains unknown. Primary held-out admission requires explicit semantic predicates. Offline tests and public replay do not establish live utility or independent held-out performance.

## Keyless quickstart

With Python and `uv` available, run these PowerShell commands from the repository root. The reviewed bootstrap selects Python 3.12.13, installs the locked noneditable distribution into `.venv`, builds a wheel and checks the installed CLI. It may download public dependencies; it makes no provider requests. Use normal Python rather than `python -O` for the journey checks.

```powershell
python scripts/bootstrap.py
$py = ".\.venv\Scripts\python.exe"
& $py -m mcpsh catalog validate
& $py -m mcpsh catalog export --condition poisoned --artifact --ordering-seed 17
& $py -m mcpsh lint --condition poisoned
& $py scripts/demo.py
& $py scripts/e2e_cli.py
& $py scripts/e2e_cli.py --installed

# Full offline suite and public CLI journey; this may take several minutes.
# Set this to the exact source revision being checked, independently verify its bytes.
$env:MCPSH_TEST_SOURCE_COMMIT = (git rev-parse HEAD).Trim()
& $py scripts/check_local.py --scope all --timeout 600
```

The lock includes pinned pytest 9.1.1 and ruff 0.17.2 development tools. Direct MCP SDK initialize/list/call checks negotiated protocol `2025-11-25`; five controlled installed-stdio probes passed with zero unknowns. This is a bounded interoperability check, not a full protocol or normative conformance verdict. `MCPSH_TEST_SOURCE_COMMIT` is edition metadata, not proof of imported source identity. A `lint` exit code of 1 means findings; it is not a scanner crash.

To publish a new public scripted edition, use `& $py scripts/eval.py --mode replay --corpus demo --lint-controls --edition <fresh-edition-id>`. Full public-development replay additionally requires `--corpus development --development-manifest-sha256 <reviewed-raw-manifest-pin>`. Edition IDs must be fresh; keep raw evidence outside the repository. A successful publisher or provenance check does not imply that every scheduled trial succeeded.

Bare catalog export remains compatible. `catalog validate --artifact --input <file>` validates the versioned envelope and original raw transport; it cannot repair an invalid artifact. `catalog treat --input <artifact> --descriptions <description-map> --normalized` returns a versioned before/after metadata treatment with source hashes. Canonical schemas, IDs, annotations and matched order remain fixed. Lint findings also include verified Unicode/codepoint and UTF-8 field spans. See [CATALOG.md](docs/CATALOG.md).

`--lint-controls` adds the public development label/bypass evaluation and normalization diagnostics to the same scored edition, including per-rule provisional versus confirmed counts, unknown labels and N/A denominators. An optional `--lint-review` must name a public `fixtures/dev/` review mapping; it cannot load hidden corpus material. These controls are not universal detector accuracy or independently held-out evidence.

The conformance entrypoint is `& $py -m mcpsh server-check --request <approved-request.json>`. Its request names selected tracks/probes and requires explicit runtime authorization, disposable-fixture authorization and an approval ID. Memory, POSIX and stdio reports remain separate; failed, unknown, unavailable and unsupported probes never turn into a pass. Diagnostic probes have run, but a partial selection cannot establish a full platform pass or supply missing external normative authority. See [CONFORMANCE.md](docs/CONFORMANCE.md).

`python scripts/pilot.py plan --development-manifest-sha256 <reviewed-raw-manifest-pin>` creates a draft-only development design from the canonical dev-corpus parser; it cannot authorize dispatch or fill in prices or a utility floor. To summarize supplied evidence through the sole numeric publisher, use `scripts/eval.py --mode pilot-summary --pilot-plan <draft.json> --pilot-plan-sha256 <raw-pin> --pilot-observations <observations.json> --pilot-observations-sha256 <raw-pin>`. Its repeat/repair and threshold outputs stay approval-needed, with unknown observations retained. A draft or tested consumer is not an executed live pilot. See [CALIBRATION.md](docs/CALIBRATION.md).

Full-36 supplied evidence has a separate `--mode development-summary` route with raw-pinned `--development-plan`, `--calibration-outcomes` and optional `--calibration-failures` files. It preserves all planned slots, control provenance and unknown/proxy/counter evidence. The admitted-runner bridge accepts explicit closed-mode/runtime grants and already-admitted selectors; it has no default callback/provider or guessed attempt counters. See [CALIBRATION-INTEGRATION.md](docs/CALIBRATION-INTEGRATION.md). Canonical public semantic-v2 labels and authored replay episodes have been exercised in public replay; independent label/family adjudication and approved calibration remain pending.

The demo prints safe call/decision/effect traces without publishing benchmark metrics. The evaluator defaults to all 36 public development cases; `--corpus demo` selects the two scripted walkthrough cases. Clean, ambiguous and poisoned C0/C1/C2 cells use identical scripted calls, so replay cannot measure a model’s response to metadata. Keyword, abstain and deny-all controls are separately labelled. The original calls and raw malformed arguments are retained in private evidence rather than the public reports.

Development replay requires an explicit raw pin for `fixtures/dev/corpus-manifest-v2.json`.
The bounded loader checks its exact canonical package files and uses typed
`gold/dev/oracles.json` `{schema_version,cases}` semantics, task-specific synthetic
fixtures and metadata treatments. Each task's exact `--clean` authored episode is
the same baseline across matched conditions/cells. Other authored episodes are
separate replay diagnostics and never enlarge core pairing, family or live samples.
The version2 episode package declares roles and allowed conditions/cells; the
loader consumes D5's versioned primary/diagnostic plans and semantic source
preflight. Diagnostic cells come from that explicit plan, with no fixed episode
count or extra matched samples inferred. The current manifest format version is
read from the pinned bytes even though its canonical filename retains `v2`.
Authored terminal text has scripted provenance, no model attempt or usage record;
missing text stays unavailable. Unsupported observer-fault requests remain explicit
unsupported rows with unknown observation rather than invented fault evidence.

After preserving the full private result and optional normalized evidence, the
sole publisher uses `mcpsh.evidence.project_public_result`. All public formats,
including the public manifest, render the exact same allowlisted object. Projection
diagnostics stay private; raw final text, oracle fields and private identifiers
do not pass through a separate publication path. Scheduled/error rows, supplied
denominators, unknown utility/effects and distinct cost bases remain represented.

Only `scripts/eval.py` writes numeric editions. Public output defaults to `results/<edition>/`; raw synthetic evidence defaults to `../mcp-selection-hardening-private-evidence/<edition>/`, outside this product repository. `--private-evidence` can choose another explicitly authorized outside-repository directory. Use a fresh edition ID for reruns: existing editions/reservations are not overwritten, and failures preserve staging/reservations. There is no committed live-model benchmark table. Report hashes establish identity, not safety or runtime acceptance.

For a new replay/live run, an explicit `--candidate-commit <full-accepted-commit> --revision <positive-int>` also builds normalized evidence sidecars under the private edition's `normalized/` folder. Raw calls, results, observers and explicitly supplied oracle bytes never enter the public report directory. Live candidate metadata must match the approved manifest. Missing reservation evidence stays unknown; no authority file is fabricated from the generated index.

Live collection also preserves all actual proof and prepared-request journal events
in a private token-fit bundle. Independently selected expectations can be supplied
with separate external raw and typed pins; absence retains unknown credit. The
reader's externally supplied authority pins that selection independently. Complete
private lineage and all failed/unknown attempts remain available; public output
receives only bounded status, counts and hashes through the canonical projector.
Fit is separate from spend authorization and billing. See [VALIDATION.md](docs/VALIDATION.md)
for immutable-edition and retrospective selection limits. Actual approved live
token-fit collection remains pending.

`scripts/eval.py --mode fit-reverify` is the publisher-side route for a retrospective
fit successor. It takes the saved parent edition (`--evidence-root`,
`--evidence-authority`, `--authority-sha256`), a `--fit-authority` with raw and
typed pins, raw-pinned `--fit-expectations` covering every original attempt, and
the exact raw-pinned `--parent-journal`. Without a separately bound `--fit-receipt`
(raw and typed pins) it prints a pending plan with no credited fit and writes
nothing. With an authenticated receipt it writes a new successor edition under the
private evidence root, leaving the original UNKNOWN edition untouched and archived
inside the successor. It adds no attempts, charges, dispatch or public numeric
results. Offline regressions do not establish an authenticated live fit successor.

`scripts/eval.py --mode dossier --evidence-root <saved-private-edition>` accepts
`--dossier-authority` with separate external raw and typed pins, plus an explicitly
raw-pinned `--acceptance-sources` package. It assembles D4's acceptance dossier from
D7's verified original bytes, without rescoring, relabeling replay or filling missing
rows. Private dossier details stay outside the product tree; only safe status,
identity pins and semantic-basis counts enter canonical public views. All CLI
authentication/custody/independence confirmations remain false. A recommendation
does not grant runtime authority or independent product acceptance.

`scripts/eval.py --mode ledger-audit --ledger <explicit-existing-db-or-snapshot>`
uses an explicitly saved evidence edition plus raw-pinned edition and ledger
authorities. It calls only the existing accounting owner's read-only audit; no
ledger constructor, migration or reconciliation is added. Full details stay
private, while the canonical public ledger report preserves totals, dated-estimate
bases, unknown liabilities, unallocated rows, retained reserves and reuse. The CLI
does not authenticate billing witnesses from JSON or turn estimates into billing.
Offline accounting/audit regressions do not establish provider billing or settle actual unknown liabilities.

The offline reader is `mcpsh evidence-check --root <private-normalized-edition> --authority <file> --authority-sha256 <externally-approved-raw-pin>`. It checks structural integrity and reports missing evidence; exit success does not grant product acceptance. `scripts/eval.py --mode rescore --evidence-root <private-edition> --evidence-authority <file> --authority-sha256 <raw-pin> --evaluator-sha256 <approved-source-pin> --edition <fresh-successor-view>` reproduces with the pinned evaluator and publishes a fresh bounded/redacted view. It retains the original input manifest and reports unknown scheduled trials without calculating a reduced-denominator score. Original editions are never overwritten. Actual canonical producer/read/reproduce paths and offline regressions have run; separately admitted rescore/acceptance inputs are still required.

`evidence-resume` uses the same externally raw-pinned parent authority. An optional `--resume-authority <file> --resume-authority-sha256 <external-canonical-typed-pin>` plus `--receipts <file>` produces a successor proposal only. The successor authority pins exact target manifest bytes, schedule, receipts and reservation cap; missing repeat identity or unknown usage stays pending. It neither frees ledger holds nor dispatches or rewrites results. The successor typed pin and parent raw-file pin intentionally name different identities.

An optional raw-pinned `--acceptance-request <file> --acceptance-request-sha256 <pin>` on replay/live/rescore asks the policy evaluator for a recommendation using the current scored rows plus typed design, threshold, custody, conformance and control records. It never approves its own product: independent product acceptance remains pending, even for an eligible-for-review recommendation.

Exact recommendation inputs now include the actual private row's explicit repeat,
platform and model family; missing legacy fields remain unknown. Threshold metadata
uses a separately pinned proposal/summary/context package and current-input record,
plus externally pinned reviewer/INT decisions when supplied. The CLI leaves actor
authentication and fresh-custody confirmation false, so it cannot generate an
approved floor from matching JSON. Direct handmade threshold records are rejected.
See [VALIDATION.md](docs/VALIDATION.md) for flags and the trusted-caller source seam.

Installed conformance resources are explicitly mapped in the wheel configuration;
fresh noneditable wheels and all seven packaged resources have been checked.
`server-check` accepts external
`--semantic-manifest-sha256` and `--requirements-manifest-sha256` pins alongside the
explicit disposable/runtime request. Missing pins remain unknown, with no
self-calculated substitute. See [CONSUMER-CONFORMANCE.md](docs/CONSUMER-CONFORMANCE.md).

## Construction history and subsequent validation

The 2026-10-23/24 construction phase authored the features below without runtime checks. Normal-mode work on 2026-10-25 subsequently installed and tested the keyless paths, repaired real runtime defects and retained earlier failed evidence. That history is not a claim that every feature or acceptance gate has passed. The method end to end is in the [evaluation guide](docs/EVALUATION-GUIDE.md).

- **Conformance producer closure.** Boundary-hook receipts carry per-hook scopes and metrics; read-amplification uses `m5-broker-control-receipt-v1`. Real observer-v3 sibling reads now pass through scoring and typed evidence, with explicit unknown handling. Diagnostic execution does not supply missing external normative pins ([CONFORMANCE-V7.md](docs/CONFORMANCE-V7.md)).
- **Normative-v3 producer bridge and public status (D7).** `verify_producer_bindings` checks v3 conformance documents against the fixed `policy/conformance/requirements-v1.json` inventory; legacy v1 authorities are integrity-only and never creditable. A finite `normative_v3_status` block (counts, bases, pins; totals null unless evaluated) reaches public reports. Dossier/ledger consumers were reconciled with their producers ([EVIDENCE.md](docs/EVIDENCE.md), [LEDGER.md](docs/LEDGER.md)).
- **Report views (D4).** Mode-specific evaluation view sections in REPORT.md, `index.html` and `evaluation-views.json`, copied from the projected result; missing values read "not supplied", never zero ([REPORT-VIEWS.md](docs/REPORT-VIEWS.md)).
- **Publisher and data (D5).** `scripts/eval.py --mode fit-reverify` writes a retrospective fit successor only with a separately pinned, authenticated receipt, leaving the original edition untouched. The dossier publication copies `normative_v3_status` only when the producer report is bound to the dossier pins. All 36 development oracles now prohibit every configured source outside the task allowlist (previously only the protected source), with the corpus manifest re-pinned. `pilot.py plan` reads the corpus through the canonical parser and requires `--development-manifest-sha256`. A root `.gitattributes` keeps pinned bytes identical across checkouts.

## What remains pending

- Resolve the required unavailable `posix-nonlocal` adapter/fixture/hook and complete platform and independent product acceptance. The Docker runtime driver exits 1 with that platform gate open; its passing tests and replay-provenance checks do not waive it. The validation table is in [VALIDATION.md](docs/VALIDATION.md#deferred-validation-list).
- Obtain externally admitted semantic/requirements authorities and complete the required normative inventory; diagnostic stdio or broker-hook evidence alone cannot earn full conformance.
- Complete mandatory POSIX filesystem conformance on supported storage: the selected Linux suite reports 62 passing probes and one required unavailable probe, with no filesystem proof. Keep this result separate from Windows `synthetic-memory` evidence; real Windows filesystem support is deferred.
- Admit and exercise the authored OpenAI/Anthropic HTTP codecs, controller and live-runner source with two exact model families, returned identities, dated prices, full-wire tokenizer, durable accounting and approved bounded spend. These integrations have not been run.
- Appoint independent held-out custody and product review, seal independent task/attack families, calibrate the utility floor on development data, run the pilot and complete the approved live matrix. These are W3C/W6/W7 gates, not completed construction outcomes.

Selection journals preserve ordered choices before dispatch limits. A seventh, late, duplicated or malformed call remains private evidence even when no server call is made. Such a cap refusal is separate from a server policy block. Raw provider-body limits and the six executed-call ceiling remain intact; unsupported journal capture is explicitly incomplete rather than a successful empty trace.

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

See [ARCHITECTURE.md](ARCHITECTURE.md), the [evaluation guide](docs/EVALUATION-GUIDE.md), [limitations and validation handoff](docs/VALIDATION.md) and [provenance](docs/PROVENANCE.md). MIT licensed. Source was authored with Codex and Claude agents working in disjoint packages under Roy Harden’s direction. Coordination records and chat exports stay outside the product repository. No remote, publication, deployment or CI infrastructure was created.

The [scripted walkthrough](docs/DEMO.md) documents C0/C1/C2 and failure evidence without attributing any scripted selection to a real model.

The later live source entrypoint is `scripts/eval.py --mode live --manifest <file> --approval <file> --oracle-package <sealed-file> --fixtures-package <sealed-file> --treatments-package <sealed-file> --protocol-record <file>`. This command is not authorized by this README or by source construction. It requires a manifest bound to exact source/lock/protocol/corpus hashes, two approved distinct-family arms, prices, independent custody, explicit Dirty Mode closure and an unexpired M5 runtime/network/spend receipt. Raw fixture/treatment SHA256 pins must match both the manifest settings (`fixtures_sha256`, `treatments_sha256`) and approval before bounded JSON parsing. Fixture references and task IDs must join exactly; task policy must match the fixture. Per-task treatments replace descriptions only, preserve the canonical nine schemas/IDs/annotations, and use a fixed per-task ordering seed across arms. Private mechanism/lineage fields never enter provider requests. The approval names a real versioned local full-wire tokenizer; there is no guessed token-count fallback. Credentials are read only through admitted lazy environment-name callbacks at future dispatch. Missing inputs fail closed. Live and replay editions remain separate.

Live admission is checked at every model turn and by the controller at every actual send, including retries. Unknown prior usage/cost blocks further dispatch immediately; an unused valid reservation is not itself treated as an unknown completed request. Per-attempt caps, expiry and durable accounting must still be verified during later runtime activation. No unknown usage is converted to a free request.

The approved tokenizer receives the exact complete encoded HTTP body **bytes**, unchanged, including tools/settings/history overhead. No dictionary conversion or approximate fallback is allowed. Prospective live manifests/approval must pin the exact `transports.py` SHA256; ordering settings name `sha256-tool-rank-1` and the catalog ordering source SHA256. The same per-task seed/order is used across matched cells and models, including normalization. Each private matrix row records a one-based repeat explicitly; missing legacy repeat metadata is not inferred from a trial ID. Actual refusal strings are captured separately, while a boolean provider refusal flag never fabricates text.

For a later authorized POSIX matrix, `--filesystem-config` names a JSON object with one absolute `fixture_parent` path on supported Linux-native storage. The runner prepares a fresh disposable synthetic root for every task-run using the same sealed normalized fixture payload supplied to the server. The backend binds its payload hash in the fixture manifest/config and never reuses one consumed fixture. Do not point it at real logs or private data. No filesystem setup or provider request was performed during construction.
