"""Explicit read-only audit of CostLedger's existing schema; no I/O on import.

No constructor, migration, settlement, reconciliation or benchmark writer lives
here. Numeric publication belongs solely to D1. SQLite is opened only by the
explicit audit call, under a consistent read transaction, never during imports.
"""

from collections import Counter, defaultdict
from pathlib import Path
import sqlite3
from typing import Literal

from pydantic import Field

from mcpsh.records import typed_hash
from mcpsh.records.models import Record
from mcpsh.evidence.reader import EvidenceRejected, model, read_bounded, strict_json

from . import CostLedger

MAX_ROWS = 60000
MAX_DATABASE_BYTES = 64 * 1024 * 1024
# Exactly the existing CostLedger schema. No new table, cost basis, or balance law.
TABLES = {
    "budget": ("id", "amount"),
    "operations": ("id", "reserved", "status", "metadata"),
    "attempts": ("id", "operation_id", "provider", "model", "status", "cost", "usage"),
    "non_model": ("id", "category"),
    "dispatches": ("attempt_id", "scope"),
    "dispatch_stops": ("reason",),
}


class LedgerAuditAuthority(Record):
    experiment_id: str = Field(min_length=1, max_length=256)
    edition_index_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    # Canonical logical table snapshot, including all unknown/extra rows and holds.
    logical_snapshot_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    price_snapshot_hashes: dict[str, str] = Field(max_length=64)
    snapshot_kind: Literal["read-transaction", "immutable-file"]
    immutable_file_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    billing_evidence_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")


class BillingEvidence(Record):
    """Externally authenticated billing, separate from token-price estimation."""
    attempt_id: str = Field(min_length=1, max_length=256)
    provider: str = Field(min_length=1, max_length=128)
    model_id: str = Field(min_length=1, max_length=256)
    billed_microunits: int = Field(ge=0, le=2**63 - 1)
    receipt_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


def _snapshot(db):
    schema = db.execute("SELECT name,type FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' ORDER BY name").fetchall()
    if schema != sorted((name, "table") for name in TABLES):
        raise EvidenceRejected("ledger schema differs from CostLedger authority")
    result, total, byte_count = {}, 0, 0
    for name, columns in TABLES.items():
        found = tuple(row[1] for row in db.execute(f"PRAGMA table_info({name})"))
        if found != columns:
            raise EvidenceRejected("ledger columns differ from CostLedger authority")
        rows = []
        cursor = db.execute(f"SELECT * FROM {name} ORDER BY 1")
        for row in cursor:
            total += 1
            byte_count += sum(len(value.encode()) if isinstance(value, str) else
                              len(value) if isinstance(value, bytes) else 32 for value in row)
            byte_count += sum(len(column) + 8 for column in columns)
            if total > MAX_ROWS or byte_count > MAX_DATABASE_BYTES:
                raise EvidenceRejected("ledger audit row/byte cap exceeded; no partial audit")
            rows.append(row)
        result[name] = [dict(zip(columns, row, strict=True)) for row in rows]
        if len({row[0] for row in rows}) != len(rows):
            raise EvidenceRejected("duplicate ledger primary identity; no row may be dropped")
    if len(result["budget"]) != 1 or result["budget"][0]["id"] != 1:
        raise EvidenceRejected("ledger budget row absent or duplicated")
    for name, amount in (("budget", "amount"), ("operations", "reserved"), ("attempts", "cost")):
        for row in result[name]:
            value = row[amount]
            if value is None and name == "attempts":
                continue
            if type(value) is not int or not 0 <= value <= 2**63 - 1:
                raise EvidenceRejected("ledger amount type/range invalid")
    for name, columns in TABLES.items():
        for row in result[name]:
            for key in columns:
                if key not in {"amount", "reserved", "cost"} and not (name == "budget" and key == "id"):
                    if type(row[key]) is not str or not row[key] or len(row[key].encode()) > 1024 * 1024:
                        raise EvidenceRejected("ledger text type/size invalid")
    return result


