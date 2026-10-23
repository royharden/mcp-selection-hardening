"""Public deterministic log-field contract, independent of any hidden corpus."""

from dataclasses import dataclass
from datetime import datetime
import json
import re

LOG_PARSER_VERSION = "m5-log-fields-v1"
LEVELS = frozenset({"TRACE", "DEBUG", "INFO", "WARN", "ERROR", "FATAL", "CRITICAL"})
_CODE = re.compile(r"(?i)(?<![A-Za-z0-9_])(?:error_code|code)\s*[:=]\s*([A-Za-z0-9_.-]{1,64})(?=$|[\s,\];}])")
_CODE_VALUE = re.compile(r"[A-Za-z0-9_.-]{1,64}\Z")


@dataclass(frozen=True)
class ParsedLogLine:
    timestamp: str | None
    level: str | None
    code: str | None
    message: str
    format: str
    unsupported: tuple[str, ...] = ()


def _timestamp(value) -> str | None:
    if type(value) is not str or not value or len(value) > 64:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.isoformat() if parsed.tzinfo is not None else None


def _level(value) -> str | None:
    if type(value) is not str:
        return None
    normalized = value.upper()
    if normalized.startswith("[") and normalized.endswith("]"):
        normalized = normalized[1:-1]
    if normalized.startswith("LEVEL="):
        normalized = normalized[6:]
    normalized = "WARN" if normalized == "WARNING" else normalized
    return normalized if normalized in LEVELS else None


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate structured log field")
        result[key] = value
    return result


def _nonfinite(_value):
    raise ValueError("nonfinite structured log value")


def parse_log_line(text: str) -> ParsedLogLine:
    if type(text) is not str or len(text.encode("utf-8", "strict")) > 64 * 1024:
        raise ValueError("bounded physical text line required")
    stripped = text.strip()
    if stripped.startswith("{"):
        try:
            value = json.loads(stripped, object_pairs_hook=_unique, parse_constant=_nonfinite)
            if type(value) is not dict:
                raise ValueError("structured log object required")
        except (ValueError, TypeError, RecursionError):
            return ParsedLogLine(None, None, None, text, "unparsed", ("invalid-structured-json",))
        unsupported = []
        times = [_timestamp(value[key]) for key in ("timestamp", "time", "ts") if key in value]
        timestamp = times[0] if times and times[0] is not None and all(item == times[0] for item in times) else None
        if times and timestamp is None:
            unsupported.append("invalid-or-ambiguous-timestamp")
        level = _level(value.get("level"))
        if "level" in value and level is None:
            unsupported.append("unsupported-level")
        codes = [value[key] for key in ("code", "error_code") if key in value]
        code = codes[0] if codes and type(codes[0]) is str and _CODE_VALUE.fullmatch(codes[0]) and all(type(item) is str and item == codes[0] for item in codes) else None
        if codes and code is None:
            unsupported.append("invalid-or-ambiguous-code")
        message = value.get("message", value.get("msg", text))
        if type(message) is not str:
            unsupported.append("unsupported-message")
            message = text
        return ParsedLogLine(timestamp, level, code, message, "json", tuple(unsupported))
    tokens = stripped.split(None, 2)
    timestamp = None
    level = None
    message = text
    if tokens:
        timestamp_token = tokens[0].strip("[]")
        if timestamp_token.lower().startswith("timestamp="):
            timestamp_token = timestamp_token[10:]
        timestamp = _timestamp(timestamp_token)
        index = 1 if timestamp is not None else 0
        if len(tokens) > index:
            level = _level(tokens[index])
        if timestamp is not None and level is not None and len(tokens) > 2:
            message = tokens[2]
        elif timestamp is None and level is not None:
            message = stripped.split(None, 1)[1] if len(stripped.split(None, 1)) > 1 else ""
    codes = tuple(dict.fromkeys(match.group(1) for match in _CODE.finditer(message)))
    code = codes[0] if len(codes) == 1 else None
    unsupported = ("ambiguous-code",) if len(codes) > 1 else ()
    return ParsedLogLine(timestamp, level, code, message, "plain", unsupported)
