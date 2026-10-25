# Validation handoff

Updated 2026-10-25 for PB-M5-R03. Normal-mode execution has replaced the earlier construction-only status. The source revision covered by this update is `a1f61c1320166cc68f14b3bfebc5dfac634514ef` (tree `c04bc5755380db089f99dfc22251b7a3a224deed`). This is a local development candidate, not an accepted product or a live benchmark. The method is in [EVALUATION-GUIDE.md](EVALUATION-GUIDE.md).

## Deferred-validation list

The table separates completed bounded checks from open gates. Counts belong to their stated source and scope; earlier component evidence does not become a final joined verdict. Independent High-effort review approved the exact public synthetic-memory joined source with notes. Final Docker/Linux execution and product acceptance remain pending at this documentation checkpoint.

| Component | Executed evidence | Remaining scope or gate |
|---|---|---|
| Dependencies and packaging | `uv.lock` exists. Python 3.12.13; Pydantic 2.14.1, MCP SDK 2.3.0, pytest 9.1.1 and ruff 0.17.2 pinned. Reviewed bootstrap builds and installs a noneditable wheel. | New environments must use the lock and verify installed source/resource identity; a version declaration is not execution proof. |
| Windows local runner | At `a1f61c1`, `scripts/check_local.py --scope all --timeout 600` reports 877 passed, 3 skipped, 0 failures/errors, exit 0; the public CLI journey also passes. | The three skips are Linux-only POSIX tests. The root runner does not supply independent product or platform acceptance. |
| Fresh installed distribution | D8's `a1f61c1` receipt reports 110 installed Python files matching joined source, 121 wheel payload files matching installation and seven resource matches. Public installed journey: eight checks passed. | Installed proof is scoped; byte identity and a successful journey do not establish every feature or acceptance requirement. |
| SDK and stdio | Fresh-installed SDK initialize/list/call smoke passed at `a1f61c1`, negotiated protocol `2025-11-25`, listed nine tools, allowed source discovery and denied export. Five controlled stdio probes passed, zero unknowns. | Diagnostic five-probe selection only; full normative verdict remains pending external semantic/requirements authority pins. |
| Broker, observer, scoring | Process startup readiness, bounded stdio reads and installed-launcher identity were repaired. Observer-v3 sibling state reaches scoring/diagnostics; observed effects dominate incomplete evidence. | Broader platform claims need their own evidence; missing/unknown observations never earn complete safe absence. |
| Trace and evidence contract | Independent High-effort joined review at `a1f61c1` closes JEV-F1/F2 for the bounded public source scope. Its 21-test JEV suite includes original producer/build/read/reproduce positives and the ordinary 24-row publisher/readback; 15 effect-authority/observer-contract tests also passed. | This is source execution, not a full installed-suite or product verdict. Reviewer-filtered traces and stand-ins cannot replace the original chain. |
| Sibling configuration authority | Reviewed JEV controls bind retained nonprotected reads to the pinned public-task allowlist. Omitted/fake sibling inventories cannot erase unauthorized reads; missing authority cannot earn complete safe absence. | Rebound synthetic-authority tests do not demonstrate tampering past an independently immutable production authority. |
| Installed actual evidence chain | At `a1f61c1`, D8 ran two canonical actual producer/build/read/reproduce cases (allowed and sibling), both passing; 19 other cases were deselected. | This receipt is not a second full 21-test JEV run or a 24-row publisher run. |
| Public development replay | The 36-task loader and scripted publisher have executed. Earlier 477-slot public replay retained nine failed outcomes and 21 unknown utility rows. | Provenance/immutability success is not task-utility success; retain all failures and unknowns. Final r3 public-evaluation receipt remains pending. |
| Docker and Linux/POSIX | Earlier corrected-context `6189e0a` targeted detached-consumer run: five passed, exit 0, network disabled, no published ports. | Final full `a1f61c1` Docker/Linux/public-evaluation result pending. Windows skips and memory evidence cannot close POSIX path/handle/race requirements; real Windows filesystem support remains deferred. |
| Normative conformance | Local diagnostic/hook tests and installed resources have executed. | External semantic/requirements authorities, complete inventory coverage and any unsupported/missing cases remain required; local hashes cannot self-authorize normative credit. |
| Dossier, ledger and fit consumers | Offline regressions have run as part of keyless suites. | No authenticated provider billing, real live token-fit collection or independently admitted live successor is established by those tests. See the contracts below. |
| Calibration, pilot and held-out families | Public synthetic development data and draft/consumer paths exist. | Independently reviewed labels/families, approved utility floor, real pilot and live matrix remain pending; a draft cannot grant dispatch. |
| Byte stability | Pinned source/resource bytes were checked for the scoped builds/reviews. | A general fresh-clone comparison under both `core.autocrlf` settings is not established by those checks. |
| Live models and product acceptance | No live/paid or hidden/held-out execution is claimed. | Two distinct approved model families, dated prices, full-wire fit, durable accounting, independent custody and product acceptance remain open. |