def audit_ledger(path: str | Path, *, edition, authority: LedgerAuditAuthority,
                 billing_evidence: tuple[BillingEvidence, ...] = ()) -> dict:
    """Return a PRIVATE read-only report; expected pins come from external custody.

The logical snapshot pin is over TABLES' complete SELECT * rows ordered by primary
key, with original metadata/usage JSON strings unchanged. A main-file hash alone
does not bind a WAL snapshot. Historical snapshot identity is not freshness.
"""
    authority = model(LedgerAuditAuthority, authority.model_dump(mode="json"))
    index, manifest, trials, _, _ = edition.validate()
    if (authority.edition_index_sha256 != edition.authority.index_sha256
            or authority.experiment_id != index.edition_id
            or authority.source_sha256 != manifest.code_hash):
        raise EvidenceRejected("ledger edition/experiment/source authority mismatch")
    if any(
            type(key) is not str or not 1 <= len(key) <= 256 or type(value) is not str or len(value) != 64
            or any(c not in "0123456789abcdef" for c in value)
            for key, value in authority.price_snapshot_hashes.items()):
        raise EvidenceRejected("externally selected dated price pins required")
    for model_id, pin in authority.price_snapshot_hashes.items():
        price = manifest.prices.get(model_id)
        if not isinstance(price, dict) or price.get("snapshot_hash") != pin:
            raise EvidenceRejected("ledger price selection differs from pinned manifest")
    parsed_billing = tuple(model(BillingEvidence, item.model_dump(mode="json")) for item in billing_evidence)
    if len(parsed_billing) > MAX_ROWS:
        raise EvidenceRejected("billing evidence cap exceeded")
    billing_pinned = (authority.billing_evidence_sha256 is not None and
        typed_hash([item.model_dump(mode="json") for item in parsed_billing]) == authority.billing_evidence_sha256)
    target = Path(path).absolute()
    if not target.is_file() or target.is_symlink() or target.stat().st_size > MAX_DATABASE_BYTES:
        raise EvidenceRejected("explicit existing bounded ledger required")
    # Check all ancestors/reparse points with the established bounded evidence port.
    # For live WAL, this validates the main file but its hash is NOT used as truth.
    main_bytes = read_bounded(target.parent, target.name, MAX_DATABASE_BYTES)
    import hashlib
    immutable = authority.snapshot_kind == "immutable-file"
    wal, shm = Path(str(target) + "-wal"), Path(str(target) + "-shm")
    if immutable:
        if (authority.immutable_file_sha256 is None or wal.exists() or shm.exists()
                or hashlib.sha256(main_bytes).hexdigest() != authority.immutable_file_sha256):
            raise EvidenceRejected("immutable snapshot missing seal or contains live sidecars")
    elif wal.exists() and not shm.exists():
        raise EvidenceRejected("live WAL lacks preexisting shared-memory reader state")
    uri = target.as_uri() + "?mode=ro" + ("&immutable=1" if immutable else "")
    db = None
    try:
        db = sqlite3.connect(uri, uri=True, timeout=1, isolation_level=None)
        db.setlimit(sqlite3.SQLITE_LIMIT_LENGTH, 1024 * 1024)
        db.setlimit(sqlite3.SQLITE_LIMIT_ATTACHED, 0)
        db.execute("PRAGMA query_only=ON")
        db.execute("PRAGMA trusted_schema=OFF")
        before_version = db.execute("PRAGMA data_version").fetchone()[0]
        db.execute("BEGIN")
        snapshot = _snapshot(db)
        # Reuse the sole financial authority's SELECT-only balance law in SAME snapshot.
        budget, settled, committed = CostLedger._totals(db)
        if any(type(value) is not int or not 0 <= value <= 2**63 - 1 for value in (budget, settled, committed)):
            raise EvidenceRejected("ledger totals overflow or violate integer conservation")
        digest = typed_hash(snapshot)
        db.execute("ROLLBACK")
        concurrent = db.execute("PRAGMA data_version").fetchone()[0] != before_version
    except (sqlite3.Error, OSError, ValueError, TypeError, OverflowError, UnicodeError):
        raise EvidenceRejected("ledger snapshot unavailable/corrupt/partial; no numeric report") from None
    finally:
        if db is not None:
            if db.in_transaction:
                db.execute("ROLLBACK")
            db.close()
    return _project(snapshot, edition=edition, trials=trials, authority=authority,
        snapshot_sha256=digest, totals=(budget, settled, committed), concurrent=concurrent,
        billing=parsed_billing, billing_pinned=billing_pinned,
        scheduled_trial_ids=tuple(index.scheduled_trial_ids))


