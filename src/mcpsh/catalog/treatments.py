"""Reproducible metadata-only treatment envelopes with explicit before/after.

No label/task/oracle fields, tool suppression, execution or result publication.
The only trusted replacement map is the local canonical description authority.
"""

from copy import deepcopy
from typing import Any

from mcpsh.catalog import CANONICAL_DESCRIPTIONS
from mcpsh.catalog.artifacts import (
    MAX_DESCRIPTION_BYTES, build_catalog_artifact, validate_catalog_artifact,
)
from mcpsh.lint import NORMALIZER_VERSION
from mcpsh.records.hashing import canonical_json, raw_hash, strict_json_loads, typed_hash

TREATMENT_VERSION = "m5-metadata-treatment-1"
MAX_TREATMENT_BYTES = 4_194_304
FIELDS = {"version", "before", "after", "descriptions", "normalize",
          "normalizer_version", "trusted_map_sha256", "diffs", "integrity"}


def _construct(before: dict[str, Any], descriptions: dict[str, str], normalize: bool,
               condition: str | None) -> dict[str, Any]:
    issues = validate_catalog_artifact(before)
    if issues:
        raise ValueError("invalid before catalog artifact")
    if type(normalize) is not bool or not isinstance(descriptions, dict):
        raise ValueError("normalize must be boolean; descriptions must be an object")
    if set(descriptions) - set(CANONICAL_DESCRIPTIONS):
        raise ValueError("overlay contains an unknown canonical tool ID")
    for text in descriptions.values():
        if not isinstance(text, str) or not text or len(text.encode("utf-8")) > MAX_DESCRIPTION_BYTES:
            raise ValueError("overlay description must be bounded nonempty Unicode text")
    catalog = deepcopy(before["catalog"])
    for tool in catalog:
        if tool["name"] in descriptions:
            tool["description"] = descriptions[tool["name"]]
    after = build_catalog_artifact(
        before["condition"] if condition is None else condition,
        ordering_seed=before["record"]["ordering_seed"], catalog=catalog,
        source_revision=before["provenance"]["source_revision"], normalized=normalize,
    )
    # Hash typed immutable projections, not Python ==, which aliases True and 1.
    original_authority = [{k: v for k, v in tool.items() if k != "description"}
                          for tool in before["catalog"]]
    final_authority = [{k: v for k, v in tool.items() if k != "description"}
                       for tool in after["catalog"]]
    if typed_hash(original_authority) != typed_hash(final_authority):
        raise ValueError("treatment changed identity/order/schema/annotations")
    diffs = []
    for index, (old, new) in enumerate(zip(before["catalog"], after["catalog"], strict=True)):
        if old["description"] != new["description"]:
            diffs.append({"tool_name": old["name"], "tool_index": index,
                          "field": "description", "before": old["description"],
                          "after": new["description"],
                          "before_utf8_sha256": raw_hash(old["description"]),
                          "after_utf8_sha256": raw_hash(new["description"])})
    result = {"version": TREATMENT_VERSION, "before": deepcopy(before), "after": after,
              "descriptions": deepcopy(descriptions), "normalize": normalize,
              "normalizer_version": NORMALIZER_VERSION if normalize else "none",
              "trusted_map_sha256": typed_hash(CANONICAL_DESCRIPTIONS), "diffs": diffs}
    result["integrity"] = {"algorithm": "sha256-typed-json-1",
                           "typed_sha256": typed_hash(result)}
    if len(canonical_json(result).encode("utf-8")) > MAX_TREATMENT_BYTES:
        raise ValueError("treatment exceeds typed byte cap")
    return result


def build_treatment_artifact(before: dict[str, Any], *,
                             descriptions: dict[str, str] | None = None,
                             normalize: bool = False,
                             condition: str | None = None) -> dict[str, Any]:
    return _construct(before, {} if descriptions is None else descriptions, normalize, condition)


def validate_treatment_artifact(value: Any) -> list[dict[str, str]]:
    """Re-derive source transformation, not merely self-consistent caller hashes."""
    try:
        if not isinstance(value, dict) or set(value) != FIELDS:
            raise ValueError("treatment envelope fields differ")
        if len(canonical_json(value).encode("utf-8")) > MAX_TREATMENT_BYTES:
            raise ValueError("treatment byte cap exceeded")
        if value["version"] != TREATMENT_VERSION:
            raise ValueError("unsupported treatment version")
        if validate_catalog_artifact(value["after"]):
            raise ValueError("invalid after catalog artifact")
        expected = _construct(value["before"], value["descriptions"], value["normalize"],
                              value["after"]["condition"])
        if canonical_json(expected) != canonical_json(value):
            raise ValueError("treatment differs from trusted source transformation")
        return []
    except (ValueError, TypeError, KeyError, RecursionError, OverflowError):
        return [{"code": "TREATMENT_INVALID",
                 "message": "treatment shape, bounds, authority, transformation or integrity differs"}]


def parse_treatment_artifact(raw: str | bytes) -> dict[str, Any]:
    if not isinstance(raw, (str, bytes)):
        raise ValueError("treatment transport must be text or bytes")
    try:
        encoded = raw.encode("utf-8", errors="strict") if isinstance(raw, str) else raw
        if len(encoded) > MAX_TREATMENT_BYTES:
            raise ValueError("treatment raw byte cap exceeded")
        value = strict_json_loads(encoded.decode("utf-8", errors="strict"))
        if validate_treatment_artifact(value):
            raise ValueError("invalid treatment")
        return value
    except (ValueError, TypeError, RecursionError, OverflowError) as exc:
        raise ValueError("invalid metadata treatment transport") from exc


def serialize_treatment_artifact(value: dict[str, Any]) -> str:
    if validate_treatment_artifact(value):
        raise ValueError("invalid treatment")
    return canonical_json(value)
