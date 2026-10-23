"""Catalog and bounded lint commands. Numeric publication belongs only to eval.py."""

import argparse
import json
import sys
from pathlib import Path

from mcpsh import BANNER
from mcpsh.records import strict_json_loads


def _dump(value):
    print(json.dumps(value, ensure_ascii=True, indent=2, allow_nan=False))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="mcpsh", description=BANNER)
    commands = parser.add_subparsers(dest="command", required=True)
    catalog = commands.add_parser("catalog", help="validate or export the fixed nine-tool catalog")
    catalog.add_argument("action", choices=("validate", "export"))
    catalog.add_argument("--condition", choices=("clean", "ambiguous", "poisoned"), default="clean")
    catalog.add_argument("--input", type=Path, help="optional JSON catalog to validate")
    lint = commands.add_parser("lint", help="bounded detection, not proof of safety")
    lint.add_argument("--condition", choices=("clean", "ambiguous", "poisoned"), default="clean")
    lint.add_argument("--input", type=Path)
    lint.add_argument("--normalize", action="store_true")
    check = commands.add_parser("server-check", help="synthetic-memory development control only")
    check.add_argument("--mode", choices=("hardened", "permissive", "deny-all"), default="hardened")
    args = parser.parse_args(argv)
    try:
        if args.command in ("catalog", "lint"):
            from mcpsh.catalog import build_catalog, validate_catalog

            value = (strict_json_loads(args.input.read_bytes()) if args.input
                     else build_catalog(args.condition))
            if args.command == "catalog":
                if args.action == "export":
                    _dump(value)
                    return 0
                issues = validate_catalog(value)
                _dump({"valid": not issues, "issues": issues})
                return 1 if issues else 0
            from mcpsh.lint import lint_catalog, normalize_catalog

            findings = lint_catalog(value)
            payload = {"banner": BANNER, "findings": findings}
            if args.normalize:
                normalized, diffs = normalize_catalog(value)
                payload.update({"catalog": normalized, "diffs": diffs})
            _dump(payload)
            return 1 if findings else 0
        from mcpsh.server import ReferenceServer

        server = ReferenceServer(mode=args.mode, allowed_sources=("app",), trial_id="server-check")
        try:
            packet = server.call("list_sources", "{}")
            server.capture_wire(json.dumps(packet["result"], ensure_ascii=True,
                                            separators=(",", ":")).encode("utf-8"))
            observation = server.observe()
            _dump({"banner": BANNER, "packet": packet, "observation": observation})
            return 0 if packet["result"].get("ok") and observation.get("complete") else 1
        finally:
            server.close()
    except (ValueError, TypeError, OSError) as exc:
        print(f"mcpsh: rejected input ({type(exc).__name__})", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
