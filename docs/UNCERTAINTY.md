# Exact design and paired family uncertainty

Source constructed under Dirty Mode. No audit, bootstrap, statistics, application
import or regression test was executed on an experiment. Regression functions are
source only. A machine recommendation is never independent product acceptance.

`evaluation.design.audit_schedule(design, scored_outcomes=, observed_rows=)` accepts
a strict `ScheduleDesign`, all canonical `TrialOutcome` records, and all explicit
private `ObservedTrial` metadata. `ScheduledTrial` binds trial/task/model/condition/
cell/**repeat**. The design declares task families, two distinct model families,
platform, mode and a seed. Observed rows supply their actual repeat, platform,
model family, outcome digest and evidence digest. No value is parsed from a trial
ID, copied from an expected slot to repair evidence, or guessed from ordering.

The audit checks the entire Cartesian design, scheduled trial/coordinate uniqueness,
unexpected and missing scored/private rows, scoped identities/families/cells/repeats,
platform/mode and scored/private content hashes. Missing metadata is incomplete;
wrong/duplicate evidence is invalid. Failed scheduled rows stay present. It reports
raw and unique supplied counts against the unchanged expected denominator, legacy
utility bases, unknown utility, incomplete journals and observations. Report digests
bind supplied bytes/records; they do not authenticate an actual run or reviewer.

`evaluation.statistics.compare_paired_families(design, scored_outcomes=,
observed_rows=, before=, after=, metric="utility_success", models=None,
conditions=None, family_support=None, expected_family_support_sha256=None,
independence_authenticated=False)` returns typed `PairedComparison`.

The full schedule is audited before any comparison. Explicit model/condition
subsets choose a question without dropping missing evidence from the full audit.
Each pair matches the same task, model, condition and explicit repeat across the
two cells. Every matched stratum remains within its task-family cluster. The
family's mean paired difference receives one equal-weight contribution; all its
models/conditions/repeats move together during resampling. Repeats, calls and task
variants do not become additional independent families.

The existing percentile-bootstrap math is shared, with version
`paired-family-cluster-v2`, the design-pinned seed, stable sorted family order and
exactly 10,000 whole-family resamples. The 2.5%/97.5% empirical quantiles and paired
point difference are returned. Degenerate zero/constant differences remain valid
descriptive results. Nothing was resampled during source construction.

Invalid/incomplete schedule evidence, missing pair members, unknown metric values,
failed paired trials or legacy semantic-utility substitutes withhold the comparison
point/interval. No pair is silently removed to lower N. Selection and intent require
complete selected journals; effect comparisons require observable independent effects.
Actual failed/unknown/legacy counts remain alongside the scheduled pair denominator.

Wilson intervals are separately labeled **descriptive**, with known counts, unknown
members and an all-scheduled success lower bound. They are not the clustered paired
interval and cannot establish zero effects in the presence of unknown observations.

Unique family labels do not prove independence. `FamilySupport` binds family IDs,
reviewer/evidence and exact design hash. Its expected pin is a caller-supplied hash
of the canonical typed support record. A matching pin is only pinned metadata.
Only a trusted caller's separate `independence_authenticated=True`, after real
review/authorization, can credit supported observable families. This library does
not perform that external authentication. Fewer than 20 supported observable
families, or any remaining unsupported family, stays exploratory; no unsupported
cluster is discarded to reach a favorable independent N.

Compatibility `family_count` fields credit only supported observable independence,
not unique labels. Descriptive aggregation has no independence evidence, so it
reports zero credited families plus explicit `observed_family_labels`; the strict
comparison exposes its resampled label count separately from supported families.

The old `paired_family_bootstrap` signature remains available, but outcome-only
legacy input has no explicit actual repeat/platform evidence. It returns pending
pairing/incomplete intervals instead of claiming family inference. Supply the
explicit design/observed contract to use the new engine; no trial-ID inference is
introduced for old artifacts. Existing D1/D7 consumers must carry evidence metadata.

`evaluate_acceptance` now accepts optional `observed_rows`, `family_support`,
`expected_family_support_sha256` and `independence_authenticated`. Its `MatrixDesign`
also accepts `task_family_by_id`. Missing actual row metadata or expected family
mapping keeps matrix/retention criteria pending. Wrong row metadata fails integrity.
Custody/floor/conformance and independent product review remain separate requirements.

Construction receipt: five scoped AST parses and the acceptance/comparison
keyword-seam inspection passed. Twelve new analytic, degenerate, duplicate,
missing-pair, failure/unknown/legacy, deterministic-order and independence regressions
were authored. No tests, imports, statistics, bootstrap or runtime were executed.
