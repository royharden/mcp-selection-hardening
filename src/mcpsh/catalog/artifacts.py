"""Strict catalog transport envelopes around the shared CatalogArtifact record.

Metadata is experimental data. Validation never installs executable schemas or
changes the harness-owned server identity. This module has no file/network I/O.
"""

from copy import deepcopy
from hashlib import sha256
import re
from typing import Any

from mcpsh.catalog import CATALOG_VERSION, SERVER_INSTANCE_ID, build_catalog, validate_catalog
from mcpsh.catalog.schemas import TOOL_SCHEMAS
from mcpsh.records.hashing import canonical_json, raw_hash, strict_json_loads, typed_hash
from mcpsh.records.models import CatalogArtifact

ARTIFACT_VERSION = "m5-catalog-artifact-1"
ORDERING_ALGORITHM = "sha256-tool-rank-1"
MAX_ARTIFACT_BYTES = 1_048_576
MAX_DESCRIPTION_BYTES = 65_536
CONDITIONS = ("clean", "ambiguous", "poisoned")
ENVELOPE_FIELDS = {"artifact_version", "catalog_version", "condition", "record",
                   "catalog", "provenance", "integrity"}
RECORD_FIELDS = {"server_instance_id", "tool_names", "executable_schema_hash",
                 "presented_metadata_hash", "overlay_version", "normalizer_version",
                 "ordering_seed"}
TOOL_FIELDS = {"name", "description", "inputSchema", "annotations"}
HINT_FIELDS = {"readOnlyHint", "destructiveHint", "openWorldHint", "idempotentHint"}


def ordered_tool_names(seed: int) -> list[str]:
    """Versioned ordering independent of Python's pseudorandom implementation."""
    if type(seed) is not int or not 0 <= seed < 2**63:
        raise ValueError("ordering_seed must be an integer in 0..2**63-1")
    return sorted(TOOL_SCHEMAS, key=lambda name: (
        sha256(f"{ORDERING_ALGORITHM}:{seed}:{name}".encode("ascii")).hexdigest(), name))


def _metadata(catalog: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{"name": tool["name"], "description": tool["description"],
             "annotations": tool["annotations"]} for tool in catalog]


def _schemas(catalog: list[dict[str, Any]]) -> dict[str, Any]:
    return {tool["name"]: tool["inputSchema"] for tool in catalog}


def _catalog_issues(catalog: Any) -> list[dict[str, str]]:
    issues = validate_catalog(catalog)
    if issues:
        return issues
    for tool in catalog:
        if set(tool) != TOOL_FIELDS:
            return [{"code": "TOOL_FIELDS", "message": "catalog tool fields differ"}]
        description = tool["description"]
        if not description or len(description.encode("utf-8")) > MAX_DESCRIPTION_BYTES:
            return [{"code": "DESCRIPTION_BOUND", "message": "description is empty or too long"}]
        hints = tool["annotations"]
        if not isinstance(hints, dict) or set(hints) - HINT_FIELDS or any(
            type(value) is not bool for value in hints.values()
        ):
            return [{"code": "ANNOTATIONS", "message": "annotation hints must be known booleans"}]
    return []


def _payload(value: dict[str, Any]) -> dict[str, Any]:
    return {key: item for key, item in value.items() if key != "integrity"}


