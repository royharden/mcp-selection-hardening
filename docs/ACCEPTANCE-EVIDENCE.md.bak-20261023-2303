# Verified edition admission into acceptance

Dirty Mode construction only. No reader, dossier, evaluator, statistics, bootstrap,
test, probe, ledger or actual approval was executed while authoring this package.
No hidden corpus or private prior adjudication was read or reused.

`evaluation.acceptance_evidence.assemble_acceptance_dossier(edition, *, authority,
expected_authority_sha256, sources, authentication=None,
threshold_attachment=None, now=None)` is the pure D1/D7 consumer interface.

`edition` must be D7's actual `VerifiedEdition` type. D7's `.validate()` and
`inspect_edition()` own raw parsing, source pins, token-fit/selection/observer joins
and structural rejection. There is no second reader, filesystem discovery, rescore
or fallback zero-row edition. Rejected D7 evidence stays rejected. Every parsed
original scored row, including failures and unknowns, remains unchanged in the
private dossier. This module does not republish provider/final/oracle plaintext.

`DossierAuthority` is externally selected and separately pinned by its canonical
typed SHA256. Its `edition` is the full D7 `EditionAuthority` (raw index/manifest,
candidate, revision, mode, platform and all source pins). The additional typed
manifest digest is distinct from the raw manifest digest. Optional design,
schedule, family-support, custody, conformance/report/inventory, controls, dated
price, settlement and threshold pins are never filled from the submitted edition
as a way to authorize itself.

`AcceptanceSources` holds strict typed attachments. Externally pinned MatrixDesign
and ScheduleDesign must agree on the original ordered schedule, declared family
mapping, source task hash, mode/platform, repeats and seed. Actual repeats come only
from D7 trial records. Actual platform metadata comes from observer records; missing
observer/repeat metadata remains unavailable. Historical zero/out-of-domain repeat
ordinals are not silently rebased. No trial ID is parsed to repair missing data.

All `DossierAuthentication` flags default **false**. Matching bytes establish
integrity, not actual role, custody, truthful execution, family independence,
conformance, official prices or paid usage. A trusted admission owner must confirm
those facts through its real external channel. A narrative or self-seal is not a
substitute for the required pins and confirmations.

Conformance needs both D7's externally scoped per-probe producer report and D6's
externally pinned normative requirements audit. The complete required probe set,
actual document hashes, executed canonical checks, fixed inventory coverage and
platform must agree. D7's `full_platform_credit=false` alone cannot be promoted to
suite credit. Missing/ill-shaped reports remain pending. Caller controls require
external source pins/confirmation; control roles are not inferred merely from an
effect appearing in an ordinary task.

Dated `PriceAuthority` records must match the actual manifest's exact typed
per-model snapshots and rates. A dated estimate is not a billing receipt.
`SettlementAuthority` binds each actual attempt's settlement reference, original
usage hash and typed D7 accounting-row hash to an external witness. Missing usage,
reservation, receipt or cost remains unknown; no apparent success is made free by
substituting zero. Replay records never acquire live-model, heldout-family,
conformance or paid-usage credit from metadata flags.

`ThresholdAttachment` references the existing full36 proposal/summary/context/input
records and exact external reviewer/INT bytes. Source, semantic definition, actual
model scope, corpus and typed manifest must match the admitted edition. Only the
existing `calibration.approvals` validator can project an externally authorized
floor. Both confirmation flags remain false by default; this consumer creates no
floor or approval. Changed threshold source/settings/corpus cannot reuse old pins.

The result includes attributable admission criteria and, when design inputs are
admitted, the existing `evaluate_acceptance` recommendation. Any missing authority
or evidence keeps the combined recommendation pending; invalid identity/source
pins fail admission. Independent product acceptance always stays pending and
runtime authorization always stays false. D1 alone publishes numeric editions.

Construction receipt: two scoped AST parses and the dossier-to-acceptance keyword
seam check passed. Nine new regression functions use explicit mocked D7 contracts
for external pin/source drift, replay promotion, failed unknown-cost retention,
missing scheduled failure rejection and altered threshold source. No reader,
dossier, evaluator, statistics, bootstrap, tests or runtime were executed.
