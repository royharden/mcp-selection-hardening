"""Detached, keyless public bundle inspector. Authored only; not executed here.

Run later from outside the checkout with an explicitly supplied public bundle and
external pins. This example has no runtime/provider/backend activation option.
"""

import argparse
import importlib
import json
from pathlib import Path


def _api():
    exports = importlib.import_module("mcpsh.conformance.export_v2")
    consumer = importlib.import_module("mcpsh.conformance.consumer")
    return exports, consumer


def main(argv=None, *, load_api=None):
    parser = argparse.ArgumentParser(description="M5 public contract integrity only; no activation")
    parser.add_argument("bundle", type=Path)
    parser.add_argument("--bundle-sha256", required=True)
    parser.add_argument("--manifest-sha256", required=True)
    parser.add_argument("--runtime-schema-sha256", required=True)
    parser.add_argument("--requirements-sha256", help="separate externally approved normative inventory pin")
    parser.add_argument("--evidence", type=Path, help="optional explicit public per-probe evidence")
    parser.add_argument("--selection", type=Path, help="externally approved evidence selection/pins JSON")
    args = parser.parse_args(argv)
    if bool(args.evidence) != bool(args.selection):
        parser.error("evidence and its explicit external selection must be supplied together")
    try:
        exports, consumer = (load_api or _api)()
    except ImportError:
        print(json.dumps({"status": "unavailable", "phase": "consumer-import",
                          "runtime_acceptance": "pending", "installed_or_repaired": False}))
        return 2
    try:
        reader = getattr(exports, "read_portable_bundle", exports.read_contract_bundle)
        files = reader(args.bundle, expected_bundle_sha256=args.bundle_sha256)
        evidence_raw, selection = consumer.read_public_evidence_files(args.evidence, args.selection) if args.evidence else (None, None)
        result = consumer.inspect_bundle(files, expected_bundle_sha256=args.bundle_sha256,
            expected_manifest_sha256=args.manifest_sha256,
            expected_runtime_schema_sha256=args.runtime_schema_sha256,
            evidence_raw=evidence_raw, evidence_selection=selection,
            expected_requirements_manifest_sha256=args.requirements_sha256)
    except (ImportError, FileNotFoundError):
        print(json.dumps({"status": "unavailable", "phase": "consumer-resource-or-dependency",
                          "runtime_acceptance": "pending", "installed_or_repaired": False}))
        return 2
    except (OSError, ValueError, TypeError, KeyError):
        print(json.dumps({"status": "rejected", "phase": "explicit-public-bundle",
                          "runtime_acceptance": "pending"}))
        return 1
    print(json.dumps(result, sort_keys=True, ensure_ascii=True, allow_nan=False))
    return 0 if result["status"] == "integrity-only" else 1


if __name__ == "__main__":
    raise SystemExit(main())