def _project(snapshot, *, edition, trials, authority, snapshot_sha256, totals, concurrent,
             billing, billing_pinned, scheduled_trial_ids):
    diagnostics = []
    # Scheduled is the edition's schedule, not the supplied rows; an absent row is a gap.
    if sorted(trial.outcome.trial_id for trial in trials) != sorted(scheduled_trial_ids):
        diagnostics.append("scheduled_trial_rows_unavailable")
    pinned = snapshot_sha256 == authority.logical_snapshot_sha256
    if not pinned:
        diagnostics.append("logical_snapshot_differs_from_external_pin")
    operations = {row["id"]: row for row in snapshot["operations"]}
    attempts = {row["id"]: row for row in snapshot["attempts"]}
    dispatches = {row["attempt_id"]: row for row in snapshot["dispatches"]}
    parents, reuse, reuse_keys = {}, [], Counter()
    for trial in trials:
        outcome = trial.outcome
        if trial.reuse is not None:
            reference = trial.reuse
            key = (reference.source_index_sha256, reference.source_trial_id)
            reuse_keys[key] += 1
            reuse.append({"trial_id": outcome.trial_id, "task_id": outcome.task_id,
                "source_index_sha256": reference.source_index_sha256,
                "source_trial_id": reference.source_trial_id,
                "original_cost_microunits": reference.original_cost_microunits,
                "original_cost_basis": reference.original_cost_basis,
                "new_charge_microunits": 0, "independent_new_sample": False})
            continue
        if outcome.cost_microunits is None:
            diagnostics.append("scheduled_trial_cost_unknown")
        if outcome.model_id is not None and not trial.model_attempts:
            diagnostics.append("scheduled_model_trial_without_attempts")
        cost_by_id = {row.attempt_id: row for row in trial.accounting}
        for attempt in trial.model_attempts:
            if attempt.attempt_id in parents:
                raise EvidenceRejected("duplicate evidence parent identity")
            parents[attempt.attempt_id] = (outcome, attempt, cost_by_id[attempt.attempt_id])
    if any(count > 1 for count in reuse_keys.values()):
        diagnostics.append("duplicate_reuse_reference_no_new_charge_or_sample_credit")
    if len({item.attempt_id for item in billing}) != len(billing):
        diagnostics.append("duplicate_billing_evidence")
        billing_pinned = False
    receipts = {item.attempt_id: item for item in billing}
    if set(receipts) - set(attempts):
        diagnostics.append("unallocated_billing_evidence")
    rows = []
    for identity, attempt in attempts.items():
        reasons = []
        operation = operations.get(attempt["operation_id"])
        metadata = strict_json(operation["metadata"].encode()) if operation else None
        usage = strict_json(attempt["usage"].encode())
        if not isinstance(usage, dict) or (metadata is not None and not isinstance(metadata, dict)):
            raise EvidenceRejected("ledger metadata/usage shape invalid")
        if operation is None:
            reasons.append("missing_operation_parent")
        expected_price = authority.price_snapshot_hashes.get(attempt["model"])
        price_ok = bool(metadata and expected_price and metadata.get("price_snapshot_hash") == expected_price)
        if not price_ok:
            reasons.append("missing_or_mismatched_original_price_pin")
        parent = parents.get(identity)
        allocated = False
        if parent is None:
            reasons.append("unallocated_attempt_parent_unknown")
        else:
            outcome, model_attempt, cost = parent
            allocated = (model_attempt.trial_id == outcome.trial_id and model_attempt.turn_id is not None
                and (attempt["provider"], attempt["model"], attempt["operation_id"]) ==
                (model_attempt.provider_id, model_attempt.requested_model_id, cost.operation_id))
            if not allocated:
                reasons.append("trial_turn_model_operation_parent_mismatch")
            if attempt["cost"] != cost.cost_microunits:
                reasons.append("recorded_cost_differs_from_edition")
            if typed_hash(usage) != typed_hash(model_attempt.usage):
                reasons.append("recorded_usage_differs_from_edition")
            if (cost.settlement_reference != identity or model_attempt.settlement_reference != identity):
                reasons.append("settlement_reference_not_bound_to_attempt")
            if cost.price_snapshot_hash is not None and cost.price_snapshot_hash != expected_price:
                reasons.append("edition_original_price_pin_mismatch")
            if metadata and (metadata.get("provider"), metadata.get("model")) != (attempt["provider"], attempt["model"]):
                reasons.append("operation_provider_model_mismatch")
            if cost.raw_request_sha256 is not None and metadata and metadata.get("request_hash") != cost.raw_request_sha256:
                reasons.append("operation_request_pin_mismatch")
        if attempt["status"] not in {"prepared", "sent", "unknown", "settled", "retryable"}:
            reasons.append("unknown_attempt_state")
        if attempt["status"] != "prepared" and identity not in dispatches:
            reasons.append("attempt_missing_dispatch_intent")
        if attempt["cost"] is None:
            reasons.append("unknown_liability_reservation_retained")
        elif attempt["status"] not in {"settled", "retryable"}:
            reasons.append("amount_and_attempt_state_disagree")
        receipt = receipts.get(identity)
        billed = bool(billing_pinned and receipt is not None and
            (receipt.provider, receipt.model_id) == (attempt["provider"], attempt["model"]))
        # Receipt amounts remain separate; never rewrite a dated ledger estimate.
        basis = "dated-price-estimate" if (attempt["cost"] is not None and price_ok and allocated
            and parent[2].cost_basis == "dated-price-estimate"
            and parent[2].cost_microunits == attempt["cost"]) else "unknown"
        if receipt is not None and not billed:
            reasons.append("billing_evidence_unpinned_or_mismatched")
        rows.append({"attempt_id": identity, "operation_id": attempt["operation_id"],
            "provider": attempt["provider"], "model_id": attempt["model"], "ledger_status": attempt["status"],
            "dispatch_recorded": identity in dispatches, "dispatch_scope": dispatches.get(identity, {}).get("scope"),
            "trial_id": parent[0].trial_id if allocated else None,
            "task_id": parent[0].task_id if allocated else None,
            "turn_id": parent[1].turn_id if allocated else None,
            "recorded_microunits": attempt["cost"], "recorded_cost_basis": basis,
            "price_snapshot_hash": metadata.get("price_snapshot_hash") if metadata else None,
            "usage": usage, "unknown_liability": attempt["cost"] is None,
            "billed_microunits": receipt.billed_microunits if billed else None,
            "billing_receipt_sha256": receipt.receipt_sha256 if billed else None,
            "billing_basis": "provider-billed" if billed else "unknown",
            "state": "verified-snapshot-row" if pinned and not reasons else "unknown",
            "reasons": reasons})
    missing = sorted(set(parents) - set(attempts))
    if missing:
        diagnostics.append("edition_attempts_missing_from_ledger")
    extra_dispatch = sorted(set(dispatches) - set(attempts))
    if extra_dispatch:
        diagnostics.append("dispatches_missing_attempt_parent")
    if any(row["category"] not in {"replay", "keyword", "abstain"} for row in snapshot["non_model"]):
        diagnostics.append("unknown_non_model_category")
    operation_rows = []
    by_operation = defaultdict(list)
    for child in snapshot["attempts"]:
        by_operation[child["operation_id"]].append(child)
    for identity, operation in operations.items():
        children = by_operation[identity]
        known = sum(row["cost"] for row in children if row["cost"] is not None)
        unknown = sum(row["cost"] is None for row in children)
        reasons = []
        if operation["status"] not in {"reserved", "inflight", "finished", "overrun", "cancelled"}:
            reasons.append("unknown_operation_state")
        if operation["status"] != "finished":
            reasons.append("open_reservation_unsettled")
        if known > operation["reserved"]:
            reasons.append("known_cost_exceeds_reservation")
        if operation["status"] == "finished" and unknown:
            reasons.append("finished_operation_hides_unknown_liability")
        metadata = strict_json(operation["metadata"].encode())
        if not isinstance(metadata, dict):
            raise EvidenceRejected("operation metadata shape invalid")
        operation_rows.append({**operation, "metadata": metadata,
            "known_recorded_microunits": known, "unknown_attempts": unknown,
            "reservation_retained": operation["status"] != "finished", "reasons": reasons})
    budget, settled, committed = totals
    if committed > budget:
        diagnostics.append("committed_over_budget")
    complete = pinned and not diagnostics and not missing and all(not row["reasons"] for row in rows + operation_rows)
    return {"schema_version": 1, "scope": "read-only-authoritative-ledger-snapshot", "complete": complete,
        "experiment_id": authority.experiment_id, "source_sha256": authority.source_sha256,
        "edition_index_sha256": edition.authority.index_sha256,
        "logical_snapshot_sha256": snapshot_sha256, "snapshot_pin_matches": pinned,
        "snapshot_kind": authority.snapshot_kind, "concurrent_change_observed": concurrent,
        "freshness_claim": False, "database_mutated": False, "publication_performed": False,
        "totals": {"budget_microunits": budget, "recorded_known_microunits": settled,
            "committed_microunits": committed, "available_microunits": max(0, budget - committed),
            "unknown_attempts": sum(row["unknown_liability"] for row in rows),
            "cost_basis": "recorded-ledger-amounts-not-provider-billing"},
        "operations": operation_rows, "attempts": rows, "reuse": reuse,
        "scheduled_trials": len(scheduled_trial_ids),
        "trial_audit": [{"trial_id": trial.outcome.trial_id, "task_id": trial.outcome.task_id,
            "model_id": trial.outcome.model_id, "attempt_ids": list(trial.outcome.model_attempt_ids),
            "recorded_outcome_cost_microunits": trial.outcome.cost_microunits,
            "recorded_outcome_cost_basis": trial.outcome.cost_basis,
            "reused_evidence": trial.reuse is not None,
            "independent_new_sample": False if trial.reuse is not None else None,
            "ledger_missing_attempt_ids": [identity for identity in trial.outcome.model_attempt_ids if identity not in attempts]}
            for trial in trials],
        "non_model": snapshot["non_model"], "dispatches": snapshot["dispatches"],
        "dispatch_stops": snapshot["dispatch_stops"],
        "missing_attempt_ids": missing, "unallocated_dispatch_attempt_ids": extra_dispatch,
        "diagnostics": diagnostics, "empirical_verdict": "pending", "product_verdict": "pending"}


