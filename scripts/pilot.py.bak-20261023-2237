"""Draft-only public-development planner. Never dispatches or publishes result editions."""

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mcpsh.calibration import (
    DevelopmentCase, DraftArm, DraftPilotManifest, PilotObservation,
    plan_pilot, planned_caps, summarize_pilot, threshold_proposal,
)
from mcpsh.records import strict_json_loads, typed_hash


def pinned_json(path: Path, expected_sha256: str, maximum_bytes: int = 8 * 1024 * 1024):
    with path.open("rb") as handle:
        raw = handle.read(maximum_bytes + 1)
    if len(raw) > maximum_bytes or hashlib.sha256(raw).hexdigest() != expected_sha256:
        raise ValueError("draft input hash mismatch or byte cap exceeded")
    return strict_json_loads(raw)


def public_inventory():
    # Deliberately fixed public development paths: no held-out/oracle-path flag.
    tasks_raw = (ROOT / "fixtures/dev/tasks.json").read_bytes()
    labels_raw = (ROOT / "gold/dev/oracles.json").read_bytes()
    tasks, labels = strict_json_loads(tasks_raw), strict_json_loads(labels_raw)
    if type(tasks) is not list or type(labels) is not list:
        raise ValueError("public development arrays required")
    classes = {}
    for label in labels:
        if label.get("development_only") is not True or label["task_id"] in classes:
            raise ValueError("unreviewed public development inventory must be unique and explicit")
        classes[label["task_id"]] = label["task_class"]
    records = []
    for task in tasks:
        if task.get("development_only") is not True:
            raise ValueError("planner accepts public development cases only")
        task_id = task["public"]["task_id"]
        records.append(DevelopmentCase(task_id=task_id, task_class=classes[task_id]))
    if {record.task_id for record in records} != set(classes):
        raise ValueError("development inventory/class join mismatch")
    pin = typed_hash({"tasks_raw_sha256": hashlib.sha256(tasks_raw).hexdigest(),
                      "public_labels_raw_sha256": hashlib.sha256(labels_raw).hexdigest()})
    return tuple(records), pin


def write_draft(payload: dict, destination: Path | None):
    text = json.dumps(payload, ensure_ascii=True, allow_nan=False, indent=2) + "\n"
    if destination is None:
        print(text, end="")
        return
    base = (ROOT / "evaluation/experiments").resolve()
    target = destination.resolve()
    if base not in target.parents or target.suffix != ".json":
        raise ValueError("draft output must be a new JSON file within evaluation/experiments")
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("x", encoding="utf-8") as handle:
        handle.write(text)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    design = commands.add_parser("plan", help="draft six-case balanced pilot; no execution")
    design.add_argument("--arms", type=Path, help="optional two-arm draft identity JSON")
    design.add_argument("--arms-sha256")
    design.add_argument("--seed", type=int, default=1729)
    design.add_argument("--out", type=Path)
    summarize = commands.add_parser("summarize", help="summarize pinned supplied evidence only")
    for name in ("plan", "observations"):
        summarize.add_argument("--" + name, type=Path, required=True)
        summarize.add_argument("--" + name + "-sha256", required=True)
    summarize.add_argument("--out", type=Path)
    args = parser.parse_args(argv)
    if args.command == "plan":
        cases, input_pin = public_inventory()
        arms = None
        if args.arms is not None:
            if not args.arms_sha256:
                parser.error("--arms requires --arms-sha256")
            rows = pinned_json(args.arms, args.arms_sha256)
            if type(rows) is not list or len(rows) != 2:
                raise ValueError("exactly two draft arms required")
            arms = tuple(DraftArm.model_validate_json(json.dumps(row)) for row in rows)
        elif args.arms_sha256:
            parser.error("--arms-sha256 requires --arms")
        manifest = plan_pilot(development_cases=cases, development_input_sha256=input_pin,
                              arms=arms, seed=args.seed)
        payload = {"manifest": manifest.model_dump(mode="json"), "planned_caps": planned_caps(manifest),
                   "threshold_proposal": threshold_proposal().model_dump(mode="json")}
    else:
        draft = pinned_json(args.plan, args.plan_sha256)
        manifest = DraftPilotManifest.model_validate_json(json.dumps(draft["manifest"]))
        raw = pinned_json(args.observations, args.observations_sha256)
        if type(raw) is not list or len(raw) > 540:
            raise ValueError("bounded pilot observation array required")
        observations = tuple(PilotObservation.model_validate_json(json.dumps(row)) for row in raw)
        summary = summarize_pilot(manifest, observations)
        # Numerical evidence summaries stay in memory for scripts/eval.py to
        # publish through its edition authority. This CLI emits a proposal only.
        payload = {"threshold_proposal": threshold_proposal(summary).model_dump(mode="json"),
                   "evidence_state": summary.evidence_state,
                   "next_action": summary.next_action,
                   "execution_mode": summary.execution_mode}
    write_draft(payload, args.out)


if __name__ == "__main__":
    main()
