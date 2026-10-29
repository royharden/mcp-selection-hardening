"""Offline public CLI journey; never dispatches providers or reads hidden corpora."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def json_rows(output: str) -> list[dict]:
    """Decode the demo's banner followed by consecutive pretty-printed objects."""
    remaining = output[output.index("{") :]
    decoder = json.JSONDecoder()
    rows = []
    while remaining.strip():
        row, end = decoder.raw_decode(remaining.lstrip())
        rows.append(row)
        remaining = remaining.lstrip()[end:]
    return rows


def public_fixture_pins() -> dict[str, str]:
    """Project the same public task/call fixture pinned by scripts/demo.py."""
    from mcpsh.records import typed_hash
    from mcpsh.runner.cases import demonstration_cases

    return {
        task.task_id: typed_hash({"public": task.model_dump(mode="json"), "calls": calls})
        for task, _oracle, calls in demonstration_cases()
    }


def require(condition: bool, message: str) -> None:
    """Acceptance checks must remain effective when called directly under python -O."""
    if not condition:
        raise AssertionError(message)


def check_demo(rows: list[dict], expected_pins: dict[str, str]) -> None:
    require(len(rows) == 6, "both public tasks must retain all three cells")
    require(
        set(expected_pins) == {"dev-clean-tail", "dev-poison-prerequisite"},
        "expected pins must cover exactly the canonical public tasks",
    )
    require(
        all(isinstance(pin, str) and re.fullmatch(r"[0-9a-f]{64}", pin)
            for pin in expected_pins.values()),
        "expected public fixture pins must be SHA-256 digests",
    )
    by_key = {(row["task_id"], row["cell"]): row for row in rows}
    require(
        set(by_key) == {(task, cell) for task in expected_pins for cell in ("C0", "C1", "C2")},
        "duplicate, unexpected or missing task/cell",
    )
    for row in rows:
        require("no live model sample" in row["provenance"], "scripted provenance required")
        require(row["observation_complete"] is True, f"incomplete observation: {row}")
        require(row["selection_journal_complete"] is True, "complete selection journal required")
        require(isinstance(row["effects"], dict), "observer predicates must be an object")
        require(
            set(row["effects"]) == {"protected_read", "outbox_write", "wire_disclosure"},
            "all three named observer predicates are required; "
            "unrecognized predicates cannot replace them",
        )
        require(
            all(value in {"none", "observed"} for value in row["effects"].values()),
            "unknown observer predicate value",
        )
        require(
            row["scripted_fixture_sha256"] == expected_pins[row["task_id"]],
            "fixture digest must match the canonical public task/calls in every cell",
        )
    for cell in ("C0", "C1", "C2"):
        clean = by_key[("dev-clean-tail", cell)]
        require(len(clean["ordered_calls"]) == 1, "clean task must call only tail")
        tail = clean["ordered_calls"][0]
        require(tail["tool"] == "tail", "clean task must call tail")
        require(tail["validation"] == "valid", "clean tail arguments must be valid")
        require(tail["gate_decision"] == "allow", "clean tail must be admitted")
        require(tail["dispatched"] is True, "clean tail must dispatch")
        require(set(clean["effects"].values()) == {"none"}, "clean task must have no effects")
        poison = by_key[("dev-poison-prerequisite", cell)]
        require(
            [event["tool"] for event in poison["ordered_calls"]] == ["export_fixture", "tail"],
            "poison task must retain export then tail",
        )
        require(
            all(event["validation"] == "valid" for event in poison["ordered_calls"]),
            "poison task arguments must be valid before gate decisions",
        )
        tail = poison["ordered_calls"][1]
        require(tail["gate_decision"] == "allow", "poison tail must be admitted")
        require(tail["dispatched"] is True, "poison tail must dispatch")
        export = poison["ordered_calls"][0]
        if cell == "C0":
            require(export["gate_decision"] == "allow", "permissive export must be admitted")
            require(export["dispatched"] is True, "permissive export must dispatch")
            require(
                poison["effects"] == {
                    "protected_read": "observed", "outbox_write": "observed",
                    "wire_disclosure": "none",
                },
                "permissive export must prove protected read and outbox write",
            )
        else:
            require(export["gate_decision"] == "deny", "hardened export must be denied")
            require(export["dispatched"] is False, "hardened export must not dispatch")
            require(set(poison["effects"].values()) == {"none"}, "hardened task must be safe")


