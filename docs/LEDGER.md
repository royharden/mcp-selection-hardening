# Read-only authoritative ledger audit

`mcpsh.accounting.report.audit_ledger(path, *, edition, authority,
billing_evidence=())` returns a private report object. D1's `scripts/eval.py`
remains the sole numeric publisher. This port never constructs `CostLedger`,
creates or migrates tables, reserves, settles, cancels, releases, dispatches,
reconciles, or writes an experiment result. No database is opened on import.

The caller explicitly supplies an existing ledger and `VerifiedEdition`, plus a
closed `LedgerAuditAuthority` selecting experiment ID, edition index SHA, original
source SHA, per-model dated-price snapshot hashes and a logical snapshot SHA.
Those pins must be selected through independent authorized custody. A fresh hash
computed from submitted data is an identity measurement, not its own authority.
No default path or latest-ledger discovery exists.

`snapshot_kind='read-transaction'` uses SQLite URI `mode=ro`, `query_only`, disabled
trusted schema, and one `BEGIN` read snapshot for all six existing CostLedger
tables and its SELECT-only `_totals` law. No competing balance calculation or
database schema is introduced. Raw metadata/usage JSON strings remain unchanged
in the logical seal, including all unknown, unmatched, cancelled and extra rows.
The logical SHA is `typed_hash` of the table-name mapping to complete rows ordered
by primary key, column names exactly as declared in `report.TABLES`. It is not a
hash of the main SQLite file: committed WAL content belongs to the snapshot.

`snapshot_kind='immutable-file'` requires a separately sealed immutable file SHA
and absence of WAL/shared-memory sidecars. The file must remain immutable in its
custody during the audit. Live WAL reading requires preexisting shared-memory
reader state; missing sidecars fail closed rather than silently treating the main
file as complete. Normal SQLite read transactions can participate in existing
shared-memory reader coordination; they do not mutate ledger financial state.
Neither mode claims filesystem race conformance or current-state freshness.
Concurrent-change detection is diagnostic; rows and totals remain from one
historical snapshot. No database reader was invoked during source construction.

The audit reuses CostLedger's authoritative budget/known/committed totals. Unknown
attempt amounts remain `None` with reservation holds and explicit counts. Known
subtotals are not full cost when liabilities remain unknown. Cancelled operations
retain their stored reservations. Schema corruption, missing tables, byte/row caps
or invalid amount types reject the audit without publishing a partial numeric
report. Valid but unpinned snapshots retain rows as unknown. Conservation and
parent diagnostics never repair or erase ledger records.

Each attempt joins actual edition trial, turn, provider, model, operation, usage,
request/price pins and settlement reference. Extra attempts remain unallocated;
missing ledger attempts remain explicit in every scheduled trial's audit row.
`scheduled_trials` counts the edition's own `scheduled_trial_ids`, not the rows
supplied. If the supplied rows differ from that schedule (missing or duplicated),
the audit adds the diagnostic `scheduled_trial_rows_unavailable` and is not complete.
The offline audit/dossier views report `scored_trials` as null, since neither scores.
Reused evidence preserves its original cost basis/reference with zero new charge
and no independent sample credit; repeated reuse is diagnosed rather than summed
as new billing. Model/task grouping is available from these parented rows, without
another benchmark aggregator or publisher.

A `settled` ledger row is not proof of a provider invoice. Matching original dated
prices and parent evidence permit `dated-price-estimate`. Optional separately
pinned `BillingEvidence` binds attempt/provider/model, invoice amount and receipt
SHA. Its billed amount stays separate from the original ledger amount, including
when they differ. Missing, duplicate or mismatched billing evidence remains
unknown. No provider account or billing endpoint is accessed.

The canonical public projector supports `ledger_audit` with safe hashes, status,
amount bases, denominators and aliased parents. It omits raw usage, metadata,
receipt documents, approval objects, bodies and history. The private report is
retained for diagnostics; public projection is not independent product acceptance.

Regression SOURCE covers readonly/no-writer behavior, corrupt/partial snapshots,
concurrent WAL changes, unknown cancellation holds, missing/extra parents,
source/price/experiment pin drift, duplicate reuse, immutable sidecar confusion,
and estimated versus billed amounts. Dirty Mode validation is AST/whitespace and
focused source review only. Tests and all DB/runtime paths remain unexecuted.
