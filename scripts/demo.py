"""Keyless scripted trace demonstration. Does not publish benchmark numbers."""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mcpsh import BANNER
from mcpsh.adapters import ReplaySelector
from mcpsh.catalog import build_catalog
from mcpsh.runner import run_trial
from mcpsh.runner.cases import demonstration_cases


def main() -> int:
    parser = argparse.ArgumentParser(description=BANNER)
    parser.add_argument("--case", choices=("clean", "poison", "both"), default="both")
    args = parser.parse_args()
    print(BANNER)
    print("Scripted development calls; no real model made these selections.")
    for index, (task, oracle, calls) in enumerate(demonstration_cases()):
        if args.case == "clean" and index != 0 or args.case == "poison" and index != 1:
            continue
        for mode in ("permissive", "hardened"):
            row = run_trial(task=task, oracle=oracle, selector=ReplaySelector(calls),
                            catalog=build_catalog("clean" if index == 0 else "poisoned"),
                            trial_id=f"demo-{task.task_id}-{mode}",
                            condition="clean" if index == 0 else "poisoned",
                            cell="C0" if mode == "permissive" else "C1", mode=mode)
            safe = {"task_id": task.task_id, "execution": mode,
                    "ordered_calls": [{"tool": event["tool_name"],
                                       "validation": event["validation"],
                                       "gate_decision": event["gate_decision"],
                                       "dispatched": event["dispatched"]} for event in row["trace"]],
                    "effects": row["observation"].get("predicates", {}),
                    "observation_complete": row["observation"].get("complete", False),
                    "failures": row["outcome"]["failures"]}
            print(json.dumps(safe, ensure_ascii=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
