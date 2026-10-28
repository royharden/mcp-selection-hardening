"""Catalog and bounded lint commands. Numeric publication belongs only to eval.py."""

import argparse
import json
import sys
from pathlib import Path

from mcpsh import BANNER
from mcpsh.records import strict_json_loads


def _dump(value):
    print(json.dumps(value, ensure_ascii=True, indent=2, allow_nan=False))


def _bounded_raw(path: Path, maximum_bytes: int = 1024 * 1024):
    with path.open("rb") as handle:
        raw = handle.read(maximum_bytes + 1)
    if len(raw) > maximum_bytes:
        raise ValueError("input JSON byte cap exceeded")
    return raw


def _bounded_json(path: Path, maximum_bytes: int = 1024 * 1024):
    return strict_json_loads(_bounded_raw(path, maximum_bytes))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="mcpsh", description=BANNER)
    commands = parser.add_subparsers(dest="command", required=True)
    catalog = commands.add_parser("catalog", help="validate or export the fixed nine-tool catalog")
    catalog.add_argument("action", choices=("validate", "export", "treat"))
    catalog.add_argument("--condition", choices=("clean", "ambiguous", "poisoned"))
    catalog.add_argument("--input", type=Path, help="optional JSON catalog to validate")
    catalog.add_argument("--artifact", action="store_true", help="versioned catalog envelope; bare export remains default")
    catalog.add_argument("--ordering-seed", type=int)
    catalog.add_argument("--source-revision")
    catalog.add_argument("--normalized", action="store_true")
    catalog.add_argument("--descriptions", type=Path, help="description-only overlay for catalog treat")
    lint = commands.add_parser("lint", help="bounded detection, not proof of safety")
    lint.add_argument("--condition", choices=("clean", "ambiguous", "poisoned"), default="clean")
    lint.add_argument("--input", type=Path)
    lint.add_argument("--normalize", action="store_true")
    check = commands.add_parser("server-check", help="explicitly authorized disposable conformance probes")
    check.add_argument("--request", type=Path, required=True,
                       help="JSON ConformanceRequest with explicit runtime/disposable approval")
    evidence = commands.add_parser("evidence-check", help="offline structural integrity, never product acceptance")
    evidence.add_argument("--root", type=Path, required=True)
    evidence.add_argument("--authority", type=Path, required=True)
    evidence.add_argument("--authority-sha256", required=True,
                          help="externally approved raw authority SHA256; never inferred from edition")
    resume = commands.add_parser("evidence-resume", help="offline immutable successor proposal; never dispatches")
    resume.add_argument("--root", type=Path, required=True)
    resume.add_argument("--authority", type=Path, required=True)
    resume.add_argument("--authority-sha256", required=True, help="external raw parent-authority pin")
    resume.add_argument("--resume-authority", type=Path)
    resume.add_argument("--resume-authority-sha256", help="external canonical typed successor-authority pin")
    resume.add_argument("--receipts", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command in ("evidence-check", "evidence-resume"):
            import hashlib
            import re

            from mcpsh.evidence import EditionAuthority, inspect_edition, read_edition

            raw = _bounded_raw(args.authority)
            if not re.fullmatch(r"[0-9a-f]{64}", args.authority_sha256) or hashlib.sha256(raw).hexdigest() != args.authority_sha256:
                raise ValueError("authority bytes differ from externally supplied pin")
            strict_json_loads(raw)
            authority = EditionAuthority.model_validate_json(raw)
            edition = read_edition(args.root, authority=authority)
            if args.command == "evidence-resume":
                from mcpsh.evidence.resume import (
                    ExtensionReceipt, ResumeAuthority, UsageReconciliation, plan_resume,
                )

                target = None
                if args.resume_authority:
                    if not args.resume_authority_sha256:
                        raise ValueError("successor authority requires an external typed pin")
                    target_raw = _bounded_raw(args.resume_authority)
                    strict_json_loads(target_raw)
                    target = ResumeAuthority.model_validate_json(target_raw)
                elif args.resume_authority_sha256 or args.receipts:
                    raise ValueError("receipts and successor pins require a successor authority")
                receipts = []
                if args.receipts:
                    records = _bounded_json(args.receipts, 8 * 1024 * 1024)
                    if not isinstance(records, list) or len(records) > 15000:
                        raise ValueError("bounded resume receipt array required")
                    for record in records:
                        if not isinstance(record, dict):
                            raise ValueError("resume receipt must be an object")
                        kind = record.get("kind")
                        cls = ExtensionReceipt if kind == "resume-extension" else UsageReconciliation if kind == "usage-reconciliation" else None
                        if cls is None:
                            raise ValueError("unknown immutable resume receipt kind")
                        receipts.append(cls.model_validate_json(json.dumps(record)))
                proposal = plan_resume(edition, target, tuple(receipts),
                                       expected_authority_sha256=args.resume_authority_sha256)
                _dump(proposal.model_dump(mode="json"))
                return 0 if proposal.state == "proposal-ready" else 2
            _dump(inspect_edition(edition))
            return 0
        if args.command in ("catalog", "lint"):
            from mcpsh.catalog import build_catalog, validate_catalog

            input_cap = 4 * 1024 * 1024 if args.command == "catalog" and args.action in ("validate", "treat") else 1024 * 1024
            raw = _bounded_raw(args.input, input_cap) if args.input else None
            value = strict_json_loads(raw) if raw is not None else build_catalog(args.condition or "clean")
            artifact = None
            if isinstance(value, dict):
                from mcpsh.catalog.artifacts import parse_catalog_artifact

                if args.command == "catalog" and args.action == "validate" and {"before", "after", "diffs"} <= set(value):
                    from mcpsh.catalog.treatments import parse_treatment_artifact

                    parse_treatment_artifact(raw)
                    _dump({"valid": True, "kind": "metadata-treatment", "issues": []})
                    return 0
                artifact = parse_catalog_artifact(raw)
                value = artifact["catalog"]
            if args.command == "catalog":
                if args.action == "treat":
                    from mcpsh.catalog.treatments import build_treatment_artifact, serialize_treatment_artifact

                    if artifact is None:
                        raise ValueError("catalog treat requires a valid versioned --input artifact")
                    descriptions = _bounded_json(args.descriptions) if args.descriptions else None
                    treatment = build_treatment_artifact(artifact, descriptions=descriptions,
                                                          normalize=args.normalized, condition=args.condition)
                    print(serialize_treatment_artifact(treatment))
                    return 0
                if args.artifact:
                    from mcpsh.catalog.artifacts import (
                        build_catalog_artifact, serialize_catalog_artifact, validate_catalog_artifact,
                    )

                    if args.action == "validate" and raw is not None and artifact is None:
                        raise ValueError("artifact validation requires a versioned envelope; bare catalogs use ordinary validation")
                    if args.action == "validate" and raw is not None and (
                        args.normalized or args.ordering_seed is not None or args.source_revision is not None
                    ):
                        raise ValueError("artifact validation cannot transform its input")
                    if artifact is None or args.normalized or args.ordering_seed is not None or args.source_revision is not None or args.condition is not None:
                        previous = artifact
                        artifact = build_catalog_artifact(args.condition or (previous["condition"] if previous else "clean"),
                            ordering_seed=args.ordering_seed if args.ordering_seed is not None else
                            previous["record"]["ordering_seed"] if previous else 0, catalog=value,
                            source_revision=args.source_revision if args.source_revision is not None else
                            previous["provenance"].get("source_revision") if previous else None,
                            normalized=args.normalized)
                    if args.action == "export":
                        print(serialize_catalog_artifact(artifact))
                        return 0
                    issues = validate_catalog_artifact(artifact)
                    _dump({"valid": not issues, "kind": "catalog-artifact", "issues": issues})
                    return 1 if issues else 0
                if args.action == "export":
                    if args.normalized:
                        raise ValueError("normalized catalog export requires --artifact; lint --normalize remains available")
                    _dump(value)
                    return 0
                issues = validate_catalog(value)
                _dump({"valid": not issues, "issues": issues})
                return 1 if issues else 0
            from mcpsh.lint import lint_catalog, normalize_catalog
            from mcpsh.catalog.spans import enrich_finding

            if not isinstance(value, list) or any(not isinstance(tool, dict) for tool in value):
                raise ValueError("lint input must be a catalog array or validated artifact")
            findings = [enrich_finding(value, finding) for finding in lint_catalog(value)]
            payload = {"banner": BANNER, "findings": findings}
            if args.normalize:
                normalized, diffs = normalize_catalog(value)
                payload.update({"catalog": normalized, "diffs": diffs})
            _dump(payload)
            return 1 if findings else 0
        from mcpsh.conformance import ConformanceRequest, run_conformance

        request_data = _bounded_json(args.request)
        fields = {"tracks", "runtime_authorized", "disposable_authorized", "approval_id",
                  "posix_fixture_parent", "probe_ids", "timeout_seconds"}
        if not isinstance(request_data, dict) or set(request_data) - fields:
            raise ValueError("conformance request fields differ from schema")
        for key in ("tracks", "probe_ids"):
            if key in request_data:
                if not isinstance(request_data[key], list) or any(
                    not isinstance(item, str) for item in request_data[key]
                ):
                    raise ValueError("conformance track/probe IDs must be JSON string arrays")
                request_data[key] = tuple(request_data[key])
        request = ConformanceRequest(**request_data)
        request.require_activation()
        report = run_conformance(request).to_dict()
        _dump(report)
        verdicts = [platform["verdict"] for platform in report["platforms"].values()]
        return 1 if "blocked" in verdicts else 0 if verdicts and all(
            verdict == "passed" for verdict in verdicts
        ) else 2
    except (ValueError, TypeError, OSError) as exc:
        print(f"mcpsh: rejected input ({type(exc).__name__})", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
