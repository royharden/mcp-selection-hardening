"""Windows launcher seam: inspect commands without launching a host or reading secrets."""

import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from mcpsh.conformance import ConformanceRequest, channel, stdio

pytestmark = pytest.mark.skipif(os.name != "nt", reason="Windows interpreter redirection contract")


def capture(monkeypatch, tmp_path, *, virtual=True, base=None):
    captured = {}

    class Control:
        def __init__(self, request):
            captured["control"] = self
            self.closed = False

        def child_arguments(self):
            return ["--synthetic-control", "owned"], {}

        def close(self):
            self.closed = True

    def popen(command, **options):
        captured.update(command=command, options=options)
        raise OSError("deliberate pre-spawn failure")

    actual = getattr(sys, "_base_executable", sys.executable) if base is None else base
    monkeypatch.setattr(
        stdio,
        "sys",
        SimpleNamespace(
            executable=str(tmp_path / "redirector.exe"),
            prefix="venv",
            base_prefix="base" if virtual else "venv",
            _base_executable=actual,
        ),
    )
    monkeypatch.setattr(
        stdio,
        "os",
        SimpleNamespace(
            name="nt",
            pathsep=os.pathsep,
            environ={"SYSTEMROOT": "synthetic-system", "UNTRUSTED_TEST": "synthetic-value"},
        ),
    )
    monkeypatch.setattr(
        stdio,
        "sysconfig",
        SimpleNamespace(get_path=lambda scheme: str(tmp_path / "synthetic-site")),
    )
    monkeypatch.setattr(
        stdio, "importlib", SimpleNamespace(util=SimpleNamespace(find_spec=lambda name: object()))
    )
    monkeypatch.setattr(channel, "InheritedControl", Control)
    monkeypatch.setattr(stdio, "subprocess", SimpleNamespace(Popen=popen, PIPE=-1, DEVNULL=-3))
    return captured


def request():
    return ConformanceRequest(
        tracks=("stdio",),
        runtime_authorized=True,
        disposable_authorized=True,
        approval_id="rv2-public-bootstrap",
    )


def test_windows_venv_uses_actual_interpreter_and_unique_site_paths(monkeypatch, tmp_path):
    """what_bug_this_catches: a venv redirector PID differs from the verified control peer."""
    captured = capture(monkeypatch, tmp_path)
    with pytest.raises(OSError, match="deliberate"):
        stdio.StdioSession(request(), "stdio", SimpleNamespace(semantic_case_id=None))
    command = captured["command"]
    assert command[0] == str(Path(sys._base_executable).resolve())
    assert command[1] == "-c"
    assert "site.addsitedir" in command[2]
    assert "run_module('mcpsh.conformance.stdio_host'" in command[2]
    assert json.loads(command[3]) == [str(tmp_path / "synthetic-site")]
    assert command[4:6] == ["--synthetic-control", "owned"]
    assert captured["control"].closed


def test_native_interpreter_keeps_module_launch_without_venv_bootstrap(monkeypatch, tmp_path):
    """what_bug_this_catches: forcing Windows venv bootstrap into the ordinary interpreter path."""
    captured = capture(monkeypatch, tmp_path, virtual=False)
    with pytest.raises(OSError):
        stdio.StdioSession(request(), "stdio", SimpleNamespace(semantic_case_id=None))
    assert captured["command"][1:3] == ["-m", "mcpsh.conformance.stdio_host"]


def test_launch_environment_is_allowlisted_and_uses_no_shell(monkeypatch, tmp_path):
    """what_bug_this_catches: inherited environment or shell dispatch entering host setup."""
    captured = capture(monkeypatch, tmp_path)
    with pytest.raises(OSError):
        stdio.StdioSession(request(), "stdio", SimpleNamespace(semantic_case_id=None))
    options = captured["options"]
    assert options["shell"] is False
    assert set(options["env"]) == {"SYSTEMROOT", "PYTHONPATH"}
    assert "UNTRUSTED_TEST" not in options["env"]


def test_missing_actual_interpreter_refuses_before_control_allocation(monkeypatch, tmp_path):
    """what_bug_this_catches: unavailable actual interpreter weakens exact PID verification."""
    captured = capture(monkeypatch, tmp_path, base=str(tmp_path / "missing-base.exe"))
    with pytest.raises(stdio.BackendUnavailable, match="actual Windows interpreter unavailable"):
        stdio.StdioSession(request(), "stdio", SimpleNamespace(semantic_case_id=None))
    assert "control" not in captured and "command" not in captured


def test_installed_root_equal_to_site_path_still_initializes_site_once(monkeypatch, tmp_path):
    """what_bug_this_catches: wheel-root deduplication skips pywin32 .pth initialization."""
    site_path = tmp_path / "synthetic-site"
    monkeypatch.setattr(stdio, "__file__", str(site_path / "mcpsh/conformance/stdio.py"))
    captured = capture(monkeypatch, tmp_path)
    with pytest.raises(OSError):
        stdio.StdioSession(request(), "stdio", SimpleNamespace(semantic_case_id=None))
    command = captured["command"]
    assert command[0] == str(Path(sys._base_executable).resolve())
    assert command[1] == "-c" and "site.addsitedir" in command[2]
    assert json.loads(command[3]) == [str(site_path)]
    assert captured["options"]["env"]["PYTHONPATH"].split(os.pathsep) == [str(site_path)]
    assert request().timeout_seconds == 5.0
    assert captured["control"].closed
