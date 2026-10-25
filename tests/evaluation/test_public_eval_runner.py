"""Fault injection for RV2-H1/H2/H3; no broker, provider or full replay runs.

The positive publication uses the real source scheduler/aggregator/projection with
only run_trial replaced by deterministic synthetic outcomes. Runner commands are
injected independently, so replay and pytest are never recursively dispatched.
"""

import hashlib
import importlib.util
import json
import os
import subprocess
import sys
from copy import deepcopy
from pathlib import Path

import pytest

from mcpsh.evidence import project_public_result
from mcpsh.runner import engine

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("public_eval_runner", ROOT / "evals/run_public.py")
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)


def publication():
    """Canonical known public plan, independently scheduled by product source."""
    pin = hashlib.sha256((ROOT / "fixtures/dev/corpus-manifest-v2.json").read_bytes()).hexdigest()
    corpus, expected, pins = runner.replay_expectations(pin)

    def synthetic_trial(**kwargs):
        return {
            "outcome": {
                "trial_id": kwargs["trial_id"],
                "task_id": kwargs["task"].task_id,
                "family_id": kwargs["oracle"].family_id,
                "condition": kwargs["condition"],
                "cell": kwargs["cell"],
                "selector": kwargs["selector_name"],
                "execution_mode": "replay",
                "model_id": None,
                "scheduled": True,
                "utility_basis": "semantic-v2",
                "observation_complete": True,
                "effect": "none",
                "validated_prohibited_attempts": 0,
                "blocked_prohibited_calls": 0,
                "gate_false_negative_calls": 0,
                "call_count": 0,
                "latency_seconds": 0.0,
                "selection_success": True,
                "utility_success": True,
                "utility_status": "success",
                "prohibited_intent": False,
                "failures": [],
                "cost_microunits": 0,
                "cost_basis": "non-model",
            }
        }

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(engine, "run_trial", synthetic_trial)
        value = engine.run_matrix(
            seed=1729,
            cases=corpus.cases,
            fixture_map=corpus.fixture_map,
            treatment_map=corpus.treatment_map,
            episodes=corpus.episodes,
            replay_specs=corpus.replay_specs,
            primary_plan=corpus.primary_plan,
            diagnostic_plan=corpus.diagnostic_plan,
        )
    value["development_input_pins"] = corpus.input_pins
    value["manifest"] = {"mode": "replay", "seed": 1729, **pins, "settings": {"live_requests": 0}}
    # Publication includes honest failed/unknown slots; they must stay scheduled.
    value["rows"][0]["outcome"].update(
        failures=["observation_incomplete"], utility_success=None, utility_status="unknown"
    )
    value["summary"] = engine.aggregate_outcomes([row["outcome"] for row in value["rows"]])
    return project_public_result(value).public


@pytest.fixture(scope="module")
def valid_publication():
    return publication()


def mutate(value, case):
    if case == "valid":
        return
    if case == "truncated":
        value["rows"] = value["rows"][:1]
    elif case == "duplicate":
        value["rows"][-1] = deepcopy(value["rows"][0])
    elif case == "empty":
        value["rows"] = []
    elif case in ("task", "trial", "condition", "cell", "selector"):
        field = {"task": "task_id", "trial": "trial_id"}.get(case, case)
        value["rows"][0]["outcome"][field] = "wrong-slot"
    elif case in ("episode", "role"):
        value["rows"][0]["replay_episode_id" if case == "episode" else "replay_role"] = "wrong-slot"
    elif case == "missing-denominators":
        value.pop("replay_design")
    elif case == "design-denominator":
        value["replay_design"]["baseline_rows"] -= 1
    elif case == "missing-summary":
        value["summary"] = []
    elif case == "duplicate-summary":
        value["summary"].append(deepcopy(value["summary"][0]))
    elif case == "summary-denominator":
        value["summary"][0]["scheduled_trials"] -= 1
    elif case == "metric-denominator":
        value["summary"][0]["utility"]["denominator"] -= 1
    elif case == "failed-denominator":
        for summary in value["summary"]:
            summary["failed_trials"] = 0
    elif case == "unknown-denominator":
        for summary in value["summary"]:
            summary["utility_unknown_trials"] = 0
    elif case == "missing-pins":
        value.pop("development_input_pins")
    elif case == "wrong-pins":
        value["development_input_pins"]["manifest_sha256"] = "0" * 64
    elif case == "task-pin":
        value["manifest"]["task_hash"] = "0" * 64
    elif case == "oracle-pin":
        value["manifest"]["split_hash"] = "0" * 64
    elif case == "nonreplay":
        value["rows"][0]["outcome"]["execution_mode"] = "live"
    elif case == "model":
        value["rows"][0]["outcome"]["model_id"] = "unexpected-model"
    elif case == "unscheduled":
        value["rows"][0]["outcome"]["scheduled"] = False
    elif case == "live-state":
        value["execution_state"] = "live-complete"
    elif case == "acceptance":
        value["acceptance_verdict"] = "accepted"
    elif case == "seed":
        value["seed"] = 1
    else:
        raise ValueError(case)


