"""Portable M5 source-contract bundle. Integrity is never runtime acceptance.

Pure builders/validators consume explicit bytes. Resource and directory helpers
perform only requested bounded file I/O; no server, SDK, provider or process starts.
"""

import ast
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Mapping

from .capabilities import capability_report
from .manifest import semantic_manifest, verify_semantic_manifest

BUNDLE_FORMAT = "m5-conformance-bundle-v1"
MAX_FILE_BYTES = 256 * 1024
MAX_TOTAL_BYTES = 2 * 1024 * 1024
SCHEMAS = {
    "evidence-v1.schema.json": "urn:mcpsh:conformance-evidence:v1",
    "evidence-v2.schema.json": "urn:mcpsh:conformance-evidence:v2",
    "required-cases-v1.schema.json": "urn:mcpsh:required-conformance:v1",
}
SOURCE_KEYS = frozenset({"grammar", "parser", "observer", "policy", "runtime_schema"})
PAYLOADS = frozenset({"cases/semantics-v1.json", "contracts/required-cases-v1.json",
    "contracts/runtime-schemas-v1.json", "contracts/capabilities-v1.json",
    *("schemas/" + name for name in SCHEMAS)})
INDEX_FIELDS = frozenset({"schema_version", "bundle_format", "origin", "claim", "s1_operational_acceptance",
    "manifest_sha256", "runtime_schema_sha256", "versions", "source_pins", "platform_claims", "files"})
PLATFORM_CLAIMS = {"component": "diagnostic-only", "synthetic-memory": "pending",
                   "filesystem-posix": "pending", "stdio": "pending"}


def _bytes(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=True, allow_nan=False,
                      separators=(",", ":")).encode("utf-8") + b"\n"


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _pin(value):
    return type(value) is str and len(value) == 64 and all(char in "0123456789abcdef" for char in value)


def _json(raw):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate bundle JSON member")
            result[key] = value
        return result

    def nonfinite(_value):
        raise ValueError("nonfinite bundle JSON")

    if type(raw) is not bytes or len(raw) > MAX_FILE_BYTES:
        raise ValueError("bounded artifact bytes required")
    return json.loads(raw, object_pairs_hook=unique, parse_constant=nonfinite)


def safe_name(name):
    if type(name) is not str or not name or len(name) > 160 or any(char in name for char in "\\:\x00"):
        raise ValueError("invalid bundle relative path")
    path = PurePosixPath(name)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in name.split("/")) or str(path) != name:
        raise ValueError("bundle path escapes or is noncanonical")
    return name


def _version(raw, constant):
    if type(raw) is not bytes or len(raw) > 1024 * 1024:
        raise ValueError("bounded public source bytes required")
    module = ast.parse(raw.decode("utf-8"))
    values = [ast.literal_eval(node.value) for node in module.body if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == constant for target in node.targets)]
    if len(values) != 1 or type(values[0]) is not str or not 1 <= len(values[0]) <= 96:
        raise ValueError("explicit source version constant required")
    return values[0]


def _runtime_artifact(runtime_schemas):
    # Reuse the real executable schema authority; no second nine-tool definition.
    from mcpsh.catalog.schemas import TOOL_SCHEMAS

    if type(runtime_schemas) is not dict or len(TOOL_SCHEMAS) != 9 or _bytes(runtime_schemas) != _bytes(TOOL_SCHEMAS):
        raise ValueError("runtime schema set differs from actual canonical nine tools")
    return {"schema_version": 1, "origin": "m5-owned-fallback", "tool_ids": sorted(TOOL_SCHEMAS),
            "tools": runtime_schemas}


def _canonical_control_versions():
    # Metadata constants only; neither observer nor policy construction is invoked.
    from mcpsh.observer import OBSERVER_VERSION
    from mcpsh.policy import POLICY_VERSION

    return OBSERVER_VERSION, POLICY_VERSION


def _schema_refs(value):
    if type(value) is dict:
        if "$ref" in value:
            reference = value["$ref"]
            if type(reference) is not str or not (reference.startswith("#/") or any(
                reference.startswith(name + "#/") for name in SCHEMAS)):
                raise ValueError("schema reference leaves the explicit portable bundle")
        for child in value.values():
            _schema_refs(child)
    elif type(value) is list:
        for child in value:
            _schema_refs(child)


@dataclass(frozen=True)
class BundleInputs:
    case_source: bytes
    required_manifest: dict
    runtime_schemas: dict
    schemas: Mapping[str, bytes]
    source_bytes: Mapping[str, bytes]
    capabilities: dict