def build_catalog_artifact(condition: str = "clean", *, ordering_seed: int = 0,
                           catalog: list[dict[str, Any]] | None = None,
                           source_revision: str | None = None,
                           normalized: bool = False) -> dict[str, Any]:
    """Build ordered transport data; a supplied catalog cannot redefine authority.

    A condition is a caller-supplied experimental classification, not a certified
    assertion that metadata equals a built-in overlay. Provenance hashes pin the
    actual text. ``normalized=True`` performs the trusted-map operation itself.
    """
    if condition not in CONDITIONS or type(normalized) is not bool:
        raise ValueError("unknown condition or nonboolean normalized flag")
    order = ordered_tool_names(ordering_seed)
    source = build_catalog(condition) if catalog is None else deepcopy(catalog)
    issues = _catalog_issues(source)
    if issues:
        raise ValueError(issues[0]["code"])
    by_name = {tool["name"]: tool for tool in source}
    ordered = [by_name[name] for name in order]
    normalizer_version = "none"
    if normalized:
        from mcpsh.lint import NORMALIZER_VERSION, normalize_catalog

        ordered, _ = normalize_catalog(ordered)
        normalizer_version = NORMALIZER_VERSION
    record = CatalogArtifact(
        server_instance_id=SERVER_INSTANCE_ID, tool_names=tuple(order),
        executable_schema_hash=typed_hash(_schemas(ordered)),
        presented_metadata_hash=typed_hash(_metadata(ordered)),
        overlay_version=f"m5-overlay-{condition}-1", normalizer_version=normalizer_version,
        ordering_seed=ordering_seed,
    )
    result = {
        "artifact_version": ARTIFACT_VERSION, "catalog_version": CATALOG_VERSION,
        "condition": condition, "record": record.model_dump(mode="json"),
        "catalog": ordered,
        "provenance": {"producer": "mcpsh.catalog.artifacts",
                       "ordering_algorithm": ORDERING_ALGORITHM,
                       "canonical_schema_hash": typed_hash(TOOL_SCHEMAS),
                       "source_revision": source_revision},
    }
    result["integrity"] = {"algorithm": "sha256-typed-json-1",
                           "typed_sha256": typed_hash(result)}
    issues = validate_catalog_artifact(result)
    if issues:
        raise ValueError(issues[0]["code"])
    return result


