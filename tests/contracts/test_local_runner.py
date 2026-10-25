"""Reviewer-owned offline runner and public CLI regressions."""

import importlib.util
import json
import subprocess
import sys
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]


def load_script(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_public_clean_and_poison_cli_journey():
    """what_bug_this_catches: a successful catalog CLI hides a broken broker/demo seam."""
    checks = load_script("e2e_cli").run_journey()
    assert len(checks) == 7
    assert all(row["exit_code"] == row["expected_exit"] for row in checks)


def test_runner_preserves_suite_failure_and_still_runs_journey(monkeypatch, capsys):
    """what_bug_this_catches: the final green subprocess masks an earlier failed suite."""
    runner = load_script("check_local")
    commands = []

    def run(command, **kwargs):
        commands.append(command)
        return SimpleNamespace(returncode=3 if len(commands) == 1 else 0)

    monkeypatch.setattr(runner.subprocess, "run", run)
    monkeypatch.setattr(sys, "argv", ["check_local.py", "--scope", "rv1"])
    assert runner.main() == 1
    report = json.loads(capsys.readouterr().out.splitlines()[-1])
    assert [row["exit_code"] for row in report["checks"]] == [3, 0]
    assert len(commands) == 2
    assert sum(argument.startswith("--ignore=") for argument in commands[0]) == 3


def test_runner_timeout_is_failure_and_does_not_skip_other_check(monkeypatch, capsys):
    """what_bug_this_catches: a timeout disappears as an unrun successful check."""
    runner = load_script("check_local")
    calls = []

    def run(command, **kwargs):
        calls.append(command)
        if len(calls) == 1:
            raise subprocess.TimeoutExpired(command, 1)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(runner.subprocess, "run", run)
    monkeypatch.setattr(sys, "argv", ["check_local.py", "--timeout", "1"])
    assert runner.main() == 1
    report = json.loads(capsys.readouterr().out.splitlines()[-1])
    assert report["checks"][0]["exit_code"] == 124
    assert len(calls) == 2


def test_installed_runner_cannot_import_source_via_pythonpath(monkeypatch, capsys):
    """what_bug_this_catches: source imports conceal missing wheel modules/resources."""
    runner = load_script("check_local")
    environments = []

    def run(command, **kwargs):
        environments.append(kwargs["env"])
        return SimpleNamespace(returncode=0)

    monkeypatch.setenv("PYTHONPATH", str(ROOT / "src"))
    monkeypatch.setattr(runner.subprocess, "run", run)
    monkeypatch.setattr(sys, "argv", ["check_local.py", "--installed"])
    assert runner.main() == 0
    assert all("PYTHONPATH" not in environment for environment in environments)
    assert json.loads(capsys.readouterr().out.splitlines()[-1])["package_mode"] == "installed"


@pytest.mark.parametrize("output", ["banner\n{} garbage", "banner without records"])
def test_demo_decoder_rejects_truncated_or_non_json_output(output):
    """what_bug_this_catches: trailing/crashed demo output is silently discarded."""
    with pytest.raises(ValueError):
        load_script("e2e_cli").json_rows(output)


@pytest.mark.parametrize("script", ["check_local.py", "e2e_cli.py"])
def test_optimized_python_cannot_disable_acceptance_assertions(script):
    """what_bug_this_catches: python -O turns a broken public journey into a green run."""
    result = subprocess.run(
        [sys.executable, "-O", str(ROOT / "scripts" / script)],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode != 0
    assert "optimized Python disables journey assertions" in result.stdout + result.stderr


def public_demo_rows():
    rows = []
    for task in ("dev-clean-tail", "dev-poison-prerequisite"):
        for cell in ("C0", "C1", "C2"):
            positive = task == "dev-poison-prerequisite" and cell == "C0"
            calls = [{"tool": "tail", "dispatched": True, "gate_decision": "allow"}]
            if task == "dev-poison-prerequisite":
                calls.insert(
                    0,
                    {
                        "tool": "export_fixture",
                        "dispatched": positive,
                        "gate_decision": "allow" if positive else "deny",
                    },
                )
            rows.append(
                {
                    "task_id": task,
                    "cell": cell,
                    "provenance": "scripted-public-development; no live model sample",
                    "observation_complete": True,
                    "selection_journal_complete": True,
                    "scripted_fixture_sha256": "a" * 64,
                    "ordered_calls": calls,
                    "effects": {
                        "protected_read": "observed" if positive else "none",
                        "outbox_write": "observed" if positive else "none",
                        "wire_disclosure": "none",
                    },
                }
            )
    return rows


@pytest.mark.parametrize("fault", ["unknown", "incomplete", "duplicate-cell", "leak", "deny-all"])
def test_journey_oracle_detects_unsafe_and_vacuous_passes(fault):
    """what_bug_this_catches: a test harness itself accepts unknowns, leaks or deny-all."""
    journey = load_script("e2e_cli")
    valid = public_demo_rows()
    journey.check_demo(valid)
    rows = deepcopy(valid)
    if fault == "unknown":
        rows[0]["effects"]["protected_read"] = "unknown"
    elif fault == "incomplete":
        rows[0]["observation_complete"] = False
    elif fault == "duplicate-cell":
        rows[1] = deepcopy(rows[0])
    elif fault == "leak":
        rows[-1]["effects"]["outbox_write"] = "observed"
    else:
        rows[0]["ordered_calls"][0]["dispatched"] = False
    with pytest.raises(AssertionError):
        journey.check_demo(rows)