## Reproduce the bounded checks

Use the [README quickstart](../README.md#keyless-quickstart) from the repository root. `scripts/bootstrap.py` selects Python 3.12.13 and runs locked, noneditable installation before a wheel build and installed CLI help check. It makes no provider requests.

```powershell
python scripts/bootstrap.py
$py = ".\.venv\Scripts\python.exe"
& $py scripts/e2e_cli.py
& $py scripts/e2e_cli.py --installed
$env:MCPSH_TEST_SOURCE_COMMIT = (git rev-parse HEAD).Trim()
& $py scripts/check_local.py --scope all --timeout 600
```

The commit environment variable supplies edition metadata only. Independently verify imported paths, source bytes and installed resources when making source-identity claims. `--installed` on the journey checks the noneditable package without source-checkout rescue; the default runner checks source. Use normal Python: optimized mode disables assertions and is refused by these scripts. Inspect per-check results and row completeness; process exit zero alone does not establish a valid effect-free trial.

The default demonstration has two public scripted tasks across C0/C1/C2. Clean rows have no observed prohibited effects; the permissive poisoned row exposes synthetic protected-read/outbox effects; hardened rows deny export before dispatch. All six need complete observations and selection journals. `scripts/demo.py --include-failures` adds malformed, extra-selection and missing-answer diagnostics; those rows do not expand the successful default sample or create live model evidence.

## Evidence history and open authority

Earlier failed startup, installed-launcher, Docker-context and canonical-evidence editions are retained with their original evidence. Successor checks bind new immutable source/edition identities; they do not overwrite or retroactively pass failed editions. Public reports contain only the bounded projection, never private raw payloads or hidden labels. Original observations, full traces and failed/unknown scheduled rows remain available to their authorized reviewers.

The source-owned sibling scorer/evidence repairs and exact `a1f61c1` joined J0–J7 are independently reviewed within bounded public synthetic-memory scope. J4 uses an explicit controlled policy fault; cancellation derivatives are synthetic, not evidence of actual cancellation execution. Final Docker/Linux checks and independent product acceptance remain separate gates. Source/installed J7 pass at earlier joined `7b7e97c` remains scoped to that revision; the successor uses fresh source execution and read-only independent assessment of current D8 installed evidence. The 877-test Windows result and installed receipt above belong to `a1f61c1`.

The joined review's packaging note retains exact installed Python/lock/script/resource and wheel-payload identities. The build-stage `pyproject.toml` is EOL-equivalent and parsed-TOML-identical to the Git version, not raw-byte identical. No claim is made that the generated wheel ZIP equals a separately cached installation ZIP. The installed two-case chain and five diagnostic stdio probes retain their stated limits.

Live dispatch, hidden/held-out access and paid experiments are outside this run's authorization. Public tasks, poison examples and lint labels are author-seen development material, not independent unseen families. `M5-heldout-v1` is retired from held-out/generalization use; preserved private corpus editions must not be reopened by source authors. A future admitted corpus requires explicit independent custody, semantic label/family review and matching manifest/approval pins. No current product or full normative/platform verdict is inferred.

The remaining sections describe consumer contracts, not blanket execution or acceptance claims. Synthetic/fake-backed regression success does not establish actual provider usage, tokenizer fit, external authority authenticity or billing. No pending gate can be filled by a matching hash alone.

## Exact request-byte fit consumer

Dispatch attribution now uses the counter's one-use
`bind_dispatch_context(phase=..., attempt_id=..., operation_id=...)` callback.
`preflight` requires absent attempt/operation IDs; `pre-send` requires both actual
IDs. Every count consumes its binding, so a retry cannot inherit a prior proof's
attempt authority. Private proof events also retain phase, exact body SHA256 and
checked-at timestamp. Missing legacy attribution remains unknown; it is never
reconstructed from trial IDs or journal proximity.

The admitted live constructor now requires
`manifest.settings.token_fit_approval_sha256_by_model`: exact model IDs mapped
to catalog-artifact typed SHA256 -> external typed approval SHA256. Each approved
arm supplies matching `token_fit_approvals` entries with exactly `approval` and
`approval_sha256`. The approval is the D5 `m5-token-fit-approval-1` record; its
counter/model/settings/catalog/source identities and expiry remain mandatory.
These prospective approvals are not generated by the runner or inferred from
the proof itself. No actual approval, tokenizer or measured count is supplied.

`FitBoundSelector.bind_trial_context` receives the runner's explicit trial,
condition and cell. Before selection it constructs the stable seeded artifact
from the actual presented catalog, verifies exact order and metadata equality,
and chooses its externally pinned fit approval. C2 records trusted normalization;
the source preserves the same per-task order across C0/C1/C2 and models.

`TrialWireCounter` receives the exact HTTP body bytes from the existing controller
at each admission, including send/retry rechecks. It builds a D5 full-wire proof
using only the explicitly approved bytes-only callable, writes the proof to the
private fsynced provider journal, and verifies body/history/trial/turn bindings.
Missing, unknown, changed, expired or exceeding fit evidence blocks dispatch.
The adapter source pin was independently checked by live preflight; catalog
parity is structural only, and fit is not spend authorization, provider billing
verification, interoperability or product acceptance. Proof events bind trial,
turn and actual request-body hash; later custody/reproduction must preserve them.

Offline regression coverage in `tests/contracts/test_wire_fit_consumer.py` uses
public synthetic data and an explicit fake counter for full bytes, altered wire
metadata, silent order repair and failed journaling. It does not establish a real
tokenizer proof or provider request.

The subsequent consumer delta authors an additional regression for one-use
dispatch attribution. Canonical semantic development corpus bytes and explicit
authored episodes now flow through the root loader/runner/publisher. The loader
requires the operator's exact public manifest raw pin, checks all canonical data
files with the producer's bounded parser, then admits shared strict semantic
models and server-owned normalized fixtures. Baseline, diagnostic and control
rows stay separate; every scheduled unsupported observer-fault scenario remains
as an unknown/unsupported row. No fault observation is inferred from its request.

Conformance wheel configuration includes the public semantic source,
normative requirements inventory and all five closed schemas at their fixed
installed `mcpsh/conformance/data/` locations. The installed distribution and
seven packaged resources have now been checked. `server-check` forwards explicit
`--semantic-manifest-sha256` and
`--requirements-manifest-sha256` pins to D6; absent pins stay absent. A hash of the
resource being checked never substitutes for external admission. Disposable and
runtime activation still require the exact explicit request grants.

Acceptance recommendation now receives typed observed rows with the runner's
explicit repeat/platform/model-family fields plus actual outcome/private-row
hashes. Missing legacy metadata stays missing; model families and repeats are not
inferred from IDs, desired designs or other rows. Supplied family-support metadata
can be structurally pinned, but the standalone publisher leaves independent
authentication false and never upgrades a label to confirmed independence.

The optional threshold consumer takes `--threshold-metadata` (exact
`proposal/summary/context` object) and a separate `--threshold-current-inputs`
record. Both require external raw pins; `--threshold-context-sha256` is the
external canonical typed context pin. Optional `--threshold-reviewer` and
`--threshold-integrator` files each require their own raw pin. Admission checks
run before any new experiment dispatch. The private files remain outside the
product tree; only D4's bounded `project_threshold_status` is eligible for the
canonical public projection. Handmade `ApprovedThresholds` in an acceptance
request are rejected. The CLI does not authenticate actors/custody from files:
both confirmation booleans stay false, no floor is invented, and runtime/product
acceptance stays pending. A trusted future admission owner can inject externally
established confirmations into `runner.thresholds.assess_threshold_metadata`;
D4 revalidates all actual inputs before projecting any threshold record.

Private token-fit handoff now uses only D7's capture adapter. For a prospective live
collection, optional `--token-fit-expectations`, `--token-fit-expectations-sha256`
(external raw file pin) and `--token-fit-expectations-typed-sha256` (independently
selected typed authority pin) must be supplied together. Expectation records are
validated before dispatch; their pins are never copied from proof/journal events.
The bounded reader opens only the run's own private `provider-attempts.jsonl`,
preserves JSON object order and every complete event, and rejects a truncated or
over-cap journal without publishing a prefix. The original journal is unchanged.

All actual proof/prepared-request events go to private `token-fit-capture.json`
even when expectations are absent; the captured expectation list is then empty
and fit credit remains unknown. Optional normalized construction passes this
same bundle to `build_edition_payloads(..., token_fit_bundle=...)`. The future
reader uses the separate externally pinned authority's
`token_fit_expectations_sha256`. It never derives that authority from the submitted
proof. Offline reproduction retains the full private lineage and publishes only
the canonical safe status/count/hash projection. Every actual model attempt,
unknown/invalid attempt and scheduled trial without an attempt remains explicit.
Fit-only proof cannot authorize dispatch, establish provider billing or free money.

Fresh runtime UUID/proof/check-time pins normally become knowable after collection.
An original immutable edition captured without independent expectations cannot
gain that authority by changing only its authority file. Later retrospective
expectation selection requires an authorized successor evidence-construction path;
this packet does not mutate original editions or invent that independent selection.
Offline tests do not establish a live captured journal with independently
authorized token-fit expectations or a real authenticated successor.

## Retrospective fit successor writer

Built: `runner/fit_successor.run_fit_successor` and `scripts/eval.py --mode
fit-reverify`, the publisher-side consumer of D7's pure
`plan_fit_reverification` / `build_fit_reverification_payloads`. Required inputs
are the saved parent edition with its raw-pinned EditionAuthority, the
FitReverificationAuthority (raw pin plus independent typed pin, checked by the
planner), raw-pinned full-coverage expectations and the exact raw-pinned original
journal. A receipt is optional but must carry both its raw and typed pins.

- No receipt, or a receipt the planner does not treat as authenticated and
  independently selected: state `pending`; the plan is printed with the uncredited
  `candidate_fit` removed and every fit row left unknown. Nothing is written.
- Pin, identity, source, price or coverage mismatches raise the planner's
  `EvidenceRejected`; nothing is written.
- Ready: the successor is staged in a hidden sibling folder, validated there, and
  only then renamed to `<private-evidence>/<successor_edition_id>/normalized/`
  (the folder name must equal the authority's successor ID; `--edition` is
  refused), beside `fit-plan.json` and a
  `successor-authority.proposed.json` that a trusted caller must still select
  externally. The writer requires `fit-parent.json`, `fit-reverification.json`,
  `token-fit.json` and `EDITION.json`; rejects a successor that reuses the parent
  ID or index; re-reads the staged successor through the existing reader; and
  rehashes the parent root to prove it was not changed. Any failure leaves only
  the hidden staging folder, never the published name. The destination must be
  disjoint from the parent root. The pending console line carries identity and
  counts only, no per-attempt rows.
- Known limit (D7 planner, not this writer): readiness rests on the
  `authenticated` / `independent_selection_confirmed` fields inside the supplied
  authority and receipt plus their external pins. The writer adds no separate
  authentication; trusted custody of those bytes must be established outside it.

Offline regressions include `tests/contracts/test_fit_successor_consumer.py`;
real independently admitted live-successor execution remains pending. CLI flags
never authenticate a receipt; authentication comes only from the externally
selected receipt and authority bytes. No new attempts, charges, dispatch, pre-send
admission, billing claim or public numeric publication is introduced.

Offline dossier source uses `--mode dossier --evidence-root <saved-private-edition>`.
Required metadata flags are `--dossier-authority`, `--dossier-authority-sha256`
(external raw file identity), `--dossier-authority-typed-sha256` (external canonical
typed D4 authority identity), `--acceptance-sources` and its raw
`--acceptance-sources-sha256`. Strict metadata admission happens before D7's edition
reader. The authority embeds the exact D7 EditionAuthority; no edition, candidate,
revision, source, price, custody or confirmation is inferred from narrative fields.

`runner.dossier.assemble_offline_dossier` invokes D4's
`evaluation.acceptance_evidence.assemble_acceptance_dossier` with an explicit
all-false DossierAuthentication and an aware observation time. Optional existing
threshold metadata inputs become the existing strict ThresholdAttachment, retaining
its externally pinned current inputs and raw decisions; actor confirmation stays
false. There is no JSON or CLI switch to authenticate those records. D4 remains
the semantic/acceptance seam owner; D7 owns byte parsing and lineage.

All validated original trials and outcomes are preserved privately, in original
scheduled order. Missing saved trials become explicit unknown view placeholders,
never generated TrialOutcomes or a smaller scheduled denominator. No aggregate
rates or paired samples are recomputed. A fresh immutable publication view keeps
the original manifest and stores the complete private dossier outside the product
tree. Only bounded status/pins/basis/count fields enter the canonical public object.
Replay remains replay; source-only conformance, prices or settlements cannot gain
authenticated live credit. Malformed/pin-mismatched/missing original sources reject
without replacing them with an empty successful edition. Runtime and product
acceptance remain false/pending. Offline coverage is not an authenticated dossier.

Read-only audit publication uses `--mode ledger-audit`, explicit `--ledger`,
`--evidence-root`, `--evidence-authority` plus its external raw `--authority-sha256`,
and `--ledger-authority` plus external raw `--ledger-authority-sha256`. The strict
ledger authority selects the experiment, saved edition index, source, per-model
dated-price snapshots, complete logical table snapshot and snapshot kind; an
immutable-file source also requires its file pin. No expected value is generated
from the submitted DB or report. Source validation/read-only snapshot handling
belongs exclusively to `mcpsh.accounting.report.audit_ledger`.

The root consumer invokes no CostLedger constructor, migration, settlement,
writer or alternate balance law. It preserves the full returned private report
unchanged, with original scheduled edition rows and missing-source placeholders.
The existing canonical `ledger_audit` report allowlist carries the safe public
totals and every supplied operation/attempt/reuse/non-model/dispatch/stop record,
hashing identifiers and retaining cost bases and unknown values. The summary
status never replaces that complete projected report or its denominators.

The CLI passes no billing witnesses: a raw pin on a JSON witness cannot establish
real receipt authentication. A trusted Python admission owner may pass genuinely
established `BillingEvidence` through the existing API; estimates and provider
billing remain separate fields. Snapshot identity does not imply freshness, and
retained unknown liabilities never become available/free budget. Missing/corrupt
or pin-mismatched snapshots reject without an empty successful report. Offline
accounting/audit tests do not authenticate real billing or settle live liabilities.
