"""Detached integrity/evidence compatibility inspection; never activates a backend."""

import hashlib

from .evidence import verify_evidence
from .evidence_v2 import verify_evidence_v2
from .export import MAX_FILE_BYTES, _json, _pin, _read_bounded, validate_contract_bundle

SELECTION_FIELDS = frozenset({"expected_evidence_sha256", "expected_probe_id", "expected_track",
    "expected_request_sha256", "expected_source_pins", "expected_server_instance_id",
    "expected_fixture_payload_sha256"})


def read_public_evidence_files(evidence_path, selection_path):
    """Only explicitly supplied public files; bounded reads, no auto-discovery."""
    return _read_bounded(evidence_path), _json(_read_bounded(selection_path))


def inspect_consumer_evidence(raw, selection, *, manifest, expected_manifest_sha256):
    """Use externally supplied pins; no paths, process handles or credentials."""
    if type(selection) is not dict or set(selection) != SELECTION_FIELDS or type(raw) is not bytes or len(raw) > MAX_FILE_BYTES:
        return {"valid": False, "creditable": False, "compatibility": "rejected",
                "violations": ["consumer.evidence-selection"], "predicates": {}}
    if not _pin(selection["expected_evidence_sha256"]) or hashlib.sha256(raw).hexdigest() != selection["expected_evidence_sha256"]:
        return {"valid": False, "creditable": False, "compatibility": "rejected",
                "violations": ["consumer.evidence-byte-pin"], "predicates": {}}
    try:
        document = _json(raw)
        if type(document) is not dict or type(document.get("schema_version")) is not int:
            raise ValueError("explicit evidence version required")
        pins = {key: value for key, value in selection.items() if key != "expected_evidence_sha256"}
        if document["schema_version"] == 1:
            result = verify_evidence(document, **pins)
            # v1 has no required-case/semantic authority, even if it is well-shaped.
            return {**result, "creditable": False, "compatibility": "legacy-v1-integrity-only",
                    "limitations": ["Evidence v1 cannot establish v2 semantic required-case credit."]}
        if document["schema_version"] == 2:
            result = verify_evidence_v2(document, semantic_manifest=manifest,
                expected_manifest_sha256=expected_manifest_sha256, **pins)
            return {**result, "compatibility": "evidence-v2",
                    "limitations": ["A per-probe structural check is not full platform or product acceptance."]}
        return {"valid": False, "creditable": False, "compatibility": "unsupported",
                "violations": ["consumer.unsupported-evidence-version"], "predicates": {}}
    except (ValueError, TypeError, KeyError, UnicodeError, RecursionError):
        return {"valid": False, "creditable": False, "compatibility": "rejected",
                "violations": ["consumer.ill-shaped-evidence"], "predicates": {}}


def inspect_bundle(files, *, expected_bundle_sha256, expected_manifest_sha256,
                    expected_runtime_schema_sha256, evidence_raw=None, evidence_selection=None):
    """Default integrity-only consumer. No activation option or backend factory."""
    bundle = validate_contract_bundle(files, expected_bundle_sha256=expected_bundle_sha256,
        expected_manifest_sha256=expected_manifest_sha256,
        expected_runtime_schema_sha256=expected_runtime_schema_sha256)
    result = {"schema_version": 1, "mode": "integrity-only", "status": "integrity-only" if bundle["valid"] else "rejected",
        "bundle": bundle, "evidence": None, "runtime_acceptance": "pending",
        "conformance_acceptance": "pending", "providers_used": False,
        "limitations": ["No backend, provider, SDK, process or conformance suite is activated.",
                        "Public required-case counts describe scope, not measured outcomes."]}
    if not bundle["valid"]:
        return result
    manifest = _json(files["contracts/required-cases-v1.json"])
    result["required_probe_counts"] = {track: len(ids) for track, ids in manifest["required_probe_ids"].items()}
    if evidence_raw is None and evidence_selection is None:
        return result
    if evidence_raw is None or evidence_selection is None:
        result.update(status="rejected", evidence={"valid": False, "creditable": False,
            "violations": ["consumer.evidence-and-selection-required"]})
        return result
    result["evidence"] = inspect_consumer_evidence(evidence_raw, evidence_selection,
        manifest=manifest, expected_manifest_sha256=expected_manifest_sha256)
    if not result["evidence"]["valid"]:
        result["status"] = "rejected"
    return result
