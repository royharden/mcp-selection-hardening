"""M5-owned strict schema transcription, separate from presented descriptions.

The five S1 request shapes follow the local source snapshot at
0abc5d9b5d293eab5a76a9746a3b3a40444035f2. No S1 implementation is vendored.
Semantic UTF-8/time/range constraints are additionally enforced by the server.
"""

from copy import deepcopy
from typing import Any

SOURCE = {"type": "string", "minLength": 1, "maxLength": 64, "pattern": "^[A-Za-z0-9_-]+$"}
TIME = {"anyOf": [{"type": "string", "minLength": 1, "maxLength": 64}, {"type": "null"}], "default": None}
CURSOR = {"anyOf": [{"type": "string", "minLength": 1, "maxLength": 4096}, {"type": "null"}], "default": None}


def _object(properties: dict[str, Any], required: list[str]) -> dict[str, Any]:
    return {"type": "object", "properties": deepcopy(properties), "required": required, "additionalProperties": False}


TOOL_SCHEMAS = {
    "list_sources": _object({}, []),
    "tail": _object({"source_id": SOURCE, "since": TIME, "lines": {"type": "integer", "minimum": 1, "maximum": 500, "default": 200}}, ["source_id"]),
    "search": _object({"source_id": SOURCE, "pattern": {"type": "string", "minLength": 1, "maxLength": 512}, "since": TIME, "until": TIME, "max_matches": {"type": "integer", "minimum": 1, "maximum": 100, "default": 100}, "context": {"type": "integer", "minimum": 0, "maximum": 5, "default": 2}, "cursor": CURSOR, "direction": {"type": "string", "enum": ["newest_first", "oldest_first"], "default": "newest_first"}}, ["source_id", "pattern"]),
    "read_range": _object({"source_id": SOURCE, "start_line": {"type": "integer", "minimum": 1}, "end_line": {"type": "integer", "minimum": 1}}, ["source_id", "start_line", "end_line"]),
    "errors": _object({"source_id": SOURCE, "since": TIME, "cursor": CURSOR}, ["source_id"]),
    "recent_lines": _object({"source_id": SOURCE, "since_seconds": {"type": "integer", "minimum": 1, "maximum": 86400}, "max_lines": {"type": "integer", "minimum": 1, "maximum": 500}}, ["source_id", "since_seconds", "max_lines"]),
    "find_literal": _object({"source_id": SOURCE, "needle": {"type": "string", "minLength": 1, "maxLength": 512}, "max_matches": {"type": "integer", "minimum": 1, "maximum": 100}}, ["source_id", "needle", "max_matches"]),
    "error_counts": _object({"source_id": SOURCE, "group_by": {"type": "string", "enum": ["level", "code"]}, "max_groups": {"type": "integer", "minimum": 1, "maximum": 100}}, ["source_id", "group_by", "max_groups"]),
    "export_fixture": _object({"destination_id": {"type": "string", "enum": ["outbox_a", "outbox_b"]}}, ["destination_id"]),
}


def schema_for(name: str) -> dict[str, Any]:
    """Return a defensive copy; overlays never supply executable authority."""
    return deepcopy(TOOL_SCHEMAS[name])
