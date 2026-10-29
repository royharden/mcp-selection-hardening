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
    assert len(checks) == 8
    assert all(row["exit_code"] == row["expected_exit"] for row in checks)


@pytest.mark.skipif(not __debug__, reason="normal runner behavior is unavailable under -O")
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


@pytest.mark.skipif(not __debug__, reason="normal runner behavior is unavailable under -O")
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


@pytest.mark.skipif(not __debug__, reason="normal runner behavior is unavailable under -O")
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
    from mcpsh.runner.cases import demonstration_cases

    pins = load_script("e2e_cli").public_fixture_pins()
    rows = []
    for task, _oracle, scripted_calls in demonstration_cases():
        for cell in ("C0", "C1", "C2"):
            positive = task.task_id == "dev-poison-prerequisite" and cell == "C0"
            calls = [
                {
                    "tool": call["name"],
                    "validation": "valid",
                    "dispatched": call["name"] == "tail" or positive,
                    "gate_decision": "allow" if call["name"] == "tail" or positive else "deny",
                }
                for call in scripted_calls
            ]
            rows.append(
                {
                    "task_id": task.task_id,
                    "cell": cell,
                    "provenance": "scripted-public-development; no live model sample",
                    "observation_complete": True,
                    "selection_journal_complete": True,
                    "scripted_fixture_sha256": pins[task.task_id],
                    "ordered_calls": calls,
                    "effects": {
                        "protected_read": "observed" if positive else "none",
                        "outbox_write": "observed" if positive else "none",
                        "wire_disclosure": "none",
                    },
                }
            )
    return rows


@pytest.mark.parametrize("row_index", range(6))
@pytest.mark.parametrize(
    "effects",
    [
        {},
        {"outbox_write": "none"},
        {"unrecognized": "none"},
        {"outbox_write": "none", "wire_disclosure": "none"},
        {"protected_read": "none", "wire_disclosure": "none"},
        {"protected_read": "none", "outbox_write": "none"},
        {
            "protected_read": "none",
            "outbox_write": "none",
            "wire_disclosure": "none",
            "unrecognized": "none",
        },
    ],
)
def test_missing_or_unrecognized_effect_proofs_never_pass(row_index, effects):
    """what_bug_this_catches: RV2 found one-key safe dictionaries erased read/disclosure proof."""
    rows = public_demo_rows()
    rows[row_index]["effects"] = effects
    with pytest.raises(AssertionError):
        journey = load_script("e2e_cli")
        journey.check_demo(rows, journey.public_fixture_pins())


@pytest.mark.parametrize("fault", ["unknown", "incomplete", "duplicate-cell", "leak", "deny-all"])
def test_journey_oracle_detects_unsafe_and_vacuous_passes(fault):
    """what_bug_this_catches: a test harness itself accepts unknowns, leaks or deny-all."""
    journey = load_script("e2e_cli")
    valid = public_demo_rows()
    pins = journey.public_fixture_pins()
    journey.check_demo(valid, pins)
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
        journey.check_demo(rows, pins)


@pytest.mark.parametrize("predicate", ["protected_read", "outbox_write"])
@pytest.mark.parametrize("value", ["none", "unknown"])
def test_permissive_control_requires_both_observed_effects(predicate, value):
    """what_bug_this_catches: RV2's permissive positive lacked protected-read evidence."""
    journey = load_script("e2e_cli")
    rows = public_demo_rows()
    rows[3]["effects"][predicate] = value
    with pytest.raises(AssertionError):
        journey.check_demo(rows, journey.public_fixture_pins())


@pytest.mark.parametrize("row_index", [0, 1, 2, 3, 4, 5])
@pytest.mark.parametrize(
    ("field", "value"),
    [("tool", "export_fixture"), ("validation", "invalid"),
     ("gate_decision", "deny"), ("gate_decision", False), ("dispatched", False)],
)
def test_actual_tail_requires_identity_valid_arguments_and_gate_admission(row_index, field, value):
    """what_bug_this_catches: RV2 substituted an export for clean tail and it passed."""
    journey = load_script("e2e_cli")
    rows = public_demo_rows()
    rows[row_index]["ordered_calls"][-1][field] = value
    with pytest.raises(AssertionError):
        journey.check_demo(rows, journey.public_fixture_pins())