@dataclass(frozen=True)
class ContractBundle:
    files: tuple[tuple[str, bytes], ...]
    bundle_sha256: str
    manifest_sha256: str
    runtime_schema_sha256: str

    def to_files(self):
        return dict(self.files)


def build_contract_bundle(inputs: BundleInputs) -> ContractBundle:
    """Deterministic bounded bytes only; does not write or invoke conformance."""
    if set(inputs.source_bytes) != SOURCE_KEYS or set(inputs.schemas) != set(SCHEMAS):
        raise ValueError("missing/extra public source or schema inputs")
    source_pins = {name: _sha(raw) for name, raw in inputs.source_bytes.items()
                   if type(raw) is bytes and len(raw) <= 1024 * 1024}
    if set(source_pins) != SOURCE_KEYS:
        raise ValueError("source-byte type/cap mismatch")
    required = semantic_manifest(inputs.case_source, grammar_source_sha256=source_pins["grammar"],
                                  parser_source_sha256=source_pins["parser"])
    if _bytes(inputs.required_manifest) != _bytes(required):
        raise ValueError("supplied semantic authority differs from actual case/source inputs")
    versions = {"grammar": _version(inputs.source_bytes["grammar"], "PATTERN_GRAMMAR_VERSION"),
        "parser": _version(inputs.source_bytes["parser"], "LOG_PARSER_VERSION"),
        "observer": _version(inputs.source_bytes["observer"], "OBSERVER_VERSION"),
        "policy": _version(inputs.source_bytes["policy"], "POLICY_VERSION"),
        "cases": required["case_source_version"]}
    if versions["grammar"] != required["grammar_version"] or versions["parser"] != required["parser_version"]:
        raise ValueError("genuine source versions differ from approved case semantics")
    if (versions["observer"], versions["policy"]) != _canonical_control_versions():
        raise ValueError("observer/policy source versions differ from canonical metadata")
    if _bytes(inputs.capabilities) != _bytes(capability_report()):
        raise ValueError("capability source differs or promotes an unmeasured claim")
    files = {"cases/semantics-v1.json": inputs.case_source,
        "contracts/required-cases-v1.json": _bytes(required),
        "contracts/runtime-schemas-v1.json": _bytes(_runtime_artifact(inputs.runtime_schemas)),
        "contracts/capabilities-v1.json": _bytes(inputs.capabilities)}
    for name, expected_id in SCHEMAS.items():
        schema = _json(inputs.schemas[name])
        if type(schema) is not dict or schema.get("$id") != expected_id or schema.get("additionalProperties") is not False:
            raise ValueError("canonical closed evidence schema identity differs")
        _schema_refs(schema)
        files["schemas/" + name] = inputs.schemas[name]
    if any(len(raw) > MAX_FILE_BYTES for raw in files.values()) or sum(map(len, files.values())) > MAX_TOTAL_BYTES:
        raise ValueError("portable bundle byte caps exceeded")
    runtime_pin = _sha(files["contracts/runtime-schemas-v1.json"])
    index = {"schema_version": 1, "bundle_format": BUNDLE_FORMAT, "origin": "m5-owned-fallback",
        "claim": "source-integrity-only", "s1_operational_acceptance": False,
        "manifest_sha256": required["manifest_sha256"], "runtime_schema_sha256": runtime_pin,
        "versions": versions, "source_pins": source_pins, "platform_claims": dict(PLATFORM_CLAIMS),
        "files": [{"path": name, "sha256": _sha(raw), "bytes": len(raw)} for name, raw in sorted(files.items())]}
    files["bundle.json"] = _bytes(index)
    return ContractBundle(tuple(sorted(files.items())), _sha(files["bundle.json"]), required["manifest_sha256"], runtime_pin)


