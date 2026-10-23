"""Sole numeric-edition publication entrypoint. Replay is never promoted to live."""

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mcpsh import BANNER
from mcpsh.records import ExperimentManifest, strict_json_loads, typed_hash
from mcpsh.report import render_bundle
from mcpsh.runner import run_live_matrix, run_matrix
from mcpsh.runner.cases import load_development_cases


def source_hash(directory: Path) -> str:
    records = []
    for path in sorted(directory.rglob("*.py")):
        records.append((path.relative_to(directory).as_posix(), hashlib.sha256(path.read_bytes()).hexdigest()))
    return typed_hash(records)


def public_projection(value):
    """Conservative bounded public trace projection; raw results never leave this process."""
    if isinstance(value, list):
        return [public_projection(item) for item in value]
    if isinstance(value, dict):
        # Retain evidence hashes and classifications, omit raw provider/log/wire payloads.
        return {key: public_projection(item) for key, item in value.items()
                if key not in {"results", "raw_arguments", "typed_arguments", "events",
                               "public_task", "outbox_hashes", "family_id", "attack_family", "split"}}
    if isinstance(value, str):
        # Never publish arbitrary server reasons or untrusted strings containing the canary marker.
        from mcpsh.server import redact_public

        return redact_public(value)[:4096]
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=BANNER)
    parser.add_argument("--mode", choices=("replay", "live"), default="replay")
    parser.add_argument("--out", type=Path, default=ROOT / "results")
    parser.add_argument("--edition")
    parser.add_argument("--seed", type=int, default=1729)
    parser.add_argument("--corpus", choices=("development", "demo"), default="development")
    parser.add_argument("--private-evidence", type=Path,
                        default=ROOT.parent / (ROOT.name + "-private-evidence"),
                        help="raw synthetic evidence destination; must remain outside product root")
    parser.add_argument("--oracle-package", type=Path,
                        help="explicit sealed scorer-only package for a later approved live run")
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--approval", type=Path)
    parser.add_argument("--protocol-record", type=Path)
    parser.add_argument("--filesystem-config", type=Path)
    args = parser.parse_args()
    if args.mode == "live":
        if not all((args.manifest, args.approval, args.oracle_package, args.protocol_record)):
            parser.error("live requires exact manifest, approval, sealed oracle and protocol record; no defaults authorize dispatch")
        preview = ExperimentManifest.model_validate_json(args.manifest.read_bytes())
        if args.edition and args.edition != preview.edition_id:
            parser.error("CLI edition differs from the approved manifest")
        args.edition = preview.edition_id
    elif args.oracle_package or args.manifest or args.approval:
        parser.error("independent held-out custody and execution are not admitted in this development runner")
    if not args.edition:
        args.edition = "replay-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,99}", args.edition):
        parser.error("edition must be a bounded safe identifier")
    private_root = args.private_evidence.resolve()
    if private_root == ROOT or ROOT in private_root.parents:
        parser.error("raw evidence must be outside the product repository")
    args.out.mkdir(parents=True, exist_ok=True)
    destination = args.out / args.edition
    lock = args.out / ("." + args.edition + ".reservation")
    if destination.exists():
        parser.error("immutable edition already exists; choose a successor ID")
    # Exclusive, durable reservation prevents concurrent writers of this edition ID.
    reservation = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(reservation, "w", encoding="utf-8") as handle:
        handle.write(args.edition + "\n")
    private_destination = private_root / args.edition
    if private_destination.exists():
        parser.error("private immutable edition already exists")
    source = ROOT / "src" / "mcpsh"
    if args.mode == "live":
        from mcpsh.runner.live import prepare_live_run

        pins = {"code_hash": source_hash(source), "policy_hash": source_hash(source / "policy"),
                "scorer_hash": source_hash(source / "evaluation"),
                "observer_hash": source_hash(source / "observer")}
        admitted, cases, factory = prepare_live_run(
            manifest_path=args.manifest, approval_path=args.approval,
            oracle_path=args.oracle_package, protocol_record=args.protocol_record,
            product_root=ROOT, private_directory=private_destination, source_hashes=pins)
        filesystem_config = None
        if args.filesystem_config:
            config = strict_json_loads(args.filesystem_config.read_bytes())
            if not isinstance(config, dict) or set(config) != {"fixture_parent"}:
                parser.error("filesystem configuration must name only an approved fixture_parent")
            parent = Path(config["fixture_parent"])
            if not parent.is_absolute():
                parser.error("POSIX fixture parent must be an explicit absolute approved path")

            def filesystem_config(trial_id):
                from mcpsh.broker.posix import prepare_posix_fixture

                return prepare_posix_fixture(str(parent / trial_id))
        result = run_live_matrix(manifest=admitted, cases=cases, selector_factory=factory,
                                 filesystem_config=filesystem_config)
        manifest = admitted.model_dump(mode="json")
    else:
        result = run_matrix(seed=args.seed, cases=load_development_cases(ROOT)
                            if args.corpus == "development" else None)
        catalogs = sorted({row["catalog_hash"] for row in result["rows"]})
        manifest = ExperimentManifest(
            edition_id=args.edition, mode="replay", platform_scope="synthetic-memory",
            code_hash=source_hash(source), lock_hash=None, protocol_hash=None,
            task_hash=typed_hash([row["public_task"] for row in result["rows"]]),
            catalog_hash=typed_hash(catalogs), policy_hash=source_hash(source / "policy"),
            scorer_hash=source_hash(source / "evaluation"),
            observer_hash=source_hash(source / "observer"),
            split_hash=typed_hash({"split": "development", "corpus": args.corpus}),
            seed=args.seed, settings={"live_requests": 0, "catalog_hashes": catalogs,
                                      "sdk_interoperability": "pending"},
        ).model_dump(mode="json")
    result["manifest"] = manifest
    result["raw_evidence_hash"] = typed_hash(result["rows"])
    result["projection"] = "bounded/redacted; raw synthetic payloads not published"
    # Preserve malformed/raw arguments and synthetic payloads outside the public product tree.
    private_root.mkdir(parents=True, exist_ok=True)
    private_destination.mkdir(exist_ok=args.mode == "live")
    (private_destination / "raw-trials.jsonl").write_text(
        "".join(json.dumps(row, ensure_ascii=True, allow_nan=False) + "\n"
                for row in result["rows"]), encoding="utf-8", newline="\n")
    (private_destination / "MANIFEST.json").write_text(
        json.dumps(manifest, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
    safe = public_projection(result)
    files = render_bundle(safe)
    files["MANIFEST.json"] = json.dumps(manifest, ensure_ascii=True, indent=2) + "\n"
    staging = Path(tempfile.mkdtemp(prefix=".stage-" + args.edition + "-", dir=args.out))
    for name, content in files.items():
        (staging / name).write_text(content, encoding="utf-8", newline="\n")
    checksums = {name: hashlib.sha256((staging / name).read_bytes()).hexdigest() for name in files}
    (staging / "SHA256SUMS.json").write_text(json.dumps(checksums, indent=2) + "\n", encoding="utf-8")
    if destination.exists():
        raise FileExistsError("edition appeared during publication; staging preserved")
    staging.rename(destination)
    print(result["banner"])
    print(f"Published {result['execution_state']} edition: {destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
