"""Explicit normative-inventory extension; v1/v2 pin contracts stay unchanged."""

from .evidence import ROOT_FIELDS, digest
from .evidence_v2 import verify_evidence_v2

REQUIREMENT_FIELDS = frozenset({"inventory_version", "inventory_sha256", "requirement_ids", "required_scope"})


def build_evidence_v3(base, *, inventory):
    track, probe_id = base["track"], base["probe_id"]
    scope = inventory.to_dict()["proof_scopes"][track]
    mapped = sorted(row.requirement_id for row in inventory.requirements
                    if track in row.tracks and probe_id in row.probe_ids)
    value = {**base, "schema_version": 3, "requirements": {
        "inventory_version": inventory.version, "inventory_sha256": inventory.sha256,
        "requirement_ids": mapped, "required_scope": scope}}
    value["record_sha256"] = digest({key: item for key, item in value.items() if key != "record_sha256"})
    return value


def verify_evidence_v3(document, *, requirements_raw, expected_requirements_manifest_sha256,
                        **v2_selection):
    from .requirements import decode_requirements, verify_requirements_manifest

    if type(document) is not dict or set(document) != ROOT_FIELDS | {"semantic", "requirements"} or type(document.get("schema_version")) is not int or document["schema_version"] != 3:
        return {"valid": False, "creditable": False, "violations": ["evidence-v3.fields"], "scope": "unknown", "predicates": {}}
    authority = verify_requirements_manifest(requirements_raw,
        expected_requirements_manifest_sha256=expected_requirements_manifest_sha256)
    issues = list(authority["violations"])
    try:
        inventory = decode_requirements(requirements_raw)
        binding = document["requirements"]
        if type(binding) is not dict or set(binding) != REQUIREMENT_FIELDS:
            raise ValueError("normative evidence fields differ")
        track, probe_id = v2_selection["expected_track"], v2_selection["expected_probe_id"]
        mapped = sorted(row.requirement_id for row in inventory.requirements
                        if track in row.tracks and probe_id in row.probe_ids)
        if binding["inventory_version"] != inventory.version or binding["inventory_sha256"] != inventory.sha256:
            issues.append("evidence-v3.inventory-identity")
        if binding["requirement_ids"] != mapped or binding["required_scope"] != inventory.to_dict()["proof_scopes"].get(track):
            issues.append("evidence-v3.normative-scope-or-mapping")
        if digest({key: value for key, value in document.items() if key != "record_sha256"}) != document["record_sha256"]:
            issues.append("evidence-v3.digest")
        # Only translate after the closed v3 extension has been checked.
        base = {key: value for key, value in document.items() if key != "requirements"}
        base["schema_version"] = 2
        base["record_sha256"] = digest({key: value for key, value in base.items() if key != "record_sha256"})
        result = verify_evidence_v2(base, **v2_selection)
        issues.extend(result["violations"])
        return {**result, "valid": not issues, "creditable": result["creditable"] and not issues,
                "violations": sorted(set(issues))}
    except (ValueError, TypeError, KeyError, UnicodeError, RecursionError):
        return {"valid": False, "creditable": False, "violations": sorted(set(issues + ["evidence-v3.ill-shaped"])), "scope": "unknown", "predicates": {}}
