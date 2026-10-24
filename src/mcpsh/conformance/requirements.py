"""Normative boundary authority, independent of the implemented probe registry."""

import hashlib
from dataclasses import dataclass
from pathlib import Path

from .models import ProbeDefinition, ProbeResult

INVENTORY_VERSION = "m5-conformance-boundaries-v1"
SCOPES = {"synthetic-memory": "actual-memory", "filesystem-posix": "actual-posix", "stdio": "actual-stdio"}
ROOT_FIELDS = frozenset({"schema_version", "inventory_version", "source_plan", "proof_scopes", "requirements"})
ROW_FIELDS = frozenset({"id", "citation", "tracks", "probe_ids", "expectation"})
BINDING_FIELDS = frozenset({"semantic_manifest", "expected_manifest_sha256", "expected_probe_id", "expected_track",
    "expected_request_sha256", "expected_source_pins", "expected_server_instance_id", "expected_fixture_payload_sha256"})


@dataclass(frozen=True)
class BoundaryRequirement:
    requirement_id: str
    citation: str
    tracks: tuple[str, ...]
    probe_ids: tuple[str, ...]
    expectation_json: str


@dataclass(frozen=True)
class RequirementsInventory:
    sha256: str
    version: str
    requirements: tuple[BoundaryRequirement, ...]
    document_json: str

    def to_dict(self):
        import json

        return json.loads(self.document_json)


def _text(value, maximum=256):
    return type(value) is str and 0 < len(value.encode("utf-8")) <= maximum and "\x00" not in value


def _pin(value):
    return type(value) is str and len(value) == 64 and all(char in "0123456789abcdef" for char in value)


def requirements_source():
    """Explicit fixed public resource read, not registry generation or activation."""
    checkout = Path(__file__).resolve().parents[3] / "policy/conformance/requirements-v1.json"
    path = checkout if checkout.is_file() else Path(__file__).resolve().parent / "data/requirements-v1.json"
    with path.open("rb") as handle:
        raw = handle.read(128 * 1024 + 1)
    if len(raw) > 128 * 1024:
        raise ValueError("normative requirement source byte cap")
    return raw


def decode_requirements(raw: bytes) -> RequirementsInventory:
    """Shape/decode only. This function does not approve its own byte hash."""
    import json

    if type(raw) is not bytes or not 1 <= len(raw) <= 128 * 1024:
        raise ValueError("bounded normative inventory bytes required")
    from mcpsh.records import strict_json_loads

    document = strict_json_loads(raw)
    if type(document) is not dict or set(document) != ROOT_FIELDS or type(document["schema_version"]) is not int or document["schema_version"] != 1 or document["inventory_version"] != INVENTORY_VERSION or document["proof_scopes"] != SCOPES:
        raise ValueError("normative inventory version/fields/scopes differ")
    source = document["source_plan"]
    if type(source) is not dict or set(source) != {"path", "sha256", "requirement", "sections"} or source["path"] != "planning/promoted/Plan_M5_Selected_v1.md" or not _pin(source["sha256"]) or source["requirement"] != "M5-04" or type(source["sections"]) is not list or not source["sections"] or any(type(section) is not int or section not in {2, 3, 4, 6} for section in source["sections"]):
        raise ValueError("normative plan citation differs")
    rows = document["requirements"]
    if type(rows) is not list or not 1 <= len(rows) <= 64:
        raise ValueError("normative requirement count cap")
    seen = set()
    requirements = []
    for row in rows:
        if type(row) is not dict or set(row) != ROW_FIELDS or not _text(row["id"], 96) or row["id"] in seen or not _text(row["citation"]):
            raise ValueError("duplicate or invalid normative requirement")
        seen.add(row["id"])
        tracks, probes = row["tracks"], row["probe_ids"]
        if type(tracks) is not list or not tracks or any(type(track) is not str or track not in SCOPES for track in tracks) or len(set(tracks)) != len(tracks):
            raise ValueError("normative platform scope differs")
        if type(probes) is not list or not 1 <= len(probes) <= 32 or any(not _text(probe, 128) for probe in probes) or len(set(probes)) != len(probes):
            raise ValueError("normative probe mapping differs")
        expected = row["expectation"]
        if type(expected) is not dict or set(expected) != {"kind", "metric", "maximum", "unit"} or not _text(expected["kind"], 96):
            raise ValueError("normative expectation fields differ")
        if expected["maximum"] is None:
            if expected["metric"] is not None or expected["unit"] is not None:
                raise ValueError("incomplete normative cap")
        elif type(expected["maximum"]) is not int or not 1 <= expected["maximum"] <= 8 * 1024 * 1024 or not _text(expected["metric"], 96) or expected["unit"] not in {"bytes", "lines", "seconds", "characters", "calls", "rules", "sources"}:
            raise ValueError("invalid normative cap")
        requirements.append(BoundaryRequirement(row["id"], row["citation"], tuple(tracks), tuple(probes), json.dumps(expected, sort_keys=True)))
    return RequirementsInventory(hashlib.sha256(raw).hexdigest(), document["inventory_version"], tuple(requirements),
                                  json.dumps(document, sort_keys=True, ensure_ascii=True, allow_nan=False))


