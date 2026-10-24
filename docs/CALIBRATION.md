# Development pilot and calibration drafts

Constructed under Dirty Mode: source and regression authoring with static review
only. No pilot, tokenizer, provider, scorer, test, app or backend was executed.
Private/retired data is neither read nor copied. This package does not establish
prices, model identity, family independence, token fit, utility or readiness.

The pilot inventory is the public 36-case development set: six declared classes
with six cases each. `plan_pilot` deterministically selects one task ID per class
(or validates an explicit selection), preserving the full inventory hash. It does
not claim these six classes or repeated public templates are unseen families.
Two `DraftArm` slots may have unresolved provider/family/model identities; `None`
means pending, and supplied equal model/family identities reject the draft.

The typed `DraftPilotManifest` is a **draft-no-dispatch** contract, deliberately
distinct from `ExperimentManifest`. It is not usable as live admission. Initial
N=3, all three metadata conditions and C0/C1/C2 cells give 324 planned task-runs
for six cases/two arms. Three turns and one allowed retry per request reserve up
to 1,944 planned attempts. Planned token caps are placeholders requiring actual
full-wire tokenization later. No dated price, spend receipt, absolute floor or
authorization is filled in. Planned counts are not measured results.

`summarize_pilot(manifest, observations)` accepts typed, explicitly supplied
`PilotObservation` records from future immutable development evidence. Each row
joins an arm/task/condition/cell/repeat, carries a journal digest, and separates
request attempts, failed transport attempts, returned outputs, semantic-invalid
outputs and tri-state semantic utility. Incorrect task answers are not automatically
malformed model outputs. Retries count in request denominators. Duplicate,
out-of-schedule and inconsistent counter/identity records reject. Live/replay
rows cannot be pooled; replay diagnostics never satisfy live pilot evidence.
Hashes bind bytes supplied by a caller; they do not authenticate that a run happened.

Per arm, semantic invalidity uses invalid returned outputs / all returned outputs;
transport failure uses failed attempts / all attempts. Utility variance is the
descriptive plug-in Bernoulli variance `p(1-p)` over known semantic utility
judgments, available with at least two observations. Its use is a pilot repeat
diagnostic; it is not independent-sample inference over clustered cases. Missing
rows, unknown utility and zero denominators are explicit. Wilson intervals reuse
the existing statistics module and describe known utility observations only.

Strict thresholds, compared as exact fractions:

- Either arm above 10% semantic-invalid outputs proposes N=5 for **both** arms.
- Either arm with utility variance above 0.20 likewise proposes N=5 for both.
- Either arm above 5% failed transport attempts requires repair/re-pilot first.
  Repeat inflation cannot substitute for repair; any N=5 proposal remains pending.
- Exactly 10%, 0.20 or 5% does not cross the corresponding strict threshold.
- Partial evidence may reveal a repair need/repeat proposal but cannot establish
  completed pilot collection. No automatic reduction from N=5 occurs.

Unknown utility, empty evidence and missing scheduled trials never become successful
empty samples. `supplied-complete` means only schedule/utility completeness of
caller-supplied data; it is neither independent evidence acceptance nor dispatch
authorization. Full live identity/version/cost/provider and experiment gates remain
with the existing runner/admission owner. Pilot summaries never fill those gates.

`threshold_proposal` always keeps `absolute_utility_floor=null`, an approval-needed
status, pending uncertainty rule, and no independent approval. Establish the floor
only after all 36 public development cases, task difficulty and no-tool utility,
baseline/deny-all contrast and independent approval. Poor utility never lowers the
floor automatically. The selected paired retention margin remains five percentage
points, with its interval rule pending the required approval.

Future CLI surface (do not execute while Dirty Mode is open):

```text
python scripts/pilot.py plan --development-manifest-sha256 MANIFEST_RAW_SHA256 [--arms draft-arms.json --arms-sha256 RAW_SHA256]
python scripts/pilot.py summarize --plan draft.json --plan-sha256 RAW_SHA256 \
  --observations observed-dev.json --observations-sha256 RAW_SHA256
```

`plan` reads only fixed public development inventory paths; there is no hidden
oracle path flag. An omitted arm file leaves explicit unresolved slots.
`summarize` requires raw pins for external draft/evidence bytes and emits only
an approval-needed proposal and state/action. Its numeric summary is available
through the library for the existing `scripts/eval.py` publication owner. Optional
`--out` creates a new `.json` draft only under `evaluation/experiments/`, never
overwriting a file. This command does not publish metric editions or README results.

