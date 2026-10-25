"""Offline public-development checks. This never grants product/live acceptance."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def execute(name: str, command: list[str], directory: Path, timeout: int = 900) -> dict:
    started = time.monotonic()
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=timeout)
        output = result.stdout + result.stderr
        code = result.returncode
    except subprocess.TimeoutExpired as error:
        output = f"timeout after {timeout}s\n{error}"
        code = 124
    (directory / f"{name}.log").write_text(output, encoding="utf-8")
    return {
        "name": name,
        "command": command,
        "exit_code": code,
        "status": "pass" if code == 0 else "fail",
        "seconds": round(time.monotonic() - started, 3),
        "log_sha256": hashlib.sha256(output.encode()).hexdigest(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--artifacts",
        type=Path,
        required=True,
        help="fresh M5-owned artifact directory outside the product checkout",
    )
    args = parser.parse_args()
    directory = args.artifacts.resolve()
    if directory == ROOT or ROOT in directory.parents:
        parser.error("artifacts must remain outside the product checkout")
    directory.mkdir(parents=True, exist_ok=False)
    os.environ["PYTHONPATH"] = str(ROOT / "src")
    # pytest owns only this newly created disposable subtree; no old basetemp is reused.
    temp_parent = directory / "pytest"
    temp_parent.mkdir()
    checks = [
        execute(
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
        "m5-public-development",
    ]
    replay = execute("public-replay", command, directory)
    checks.append(replay)
    if replay["status"] == "pass":
        # An immutable edition must reject a second publisher without changing published bytes.
        public = directory / "public/m5-public-development"
        try:
            result = json.loads((public / "results.json").read_text(encoding="utf-8"))
            outcomes = [row["outcome"] for row in result["rows"]]
            assert outcomes, "no scheduled development outcomes"
            assert result["execution_state"] == "replay-only", "replay promoted to live"
            assert result["acceptance_verdict"] == "pending", "publisher granted acceptance"
            assert all(row["execution_mode"] == "replay" for row in outcomes)
            assert all(row.get("model_id") is None for row in outcomes)
            checks.append(
                {"name": "replay-provenance", "status": "pass", "outcomes": len(outcomes)}
            )
        except (OSError, ValueError, KeyError, TypeError, AssertionError) as error:
            checks.append({"name": "replay-provenance", "status": "fail", "reason": str(error)})
        before = {
            p.name: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in public.iterdir()
            if p.is_file()
        }
        duplicate = execute("duplicate-edition", command, directory)
        after = {
            p.name: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in public.iterdir()
            if p.is_file()
        }
        duplicate["status"] = "pass" if duplicate["exit_code"] != 0 and before == after else "fail"
        duplicate["expected"] = "nonzero exit and unchanged published file hashes"
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