def verify_requirements_manifest(raw, *, expected_requirements_manifest_sha256):
    """External approval pin is mandatory; never derive it from this inventory."""
    try:
        inventory = decode_requirements(raw)
        valid = _pin(expected_requirements_manifest_sha256) and inventory.sha256 == expected_requirements_manifest_sha256
        return {"valid": valid, "violations": [] if valid else ["requirements.external-pin"],
                "inventory_version": inventory.version, "inventory_sha256": inventory.sha256,
                "required_counts": {track: sum(track in row.tracks for row in inventory.requirements) for track in SCOPES}}
    except (ValueError, TypeError, KeyError, UnicodeError, RecursionError):
        return {"valid": False, "violations": ["requirements.ill-shaped"],
                "inventory_version": INVENTORY_VERSION, "inventory_sha256": None, "required_counts": {}}


def registry_projection(registry):
    """Actual registry is an observation, never normative scope authority."""
    if type(registry) not in {tuple, list} or len(registry) > 256:
        raise ValueError("bounded registry sequence required")
    rows = []
    for probe in registry:
        if isinstance(probe, ProbeDefinition):
            rows.append({"probe_id": probe.probe_id, "tracks": list(probe.tracks), "required": probe.required})
        elif type(probe) is dict and set(probe) == {"probe_id", "tracks", "required"}:
            rows.append(dict(probe))
        else:
            raise ValueError("registry projection fields differ")
    if len(rows) > 256:
        raise ValueError("registry projection cap")
    for row in rows:
        if not _text(row["probe_id"], 128) or type(row["required"]) is not bool or type(row["tracks"]) not in {tuple, list} or not row["tracks"] or any(type(track) is not str or track not in SCOPES for track in row["tracks"]) or len(set(row["tracks"])) != len(row["tracks"]):
            raise ValueError("registry identity/track projection invalid")
    return rows


def _proof(row, *, track, probe_id, bindings, raw, inventory_pin):
    from .evidence_v3 import verify_evidence_v3

    evidence = row.get("evidence", {})
    binding = bindings.get(track + "/" + probe_id)
    if type(binding) is not dict or set(binding) != BINDING_FIELDS:
        return ["proof.external-binding-missing"]
    if binding["expected_probe_id"] != probe_id or binding["expected_track"] != track:
        return ["proof.external-selection-mismatch"]
    document = evidence.get("provenance") if type(evidence) is dict else None
    if type(document) is not dict or document.get("schema_version") != 3:
        return ["proof.v3-normative-attribution-required"]
    verification = verify_evidence_v3(document, requirements_raw=raw,
        expected_requirements_manifest_sha256=inventory_pin, **binding)
    violations = list(verification["violations"])
    if verification["scope"] != SCOPES[track]:
        violations.append("proof.wrong-platform-scope")
    if verification["creditable"] is not True:
        violations.append("proof.unknown-component-or-incomplete")
    return violations


