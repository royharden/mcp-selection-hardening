"""M5 local SQLite cost authority; source only until runtime activation.

Unknown usage retains its reservation across cancellation/restart. Integer
microunits avoid floating-price arithmetic. No database is opened on import.
"""

from contextlib import contextmanager
import json
from pathlib import Path
import sqlite3
from typing import Any, Iterator


class BudgetDenied(RuntimeError):
    pass


def _amount(value: int) -> int:
    if type(value) is not int or value < 0:
        raise ValueError("cost amounts must be nonnegative integer microunits")
    return value


class CostLedger:
    def __init__(self, path: str | Path, budget_microunits: int):
        self.path = str(path)
        if not self.path or self.path == ":memory:":
            raise ValueError("persistent on-disk ledger path is required")
        budget_microunits = _amount(budget_microunits)
        with self._transaction() as db:
            db.execute("CREATE TABLE IF NOT EXISTS budget (id INTEGER PRIMARY KEY CHECK(id=1), amount INTEGER NOT NULL)")
            db.execute("CREATE TABLE IF NOT EXISTS operations (id TEXT PRIMARY KEY, reserved INTEGER NOT NULL, status TEXT NOT NULL, metadata TEXT NOT NULL)")
            db.execute("CREATE TABLE IF NOT EXISTS attempts (id TEXT PRIMARY KEY, operation_id TEXT NOT NULL REFERENCES operations(id), provider TEXT NOT NULL, model TEXT NOT NULL, status TEXT NOT NULL, cost INTEGER, usage TEXT NOT NULL)")
            db.execute("CREATE TABLE IF NOT EXISTS non_model (id TEXT PRIMARY KEY, category TEXT NOT NULL)")
            db.execute("CREATE TABLE IF NOT EXISTS dispatches (attempt_id TEXT PRIMARY KEY REFERENCES attempts(id), scope TEXT NOT NULL)")
            db.execute("CREATE TABLE IF NOT EXISTS dispatch_stops (reason TEXT PRIMARY KEY)")
            row = db.execute("SELECT amount FROM budget WHERE id=1").fetchone()
            if row is None:
                db.execute("INSERT INTO budget VALUES (1,?)", (budget_microunits,))
            elif row[0] != budget_microunits:
                raise BudgetDenied("persistent budget differs; an explicit successor ledger is required")

    @contextmanager
    def _transaction(self) -> Iterator[sqlite3.Connection]:
        db = sqlite3.connect(self.path, timeout=5, isolation_level=None)
        try:
            db.execute("PRAGMA foreign_keys=ON")
            db.execute("BEGIN IMMEDIATE")
            yield db
            db.execute("COMMIT")
        except BaseException:
            if db.in_transaction:
                db.execute("ROLLBACK")
            raise
        finally:
            db.close()

    @staticmethod
    def _totals(db: sqlite3.Connection) -> tuple[int, int, int]:
        budget = db.execute("SELECT amount FROM budget WHERE id=1").fetchone()[0]
        settled = db.execute("SELECT COALESCE(SUM(cost),0) FROM attempts WHERE cost IS NOT NULL").fetchone()[0]
        # An open operation consumes its whole reservation, including known costs;
        # do not add settled costs twice for open operations.
        active = db.execute("SELECT COALESCE(SUM(reserved),0) FROM operations WHERE status!='finished'").fetchone()[0]
        finished_cost = db.execute("SELECT COALESCE(SUM(a.cost),0) FROM attempts a JOIN operations o ON a.operation_id=o.id WHERE o.status='finished'").fetchone()[0]
        return budget, settled, active + finished_cost

    def reserve(self, operation_id: str, amount_microunits: int, metadata: dict[str, Any] | None = None) -> str:
        amount_microunits = _amount(amount_microunits)
        if not operation_id:
            raise ValueError("operation_id required")
        encoded = json.dumps(metadata or {}, sort_keys=True, allow_nan=False)
        with self._transaction() as db:
            previous = db.execute("SELECT reserved,metadata,status FROM operations WHERE id=?", (operation_id,)).fetchone()
            if previous:
                if previous[:2] != (amount_microunits, encoded) or previous[2] == "finished":
                    raise BudgetDenied("operation reuse has different reservation or is already finished")
                self._assert_clear(db, operation_id)
                return operation_id
            self._assert_clear(db)
            budget, _, committed = self._totals(db)
            if committed + amount_microunits > budget:
                raise BudgetDenied("reservation would exceed persistent budget")
            db.execute("INSERT INTO operations VALUES (?,?,?,?)", (operation_id, amount_microunits, "reserved", encoded))
        return operation_id

    @staticmethod
    def _assert_clear(db: sqlite3.Connection, current_operation_id: str | None = None,
                      prepared_attempt_id: str | None = None) -> None:
        if db.execute("SELECT 1 FROM dispatch_stops LIMIT 1").fetchone():
            raise BudgetDenied("durable dispatch stop requires explicit reconciliation")
        budget, _, committed = CostLedger._totals(db)
        if committed > budget or db.execute("SELECT 1 FROM operations WHERE status='overrun'").fetchone():
            raise BudgetDenied("known overrun blocks dispatch")
        if current_operation_id is not None:
            row = db.execute("SELECT status FROM operations WHERE id=?", (current_operation_id,)).fetchone()
            if row is None or row[0] not in {"reserved", "inflight"}:
                raise BudgetDenied("current reservation is absent or not dispatchable")
        if prepared_attempt_id is not None:
            row = db.execute("SELECT operation_id,status FROM attempts WHERE id=?", (prepared_attempt_id,)).fetchone()
            if row != (current_operation_id, "prepared"):
                raise BudgetDenied("only the current unsent prepared attempt may be exempted")
        if db.execute("SELECT 1 FROM operations WHERE status!='finished' AND (? IS NULL OR id!=?) LIMIT 1",
                      (current_operation_id, current_operation_id)).fetchone():
            raise BudgetDenied("prior unsettled reservation blocks dispatch")
        if db.execute("SELECT 1 FROM attempts WHERE cost IS NULL AND (? IS NULL OR id!=?) LIMIT 1",
                      (prepared_attempt_id, prepared_attempt_id)).fetchone():
            raise BudgetDenied("prior unknown/inflight usage blocks dispatch")

    def assert_dispatch_allowed(self, *, current_operation_id: str | None = None,
                                prepared_attempt_id: str | None = None) -> None:
        with self._transaction() as db:
            self._assert_clear(db, current_operation_id, prepared_attempt_id)

    def dispatch_count(self, scope: str) -> int:
        with self._transaction() as db:
            return db.execute("SELECT COUNT(*) FROM dispatches WHERE scope=?", (scope,)).fetchone()[0]

    def authorize_dispatch(self, operation_id: str, attempt_id: str, *, scope: str,
                           max_requests: int) -> None:
        """Durably count a send intent before network; ambiguity consumes the cap."""
        if not scope or type(max_requests) is not int or max_requests < 1:
            raise BudgetDenied("explicit dispatch scope and request cap required")
        with self._transaction() as db:
            self._assert_clear(db, operation_id, attempt_id)
            count = db.execute("SELECT COUNT(*) FROM dispatches WHERE scope=?", (scope,)).fetchone()[0]
            if count >= max_requests:
                raise BudgetDenied("durable model request cap reached")
            db.execute("INSERT INTO dispatches VALUES (?,?)", (attempt_id, scope))
            db.execute("UPDATE attempts SET status='sent' WHERE id=?", (attempt_id,))

    def halt_dispatch(self, reason: str) -> None:
        if not isinstance(reason, str) or not reason:
            raise ValueError("dispatch stop reason required")
        with self._transaction() as db:
            db.execute("INSERT OR IGNORE INTO dispatch_stops VALUES (?)", (reason,))

    def begin_attempt(self, operation_id: str, attempt_id: str, provider: str, model: str) -> None:
        if not all((attempt_id, provider, model)):
            raise ValueError("exact attempt/provider/model identity required")
        with self._transaction() as db:
            self._assert_clear(db, operation_id)
            row = db.execute("SELECT status,metadata FROM operations WHERE id=?", (operation_id,)).fetchone()
            if row is None or row[0] not in {"reserved", "inflight"}:
                raise BudgetDenied("active reservation required before dispatch")
            budget, _, committed = self._totals(db)
            if committed > budget or row[0] == "overrun":
                raise BudgetDenied("known budget overrun blocks further dispatch")
            attempts = db.execute("SELECT id,status FROM attempts WHERE operation_id=?", (operation_id,)).fetchall()
            if attempts:
                # One transient retry at most, settled/explicitly marked first.
                if len(attempts) >= 2 or attempts[0][1] != "retryable":
                    raise BudgetDenied("only one explicit transient retry is permitted")
            db.execute("INSERT INTO attempts VALUES (?,?,?,?,?,?,?)", (attempt_id, operation_id, provider, model, "prepared", None, "{}"))
            db.execute("UPDATE operations SET status='inflight' WHERE id=?", (operation_id,))

    def settle(self, attempt_id: str, cost_microunits: int | None, usage: dict[str, Any] | None = None) -> None:
        if cost_microunits is not None:
            _amount(cost_microunits)
        with self._transaction() as db:
            row = db.execute("SELECT operation_id,cost,status FROM attempts WHERE id=?", (attempt_id,)).fetchone()
            if row is None:
                raise ValueError("unknown attempt")
            if row[1] is not None:
                if row[1] != cost_microunits:
                    raise ValueError("settlement is immutable")
                return
            reserved = db.execute("SELECT reserved FROM operations WHERE id=?", (row[0],)).fetchone()[0]
            known = db.execute("SELECT COALESCE(SUM(cost),0) FROM attempts WHERE operation_id=? AND id!=?", (row[0], attempt_id)).fetchone()[0]
            status = "unknown" if cost_microunits is None else "settled"
            db.execute("UPDATE attempts SET cost=?,status=?,usage=? WHERE id=?", (cost_microunits, status, json.dumps(usage or {}, sort_keys=True, allow_nan=False), attempt_id))
            if cost_microunits is not None and known + cost_microunits > reserved:
                # Preserve actual billing and expand commitment; stop any further
                # reservation if this exceeds budget. Never erase known overrun.
                db.execute("UPDATE operations SET reserved=?,status='overrun' WHERE id=?", (known + cost_microunits, row[0]))

    def allow_transport_retry(self, attempt_id: str, reason: str) -> None:
        if reason not in {"transient_transport", "rate_limit"}:
            raise BudgetDenied("semantic failures are never retryable")
        with self._transaction() as db:
            row = db.execute("SELECT operation_id,status FROM attempts WHERE id=?", (attempt_id,)).fetchone()
            if row is None or row[1] != "settled":
                raise BudgetDenied("only known settled transient usage permits retry")
            count = db.execute("SELECT COUNT(*) FROM attempts WHERE operation_id=?", (row[0],)).fetchone()[0]
            if count != 1:
                raise BudgetDenied("retry allowance exhausted")
            db.execute("UPDATE attempts SET status='retryable' WHERE id=?", (attempt_id,))

    def finish(self, operation_id: str) -> None:
        with self._transaction() as db:
            if db.execute("SELECT 1 FROM operations WHERE id=?", (operation_id,)).fetchone() is None:
                raise ValueError("unknown operation")
            if db.execute("SELECT COUNT(*) FROM attempts WHERE operation_id=? AND cost IS NULL", (operation_id,)).fetchone()[0]:
                raise BudgetDenied("unknown/inflight costs retain their reservations")
            db.execute("UPDATE operations SET status='finished' WHERE id=?", (operation_id,))

    def cancel(self, operation_id: str) -> None:
        """Cancellation is not evidence of zero billing; hold unknown costs."""
        with self._transaction() as db:
            row = db.execute("SELECT status FROM operations WHERE id=?", (operation_id,)).fetchone()
            if row is None:
                raise ValueError("unknown operation")
            if row[0] != "finished":
                db.execute("UPDATE operations SET status='cancelled' WHERE id=?", (operation_id,))

    def record_non_model(self, event_id: str, category: str = "replay") -> None:
        if category not in {"replay", "keyword", "abstain"}:
            raise ValueError("non-model category required")
        with self._transaction() as db:
            db.execute("INSERT INTO non_model VALUES (?,?)", (event_id, category))

    def summary(self) -> dict[str, Any]:
        with self._transaction() as db:
            budget, settled, committed = self._totals(db)
            unknown = db.execute("SELECT COUNT(*) FROM attempts WHERE cost IS NULL").fetchone()[0]
            return {"budget_microunits": budget, "settled_microunits": settled, "committed_microunits": committed, "available_microunits": max(0, budget - committed), "unknown_attempts": unknown, "over_budget": committed > budget, "non_model_events": db.execute("SELECT COUNT(*) FROM non_model").fetchone()[0]}
