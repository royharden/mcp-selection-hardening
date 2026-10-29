"""Normative inventory extension of the existing portable integrity-only bundle."""

from dataclasses import dataclass
from pathlib import Path

from .export import (INDEX_FIELDS, MAX_FILE_BYTES, MAX_TOTAL_BYTES, PAYLOADS, ContractBundle,
    _bytes, _json, _pin, _read_bounded, _read_known_bundle, _schema_refs, _sha, _write_new_files,
    build_contract_bundle, packaged_bundle_inputs, read_contract_bundle, safe_name,
    validate_contract_bundle)
from .requirements import decode_requirements, requirements_source, verify_requirements_manifest

BUNDLE_FORMAT_V2 = "m5-conformance-bundle-v2"
EXTRA_SCHEMAS = {"evidence-v3.schema.json": "urn:mcpsh:conformance-evidence:v3",
                 "requirements-v1.schema.json": "urn:mcpsh:conformance-requirements:v1"}
EXTRA_PAYLOADS = frozenset({"contracts/requirements-v1.json", *("schemas/" + name for name in EXTRA_SCHEMAS)})
PAYLOADS_V2 = PAYLOADS | EXTRA_PAYLOADS
FIELDS_V2 = INDEX_FIELDS | {"requirements_manifest_sha256", "requirements_inventory_version"}


@dataclass(frozen=True)
class NormativeContractBundle(ContractBundle):
    requirements_manifest_sha256: str


def build_normative_bundle(inputs, *, requirements_raw, schemas):
    """Pure extension; all original producer/schema identities are reused."""
    if set(schemas) != set(EXTRA_SCHEMAS):
        raise ValueError("normative portable schemas missing or extra")
    base = build_contract_bundle(inputs)
    inventory = decode_requirements(requirements_raw)
    files = base.to_files()
    files["contracts/requirements-v1.json"] = requirements_raw
    for name, identity in EXTRA_SCHEMAS.items():
        value = _json(schemas[name])
        if type(value) is not dict or value.get("$id") != identity or value.get("additionalProperties") is not False:
            raise ValueError("closed normative schema identity differs")
        _schema_refs(value)
        files["schemas/" + name] = schemas[name]
    index = _json(files["bundle.json"])
    index.update(schema_version=2, bundle_format=BUNDLE_FORMAT_V2,
        requirements_manifest_sha256=inventory.sha256, requirements_inventory_version=inventory.version,
        files=[{"path": name, "bytes": len(raw), "sha256": _sha(raw)} for name, raw in sorted(files.items()) if name != "bundle.json"])
    files["bundle.json"] = _bytes(index)
    if any(type(raw) is not bytes or len(raw) > MAX_FILE_BYTES for raw in files.values()) or sum(map(len, files.values())) > MAX_TOTAL_BYTES:
        raise ValueError("normative portable byte cap")
    return NormativeContractBundle(tuple(sorted(files.items())), _sha(files["bundle.json"]),
        base.manifest_sha256, base.runtime_schema_sha256, inventory.sha256)


