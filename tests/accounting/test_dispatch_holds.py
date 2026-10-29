"""Ledger regression SOURCE; no database was opened to validate these tests."""

import pytest

from mcpsh.accounting import BudgetDenied, CostLedger


def test_only_exact_current_prepared_attempt_is_exempt(tmp_path):
    """what_bug_this_catches: a legitimate pre-send reserve self-blocking dispatch."""
    ledger = CostLedger(tmp_path / "cost.sqlite", 100)
    ledger.reserve("op", 20)
    ledger.begin_attempt("op", "a1", "fake", "fake-model")
    ledger.assert_dispatch_allowed(current_operation_id="op", prepared_attempt_id="a1")
    with pytest.raises(BudgetDenied):
        ledger.assert_dispatch_allowed()
    with pytest.raises(BudgetDenied):
        ledger.assert_dispatch_allowed(current_operation_id="op", prepared_attempt_id="wrong")
    ledger.authorize_dispatch("op", "a1", scope="trial", max_requests=1)
    with pytest.raises(BudgetDenied):
        ledger.assert_dispatch_allowed(current_operation_id="op", prepared_attempt_id="a1")


def test_cancellation_and_restart_preserve_unknown_hold(tmp_path):
    """what_bug_this_catches: clearing a pending charge by cancellation or reopening SQLite."""
    path = tmp_path / "cost.sqlite"
    ledger = CostLedger(path, 100)
    ledger.reserve("op", 20)
    ledger.begin_attempt("op", "a1", "fake", "fake-model")
    ledger.authorize_dispatch("op", "a1", scope="trial", max_requests=2)
    ledger.settle("a1", None)
    ledger.cancel("op")
    reopened = CostLedger(path, 100)
    assert reopened.summary()["committed_microunits"] == 20
    with pytest.raises(BudgetDenied):
        reopened.reserve("different", 1)
    with pytest.raises(BudgetDenied):
        reopened.finish("op")
    with pytest.raises(BudgetDenied):
        reopened.allow_transport_retry("a1", "transient_transport")


def test_scope_request_count_survives_controller_restart(tmp_path):
    """what_bug_this_catches: resetting an in-memory request counter with a new controller."""
    path = tmp_path / "cost.sqlite"
    ledger = CostLedger(path, 100)
    ledger.reserve("op", 20)
    ledger.begin_attempt("op", "a1", "fake", "fake-model")
    ledger.authorize_dispatch("op", "a1", scope="trial", max_requests=1)
    ledger.settle("a1", 3)
    ledger.finish("op")
    reopened = CostLedger(path, 100)
    reopened.reserve("op2", 20)
    reopened.begin_attempt("op2", "a2", "fake", "fake-model")
    with pytest.raises(BudgetDenied):
        reopened.authorize_dispatch("op2", "a2", scope="trial", max_requests=1)
    assert reopened.dispatch_count("trial") == 1


def test_durable_semantic_stop_cannot_be_cleared_by_new_operation(tmp_path):
    """what_bug_this_catches: ignoring a known-cost identity failure after selector restart."""
    path = tmp_path / "cost.sqlite"
    ledger = CostLedger(path, 100)
    ledger.halt_dispatch("identity_drift")
    with pytest.raises(BudgetDenied):
        CostLedger(path, 100).reserve("op", 1)
