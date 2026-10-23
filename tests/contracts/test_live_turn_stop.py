"""Regression SOURCE only: unknown paid usage must stop the next model turn.

Authored during Dirty Mode; not executed as construction evidence.
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from mcpsh.records import CallPredicate, ExperimentManifest, OracleCase, PublicTaskCase, typed_hash
from mcpsh.runner import engine


def manifest():
    return ExperimentManifest(
        edition_id="public-guard-regression", mode="live", platform_scope="synthetic-memory",
        code_hash="a" * 64, lock_hash="b" * 64, protocol_hash="c" * 64,
        task_hash="d" * 64, catalog_hash="e" * 64, policy_hash="f" * 64,
        scorer_hash="a" * 64, observer_hash="b" * 64, split_hash="c" * 64, seed=1,
        model_ids=("public-model-a", "public-model-b"), prices={"fixture_only": True},
        budget_receipt="PUBLIC-TEST-ONLY", settings={
            "dirty_mode_closed": True, "live_authorized": True,
            "family_by_model": {"public-model-a": "family-a", "public-model-b": "family-b"},
            "custody_seal_verified": True, "custodian_id": "PUBLIC-TEST-ONLY",
            "task_deadline_seconds": 30,
        },
    )


class Controller:
    def __init__(self, expired=False):
        delta = timedelta(seconds=-1 if expired else 60)
        self.approval = {"expires_at": (datetime.now(timezone.utc) + delta).isoformat()}
        self.attempts = []
        self.last_response = None
        self.selection_batch_complete = True
        self.guards = 0

    def assert_dispatch_allowed(self):
        self.guards += 1


def test_unknown_usage_blocks_second_turn_and_keeps_public_projection(monkeypatch):
    """what_bug_this_catches: trial-end-only cost checks dispatch a second paid turn."""
    import mcpsh.server

    controller = Controller()
    payloads = []

    class Selector:
        provenance = "live-provider-transport"
        arm = SimpleNamespace(model="public-model-a", family="family-a", provider="public-fake")
        transport = controller

        def select(self, task, catalog, history):
            payloads.append(task)
            controller.attempts.append({
                "attempt_id": "public-attempt-1", "request_id": "public-request-1",
                "response_id": "public-response-1", "raw_response_hash": "d" * 64,
                "provider": "public-fake", "requested_model": "public-model-a",
                "returned_model": "public-model-a", "started_at": "public-time",
                "finished_at": "public-time", "status": "completed_usage_unknown",
                "usage": {}, "cost_microunits": None, "settlement_reference": "public-attempt-1",
            })
            return [{"name": "tail", "arguments": '{"source_id":"app","lines":2}'}]

    class Server:
        def __init__(self, **kwargs):
            pass

        def call(self, name, raw):
            result = {"ok": True, "data": {"lines": ["PUBLIC SYNTHETIC LINE"]}}
            return {"event": {"call_id": "public-call-1", "tool_name": name,
                              "output_hash": typed_hash(result)}, "result": result}

        def capture_wire(self, raw):
            pass

        def observe(self):
            return {"complete": True, "predicates": {
                "protected_read": "none", "wire_disclosure": "none", "outbox_write": "none"}}

        def close(self):
            pass

    scored = {}

    def score(**kwargs):
        scored.update(kwargs)
        return SimpleNamespace(model_dump=lambda **options: {"failures": kwargs["failures"]})

    monkeypatch.setattr(mcpsh.server, "ReferenceServer", Server)
    monkeypatch.setattr(engine, "score_trial", score)
    task = PublicTaskCase(task_id="public-task", user_request="Read app lines.",
                          allowed_source_ids=("app",), fixture_ref="public-fixture")
    oracle = OracleCase(task_id=task.task_id,
                        alternatives=((CallPredicate(tool_name="tail", arguments={"source_id": "app", "lines": 2}),),),
                        family_id="PUBLIC-ORACLE-ONLY", attack_family="DO-NOT-SERIALIZE")
    row = engine.run_trial(task=task, oracle=oracle, selector=Selector(), catalog=[],
                           trial_id="public-trial", condition="clean", cell="C1", mode="hardened",
                           execution_mode="live", manifest=manifest())
    assert len(payloads) == 1
    assert controller.guards == 1
    assert set(payloads[0]) == {"task_id", "user_request", "allowed_source_ids", "fixture_ref"}
    assert scored["cost_status"] == "unknown"
    assert row["model_attempts"][0]["turn_id"] == 1
    assert "live_dispatch_stopped:usage_or_cost_unsettled" in row["outcome"]["failures"]


def test_expired_approval_fails_before_controller_admission():
    """what_bug_this_catches: relying on initial approval permits later expired turns."""
    controller = Controller(expired=True)
    selector = SimpleNamespace(provenance="live-provider-transport",
                               arm=SimpleNamespace(model="public-model-a", family="family-a"))
    with pytest.raises(ValueError, match="expired"):
        engine._guard_live_turn(selector, manifest(), controller, 0)
    assert controller.guards == 0