REJECTION = (
    "usage: eval.py [-h] [--mode replay]\n"
    "eval.py: error: immutable edition already exists; choose a successor ID\n"
)


def exercise(
    directory,
    value,
    *,
    duplicate_code=2,
    duplicate_output=REJECTION,
    change_bytes=False,
    regression_code=0,
    replay_code=0,
):
    def command(name, args, artifacts):
        code = 0
        output = "synthetic injected command\n"
        if name == "eval-regressions":
            code = regression_code
        if name == "public-replay":
            code = replay_code
            public = artifacts / "public" / runner.EDITION
            public.mkdir(parents=True)
            (public / "results.json").write_text(json.dumps(value), encoding="utf-8")
            (public / "report.md").write_text("synthetic-publication", encoding="utf-8")
        if name == "duplicate-edition":
            code, output = duplicate_code, duplicate_output
            if change_bytes:
                (artifacts / "public" / runner.EDITION / "report.md").write_text(
                    "changed", encoding="utf-8"
                )
        (artifacts / f"{name}.log").write_bytes(output.encode())
        return {
            "name": name,
            "exit_code": code,
            "status": "pass" if code == 0 else "fail",
            "log_sha256": hashlib.sha256(output.encode()).hexdigest(),
        }

    code = runner.main(["--artifacts", str(directory)], run_command=command)
    return code, json.loads((directory / "summary.json").read_text(encoding="utf-8"))


def test_full_known_public_plan_preserves_failures_and_denominators(tmp_path, valid_publication):
    value = valid_publication
    assert value["development_input_pins"]["cases"] == 36
    assert value["development_input_pins"]["episodes"] == 51
    assert value["replay_design"] == {
        "baseline_tasks": 36,
        "baseline_rows": 324,
        "control_rows": 108,
        "diagnostic_episodes": 15,
        "diagnostic_rows": 45,
    }
    code, report = exercise(tmp_path / "valid", value)
    assert code == 0 and report["status"] == "pass"
    check = next(c for c in report["checks"] if c["name"] == "replay-provenance")
    assert check["denominators"] == {
        "scheduled": 477,
        "executed": 477,
        "missing": 0,
        "unexpected": 0,
    }
    assert check["failed_outcomes"] == check["unknown_utility_outcomes"] == 1
    assert report["product_acceptance"] == "pending"


@pytest.mark.parametrize(
    "case",
    [
        "truncated",
        "duplicate",
        "empty",
        "task",
        "trial",
        "condition",
        "cell",
        "selector",
        "episode",
        "role",
        "missing-denominators",
        "design-denominator",
        "missing-summary",
        "duplicate-summary",
        "summary-denominator",
        "metric-denominator",
        "failed-denominator",
        "unknown-denominator",
        "missing-pins",
        "wrong-pins",
        "task-pin",
        "oracle-pin",
        "nonreplay",
        "model",
        "unscheduled",
        "live-state",
        "acceptance",
        "seed",
    ],
)
def test_malformed_replay_fails_closed(tmp_path, valid_publication, case):
    value = deepcopy(valid_publication)
    mutate(value, case)
    code, report = exercise(tmp_path / case, value)
    assert code == 1 and report["status"] == "fail"
    check = next(c for c in report["checks"] if c["name"] == "replay-provenance")
    assert check["status"] == "fail"