def validate_catalog_artifact(value: Any) -> list[dict[str, str]]:
    """Validate shape, bounds, canonical authority, order and every typed digest."""
    def reject(code: str, message: str) -> list[dict[str, str]]:
        return [{"code": code, "message": message}]

    try:
        if not isinstance(value, dict) or set(value) != ENVELOPE_FIELDS:
            return reject("ARTIFACT_FIELDS", "artifact envelope fields differ")
        # Also rejects nonfinite values, invalid Unicode scalars and cycles before
        # trusting any caller-supplied digest. No raw-byte hash is inferred here.
        if len(canonical_json(value).encode("utf-8")) > MAX_ARTIFACT_BYTES:
            return reject("ARTIFACT_BOUND", "artifact exceeds typed byte cap")
        if (value["artifact_version"] != ARTIFACT_VERSION
                or value["catalog_version"] != CATALOG_VERSION):
            return reject("ARTIFACT_VERSION", "unsupported artifact/catalog version")
        condition = value["condition"]
        if condition not in CONDITIONS:
            return reject("CONDITION", "unsupported condition")
        record_data = value["record"]
        if not isinstance(record_data, dict) or set(record_data) != RECORD_FIELDS:
            return reject("RECORD_FIELDS", "shared CatalogArtifact fields differ")
        names = record_data["tool_names"]
        if not isinstance(names, list) or any(not isinstance(name, str) for name in names):
            return reject("TOOL_ORDER", "tool_names must be a JSON string array")
        record = CatalogArtifact.model_validate({**record_data, "tool_names": tuple(names)})
        if record.server_instance_id != SERVER_INSTANCE_ID:
            return reject("SERVER_ID", "artifact cannot redefine harness server identity")
        order = ordered_tool_names(record.ordering_seed)
        if list(record.tool_names) != order:
            return reject("TOOL_ORDER", "declared order differs from versioned seed order")
        issues = _catalog_issues(value["catalog"])
        if issues:
            return issues
        if [tool["name"] for tool in value["catalog"]] != order:
            return reject("TOOL_ORDER", "catalog array differs from declared order")
        if record.overlay_version != f"m5-overlay-{condition}-1":
            return reject("OVERLAY_VERSION", "condition/overlay version mismatch")
        from mcpsh.lint import NORMALIZER_VERSION

        if record.normalizer_version not in {"none", NORMALIZER_VERSION}:
            return reject("NORMALIZER_VERSION", "unsupported normalizer version")
        if (record.executable_schema_hash != typed_hash(_schemas(value["catalog"]))
                or record.presented_metadata_hash != typed_hash(_metadata(value["catalog"]))):
            return reject("CONTENT_HASH", "schema or metadata digest mismatch")
        provenance = value["provenance"]
        if not isinstance(provenance, dict) or set(provenance) != {
            "producer", "ordering_algorithm", "canonical_schema_hash", "source_revision"
        }:
            return reject("PROVENANCE_FIELDS", "provenance fields differ")
        if (provenance["producer"] != "mcpsh.catalog.artifacts"
                or provenance["ordering_algorithm"] != ORDERING_ALGORITHM
                or provenance["canonical_schema_hash"] != typed_hash(TOOL_SCHEMAS)):
            return reject("PROVENANCE", "unsupported producer/order or schema identity")
        revision = provenance["source_revision"]
        if revision is not None and (not isinstance(revision, str)
                                     or re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", revision) is None):
            return reject("SOURCE_REVISION", "revision must be null or a full lowercase digest")
        integrity = value["integrity"]
        if (not isinstance(integrity, dict) or set(integrity) != {"algorithm", "typed_sha256"}
                or integrity["algorithm"] != "sha256-typed-json-1"
                or integrity["typed_sha256"] != typed_hash(_payload(value))):
            return reject("INTEGRITY", "typed envelope digest mismatch")
        return []
    except (ValueError, TypeError, KeyError, RecursionError, OverflowError):
        return reject("ARTIFACT_INVALID", "artifact is not bounded strict JSON/record data")


def parse_catalog_artifact(raw: str | bytes) -> dict[str, Any]:
    """Strict, bounded transport parser; duplicate JSON keys are always rejected."""
    if not isinstance(raw, (str, bytes)):
        raise ValueError("artifact transport must be text or bytes")
    try:
        encoded = raw.encode("utf-8", errors="strict") if isinstance(raw, str) else raw
        if len(encoded) > MAX_ARTIFACT_BYTES:
            raise ValueError("artifact raw byte cap exceeded")
        # Decode strictly before JSON parsing; never reinterpret an alternate
        # encoding or replacement characters as the original transport.
        value = strict_json_loads(encoded.decode("utf-8", errors="strict"))
        issues = validate_catalog_artifact(value)
        if issues:
            raise ValueError(issues[0]["code"])
        return value
    except (ValueError, TypeError, RecursionError, OverflowError) as exc:
        raise ValueError("invalid catalog artifact transport") from exc


def serialize_catalog_artifact(value: dict[str, Any]) -> str:
    issues = validate_catalog_artifact(value)
    if issues:
        raise ValueError(issues[0]["code"])
    return canonical_json(value)


def artifact_pins(value: dict[str, Any], *, raw: str | bytes | None = None) -> dict[str, Any]:
    """Evidence identities, not signatures, authorization or acceptance receipts."""
    issues = validate_catalog_artifact(value)
    if issues:
        raise ValueError(issues[0]["code"])
    record = value["record"]
    result = {"artifact_version": ARTIFACT_VERSION,
              "typed_sha256": value["integrity"]["typed_sha256"],
              "executable_schema_hash": record["executable_schema_hash"],
              "presented_metadata_hash": record["presented_metadata_hash"],
              "server_instance_id": SERVER_INSTANCE_ID,
              "qualified_tool_ids": [[SERVER_INSTANCE_ID, name] for name in record["tool_names"]],
              "ordering_seed": record["ordering_seed"]}
    if raw is not None:
        parsed = parse_catalog_artifact(raw)
        if typed_hash(parsed) != typed_hash(value):
            raise ValueError("raw transport does not represent supplied artifact")
        result["raw_sha256"] = raw_hash(raw)
    return result
