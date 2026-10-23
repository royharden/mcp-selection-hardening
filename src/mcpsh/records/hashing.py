"""Byte identity is distinct from canonical typed JSON identity."""

import hashlib
import json
from typing import Any


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _nonfinite(value: str) -> None:
    raise ValueError(f"nonfinite JSON value: {value}")


def strict_json_loads(raw: str | bytes) -> Any:
    return json.loads(raw, object_pairs_hook=_unique_object, parse_constant=_nonfinite)


def canonical_json(value: Any) -> str:
    """Retain array order, multiplicity and JSON number/string/bool distinctions."""
    return json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True,
                      separators=(",", ":"))


def raw_hash(raw: str | bytes) -> str:
    return hashlib.sha256(raw.encode("utf-8") if isinstance(raw, str) else raw).hexdigest()


def typed_hash(value: Any) -> str:
    return raw_hash(canonical_json(value))