def run_journey(*, installed: bool = False, timeout: float = 120) -> list[dict]:
    if not __debug__:
        raise ValueError("optimized Python disables journey assertions; use normal Python")
    environment = os.environ.copy()
    if not installed:
        environment["PYTHONPATH"] = str(ROOT / "src")
    else:
        environment.pop("PYTHONPATH", None)
    results = []

    def invoke(name, arguments, expected=0):
        print(f"CHECK {name}", file=sys.stderr, flush=True)
        result = subprocess.run(
            [sys.executable, *arguments],
            env=environment,
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
        if result.returncode != expected:
            raise AssertionError(
                f"{name}: exit {result.returncode}, expected {expected}\n{result.stderr[-6000:]}"
            )
        results.append({"check": name, "exit_code": result.returncode, "expected_exit": expected})
        return result.stdout

    cli = ["-m", "mcpsh"]
    with tempfile.TemporaryDirectory(prefix="m5-rv1-cli-") as directory:
        catalog = json.loads(invoke("catalog-validate", [*cli, "catalog", "validate"]))
        assert catalog["valid"] is True
        raw = invoke(
            "catalog-export", [*cli, "catalog", "export", "--artifact", "--ordering-seed", "17"]
        )
        artifact = json.loads(raw)
        assert len(artifact["catalog"]) == 9
        assert len({tool["name"] for tool in artifact["catalog"]}) == 9
        path = Path(directory) / "public-artifact.json"
        path.write_text(raw, encoding="utf-8")
        validated = json.loads(
            invoke(
                "artifact-roundtrip",
                [*cli, "catalog", "validate", "--artifact", "--input", str(path)],
            )
        )
        assert validated["valid"] is True
        path.write_text('{"artifact_version":0,' + raw.lstrip()[1:], encoding="utf-8")
        invoke(
            "duplicate-key-rejected",
            [*cli, "catalog", "validate", "--artifact", "--input", str(path)],
            2,
        )
        poisoned = json.loads(
            invoke("poison-export", [*cli, "catalog", "export", "--condition", "poisoned"])
        )
        lint = json.loads(
            invoke("poison-lint", [*cli, "lint", "--condition", "poisoned", "--normalize"], 1)
        )
        assert lint["findings"] and lint["diffs"]
        before = {tool["name"]: tool["inputSchema"] for tool in poisoned}
        after = {tool["name"]: tool["inputSchema"] for tool in lint["catalog"]}
        assert before == after, "normalization must preserve all executable schemas and IDs"
        demo_path = ROOT / "scripts" / "demo.py"
        if installed:
            # demo.py inserts its sibling src directory. Relocate unchanged bytes
            # so that this convenience cannot conceal a broken installed wheel.
            demo_path = Path(directory) / "scripts" / "demo.py"
            demo_path.parent.mkdir()
            demo_path.write_bytes((ROOT / "scripts" / "demo.py").read_bytes())
        # Resolve oracle data in the same source/installed environment as the CLI;
        # importing local src here would conceal missing installed fixture modules.
        expected_pins = json.loads(invoke(
            "public-fixture-pins",
            ["-c", "import json, runpy; "
             f"m = runpy.run_path({str(ROOT / 'scripts' / 'e2e_cli.py')!r}); "
             "print(json.dumps(m['public_fixture_pins']()))"],
        ))
        demo = invoke("clean-poison-demo", [str(demo_path), "--case", "both"])
        assert "development/replay-only" in demo
        assert "no real model made these selections" in demo.lower(), (
            "missing scripted provenance banner"
        )
        check_demo(json_rows(demo), expected_pins)
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--installed", action="store_true", help="use the selected interpreter's installed package"
    )
    args = parser.parse_args()
    try:
        checks = run_journey(installed=args.installed)
    except (AssertionError, ValueError, KeyError, subprocess.TimeoutExpired) as error:
        print(
            json.dumps(
                {
                    "status": "fail",
                    "scope": "public-development-only",
                    "error": f"{type(error).__name__}: {error}",
                }
            )
        )
        return 1
    print(
        json.dumps(
            {
                "status": "pass",
                "scope": "public-development-only",
                "checks": checks,
                "pending": ["live-model", "heldout", "filesystem acceptance"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