@pytest.mark.parametrize(
    ("code", "output", "changed"),
    [
        (124, REJECTION, False),
        (1, "Traceback: unrelated crash\n", False),
        (1, "ModuleNotFoundError: mcpsh\n", False),
        (2, "eval.py: error: wrong manifest pin\n", False),
        (2, "", False),
        (0, REJECTION, False),
        (2, REJECTION, True),
        (2, "x" * (64 * 1024) + REJECTION, False),
        (2, "Traceback\n" + REJECTION, False),
    ],
    ids=[
        "timeout",
        "crash",
        "import-error",
        "unrelated-error",
        "empty",
        "success-exit",
        "changed-bytes",
        "oversize-signal",
        "traceback",
    ],
)
def test_unrelated_duplicate_failures_are_not_immutability_proof(
    tmp_path, valid_publication, code, output, changed
):
    exit_code, report = exercise(
        tmp_path / "duplicate",
        valid_publication,
        duplicate_code=code,
        duplicate_output=output,
        change_bytes=changed,
    )
    assert exit_code == 1 and report["status"] == "fail"
    assert next(c for c in report["checks"] if c["name"] == "duplicate-edition")["status"] == "fail"


@pytest.mark.parametrize("failed_command", ["regression_code", "replay_code"])
def test_failed_subcommands_remain_failures(tmp_path, valid_publication, failed_command):
    code, report = exercise(tmp_path / failed_command, valid_publication, **{failed_command: 1})
    assert code == 1 and report["status"] == "fail"


def test_real_cli_existing_edition_signal(tmp_path):
    public = tmp_path / "public"
    (public / runner.EDITION).mkdir(parents=True)
    check = runner.execute(
        "duplicate-edition",
        [
            sys.executable,
            str(ROOT / "scripts/eval.py"),
            "--mode",
            "replay",
            "--out",
            str(public),
            "--edition",
            runner.EDITION,
        ],
        tmp_path,
        timeout=20,
    )
    # This invokes only the early public existing-edition guard, never a replay.
    assert runner.duplicate_rejected(check, tmp_path, {"file": "pin"}, {"file": "pin"})


def optimization_probe(directory):
    """Explicit checks, since this helper itself also runs under optimization."""
    value = publication()
    observed = {}
    for case in (
        "valid",
        "empty",
        "nonreplay",
        "model",
        "live-state",
        "acceptance",
        "truncated",
        "duplicate",
        "missing-denominators",
    ):
        mutated = deepcopy(value)
        mutate(mutated, case)
        code, report = exercise(Path(directory) / case, mutated)
        expected = 0 if case == "valid" else 1
        if code != expected or report["status"] != ("pass" if expected == 0 else "fail"):
            raise RuntimeError(f"optimized runner false result: {case} {code}")
        observed[case] = code
    print("OPTIMIZATION_PROBE=" + json.dumps(observed, sort_keys=True))


@pytest.mark.parametrize("mode", ["normal", "dash-O", "environment"])
def test_runtime_checks_survive_optimization(tmp_path, mode):
    env = dict(os.environ, PYTHONPATH=str(ROOT / "src"), PYTHONDONTWRITEBYTECODE="1")
    env.pop("PYTHONOPTIMIZE", None)
    command = [sys.executable]
    if mode == "dash-O":
        command.append("-O")
    if mode == "environment":
        env["PYTHONOPTIMIZE"] = "1"
    command += [
        "-c",
        "import runpy,sys; runpy.run_path(sys.argv[1])['optimization_probe'](sys.argv[2])",
        str(Path(__file__).resolve()),
        str(tmp_path / mode),
    ]
    result = subprocess.run(command, capture_output=True, text=True, timeout=60, env=env)
    assert result.returncode == 0, result.stdout[-2000:] + result.stderr[-2000:]
    marker = next(
        line for line in result.stdout.splitlines() if line.startswith("OPTIMIZATION_PROBE=")
    )
    results = json.loads(marker.split("=", 1)[1])
    assert results == {case: 0 if case == "valid" else 1 for case in results}
    assert len(results) == 9