def validate_normative_bundle(files, *, expected_bundle_sha256, expected_manifest_sha256,
                              expected_runtime_schema_sha256, expected_requirements_manifest_sha256=None):
    """Validate v2 completely before translating its closed v1 source subset."""
    issues = []
    authority_valid = False
    base_result = {"valid": False, "platform_claims": {}, "runtime_acceptance": "pending", "s1_operational_acceptance": False}
    try:
        if set(files) != PAYLOADS_V2 | {"bundle.json"} or not _pin(expected_bundle_sha256):
            raise ValueError("normative bundle set/pin differs")
        for name, raw in files.items():
            safe_name(name)
            if type(raw) is not bytes or len(raw) > MAX_FILE_BYTES:
                raise ValueError("normative payload cap/type")
        if sum(map(len, files.values())) > MAX_TOTAL_BYTES or _sha(files["bundle.json"]) != expected_bundle_sha256:
            issues.append("bundle-v2.external-pin-or-cap")
        index = _json(files["bundle.json"])
        if type(index) is not dict or set(index) != FIELDS_V2 or type(index["schema_version"]) is not int or index["schema_version"] != 2 or index["bundle_format"] != BUNDLE_FORMAT_V2:
            raise ValueError("normative bundle version/fields differ")
        rows = index["files"]
        if type(rows) is not list or len(rows) != len(PAYLOADS_V2):
            raise ValueError("normative payload list differs")
        seen = set()
        for row in rows:
            if type(row) is not dict or set(row) != {"path", "bytes", "sha256"}:
                raise ValueError("normative file reference differs")
            name = safe_name(row["path"])
            if name not in PAYLOADS_V2 or name in seen:
                raise ValueError("normative payload duplicate/escape")
            seen.add(name)
            if type(row["bytes"]) is not int or row["bytes"] != len(files[name]) or not _pin(row["sha256"]) or row["sha256"] != _sha(files[name]):
                issues.append("bundle-v2.payload-pin")
        if seen != PAYLOADS_V2:
            issues.append("bundle-v2.payload-omission")
        raw = files["contracts/requirements-v1.json"]
        inventory = decode_requirements(raw)
        if inventory.sha256 != index["requirements_manifest_sha256"] or inventory.version != index["requirements_inventory_version"]:
            issues.append("bundle-v2.inventory-identity")
        if expected_requirements_manifest_sha256 is not None:
            approved = verify_requirements_manifest(raw,
                expected_requirements_manifest_sha256=expected_requirements_manifest_sha256)
            authority_valid = approved["valid"]
            issues.extend(approved["violations"])
        for name, identity in EXTRA_SCHEMAS.items():
            schema = _json(files["schemas/" + name])
            if type(schema) is not dict or schema.get("$id") != identity or schema.get("additionalProperties") is not False:
                issues.append("bundle-v2.schema-identity")
            _schema_refs(schema)
        # Unknown v2 keys and all added files have been validated, never discarded.
        translated = {name: raw for name, raw in files.items() if name in PAYLOADS}
        base_index = {key: value for key, value in index.items() if key in INDEX_FIELDS}
        base_index.update(schema_version=1, bundle_format="m5-conformance-bundle-v1",
                          files=[row for row in rows if row["path"] in PAYLOADS])
        translated["bundle.json"] = _bytes(base_index)
        base_result = validate_contract_bundle(translated,
            expected_bundle_sha256=_sha(translated["bundle.json"]),
            expected_manifest_sha256=expected_manifest_sha256,
            expected_runtime_schema_sha256=expected_runtime_schema_sha256)
        issues.extend(base_result["violations"])
    except (ValueError, TypeError, KeyError, UnicodeError, RecursionError):
        issues.append("bundle-v2.ill-shaped-or-incomplete")
    return {**base_result, "schema_version": 2, "valid": not issues,
        "verdict": "integrity-only" if not issues else "rejected", "violations": sorted(set(issues)),
        "requirements_authority_valid": authority_valid, "conformance_acceptance": "pending",
        "limitations": ["File integrity does not approve normative scope; its external pin is separate.",
                        "Source bundles cannot establish runtime, platform or product acceptance."]}


def packaged_normative_inputs():
    """Explicit public resource reads only; never build, export or activate."""
    checkout = Path(__file__).resolve().parents[3] / "policy/conformance"
    schema_dir = checkout if checkout.is_dir() else Path(__file__).resolve().parent / "data/schemas"
    return packaged_bundle_inputs(), requirements_source(), {
        name: _read_bounded(schema_dir / name) for name in EXTRA_SCHEMAS}


def write_normative_bundle(bundle, directory, *, expected_requirements_manifest_sha256=None):
    files = bundle.to_files()
    validated = validate_normative_bundle(files, expected_bundle_sha256=bundle.bundle_sha256,
        expected_manifest_sha256=bundle.manifest_sha256,
        expected_runtime_schema_sha256=bundle.runtime_schema_sha256,
        expected_requirements_manifest_sha256=expected_requirements_manifest_sha256)
    if not validated["valid"]:
        raise ValueError("cannot export invalid normative contract bundle")
    _write_new_files(files, directory)
    return {"bundle_sha256": bundle.bundle_sha256, "manifest_sha256": bundle.manifest_sha256,
        "runtime_schema_sha256": bundle.runtime_schema_sha256,
        "requirements_manifest_sha256": bundle.requirements_manifest_sha256,
        "requirements_authority_valid": validated["requirements_authority_valid"],
        "claim": "source-integrity-only", "runtime_acceptance": "pending"}


def read_portable_bundle(directory: Path, *, expected_bundle_sha256):
    """Explicit version dispatch. No legacy substitution for a missing v2 file."""
    if not _pin(expected_bundle_sha256) or directory.is_symlink() or not directory.is_dir() or (directory / "bundle.json").is_symlink():
        raise ValueError("explicit pinned nonsymlink public directory required")
    raw = _read_bounded(directory / "bundle.json")
    if _sha(raw) != expected_bundle_sha256:
        raise ValueError("portable index external pin differs")
    index = _json(raw)
    if type(index) is dict and type(index.get("schema_version")) is int and index["schema_version"] == 1:
        return read_contract_bundle(directory, expected_bundle_sha256=expected_bundle_sha256)
    if type(index) is dict and type(index.get("schema_version")) is int and index["schema_version"] == 2:
        return _read_known_bundle(directory, expected_bundle_sha256=expected_bundle_sha256,
                                  payloads=PAYLOADS_V2, index_fields=FIELDS_V2)
    raise ValueError("unsupported portable bundle version")
