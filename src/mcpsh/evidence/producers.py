"""Pure adapters to D5 catalog pins and D6 per-probe evidence verification."""

from pydantic import Field

from mcpsh.records import typed_hash
from mcpsh.records.models import Record

from .reader import EvidenceRejected, VerifiedEdition, strict_json


class CatalogPins(Record):
    artifact_version: str
    typed_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    executable_schema_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    presented_metadata_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    server_instance_id: str
    qualified_tool_ids: tuple[tuple[str, str], ...] = Field(min_length=9, max_length=9)
    ordering_seed: int = Field(ge=0)
    raw_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class CatalogExpectation(Record):
    trial_id: str
    pins: CatalogPins


class ConformanceExpectation(Record):
    probe_id: str
    track: str
    request_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_pins: dict[str, str]
    server_instance_id: str
    fixture_payload_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class ProducerAuthority(Record):
    schema_version: int = Field(ge=1, le=1)
    source_index_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    catalogs: tuple[CatalogExpectation, ...] = Field(max_length=5000)
    conformance: tuple[ConformanceExpectation, ...] = Field(max_length=256)


def verify_producer_bindings(edition: VerifiedEdition, authority: ProducerAuthority, *,
                             expected_authority_sha256: str,
                             catalog_documents: dict[str, bytes],
                             conformance_documents: dict[str, bytes]) -> dict:
    """Only explicit document bytes; never discover/open producer files or a process."""
    index, _, trials, _, _ = edition.validate()
    if typed_hash(authority.model_dump(mode="json")) != expected_authority_sha256 or authority.source_index_sha256 != edition.authority.index_sha256:
        raise EvidenceRejected("producer selection/pins differ from external authority")
    catalogs = {item.trial_id: item for item in authority.catalogs}
    probes = {item.probe_id: item for item in authority.conformance}
    if len(catalogs) != len(authority.catalogs) or len(probes) != len(authority.conformance):
        raise EvidenceRejected("duplicate required catalog/probe selection")
    rows = {row.outcome.trial_id: row for row in trials}
    if not set(catalogs) <= set(rows) or not set(catalog_documents) <= set(catalogs) or not set(conformance_documents) <= set(probes):
        raise EvidenceRejected("unbound catalog/probe payload")
    if sum(len(raw) for raw in list(catalog_documents.values()) + list(conformance_documents.values())) > 64 * 1024 * 1024:
        raise EvidenceRejected("producer artifact aggregate byte cap")
    from mcpsh.catalog.artifacts import artifact_pins
    from mcpsh.conformance.evidence import verify_evidence

    catalog_results, probe_results = [], []
    for trial_id, expected in catalogs.items():
        raw = catalog_documents.get(trial_id)
        if raw is None:
            catalog_results.append({"trial_id": trial_id, "state": "unknown", "violations": ["catalog.missing"]})
            continue
        try:
            if len(raw) > 1048576:
                raise EvidenceRejected("catalog byte cap")
            value = strict_json(raw)
            pins = artifact_pins(value, raw=raw)
            if pins != expected.pins.model_dump(mode="json") or rows[trial_id].catalog_hash != typed_hash(value["catalog"]):
                raise EvidenceRejected("catalog differs from externally selected trial pins")
            catalog_results.append({"trial_id": trial_id, "state": "verified", "pins": pins, "violations": []})
        except (ValueError, TypeError, KeyError):
            catalog_results.append({"trial_id": trial_id, "state": "invalid", "violations": ["catalog.pin-or-schema-mismatch"]})
    for probe_id, expected in probes.items():
        raw = conformance_documents.get(probe_id)
        if raw is None:
            probe_results.append({"probe_id": probe_id, "state": "unknown", "creditable": False,
                                  "predicates": {}, "violations": ["conformance.missing"]})
            continue
        try:
            if len(raw) > 1048576:
                raise EvidenceRejected("conformance byte cap")
            document = strict_json(raw)
            result = verify_evidence(document, expected_probe_id=probe_id,
                expected_track=expected.track, expected_request_sha256=expected.request_sha256,
                expected_source_pins=expected.source_pins,
                expected_server_instance_id=expected.server_instance_id,
                expected_fixture_payload_sha256=expected.fixture_payload_sha256)
            if document.get("session", {}).get("platform_scope") != index.platform_scope:
                result = {**result, "valid": False, "creditable": False,
                          "violations": [*result["violations"], "conformance.edition-platform-mismatch"]}
            probe_results.append({"probe_id": probe_id, "state": "verified" if result["valid"] else "invalid", **result})
        except (ValueError, TypeError, KeyError, AttributeError):
            probe_results.append({"probe_id": probe_id, "state": "invalid", "creditable": False,
                                  "predicates": {}, "violations": ["conformance.schema-invalid"]})
    return {"visibility": "private", "schema_version": 1,
        "source_index_sha256": edition.authority.index_sha256,
        "authority_sha256": expected_authority_sha256,
        "catalogs": catalog_results, "conformance": probe_results,
        "selected_catalog_count": len(catalogs), "selected_probe_count": len(probes),
        "bindings_complete": all(item["state"] == "verified" for item in catalog_results + probe_results),
        "all_selected_probes_creditable": bool(probe_results) and all(item["creditable"] for item in probe_results),
        "full_platform_credit": False, "empirical_verdict": "pending", "product_verdict": "pending",
        "limitation": "Per-probe structural credit does not prove full supported-probe coverage or truthful observations."}
