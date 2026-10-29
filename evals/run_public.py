"""Offline public-development checks. This never grants product/live acceptance."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SEED = 1729
EDITION = "m5-public-development"


def require(condition: bool, reason: str) -> None:
    if not condition:
        raise ValueError(reason)


def replay_expectations(pin: str):
    """Use the admitted source plans and the publisher's own identity projection.

    Scheduling order/IDs follow runner.engine.run_matrix. No selector, broker or
    scorer is executed here; the corpus API admits public development data only.
    """
    import random

    from mcpsh.evidence import project_public_result
    from mcpsh.records import typed_hash
    from mcpsh.runner.cases import load_development_corpus

    corpus = load_development_corpus(ROOT, expected_manifest_sha256=pin)
    schedule = []
    for entry in corpus.primary_plan["entries"]:
        for condition in entry["conditions"]:
            for cell in entry["cells"]:
                schedule.append((entry, condition, cell, "scripted-replay", "baseline"))
        for control in ("keyword", "abstain", "deny-all"):
            schedule.append((entry, "clean", "control", control, "control"))
    for entry in corpus.diagnostic_plan["entries"]:
        for condition in entry["conditions"]:
            for cell in entry["cells"]:
                schedule.append(
                    (entry, condition, cell, "scripted-development-replay", "diagnostic")
                )
    random.Random(SEED).shuffle(schedule)
    rows = []
    for index, (entry, condition, cell, selector, role) in enumerate(schedule):
        rows.append(
            {
                "outcome": {
                    "trial_id": f"replay-{index:04d}-{entry['task_id']}",
                    "task_id": entry["task_id"],
                    "condition": condition,
                    "cell": cell,
                    "selector": selector,
                    "execution_mode": "replay",
                    "model_id": None,
                    "scheduled": True,
                },
                "replay_role": role,
                "replay_episode_id": entry["episode_id"]
                if selector not in ("keyword", "abstain")
                else None,
            }
        )
    projected = project_public_result({"rows": rows}).public["rows"]
    return (
        corpus,
        projected,
        {
            "task_hash": typed_hash([task.model_dump(mode="json") for task, _, _ in corpus.cases]),
            "split_hash": hashlib.sha256(corpus.oracle_package_bytes).hexdigest(),
        },
    )


def slot_identity(row: dict) -> tuple:
    outcome = row["outcome"]
    return tuple(
        outcome[key] for key in ("trial_id", "task_id", "condition", "cell", "selector")
    ) + (
        row["replay_role"],
        row["replay_episode_id"],
    )


def validate_replay(result: dict, corpus, expected: list[dict], manifest_pins: dict) -> dict:
    """Evidence checks remain active under -O and inherited PYTHONOPTIMIZE."""
    require(type(result) is dict, "publication must be an object")
    rows = result["rows"]
    require(type(rows) is list and bool(rows), "no scheduled development outcomes")
    require(result["execution_state"] == "replay-only", "replay promoted to live")
    require(result["acceptance_verdict"] == "pending", "publisher granted acceptance")
    require(result["seed"] == SEED and type(result["seed"]) is int, "replay seed differs")
    require(result["development_input_pins"] == corpus.input_pins, "development input pins differ")
    manifest = result["manifest"]
    require(
        manifest["mode"] == "replay" and manifest["seed"] == SEED,
        "manifest execution provenance differs",
    )
    require(manifest["settings"]["live_requests"] == 0, "manifest claims live requests")
    require(
        all(manifest[key] == value for key, value in manifest_pins.items()),
        "task/oracle input pins differ",
    )
    identities = Counter(slot_identity(row) for row in rows)
    planned = Counter(slot_identity(row) for row in expected)
    missing, unexpected = planned - identities, identities - planned
    denominators = {
        "scheduled": len(expected),
        "executed": len(rows),
        "missing": sum(missing.values()),
        "unexpected": sum(unexpected.values()),
    }
    require(identities == planned, f"public replay slot multiset differs: {denominators}")
    outcomes = [row["outcome"] for row in rows]
    require(all(outcome["execution_mode"] == "replay" for outcome in outcomes), "nonreplay outcome")
    require(all(outcome["model_id"] is None for outcome in outcomes), "model identity in replay")
    require(all(outcome["scheduled"] is True for outcome in outcomes), "unscheduled outcome")
    expected_design = {
        "baseline_tasks": len(corpus.cases),
        "baseline_rows": sum(row["replay_role"] == "baseline" for row in expected),
        "control_rows": sum(row["replay_role"] == "control" for row in expected),
        "diagnostic_episodes": len(corpus.diagnostic_plan["entries"]),
        "diagnostic_rows": sum(row["replay_role"] == "diagnostic" for row in expected),
    }
    require(
        result["replay_design"] == expected_design,
        "missing/inconsistent replay denominator metadata",
    )
    groups = Counter(
        (o["selector"], o["condition"], o["cell"], o["utility_basis"]) for o in outcomes
    )
    seen = set()
    for summary in result["summary"]:
        key = tuple(summary[name] for name in ("selector", "condition", "cell", "utility_basis"))
        require(key in groups and key not in seen, "unexpected/duplicate summary group")
        seen.add(key)
        count = groups[key]
        require(
            type(summary["scheduled_trials"]) is int and summary["scheduled_trials"] == count,
            "summary scheduled denominator differs",
        )
        for metric in ("selection", "utility", "intent"):
            denominator = summary[metric]["denominator"]
            require(type(denominator) is int and denominator == count, "metric denominator differs")
        members = [
            o
            for o in outcomes
            if (o["selector"], o["condition"], o["cell"], o["utility_basis"]) == key
        ]
        require(
            summary["failed_trials"] == sum(bool(o["failures"]) for o in members),
            "failed outcomes omitted from summary",
        )
        require(
            summary["utility_unknown_trials"] == sum(o["utility_success"] is None for o in members),
            "unknown outcomes omitted from summary",
        )
    require(seen == set(groups), "missing summary denominator groups")
    return {
        "name": "replay-provenance",
        "status": "pass",
        "outcomes": len(outcomes),
        "denominators": denominators,
        "failed_outcomes": sum(bool(o["failures"]) for o in outcomes),
        "unknown_utility_outcomes": sum(o["utility_success"] is None for o in outcomes),
    }


def published_hashes(public: Path) -> dict:
    paths = list(public.iterdir())
    require(
        bool(paths) and all(path.is_file() and not path.is_symlink() for path in paths),
        "published edition must contain regular flat files",
    )
    return {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}


def duplicate_rejected(check: dict, directory: Path, before: dict, after: dict) -> bool:
    log = directory / "duplicate-edition.log"
    # argparse's existing public CLI rejection, not merely any nonzero exit.
    with log.open("rb") as handle:
        raw = handle.read(64 * 1024 + 1)
    if len(raw) > 64 * 1024:
        return False
    output = raw.decode("utf-8")
    return (
        check["exit_code"] == 2
        and before == after
        and bool(before)
        and hashlib.sha256(raw).hexdigest() == check["log_sha256"]
        and output.startswith("usage: eval.py ")
        and "Traceback" not in output
        and output.splitlines()[-1]
        == "eval.py: error: immutable edition already exists; choose a successor ID"
    )


def execute(name: str, command: list[str], directory: Path, timeout: int = 900) -> dict:
    started = time.monotonic()
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=timeout)
        output = result.stdout + result.stderr
        code = result.returncode
    except subprocess.TimeoutExpired as error:
        output = f"timeout after {timeout}s\n{error}"
        code = 124
    # Hash exactly the persisted bytes, including on Windows (no CRLF rewriting).
    raw_output = output.encode("utf-8")
    (directory / f"{name}.log").write_bytes(raw_output)
    return {
        "name": name,
        "command": command,
        "exit_code": code,
        "status": "pass" if code == 0 else "fail",
        "seconds": round(time.monotonic() - started, 3),
        "log_sha256": hashlib.sha256(raw_output).hexdigest(),
    }


def main(argv=None, *, run_command=None) -> int:
    run_command = execute if run_command is None else run_command
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--artifacts",
        type=Path,
        required=True,
        help="fresh M5-owned artifact directory outside the product checkout",
    )
    args = parser.parse_args(argv)
    directory = args.artifacts.resolve()
    if directory == ROOT or ROOT in directory.parents:
        parser.error("artifacts must remain outside the product checkout")
    directory.mkdir(parents=True, exist_ok=False)
    os.environ["PYTHONPATH"] = str(ROOT / "src")
    # Direct script execution must use the same admitted source as subprocesses.
    sys.path.insert(0, str(ROOT / "src"))
    # pytest owns only this newly created disposable subtree; no old basetemp is reused.
    temp_parent = directory / "pytest"
    temp_parent.mkdir()
    checks = [
        run_command(
            "eval-regressions",
            [
                sys.executable,
                "-m",
                "pytest",
                "-q",
                str(ROOT / "tests/evaluation"),
                str(ROOT / "tests/evidence"),
                str(ROOT / "tests/conformance"),
                str(ROOT / "tests/accounting"),
                str(ROOT / "tests/fixtures"),
                "--tb=short",
                "--basetemp",
                str(temp_parent / "run"),
            ],
            directory,
        )
    ]
    manifest = ROOT / "fixtures/dev/corpus-manifest-v2.json"
    pin = hashlib.sha256(manifest.read_bytes()).hexdigest()
    corpus, expected, manifest_pins = replay_expectations(pin)
    command = [
        sys.executable,
        str(ROOT / "scripts/eval.py"),
        "--mode",
        "replay",
        "--corpus",
        "development",
        "--development-manifest-sha256",
        pin,
        "--out",
        str(directory / "public"),
        "--private-evidence",
        str(directory / "private"),
        "--edition",
        EDITION,
    ]
    replay = run_command("public-replay", command, directory)
    checks.append(replay)
    if replay["status"] == "pass":
        # An immutable edition must reject a second publisher without changing published bytes.
        public = directory / "public" / EDITION
        try:
            from mcpsh.records import strict_json_loads

            result = strict_json_loads((public / "results.json").read_bytes())
            checks.append(validate_replay(result, corpus, expected, manifest_pins))
        except (OSError, ValueError, KeyError, TypeError) as error:
            checks.append({"name": "replay-provenance", "status": "fail", "reason": str(error)})
        duplicate = {"name": "duplicate-edition", "status": "fail"}
        try:
            before = published_hashes(public)
            duplicate = run_command("duplicate-edition", command, directory)
            after = published_hashes(public)
            duplicate["status"] = (
                "pass" if duplicate_rejected(duplicate, directory, before, after) else "fail"
            )
            duplicate["before_sha256"] = before
            duplicate["after_sha256"] = after
        except (OSError, ValueError, KeyError, TypeError, IndexError) as error:
            duplicate["status"] = "fail"
            duplicate["reason"] = str(error)
        duplicate["expected"] = (
            "exit 2, exact bounded existing-edition argparse rejection, "
            "unchanged published file hashes"
        )
        checks.append(duplicate)
    else:
        checks.append(
            {
                "name": "duplicate-edition",
                "status": "not-run",
                "reason": "public replay did not publish",
            }
        )
    status = "pass" if all(c["status"] == "pass" for c in checks) else "fail"
    report = {
        "schema_version": 1,
        "scope": "public-development/offline",
        "status": status,
        "product_acceptance": "pending",
        "execution_mode": "replay-only",
        "development_manifest_sha256": pin,
        "python": sys.version,
        "checks": checks,
        "pending": [
            "two distinct live model families",
            "hidden/holdout evaluation",
            "independent threshold approval",
            "supported-platform product acceptance",
        ],
    }
    (directory / "summary.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if status == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