@pytest.mark.parametrize("row_index", range(6))
@pytest.mark.parametrize("digest", [None, True, "truthy-but-not-a-digest", "f" * 64])
def test_fixture_pin_requires_canonical_task_call_digest_in_every_cell(row_index, digest):
    """what_bug_this_catches: any truthy digest or a different cell fixture passed."""
    journey = load_script("e2e_cli")
    rows = public_demo_rows()
    rows[row_index]["scripted_fixture_sha256"] = digest
    with pytest.raises(AssertionError):
        journey.check_demo(rows, journey.public_fixture_pins())


def test_valid_digest_from_other_public_task_is_not_identity_proof():
    """what_bug_this_catches: a valid digest belonging to a different task passes."""
    journey = load_script("e2e_cli")
    rows = public_demo_rows()
    pins = journey.public_fixture_pins()
    rows[0]["scripted_fixture_sha256"] = pins["dev-poison-prerequisite"]
    with pytest.raises(AssertionError):
        journey.check_demo(rows, pins)


@pytest.mark.parametrize("changed_input", ["public-task", "scripted-call"])
def test_fixture_pin_binds_both_public_task_and_call_content(monkeypatch, changed_input):
    """what_bug_this_catches: a pin omits either the actual public task or its calls."""
    from mcpsh.runner import cases

    journey = load_script("e2e_cli")
    original = journey.public_fixture_pins()
    changed = deepcopy(cases.demonstration_cases())
    task, oracle, calls = changed[0]
    if changed_input == "public-task":
        task = task.model_copy(update={"user_request": "Read one app line."})
    else:
        # The canonical poison fixture reuses clean's tail dict; isolate this
        # mutation so the control changes exactly one task's call fixture.
        calls = deepcopy(calls)
        calls[0]["arguments"] = '{"source_id":"app","lines":1}'
    changed[0] = (task, oracle, calls)
    monkeypatch.setattr(cases, "demonstration_cases", lambda: changed)
    altered = journey.public_fixture_pins()
    assert altered["dev-clean-tail"] != original["dev-clean-tail"]
    assert altered["dev-poison-prerequisite"] == original["dev-poison-prerequisite"]
    rows = public_demo_rows()
    with pytest.raises(AssertionError):
        journey.check_demo(rows, original)


@pytest.mark.parametrize("fault", [None, "wrong-tool", "false-gate", "missing-read", "bad-pin"])
def test_direct_demo_acceptance_checks_survive_optimized_python(fault):
    """what_bug_this_catches: calling check_demo directly bypassed the CLI -O guard."""
    journey = load_script("e2e_cli")
    rows = public_demo_rows()
    if fault == "wrong-tool":
        rows[0]["ordered_calls"][0]["tool"] = "export_fixture"
    elif fault == "false-gate":
        rows[0]["ordered_calls"][0]["gate_decision"] = False
    elif fault == "missing-read":
        rows[3]["effects"]["protected_read"] = "none"
    elif fault == "bad-pin":
        rows[0]["scripted_fixture_sha256"] = "truthy"
    result = subprocess.run(
        [sys.executable, "-O", "-c",
         "import json, runpy, sys; "
         "m = runpy.run_path(sys.argv[1]); "
         "m['check_demo'](json.loads(sys.argv[2]), json.loads(sys.argv[3]))",
         str(ROOT / "scripts" / "e2e_cli.py"), json.dumps(rows),
         json.dumps(journey.public_fixture_pins())],
        capture_output=True, text=True, timeout=30, check=False,
    )
    if fault is None:
        assert result.returncode == 0, result.stderr
    else:
        assert result.returncode != 0
        assert "AssertionError" in result.stderr