def validate_contract_bundle(files: Mapping[str, bytes], *, expected_bundle_sha256,
                             expected_manifest_sha256, expected_runtime_schema_sha256):
    """Pure integrity/compatibility validation; never returns platform acceptance."""
    issues = []
    try:
        if not all(_pin(pin) for pin in (expected_bundle_sha256, expected_manifest_sha256, expected_runtime_schema_sha256)):
            raise ValueError("all three external pins required")
        if set(files) != PAYLOADS | {"bundle.json"}:
            raise ValueError("bundle file set differs")
        for name, raw in files.items():
            safe_name(name)
            if type(raw) is not bytes or len(raw) > MAX_FILE_BYTES:
                raise ValueError("bundle file byte cap/type")
        if sum(map(len, files.values())) > MAX_TOTAL_BYTES:
            raise ValueError("bundle total byte cap")
        if _sha(files["bundle.json"]) != expected_bundle_sha256:
            issues.append("bundle.external-pin")
        index = _json(files["bundle.json"])
        if type(index) is not dict or set(index) != INDEX_FIELDS:
            raise ValueError("bundle index fields differ")
        if type(index["schema_version"]) is not int or index["schema_version"] != 1 or index["bundle_format"] != BUNDLE_FORMAT:
            issues.append("bundle.unsupported-version")
        if index["origin"] != "m5-owned-fallback" or index["claim"] != "source-integrity-only" or index["s1_operational_acceptance"] is not False or index["platform_claims"] != PLATFORM_CLAIMS:
            issues.append("bundle.claim-promotion")
        rows = index["files"]
        if type(rows) is not list or len(rows) != len(PAYLOADS):
            raise ValueError("bundle payload list differs")
        seen = set()
        for row in rows:
            if type(row) is not dict or set(row) != {"path", "sha256", "bytes"}:
                raise ValueError("bundle payload fields differ")
            name = safe_name(row["path"])
            if name not in PAYLOADS or name in seen:
                raise ValueError("unknown/duplicate payload path")
            seen.add(name)
            if not _pin(row["sha256"]) or type(row["bytes"]) is not int or row["bytes"] != len(files[name]) or row["sha256"] != _sha(files[name]):
                issues.append("bundle.payload-pin")
        if seen != PAYLOADS:
            issues.append("bundle.payload-omission")
        pins = index["source_pins"]
        if type(pins) is not dict or set(pins) != SOURCE_KEYS or not all(_pin(pin) for pin in pins.values()):
            raise ValueError("bundle source pin fields differ")
        manifest = _json(files["contracts/required-cases-v1.json"])
        result = verify_semantic_manifest(manifest, expected_manifest_sha256=expected_manifest_sha256)
        issues.extend(result["violations"])
        if manifest != semantic_manifest(files["cases/semantics-v1.json"], grammar_source_sha256=pins["grammar"], parser_source_sha256=pins["parser"]):
            issues.append("bundle.case-source-or-ids")
        if index["manifest_sha256"] != expected_manifest_sha256:
            issues.append("bundle.manifest-pin")
        runtime_raw = files["contracts/runtime-schemas-v1.json"]
        runtime = _json(runtime_raw)
        if type(runtime) is not dict or set(runtime) != {"schema_version", "origin", "tool_ids", "tools"} or _bytes(runtime) != _bytes(_runtime_artifact(runtime["tools"])):
            issues.append("bundle.runtime-schema-identity")
        if _sha(runtime_raw) != expected_runtime_schema_sha256 or index["runtime_schema_sha256"] != expected_runtime_schema_sha256:
            issues.append("bundle.runtime-schema-pin")
        versions = index["versions"]
        if type(versions) is not dict or set(versions) != {"grammar", "parser", "observer", "policy", "cases"} or versions["grammar"] != manifest["grammar_version"] or versions["parser"] != manifest["parser_version"] or versions["cases"] != manifest["case_source_version"] or any(type(version) is not str or not 1 <= len(version) <= 96 for version in versions.values()):
            issues.append("bundle.version-identity")
        elif (versions["observer"], versions["policy"]) != _canonical_control_versions():
            issues.append("bundle.control-version-identity")
        if _bytes(_json(files["contracts/capabilities-v1.json"])) != _bytes(capability_report()):
            issues.append("bundle.capability-promotion-or-version")
        for name, expected_id in SCHEMAS.items():
            schema = _json(files["schemas/" + name])
            if type(schema) is not dict or schema.get("$id") != expected_id or schema.get("additionalProperties") is not False:
                issues.append("bundle.schema-identity")
            _schema_refs(schema)
    except (ValueError, TypeError, KeyError, UnicodeError, RecursionError, OverflowError):
        issues.append("bundle.ill-shaped-or-incomplete")
    return {"schema_version": 1, "valid": not issues,
        "verdict": "integrity-only" if not issues else "rejected", "violations": sorted(set(issues)),
        "runtime_acceptance": "pending", "s1_operational_acceptance": False,
        "platform_claims": dict(PLATFORM_CLAIMS),
        "limitations": ["Pinned source/schema integrity is not execution, effect proof or product acceptance."]}


def _read_bounded(path, maximum=MAX_FILE_BYTES):
    with path.open("rb") as handle:
        raw = handle.read(maximum + 1)
    if len(raw) > maximum:
        raise ValueError("explicit resource byte cap exceeded")
    return raw


