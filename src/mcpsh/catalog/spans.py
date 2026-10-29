"""Exact source text spans; no Unicode normalization or metadata execution."""

from copy import deepcopy
from typing import Any

from mcpsh.records.hashing import raw_hash

MAX_SPAN_FIELD_BYTES = 4_194_304


def resolve_field_span(catalog: list[dict[str, Any]], *, tool_index: int, field: str,
                       start: int, end: int,
                       unit: str = "unicode-codepoint") -> dict[str, Any]:
    """Return canonical codepoint and UTF-8 spans over the exact original field.

    UTF-8 offsets must lie on scalar boundaries. Supplementary characters,
    combining marks, bidi controls and CRLF retain their original representation.
    """
    if (not isinstance(catalog, list) or not 1 <= len(catalog) <= 256
            or type(tool_index) is not int or not 0 <= tool_index < len(catalog)
            or not isinstance(field, str) or field not in {"name", "description"}
            or type(start) is not int or type(end) is not int):
        raise ValueError("invalid field span reference")
    tool = catalog[tool_index]
    if not isinstance(tool, dict) or not isinstance(tool.get(field), str):
        raise ValueError("span field must be original text")
    text = tool[field]
    try:
        raw = text.encode("utf-8", errors="strict")
        if len(raw) > MAX_SPAN_FIELD_BYTES:
            raise ValueError("span field byte cap exceeded")
        if unit == "unicode-codepoint":
            if not 0 <= start < end <= len(text):
                raise ValueError("codepoint span out of bounds")
            char_start, char_end = start, end
            byte_start = len(text[:start].encode("utf-8"))
            byte_end = len(text[:end].encode("utf-8"))
        elif unit == "utf-8-byte":
            if not 0 <= start < end <= len(raw):
                raise ValueError("byte span out of bounds")
            char_start = len(raw[:start].decode("utf-8", errors="strict"))
            char_end = len(raw[:end].decode("utf-8", errors="strict"))
            byte_start, byte_end = start, end
        else:
            raise ValueError("unsupported span unit")
        evidence = text[char_start:char_end]
        if evidence.encode("utf-8") != raw[byte_start:byte_end]:
            raise ValueError("span encodings disagree")
        return {"tool_index": tool_index, "field": field,
                "span": {"start": char_start, "end": char_end, "unit": "unicode-codepoint"},
                "byte_span": {"start": byte_start, "end": byte_end, "unit": "utf-8-byte"},
                "evidence": evidence, "field_sha256": raw_hash(raw)}
    except UnicodeError as exc:
        raise ValueError("invalid Unicode scalar or UTF-8 span boundary") from exc


def enrich_finding(catalog: list[dict[str, Any]], finding: dict[str, Any]) -> dict[str, Any]:
    """Attach verified byte offsets without trusting or silently fixing evidence."""
    if not isinstance(finding, dict) or not isinstance(finding.get("span"), dict):
        raise ValueError("finding must contain a span object")
    span = finding["span"]
    if set(span) != {"start", "end", "unit"}:
        raise ValueError("finding span fields differ")
    resolved = resolve_field_span(
        catalog, tool_index=finding.get("tool_index"), field=finding.get("field"),
        start=span["start"], end=span["end"], unit=span["unit"],
    )
    if finding.get("evidence") != resolved["evidence"]:
        raise ValueError("finding evidence differs from original source")
    if ("tool_name" in finding
            and finding["tool_name"] != catalog[resolved["tool_index"]].get("name")):
        raise ValueError("finding tool identity differs from original source")
    if "byte_span" in finding:
        existing = finding["byte_span"]
        if (not isinstance(existing, dict)
                or type(existing.get("start")) is not int
                or type(existing.get("end")) is not int
                or existing != resolved["byte_span"]):
            raise ValueError("existing finding byte span differs from source")
    if "field_sha256" in finding and finding["field_sha256"] != resolved["field_sha256"]:
        raise ValueError("existing finding field hash differs from source")
    return {**deepcopy(finding), **resolved}
