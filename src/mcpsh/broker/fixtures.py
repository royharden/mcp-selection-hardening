"""Pure, bounded trusted synthetic fixture contract; no corpus/path loader.

The runner verifies sealed bytes before calling this module. Status strings do
not confer authority; no code, host paths or oracle labels are admitted here.
"""

from datetime import datetime
import hashlib
import json

from . import MAX_READ_BYTES, PINNED_CLOCK, _fixtures, canonical

FIXTURE_FIELDS = {"fixture_ref", "clock", "source_lines", "allowed_source_ids", "outboxes", "loader_status"}
SOURCE_IDS = frozenset({"app", "worker", "protected_fixture"})


def normalize_fixture_payload(payload: dict | None = None) -> dict:
    if payload is None:
        payload = {"fixture_ref": "m5-default-development", "clock": PINNED_CLOCK, "source_lines": _fixtures(), "allowed_source_ids": ["app", "worker"], "outboxes": ["outbox_a", "outbox_b"], "loader_status": "development-only"}
    if type(payload) is not dict or set(payload) != FIXTURE_FIELDS:
        raise ValueError("fixture payload requires exactly the v1 synthetic fields")
    for field, limit in (("fixture_ref", 64), ("clock", 64), ("loader_status", 128)):
        value = payload[field]
        if type(value) is not str or not value or "\x00" in value or len(value.encode("utf-8", "strict")) > limit:
            raise ValueError("invalid bounded fixture string field")
    try:
        clock = datetime.fromisoformat(payload["clock"].replace("Z", "+00:00"))
        if clock.tzinfo is None:
            raise ValueError("fixture clock requires timezone")
    except ValueError as exc:
        raise ValueError("fixture clock must be timezone-aware ISO8601") from exc
    source_lines = payload["source_lines"]
    if type(source_lines) is not dict or not 1 <= len(source_lines) <= 3 or set(source_lines) - SOURCE_IDS or "protected_fixture" not in source_lines:
        raise ValueError("fixture sources must be fixed configured synthetic IDs")
    copied = {}
    total = 0
    for source_id, lines in source_lines.items():
        if type(source_id) is not str or len(source_id.encode("utf-8")) > 64 or type(lines) is not list or len(lines) > 500:
            raise ValueError("invalid source ID or line count")
        copied[source_id] = []
        for line in lines:
            if type(line) is not str or any(character in line for character in ("\n", "\r", "\x00")):
                raise ValueError("fixture line must be a physical UTF-8 text line")
            size = len(line.encode("utf-8", "strict"))
            if size > 4096:
                raise ValueError("fixture line exceeds 4096 UTF-8 bytes")
            total += size + 1
            copied[source_id].append(line)
    protected = copied["protected_fixture"]
    if not protected or any(not line for line in protected):
        raise ValueError("protected fixture requires nonempty synthetic sentinels")
    public_lines = [line for source_id, lines in copied.items() if source_id != "protected_fixture" for line in lines]
    if any(sentinel in line for sentinel in protected for line in public_lines):
        raise ValueError("protected sentinels must not coincide with public fixture content")
    if total > MAX_READ_BYTES:
        raise ValueError("fixture total byte cap exceeded")
    allowed = payload["allowed_source_ids"]
    if type(allowed) is not list or any(type(value) is not str for value in allowed) or len(allowed) != len(set(allowed)) or set(allowed) - {"app", "worker"} or set(allowed) - set(copied):
        raise ValueError("invalid or duplicate task-allowed source IDs")
    if type(payload["outboxes"]) is not list or payload["outboxes"] != ["outbox_a", "outbox_b"]:
        raise ValueError("fixture outboxes must be the two canonical disposable IDs")
    normalized = {"fixture_ref": payload["fixture_ref"], "clock": clock.isoformat(), "source_lines": copied, "allowed_source_ids": list(allowed), "outboxes": list(payload["outboxes"]), "loader_status": payload["loader_status"]}
    if len(canonical(normalized)) > MAX_READ_BYTES:
        raise ValueError("serialized fixture byte cap exceeded")
    return normalized


def fixture_payload_hash(payload: dict | None = None) -> str:
    # Match records.typed_hash: UTF-8 typed JSON, not ASCII-escaped wire bytes.
    value = json.dumps(normalize_fixture_payload(payload), ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(value).hexdigest()


def fixture_source_bytes(lines: list[str]) -> bytes:
    return ("\n".join(lines) + ("\n" if lines else "")).encode("utf-8", "strict")


def protected_sentinels(payload: dict | None = None) -> tuple[str, ...]:
    fixture = normalize_fixture_payload(payload)
    return tuple(dict.fromkeys(fixture["source_lines"]["protected_fixture"]))
