"""Authored only: attribution/control dispatch without creating any processes."""

import pytest

from mcpsh.conformance import ConformanceRequest
from mcpsh.conformance.channel import InheritedControl, verify_reply
from mcpsh.conformance.host_control import dispatch


def reply():
    return {"schema_version": 1, "nonce": "owned", "child_pid": 123,
            "sequence": 1, "command": "identity", "payload": {"server_instance_id": "one"}, "error": None}


@pytest.mark.parametrize("field,value", [("nonce", "other"), ("child_pid", 456),
    ("sequence", 2), ("command", "exercise")])
def test_other_child_or_stale_control_reply_is_rejected(field, value):
    # what_bug_this_catches: a second server or old reply satisfies an owned probe.
    value_reply = reply()
    value_reply[field] = value
    with pytest.raises(ValueError):
        verify_reply(value_reply, nonce="owned", child_pid=123, sequence=1, command="identity")


def test_unapproved_request_never_creates_pipe(monkeypatch):
    # what_bug_this_catches: merely constructing an unapproved conformance request
    # allocates OS control resources before admission.
    def forbidden():
        raise AssertionError("pipe opened before activation")

    monkeypatch.setattr("mcpsh.conformance.channel.os.pipe", forbidden)
    with pytest.raises(ValueError):
        InheritedControl(ConformanceRequest())


def test_dispatch_uses_exact_existing_control_instance():
    # what_bug_this_catches: instrumentation is sourced from a replacement server.
    class Core:
        def wait_for_occupancy(self, **kwargs):
            return {"active": 4, "queued": 16, "instance": "actual-instance"}

    result = dispatch(Core(), "wait_for_occupancy", {"active": 4, "queued": 16, "timeout": 1}, {})
    assert result["instance"] == "actual-instance"
    assert result["active"] == 4 and result["queued"] == 16


def test_dispatch_refuses_path_or_pid_target():
    # what_bug_this_catches: control transport becomes an arbitrary host actuator.
    with pytest.raises(ValueError):
        dispatch(object(), "exercise", {"hook": "posix-symlink", "path": "/etc/passwd"}, {})
    with pytest.raises(ValueError):
        dispatch(object(), "hold_execution", {"pid": 456}, {})