def packaged_bundle_inputs() -> BundleInputs:
    """Explicit metadata/resource read; no backend activation or SDK import.

    Checkout and installed paths are fixed. Never search elsewhere or substitute a
    hidden fixture when a required public package resource is missing.
    """
    from mcpsh.catalog.schemas import TOOL_SCHEMAS
    from .semantics import public_case_source

    package = Path(__file__).resolve().parents[1]
    checkout = Path(__file__).resolve().parents[3]
    schema_dir = checkout / "policy/conformance"
    if not schema_dir.is_dir():
        schema_dir = Path(__file__).resolve().parent / "data/schemas"
    sources = {name: _read_bounded(package / relative, 1024 * 1024) for name, relative in {
        "grammar": "server/matching.py", "parser": "server/parsing.py",
        "observer": "observer/__init__.py", "policy": "policy/__init__.py",
        "runtime_schema": "catalog/schemas.py"}.items()}
    raw = public_case_source()
    required = semantic_manifest(raw, grammar_source_sha256=_sha(sources["grammar"]),
                                 parser_source_sha256=_sha(sources["parser"]))
    return BundleInputs(raw, required, dict(TOOL_SCHEMAS),
        {name: _read_bounded(schema_dir / name) for name in SCHEMAS}, sources, capability_report())


def _read_known_bundle(directory: Path, *, expected_bundle_sha256, payloads, index_fields):
    """Read only a version's fixed public artifacts after pinning its index."""
    if not _pin(expected_bundle_sha256) or directory.is_symlink() or not directory.is_dir():
        raise ValueError("explicit nonsymlink public bundle directory and pin required")
    root = directory.resolve(strict=True)
    index_path = root / "bundle.json"
    if index_path.is_symlink():
        raise ValueError("bundle index symlink refused")
    index_raw = _read_bounded(index_path)
    if _sha(index_raw) != expected_bundle_sha256:
        raise ValueError("bundle index differs from external pin")
    index = _json(index_raw)
    if type(index) is not dict or set(index) != index_fields or type(index.get("files")) is not list or len(index["files"]) != len(payloads):
        raise ValueError("bundle index shape differs")
    names = []
    for row in index["files"]:
        if type(row) is not dict or set(row) != {"path", "sha256", "bytes"}:
            raise ValueError("bundle file reference shape differs")
        name = safe_name(row["path"])
        if name not in payloads:
            raise ValueError("unrecognized public bundle resource")
        names.append(name)
    if len(set(names)) != len(names) or set(names) != payloads:
        raise ValueError("required public bundle resource missing or duplicated")
    files = {"bundle.json": index_raw}
    for name in names:
        candidate = root.joinpath(*PurePosixPath(name).parts)
        for part in (candidate, *candidate.parents):
            if part == root:
                break
            if part.is_symlink():
                raise ValueError("bundle resource symlink refused")
        resolved = candidate.resolve(strict=True)
        if root not in resolved.parents or not resolved.is_file():
            raise ValueError("bundle resource leaves explicit public root")
        files[name] = _read_bounded(resolved)
    if sum(map(len, files.values())) > MAX_TOTAL_BYTES:
        raise ValueError("bundle total byte cap")
    return files


def read_contract_bundle(directory: Path, *, expected_bundle_sha256):
    """Legacy v1 integrity-only reader; normative v2 has an explicit adapter."""
    return _read_known_bundle(directory, expected_bundle_sha256=expected_bundle_sha256,
                              payloads=PAYLOADS, index_fields=INDEX_FIELDS)


def write_contract_bundle(bundle: ContractBundle, directory: Path):
    """Explicit future export only; creates a fresh directory and never overwrites."""
    files = bundle.to_files()
    verified = validate_contract_bundle(files, expected_bundle_sha256=bundle.bundle_sha256,
        expected_manifest_sha256=bundle.manifest_sha256,
        expected_runtime_schema_sha256=bundle.runtime_schema_sha256)
    if not verified["valid"]:
        raise ValueError("cannot write invalid source-contract bundle")
    _write_new_files(files, directory)
    return {"bundle_sha256": bundle.bundle_sha256, "manifest_sha256": bundle.manifest_sha256,
            "runtime_schema_sha256": bundle.runtime_schema_sha256, "claim": "source-integrity-only"}


def _write_new_files(files, directory):
    directory.mkdir(exist_ok=False)
    for name, raw in sorted(files.items()):
        safe_name(name)
        destination = directory.joinpath(*PurePosixPath(name).parts)
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open("xb") as handle:
            handle.write(raw)
    # A partial export is preserved for explicit caller disposition, never deleted.
