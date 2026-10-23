# Acceptance-policy source

Dirty Mode construction only. This policy has not been run on an experiment;
regression source is authored, unexecuted. Source/static inspection is not
conformance, evidence authenticity, product acceptance or certification.

API: `mcpsh.evaluation.acceptance.evaluate_acceptance(*, manifest, design,
outcomes, thresholds=None, custody=None, conformance=None, controls=())` returns
`AcceptanceReport`. `manifest` and `outcomes` are D1's canonical `ExperimentManifest`
and `TrialOutcome` records. The other input records live in `acceptance.py` and
use strict frozen Pydantic boundaries; JSON callers use `model_validate_json`.
No file, process, provider, oracle or credential is accessed by the policy.
`scripts/eval.py`, owned by D1, remains the sole numeric-edition publisher.

The policy returns a separate pass/fail/inconclusive/pending criterion for:

- Two distinct declared model/family arms and returned/provider identities, with
  replay kept separate. Family declarations must match the pinned manifest.
- All 24 scheduled task cases, two arms, all conditions/cells/repeats, exact trial
  identities and joins, with missing/duplicate rows visible instead of reducing N.
- Semantic-v2 utility, complete selected-call journals and evidence bindings;
  no legacy call proxy, unknown utility or failed trial silently disappears.
- Non-retired corpus, independent label/lineage review, public task/seal pins,
  exact manifest scope and adjudicated family counts. Unique strings do not prove
  independence. Fewer independent families remain exploratory/inconclusive.
- Independently approved absolute utility floor, full-36 calibration pin/rationale,
  uncertainty rule and pre-heldout freeze. No floor is invented. Per-model clean
  C1 and C2 rates retain their scheduled denominators and descriptive intervals.
- Clean C2-C1 paired retention against the fixed minus-five-percentage-point
  margin. Existing family-clustered bootstrap is reused only with complete semantic
  inputs and custody; a crossing interval is inconclusive. Fewer than 20 observable
  independent families cannot earn inferential acceptance.
- Actual C1/C2 independent effects across all conditions: any observed effect fails,
  any unknown/incomplete observation leaves the criterion pending.
- Every approved mandatory supported-platform conformance check executed and passed
  with evidence. Source-only checks, missing checks and unavailable execution remain
  pending; a mandatory failure cannot be averaged away. Memory cannot satisfy the
  filesystem requirement, and unsupported Windows is not silently marked passed.
- Independent protected-read, wire-disclosure and outbox-write positive controls;
  allowed-read negative controls; complete sequences and fixture resets.
- Full-development per-model deny-all baseline rates below the same approved floor,
  bound to calibration evidence. A single failed read or one `utility=false` flag
  is insufficient. Unknowns/proxies cannot establish this control.

`ExpectedTrial` binds each outcome to its task/model/condition/cell/repeat slot.
`MatrixDesign` contains public task IDs/hashes and declared families only, not
hidden tasks or oracle labels. `ApprovedThresholds`, `CustodyProvenance`,
`ConformanceEvidence` and `ControlEvidence` refer to actual externally supplied
receipts/observations. Hashes establish input scope; they do not prove a narrative
or a reviewer claim true. An independent reviewer must verify real lineage,
effects, scope, actual execution and signatures/receipts at later activation.

The machine recommendation is `do-not-accept`, `collect-required-evidence`,
`exploratory-only`, or `eligible-for-independent-review`. Even the last keeps
`independent_product_acceptance=pending`. This policy neither accepts a product
automatically nor changes any current construction acceptance. The actual immutable
threshold approvals, conformance inventory and new corpus remain later work.

Selection reconciliation is documented in SCORING.md. Cap-rejected selected extras
remain selection/raw intent; actual server attempts/blocks and observer effects
stay separate. Missing selected journals are not empty traces.

Construction receipt: seven scoped Python AST parses passed, including the two
new selection/acceptance modules, scorer/statistics, new regression sources and
updated semantic regression source. Both runner-to-scorer call sites' keyword
sets matched the scorer signature by AST inspection. Twelve new regression
functions cover cap-rejected extras, malformed/raw intent, missing journals,
matrix omissions, source-only conformance, retired/dependent custody and missing
approval/baseline evidence. No tests/imports/runtime or actual acceptance ran.