def project_ledger_audit_status(audit: dict) -> dict:
    """Safe status/count/hash view for D1; no new cost arithmetic or publication."""
    attempts, operations, reuse = audit["attempts"], audit["operations"], audit["reuse"]
    return {"version": "m5-ledger-audit-status-1",
        "status": "verified-snapshot-only" if audit["complete"] is True else "unknown",
        "complete": audit["complete"] is True,
        "edition_index_sha256": audit["edition_index_sha256"], "source_sha256": audit["source_sha256"],
        "logical_snapshot_sha256": audit["logical_snapshot_sha256"],
        "snapshot_pin_matches": audit["snapshot_pin_matches"], "snapshot_kind": audit["snapshot_kind"],
        "concurrent_change_observed": audit["concurrent_change_observed"],
        "scheduled_trials": audit["scheduled_trials"], "attempts_total": len(attempts),
        "unknown_liabilities": sum(row["unknown_liability"] for row in attempts),
        "unallocated_attempts": sum(row["trial_id"] is None for row in attempts),
        "missing_attempts": len(audit["missing_attempt_ids"]), "operations_total": len(operations),
        "retained_reservations": sum(row["reservation_retained"] for row in operations),
        "reuse_references": len(reuse), "non_model_events": len(audit["non_model"]),
        "cost_basis": "recorded-ledger-amounts-not-provider-billing",
        "cost_bases": sorted({row["recorded_cost_basis"] for row in attempts}),
        "billed_attempts": sum(row["billing_basis"] == "provider-billed" for row in attempts),
        "freshness_claim": False, "database_mutated": False, "runtime_authorized": False,
        "independent_product_acceptance": "pending"}
