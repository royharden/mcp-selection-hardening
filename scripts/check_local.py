"""Run offline inherited tests and the public CLI journey, retaining failures."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scope", choices=("all", "rv1"), default="all")
    parser.add_argument("--installed", action="store_true")
    parser.add_argument("--timeout", type=int, default=600)
    args = parser.parse_args()
    if not __debug__:
        parser.error("optimized Python disables journey assertions; use normal Python")
    if args.timeout <= 0:
        parser.error("timeout must be positive")
    environment = os.environ.copy()
    if args.installed:
        environment.pop("PYTHONPATH", None)
    else:
        environment["PYTHONPATH"] = str(ROOT / "src")
    tests = [
        sys.executable,
        "-m",
        "pytest",
        str(ROOT / "tests"),
        "-q",
        "--tb=short",
        "-p",
        "no:cacheprovider",
    ]
    if args.scope == "rv1":
        tests.extend(
            f"--ignore={ROOT / 'tests' / name}"
            for name in ("evaluation", "conformance", "evidence")
        )
    journey = [sys.executable, str(ROOT / "scripts" / "e2e_cli.py")]
    if args.installed:
        journey.append("--installed")
    results = []
    for name, command in (("pytest", tests), ("public-cli", journey)):
        print(f"RUN {name}: {json.dumps(command)}", flush=True)
        try:
            result = subprocess.run(command, env=environment, timeout=args.timeout, check=False)
            exit_code = result.returncode
        except subprocess.TimeoutExpired:
            exit_code = 124
        results.append({"check": name, "exit_code": exit_code})
    failed = any(result["exit_code"] for result in results)
    print(
        json.dumps(
            {
                "status": "fail" if failed else "pass",
                "scope": args.scope,
                "package_mode": "installed" if args.installed else "source",
                "checks": results,
                "pending": ["paid/live models", "hidden/heldout", "unsupported platforms"],
            }
        )
    )
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
