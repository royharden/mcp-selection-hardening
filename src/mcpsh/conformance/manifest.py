"""Versioned required-case authority. Pure APIs accept caller-pinned source bytes."""

import ast
import hashlib
from pathlib import Path

from .evidence import digest
from .semantics import CASE_SOURCE_VERSION, GRAMMAR_VERSION, PARSER_VERSION, semantic_cases

MANIFEST_VERSION = "m5-required-conformance-v1"
TRACKS = ("synthetic-memory", "filesystem-posix", "stdio")
FIELDS = frozenset({"schema_version", "manifest_version", "case_source_version", "grammar_version",
    "parser_version", "case_source_sha256", "grammar_source_sha256", "parser_source_sha256",
    "required_probe_ids", "cases", "capability_scope", "manifest_sha256"})
CASE_FIELDS = frozenset({"case_id", "kind", "raw_arguments_sha256", "call_sha256", "fixture_lines_sha256", "expectation_sha256"})
CAPABILITIES = {"synthetic-memory": "synthetic-memory-only", "filesystem-posix": "approved-linux-native-handles",
                "stdio": "owned-local-child-same-reference"}


def _sha(value):
    return type(value) is str and len(value) == 64 and all(char in "0123456789abcdef" for char in value)


def semantic_manifest(raw: bytes, *, grammar_source_sha256: str, parser_source_sha256: str):
    """No imports of matching/parsing, backend creation, paths or execution."""
    from .probes import definitions

    if not _sha(grammar_source_sha256) or not _sha(parser_source_sha256):
        raise ValueError("explicit grammar and parser source SHA256 required")
    cases = semantic_cases(raw)
    probes = definitions()
    value = {"schema_version": 1, "manifest_version": MANIFEST_VERSION,
        "case_source_version": CASE_SOURCE_VERSION, "grammar_version": GRAMMAR_VERSION,
        "parser_version": PARSER_VERSION, "case_source_sha256": hashlib.sha256(raw).hexdigest(),
        "grammar_source_sha256": grammar_source_sha256, "parser_source_sha256": parser_source_sha256,
        "required_probe_ids": {track: sorted(probe.probe_id for probe in probes if probe.required and track in probe.tracks) for track in TRACKS},
        "cases": [{"case_id": case.case_id, "kind": case.kind,
            "raw_arguments_sha256": hashlib.sha256(case.call.raw_arguments.encode("utf-8")).hexdigest(),
            "call_sha256": digest({"tool": case.call.tool, "raw_arguments": case.call.raw_arguments}),
            "fixture_lines_sha256": digest(list(case.lines)), "expectation_sha256": digest(case.expected())}
            for case in cases], "capability_scope": dict(CAPABILITIES)}
    value["manifest_sha256"] = digest(value)
    return value


def verify_semantic_manifest(manifest, *, expected_manifest_sha256):
    """Reject changed authority; a self-supplied digest is not owner approval."""
    from .probes import definitions
    from .semantics import REQUIRED_CASE_IDS

    issues = []
    if type(manifest) is not dict or set(manifest) != FIELDS:
        return {"valid": False, "violations": ["manifest.fields"]}
    try:
        for key, expected in (("schema_version", 1), ("manifest_version", MANIFEST_VERSION),
                ("case_source_version", CASE_SOURCE_VERSION), ("grammar_version", GRAMMAR_VERSION),
                ("parser_version", PARSER_VERSION)):
            if type(manifest[key]) is not type(expected) or manifest[key] != expected:
                issues.append("manifest.version")
        for key in ("case_source_sha256", "grammar_source_sha256", "parser_source_sha256", "manifest_sha256"):
            if not _sha(manifest[key]):
                issues.append("manifest.pin-shape")
        if not _sha(expected_manifest_sha256) or manifest["manifest_sha256"] != expected_manifest_sha256:
            issues.append("manifest.external-pin")
        if digest({key: value for key, value in manifest.items() if key != "manifest_sha256"}) != manifest["manifest_sha256"]:
            issues.append("manifest.digest")
        probes = definitions()
        required = {track: sorted(probe.probe_id for probe in probes if probe.required and track in probe.tracks) for track in TRACKS}
        if manifest["required_probe_ids"] != required or manifest["capability_scope"] != CAPABILITIES:
            issues.append("manifest.required-or-platform-scope")
        cases = manifest["cases"]
        if type(cases) is not list or len(cases) != len(REQUIRED_CASE_IDS):
            issues.append("manifest.cases")
        else:
            seen = []
            for case in cases:
                if type(case) is not dict or set(case) != CASE_FIELDS:
                    issues.append("manifest.case-fields")
                    continue
                seen.append(case["case_id"])
                if case["kind"] not in {"matching", "parsing"} or not all(_sha(case[key]) for key in CASE_FIELDS - {"case_id", "kind"}):
                    issues.append("manifest.case-pins")
            if len(set(seen)) != len(seen) or set(seen) != set(REQUIRED_CASE_IDS):
                issues.append("manifest.case-omission")
    except (ValueError, TypeError, KeyError, UnicodeError, RecursionError):
        issues.append("manifest.ill-shaped")
    return {"valid": not issues, "violations": sorted(set(issues))}


def runtime_semantic_manifest():
    """Source-byte reads only at explicit conformance activation; no app imports."""
    from .semantics import public_case_source

    root = Path(__file__).resolve().parents[1] / "server"
    pins = {}
    for name, constant, expected in (("matching", "PATTERN_GRAMMAR_VERSION", GRAMMAR_VERSION),
                                     ("parsing", "LOG_PARSER_VERSION", PARSER_VERSION)):
        path = root / (name + ".py")
        with path.open("rb") as handle:
            raw = handle.read(1024 * 1024 + 1)
        if len(raw) > 1024 * 1024:
            raise ValueError("semantic source-byte cap")
        module = ast.parse(raw.decode("utf-8"), filename=path.name)
        versions = [ast.literal_eval(node.value) for node in module.body if isinstance(node, ast.Assign)
                    and any(isinstance(target, ast.Name) and target.id == constant for target in node.targets)]
        if versions != [expected]:
            raise ValueError("grammar/parser source version differs from public gold contract")
        pins[name] = hashlib.sha256(raw).hexdigest()
    return semantic_manifest(public_case_source(), grammar_source_sha256=pins["matching"],
                             parser_source_sha256=pins["parsing"])
