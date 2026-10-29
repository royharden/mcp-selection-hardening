"""Explicit normative-inventory extension; v1/v2 pin contracts stay unchanged."""

from .evidence import ROOT_FIELDS, digest
from .evidence_v2 import verify_evidence_v2

REQUIREMENT_FIELDS = frozenset({"inventory_version", "inventory_sha256", "requirement_ids", "required_scope"})
V3_FIELDS = ROOT_FIELDS | {"semantic", "requirements"}
# Optional versioned field (frame_rule.FRAME_RULE_VERSION); absent means the original v3 rules.
FRAME_RULE_FIELD = "frame_rule"
TRACK_SCOPES = {"synthetic-memory": "actual-memory", "filesystem-posix": "actual-posix", "stdio": "actual-stdio"}


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

    if type(document) is not dict or set(document) not in (V3_FIELDS, V3_FIELDS | {FRAME_RULE_FIELD}) or type(document.get("schema_version")) is not int or document["schema_version"] != 3:
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
        ruled = FRAME_RULE_FIELD in document
        rule_issues = []
        if ruled:
            from .frame_rule import verify_frame_rule

            rule_issues = verify_frame_rule(document[FRAME_RULE_FIELD], document=document,
                expected_probe_id=probe_id, expected_track=track,
                expected_server_instance_id=v2_selection.get("expected_server_instance_id"),
                expected_fixture_payload_sha256=v2_selection.get("expected_fixture_payload_sha256"))
            issues.extend(rule_issues)
        # Only translate after the closed v3 extension has been checked.
        base = {key: value for key, value in document.items() if key not in ("requirements", FRAME_RULE_FIELD)}
        base["schema_version"] = 2
        base["record_sha256"] = digest({key: value for key, value in base.items() if key != "record_sha256"})
        result = verify_evidence_v2(base, **v2_selection)
        waived = ruled and not rule_issues
        if waived:
            from .frame_rule import WAIVED_FRAME_VIOLATIONS, observation_complete

            # A valid bound control receipt stands in for frames; nothing else is waived.
            issues.extend(item for item in result["violations"] if item not in WAIVED_FRAME_VIOLATIONS)
            creditable = (not issues and result.get("scope") == TRACK_SCOPES.get(track)
                          and observation_complete(document)
                          and document["semantic"].get("coverage_kind") != "unknown")
        else:
            issues.extend(result["violations"])
            creditable = result["creditable"] and not issues
        return {**result, "valid": not issues, "creditable": creditable,
                "violations": sorted(set(issues))}
    except (ValueError, TypeError, KeyError, UnicodeError, RecursionError):
        return {"valid": False, "creditable": False, "violations": sorted(set(issues + ["evidence-v3.ill-shaped"])), "scope": "unknown", "predicates": {}}