D1 integration API: import `plan_pilot`, `planned_caps`, `summarize_pilot`, and
`threshold_proposal` from `mcpsh.calibration`. Inputs/outputs use the strict records
exported there. A JSON draft round-trips through
`DraftPilotManifest.model_validate_json`; public evidence rows use
`PilotObservation.model_validate_json`. `evaluation/thresholds/PROPOSAL.template.json`
has the exact `ThresholdProposal` field shape with no observations fabricated.
Future CLI routing remains D1-owned; this package changes no shared CLI or runner.

Construction receipt: focused source/logic/API inspection, six stdlib AST parses
(four calibration modules, pilot script and regression source), and static JSON
template-to-AST-field-set comparison passed. Fourteen regression functions were
authored, including strict-boundary, duplicate/missing evidence, replay/live
separation and floor-approval cases. None was run. No real draft run results or
provider/price identities were produced. Planned arithmetic is source design only.

## Full-36 protocol continuation

`plan_development_calibration(*, pilot, development_cases,
development_input_sha256, pilot_summary=None)` ties the six pilot cases to the
exact same public 36-case inventory/classification and to a pinned pilot summary.
Repeat proposals are carried forward without automatically lowering N. The result
is an approval-needed `DevelopmentProtocolPlan`; neither its construction nor its
`dispatch_authorized=false` field grants runtime authority.

`ProtocolSettings` pins conditions, cells, three turns, six calls, one retry,
semantic-v2 utility, seed, repeat count and keyword/abstain/deny-all baselines.
Derived schedules are rechecked against their exact settings digest, including
duplicates, omissions and model-copy tampering. At N=3 the full public development
design has 1,944 planned model task-runs plus 648 deterministic control task-runs
(2,592 planned slots). These are design counts, not executions. Control repetitions
per arm provide comparable denominators; they are explicitly non-model replay,
not extra live arms or independent observations.

`CalibrationOutcome` binds an actual future scored `TrialOutcome` and its hash,
the settings hash, a scheduled slot and an external evidence digest. Supplied
attempt/output/semantic-invalid counters use `PilotObservation` and must join the
same model slot, utility and identity. They never infer semantic invalidity from an
incorrect task answer. Legacy utility may be preserved in a snapshot, but it never
becomes semantic evidence. Live usage cannot be labeled non-model/free.

`summarize_development(plan, records, failures=())` retains the complete planned
denominator with explicit supplied/missing, failed, proxy, unknown-utility,
unknown-cost and incomplete-observation counts. Grouping covers every task class,
model arm, condition, cell and deterministic control. Known-only Wilson diagnostics
remain labeled alongside the all-scheduled utility lower bound. Duplicate/outside
slots, corrupted outcome hashes, changed settings and mixed live/replay model rows
are rejected. Deterministic replay controls remain separate from live model rows.

Pilot and full-development summaries now share one exact `repeat_rule`: >10%
semantic-invalid outputs or variance >0.20 proposes N=5 for both arms; >5% transport
failure takes priority and requires repair/re-pilot. Unknown counters and utility
stay visible. Retries remain in the attempt denominator. Complete collection is
not evidence acceptance, and replay diagnostics cannot trigger live floor review.

Clean C2-C1 paired intervals reuse the existing family-clustered statistics.
`retention_decision` returns pending for missing intervals and inconclusive for
unestablished/fewer-than-20 independent families or a crossing interval. Public
development template labels are never assumed independent: the protocol deliberately
does not promote them into an unseen-family pass. This does not block independent
development difficulty/floor review; its rationale remains separate from primary
held-out retention inference.

`propose_full36_thresholds(summary)` emits a `FullDevelopmentProposal` bound to
plan/settings/outcome/summary hashes. Its floor and independent approval stay null,
and its status is always approval-needed. An actual approved floor is a separate
`ApprovedThresholds` record consumed by the acceptance policy, frozen and authorized
through the required independent review. A proposal is never converted automatically,
and poor utility never lowers an approved floor.

The future injectable API is `execute_development_protocol(plan, runner=,
admission=, clock=)`. There is no default runner, provider or backend. Even a fake
runner requires a later explicit `ProtocolAdmission`, Dirty Mode closure, exact
plan/settings/pilot pins and complete pilot evidence. Live use additionally needs
real distinct arm identities, a live pilot and separate model-dispatch approval.
The injected clock checks grant expiry before each scheduled callback. A wrong-slot
return, exception, failed/unknown evidence or unsettled cost stops further callbacks;
remaining slots are explicitly not-dispatched failures, without fabricated outcomes.

