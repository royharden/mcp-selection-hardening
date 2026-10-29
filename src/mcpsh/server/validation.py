"""Small strict validator for the canonical server-owned tool schema vocabulary."""

from datetime import datetime
import hashlib
import json
import math
import re

from mcpsh.broker import MAX_FRAME_BYTES, canonical


class InvalidArguments(ValueError):
    pass


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise InvalidArguments("duplicate JSON key")
        result[key] = value
    return result


def _reject_constant(value):
    raise InvalidArguments("nonfinite JSON number")


def _validate(value, schema: dict, path: str = "arguments") -> None:
    if "anyOf" in schema:
        for alternative in schema["anyOf"]:
            try:
                _validate(value, alternative, path)
                return
            except InvalidArguments:
                continue
        raise InvalidArguments(f"{path}: invalid union value")
    kind = schema.get("type")
    if isinstance(kind, list):
        _validate(value, {**schema, "anyOf": [{"type": item} for item in kind]}, path)
        return
    valid = {
        "object": type(value) is dict, "array": type(value) is list,
        "string": type(value) is str, "integer": type(value) is int,
        "number": type(value) in {int, float} and math.isfinite(value),
        "boolean": type(value) is bool, "null": value is None,
    }
    if kind is not None and not valid.get(kind, False):
        raise InvalidArguments(f"{path}: expected {kind}")
    if "enum" in schema and not any(type(value) is type(item) and value == item for item in schema["enum"]):
        raise InvalidArguments(f"{path}: not an allowed enum value")
    if "const" in schema and (type(value) is not type(schema["const"]) or value != schema["const"]):
        raise InvalidArguments(f"{path}: invalid constant")
    if type(value) is dict:
        properties = schema.get("properties", {})
        if schema.get("additionalProperties") is False and set(value) - set(properties):
            raise InvalidArguments(f"{path}: unknown field")
        if set(schema.get("required", [])) - set(value):
            raise InvalidArguments(f"{path}: required field missing")
        for key, item in value.items():
            if key in properties:
                _validate(item, properties[key], f"{path}.{key}")
    if type(value) is str:
        try:
            value.encode("utf-8", errors="strict")
        except UnicodeError as exc:
            raise InvalidArguments(f"{path}: invalid Unicode scalar") from exc
        if len(value) < schema.get("minLength", 0) or len(value) > schema.get("maxLength", MAX_FRAME_BYTES):
            raise InvalidArguments(f"{path}: string length limit")
        if "pattern" in schema and re.search(schema["pattern"], value) is None:
            raise InvalidArguments(f"{path}: invalid string format")
    if type(value) in {int, float}:
        if value < schema.get("minimum", -math.inf) or value > schema.get("maximum", math.inf):
            raise InvalidArguments(f"{path}: numeric limit")


def parse_arguments(tool_name: str, raw: str) -> tuple[dict, str]:
    from mcpsh.catalog.schemas import TOOL_SCHEMAS
    if type(raw) is not str or len(raw.encode("utf-8", errors="surrogatepass")) > MAX_FRAME_BYTES:
        raise InvalidArguments("raw argument byte limit")
    if tool_name not in TOOL_SCHEMAS:
        raise InvalidArguments("unknown tool")
    try:
        arguments = json.loads(raw, object_pairs_hook=_unique_object, parse_constant=_reject_constant)
        _validate(arguments, TOOL_SCHEMAS[tool_name])
    except (ValueError, TypeError, RecursionError, OverflowError) as exc:
        raise InvalidArguments(str(exc)[:160]) from exc
    if "source_id" in arguments and not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", arguments["source_id"]):
        raise InvalidArguments("source_id must be an opaque configured ID")
    for key in ("pattern", "needle"):
        if key in arguments and len(arguments[key].encode("utf-8")) > 512:
            raise InvalidArguments(f"{key}: UTF-8 byte limit")
    for key in ("since", "until"):
        if arguments.get(key) is not None:
            try:
                timestamp = datetime.fromisoformat(arguments[key].replace("Z", "+00:00"))
                if timestamp.tzinfo is None:
                    raise ValueError("timezone required")
            except ValueError as exc:
                raise InvalidArguments(f"{key}: ISO timestamp with timezone required") from exc
    if arguments.get("since") and arguments.get("until"):
        if datetime.fromisoformat(arguments["since"].replace("Z", "+00:00")) > datetime.fromisoformat(arguments["until"].replace("Z", "+00:00")):
            raise InvalidArguments("time range reversed")
    if tool_name == "read_range" and (arguments["end_line"] < arguments["start_line"] or arguments["end_line"] - arguments["start_line"] + 1 > 500):
        raise InvalidArguments("line range reversed or exceeds 500")
    # Defaults are executable server semantics, applied only after validating raw types.
    for key, item in TOOL_SCHEMAS[tool_name].get("properties", {}).items():
        if key not in arguments and "default" in item:
            arguments[key] = item["default"]
    return arguments, hashlib.sha256(canonical(arguments)).hexdigest()
