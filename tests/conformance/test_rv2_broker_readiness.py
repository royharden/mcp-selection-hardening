"""Deterministic startup transport faults; no real child or host resource is touched."""

import json
import time

import pytest

from mcpsh import broker


class Connection:
    def __init__(self, context):
        self.context = context
        self.closed = False

    def close(self):
        self.closed = True

    def poll(self, timeout):
        self.context.polls.append(timeout)
        # The child is ready after the ordinary call cap but within startup's cap.
        return self.context.delay < timeout

    def recv_bytes(self, maximum):
        return self.context.raw


class Process:
    def __init__(self, context, args):
        self.context = context
        self.args = args
        self.running = False
        self.terminated = False

    def start(self):
        self.running = True
        ready = {
            "ready": True,
            "platform_scope": "synthetic-memory",
            "trial_id": self.args[2],
            "epoch": self.args[3],
        }
        ready.update(self.context.changes)
        self.context.raw = json.dumps(ready).encode()
        if self.context.malformed:
            self.context.raw = b"{"

    def is_alive(self):
        return self.running

    def join(self, timeout):
        pass

    def terminate(self):
        self.running = False
        self.terminated = True


class Context:
    def __init__(self, changes=None, delay=6, malformed=False):
        self.changes = changes or {}
        self.delay = delay
        self.malformed = malformed
        self.polls = []
        self.connections = []

    def Pipe(self, duplex):
        pair = Connection(self), Connection(self)
        self.connections.extend(pair)
        return pair

    def Process(self, target, args, daemon):
        self.process = Process(self, args)
        return self.process


def install(monkeypatch, context):
    def get_context(method):
        assert method == "spawn"
        return context

    monkeypatch.setattr(broker.multiprocessing, "get_context", get_context)


def test_ready_after_call_cap_is_accepted_before_broker_is_exposed(monkeypatch):
    """what_bug_this_catches: startup import latency charged against five-second tool budget."""
    context = Context(delay=6)
    install(monkeypatch, context)
    instance = broker.FixtureBroker("rv2-public-startup")
    try:
        assert context.polls == [30.0]
        assert broker.CALL_DEADLINE_SECONDS == 5.0
        assert instance.alive
    finally:
        instance.close(force=True)


@pytest.mark.parametrize(
    "changes",
    [
        {"ready": False},
        {"ready": 1},
        {"platform_scope": "filesystem-posix"},
        {"trial_id": "other-trial"},
        {"epoch": "other-epoch"},
        {"epoch": None},
    ],
    ids=["not-ready", "coerced-ready", "scope", "trial", "epoch", "missing-epoch"],
)
def test_mismatched_startup_is_rejected_and_owned_resources_closed(monkeypatch, changes):
    """what_bug_this_catches: stale/cross-trial readiness or truthy nonboolean admitted."""
    context = Context(changes=changes)
    install(monkeypatch, context)
    with pytest.raises(broker.BrokerUnavailable):
        broker.FixtureBroker("rv2-public-startup")
    assert context.process.terminated
    assert all(connection.closed for connection in context.connections)


@pytest.mark.parametrize(
    "delay,malformed", [(31, False), (0, True)], ids=["startup-timeout", "invalid-json"]
)
def test_missing_or_malformed_startup_closes_owned_resources(monkeypatch, delay, malformed):
    """what_bug_this_catches: timeout/decode failure leaving an owned child and pipes behind."""
    context = Context(delay=delay, malformed=malformed)
    install(monkeypatch, context)
    with pytest.raises(broker.BrokerUnavailable):
        broker.FixtureBroker("rv2-public-startup")
    assert context.process.terminated
    assert all(connection.closed for connection in context.connections)


def test_expired_call_still_uses_call_deadline_after_ready(monkeypatch):
    """what_bug_this_catches: extending tool execution budget along with startup budget."""
    context = Context(delay=6)
    install(monkeypatch, context)
    instance = broker.FixtureBroker("rv2-public-startup")
    try:
        with pytest.raises(broker.BrokerUnavailable, match="deadline"):
            instance.request("read", "rv2-call", time.monotonic() - 1, source_id="app")
        assert context.polls == [30.0]
    finally:
        instance.close(force=True)