D1 must inject its already-admitted runner and continue actual per-attempt budget,
retry, identity, expiry, protocol and fixture checks. This wrapper does not replace
those gates or authorize a real provider merely because a receipt string exists.
All callbacks and clock reads remain unexecuted during this construction work.
`ProtocolRun` and summaries remain in-memory; only D1's `scripts/eval.py` may publish
numeric editions. No shared runner/record/CLI source was edited in this package.

Full-36 construction receipt: seven focused AST parses and two constructor-field
comparisons passed without product imports. Ten new regression functions were
authored for complete plans, settings/outcome tampering, proxy/unknown semantics,
unauthorized injected callbacks, wrong-slot evidence, expiry and retention decisions.
The shared pilot repeat rule received focused logic inspection after extraction.
No test, runner, clock callback, provider, fixture, service or database was executed;
no measured outcomes or approved floor was generated. Exact-session exports were
refreshed for both designated destinations. Source backups stay uncommitted.

## External threshold-approval binding

`mcpsh.calibration.approvals` supplies `validate_threshold_approval`,
`project_approved_thresholds`, and `project_threshold_status`. This is pure source:
it reads no files/keys/accounts, creates no approval, observes no current clock,
dispatches no model and publishes no numeric edition. No actual threshold, reviewer,
INT authorization or corpus custody was established during construction.

`ThresholdInputs` binds exact full36 plan/summary/outcomes/settings, source closure,
canonical two-arm provider/model/family scope, semantic-v2 definition, later heldout
manifest and corpus-seal hashes. `ThresholdContext` binds the expected qualified
Integrator identity, source/proposal/data authors, custody state, seal/start times
and optional externally pinned prior floor. Pass `current_inputs` independently
from actual current producer/admission inputs. Any change invalidates old metadata;
copying the old context back as 'current' is not input verification.

Reviewer and INT `ThresholdDecision` bytes are bounded strict JSON, reject duplicate
keys and extra fields, and require **raw byte** SHA256 pins supplied by an external
owner. Both bind the canonical typed context digest; INT metadata additionally binds
the exact raw reviewer bytes. Reviewer independence is checked against declared
authors; role IDs must be canonical qualified registry identities. INT cannot be the
proposal author or reviewer. Registry alias/ancestry and actual actor authority
remain external checks; strings alone cannot authenticate a person or agent.

`expected_context_sha256` is explicitly the **canonical typed** context digest;
reviewer/INT expected hashes are **raw byte** digests. The model configuration digest
uses canonical `ThresholdModel` records sorted by arm slot (`model_scope_hash`).
These different hash domains must not be substituted for one another.

Matching pins mean metadata is bound, not authorized. An `ExternalConfirmation`
record also cannot authenticate itself. `external_confirmation_verified=False`
and `fresh_custody_confirmed=False` are the defaults. A trusted caller must establish
real reviewer/INT authorization, exact actor/byte bindings and actual fresh custody
through its approved external channel before asserting either confirmation. No
signing system, private key, guessed authorization or self-issued approval is added.

The validator checks full36 semantic/control/task-class denominators, unknowns,
legacy proxies, failures, costs, observation completeness and repeat/transport
decisions. The absolute floor is read only from matching explicit external decisions;
neither proposal nor poor utility supplies one. The full-development deny-all rate
for each arm must fall below that floor. Automatic lowering against a pinned prior
floor is rejected; an explicit successor lowering requires both independent reviewer
and INT to identify the prior approval and explicitly approve the change.

Missing floor/metadata/verification leaves pending status. Stale, future-dated,
self-authored, wrong-scope or changed-input metadata is invalid. `now` is an aware
caller-supplied observation, never a hidden clock read. A corpus can be sealed
**before** threshold review. Retired or author-exposed corpus identity always requires
fresh custody; later approval cannot unretire it. Actual heldout start, when supplied,
must follow review, INT decision and external confirmation. No later experiment may
reuse a stale validation timestamp instead of rechecking admission.

Only a fully eligible validation can project the canonical `ApprovedThresholds`
record, and projection revalidates all raw inputs rather than trusting a handmade
'ready' result. The result is eligible for **separate runtime admission** only;
runtime authorization stays false and independent product acceptance stays pending.
D1 still owns actual source/lock/provider/budget/custody gates and `scripts/eval.py`
publication. No real approval artifact is generated by this source package.

Construction receipt: two focused AST parses and the approval-to-acceptance
constructor-field check passed. Thirteen new synthetic regressions were authored
for missing/stale/changed/self-authored metadata, unauthenticated pins, retired
custody, seal/review ordering, explicit floor/deny-all contrast, prohibited automatic
lowering, legacy evidence and duplicate JSON. No tests, imports, bootstrap,
statistics, approval service or runtime were executed.