def audit_requirements(raw, *, expected_requirements_manifest_sha256, registry, results,
                       tracks, evidence_bindings=None):
    """Pure coverage audit: preserve the externally approved, fixed denominator."""
    approval = verify_requirements_manifest(raw, expected_requirements_manifest_sha256=expected_requirements_manifest_sha256)
    platforms = {}
    audit_valid = True
    audit_violations = []
    try:
        if type(tracks) not in {tuple, list} or not tracks or any(type(track) is not str or track not in SCOPES for track in tracks) or len(set(tracks)) != len(tracks):
            raise ValueError("explicit supported audit tracks required")
        platforms = {track: {"verdict": "pending", "requirements": []} for track in tracks}
        inventory = decode_requirements(raw)
        for track in tracks:
            applicable = [row for row in inventory.requirements if track in row.tracks]
            platforms[track].update(required_requirements=len(applicable), covered_requirements=0,
                required_probe_ids=sorted({probe for row in applicable for probe in row.probe_ids}),
                filesystem_proof=False, requirements=[{"requirement_id": row.requirement_id,
                    "probe_ids": list(row.probe_ids), "covered": False,
                    "violations": ["requirements.audit-not-complete"]} for row in applicable])
        definitions = registry_projection(registry)
        if type(results) not in {tuple, list} or len(results) > 512:
            raise ValueError("bounded result sequence required")
        outcomes = [row.to_dict() if isinstance(row, ProbeResult) else row for row in results]
        if len(outcomes) > 512 or any(type(row) is not dict for row in outcomes):
            raise ValueError("bounded result projection required")
        bindings = evidence_bindings or {}
        if type(bindings) is not dict or len(bindings) > 512:
            raise ValueError("bounded external evidence bindings required")
        for track in tracks:
            blocked = False
            requirement_rows = []
            for requirement in inventory.requirements:
                if track not in requirement.tracks:
                    continue
                issues = list(approval["violations"])
                for probe_id in requirement.probe_ids:
                    registered = [row for row in definitions if row["probe_id"] == probe_id]
                    if not registered:
                        issues.append("registry.missing:" + probe_id)
                    elif len(registered) != 1:
                        issues.append("registry.duplicate:" + probe_id)
                    elif type(registered[0]["required"]) is not bool or registered[0]["required"] is not True or track not in registered[0]["tracks"]:
                        issues.append("registry.wrong-scope-or-optional:" + probe_id)
                    found = [row for row in outcomes if row.get("track") == track and row.get("probe_id") == probe_id]
                    if len(found) != 1:
                        issues.append(("result.missing:" if not found else "result.duplicate:") + probe_id)
                        continue
                    row = found[0]
                    if row.get("status") == "fail":
                        blocked = True
                    if row.get("required") is not True or row.get("status") != "pass":
                        issues.append("result.not-required-pass:" + probe_id)
                    issues.extend(issue + ":" + probe_id for issue in _proof(row, track=track,
                        probe_id=probe_id, bindings=bindings, raw=raw,
                        inventory_pin=expected_requirements_manifest_sha256))
                requirement_rows.append({"requirement_id": requirement.requirement_id,
                    "probe_ids": list(requirement.probe_ids), "covered": not issues,
                    "violations": sorted(set(issues))})
            covered = sum(row["covered"] for row in requirement_rows)
            complete = approval["valid"] and bool(requirement_rows) and covered == len(requirement_rows)
            platforms[track] = {"verdict": "blocked" if blocked else "passed" if complete else "pending",
                "required_requirements": len(requirement_rows), "covered_requirements": covered,
                "required_probe_ids": sorted({probe for row in requirement_rows for probe in row["probe_ids"]}),
                "requirements": requirement_rows, "filesystem_proof": track == "filesystem-posix" and complete}
    except (ValueError, TypeError, KeyError, UnicodeError, RecursionError):
        audit_valid = False
        audit_violations = ["requirements.audit-ill-shaped"]
        for platform in platforms.values():
            platform.update(verdict="pending", filesystem_proof=False, covered_requirements=0)
            for row in platform["requirements"]:
                row.update(covered=False, violations=sorted(set(row["violations"] + audit_violations)))
    return {"schema_version": 1, "inventory_version": INVENTORY_VERSION,
            "inventory_sha256": approval.get("inventory_sha256"), "authority_valid": approval["valid"],
            "audit_valid": audit_valid, "violations": sorted(set(approval["violations"] + audit_violations)), "platforms": platforms,
            "product_acceptance": "pending"}
