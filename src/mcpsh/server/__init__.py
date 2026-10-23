"""M5 synthetic reference, not an accepted S1 filesystem reader or SDK release."""

from datetime import datetime, timedelta
import base64
import hashlib
import hmac
import json
import re
import secrets
import threading
import time

from mcpsh.broker import (
    CALL_DEADLINE_SECONDS, FIXTURE_VERSION, MAX_FRAME_BYTES, PINNED_CLOCK,
    SYNTHETIC_CANARY, BrokerUnavailable, FixtureBroker, canonical, digest,
)
from mcpsh.observer import EffectObserver
from mcpsh.policy import AccessPolicy, POLICY_VERSION, redact
from .validation import InvalidArguments, parse_arguments

SERVER_VERSION = "m5-reference-v1"
SOURCE_IDS = ("app", "worker", "protected_fixture")


def redact_public(value):
    """Bounded JSON projection: preserve raw trace hashes, remove protected text."""
    if isinstance(value, str):
        return redact(value, "hardened", SYNTHETIC_CANARY)
    if isinstance(value, list):
        return [redact_public(item) for item in value]
    if isinstance(value, tuple):
        return [redact_public(item) for item in value]
    if isinstance(value, dict):
        return {redact_public(key): redact_public(item) for key, item in value.items()}
    return value


def _envelope(ok: bool, *, source_id=None, generation_id=None, data=None, code=None, message="", policy=False, truncated=False, coverage=None) -> dict:
    payload = data or {}
    error = None if ok else {"code": code, "message": message[:256], "hint": "Use configured synthetic source IDs and bounded arguments.", "retryable": code == "BUSY"}
    if policy:
        error["policy_schema_version"] = 1
        error["policy_version"] = POLICY_VERSION
    return {
        "schema_version": 1, "ok": ok, "source_id": source_id, "generation_id": generation_id,
        "content_trust": "untrusted_log_data", "data": data if ok else None,
        "lines": payload.get("lines", []), "matches": payload.get("matches", []),
        "groups": payload.get("groups", []), "sources": payload.get("sources", []),
        "coverage": coverage or {"bytes_read": 0, "complete": True},
        "truncated": truncated, "truncation": {"output_lines": truncated, "output_bytes": False, "input_window": False, "oversize_line": False},
        "next_cursor": payload.get("next_cursor"), "warnings": [], "hint": "M5 synthetic-memory fallback; filesystem acceptance pending.",
        "error": error,
    }


def _supported_match(pattern: str, text: str) -> bool:
    """Finite pattern language: literal alternatives with optional ^/$ anchors.

    No repetition, groups, character classes or backreferences are executed.
    This is a declared bounded subset, not a general Python-regex service.
    """
    if any(character in pattern for character in "[](){}*+?\\"):
        raise InvalidArguments("unsupported pattern syntax; use literal alternatives and anchors")
    for alternative in pattern.split("|"):
        start, end = alternative.startswith("^"), alternative.endswith("$")
        needle = alternative[1:] if start else alternative
        needle = needle[:-1] if end else needle
        if "^" in needle or "$" in needle:
            raise InvalidArguments("anchors permitted only at alternative boundaries")
        if (text == needle if start and end else text.startswith(needle) if start else text.endswith(needle) if end else needle in text):
            return True
    return False


def _s1_projection(result: dict) -> dict:
    """Retain a separately addressable strict S1-v1 envelope for its five tools."""
    fields = ("schema_version", "ok", "source_id", "generation_id", "content_trust", "lines", "matches", "groups", "sources", "truncation", "next_cursor", "warnings", "hint", "error")
    envelope = {field: result[field] for field in fields}
    coverage_fields = {"first_line", "last_line", "bytes_read", "total_lines", "complete", "omitted_oversize_lines", "excluded_untimestamped"}
    envelope["coverage"] = {key: value for key, value in result["coverage"].items() if key in coverage_fields}
    if envelope["error"] is not None:
        envelope["error"] = {key: value for key, value in envelope["error"].items() if key in {"code", "message", "hint", "retryable"}}
        if envelope["error"]["code"] == "POLICY_DENIED":
            envelope["error"]["code"] = "PATH_FORBIDDEN"
    return envelope


class ReferenceServer:
    def __init__(self, mode: str = "hardened", allowed_sources=("app",), trial_id: str = "development", custom_redactions=(), platform_scope: str = "synthetic-memory", filesystem_config: dict | None = None):
        self._policy = AccessPolicy(mode, tuple(allowed_sources))
        if not self._policy.allowed_sources.issubset(SOURCE_IDS):
            raise ValueError("configured source does not exist in synthetic fixture")
        if type(trial_id) is not str or not 1 <= len(trial_id) <= 128:
            raise ValueError("invalid trial ID")
        self._custom_redactions = tuple(custom_redactions)
        redact("", mode, SYNTHETIC_CANARY, self._custom_redactions)
        self.trial_id = trial_id
        self.platform_scope = platform_scope
        self._broker = FixtureBroker(trial_id, platform_scope=platform_scope, filesystem_config=filesystem_config)
        self._observer = EffectObserver(self._broker.observation_connection, trial_id, self._broker.epoch, platform_scope=platform_scope)
        self._slots = threading.BoundedSemaphore(20)
        self._active = threading.BoundedSemaphore(4)
        self._counter_lock = threading.Lock()
        self._call_ids: list[str] = []
        self._expected_operations: list[str] = []
        self._cursor_key = secrets.token_bytes(32)
        self._closed = False

    @property
    def mode(self) -> str:
        return self._policy.mode

    def _cursor(self, tool: str, arguments: dict, generation_id: str, offset: int) -> str:
        bindings = {key: value for key, value in arguments.items() if key != "cursor"}
        body = canonical({"trial": self.trial_id, "tool": tool, "arguments": digest(bindings), "generation": generation_id, "offset": offset})
        signature = hmac.new(self._cursor_key, body, hashlib.sha256).hexdigest().encode("ascii")
        return base64.urlsafe_b64encode(body + b"." + signature).decode("ascii")

    def _offset(self, tool: str, arguments: dict, generation_id: str) -> int:
        cursor = arguments.get("cursor")
        if cursor is None:
            return 0
        try:
            decoded = base64.b64decode(cursor.encode("ascii"), altchars=b"-_", validate=True)
            body, signature = decoded.rsplit(b".", 1)
            if not hmac.compare_digest(signature, hmac.new(self._cursor_key, body, hashlib.sha256).hexdigest().encode("ascii")):
                raise ValueError("invalid signature")
            value = json.loads(body)
            bindings = {key: item for key, item in arguments.items() if key != "cursor"}
            if value != {"trial": self.trial_id, "tool": tool, "arguments": digest(bindings), "generation": generation_id, "offset": value.get("offset")}:
                raise ValueError("cursor binding mismatch")
            if type(value["offset"]) is not int or value["offset"] < 0:
                raise ValueError("invalid cursor offset")
            return value["offset"]
        except (ValueError, TypeError, KeyError, UnicodeError) as exc:
            raise InvalidArguments("INVALID_CURSOR") from exc

    def _line(self, number: int, text: str, *, context: bool = False, byte_offset: int = 0) -> dict:
        parts = text.split(" ", 2)
        return {"line_no": number, "byte_offset": byte_offset, "timestamp": parts[0], "level": parts[1] if len(parts) > 1 else None, "timestamp_inherited": False, "level_inherited": False, "text": redact(text, self.mode, SYNTHETIC_CANARY, self._custom_redactions), "context": context, "omitted": None}

    def _execute(self, tool: str, arguments: dict, call_id: str, deadline: float) -> dict:
        if tool == "list_sources":
            return _envelope(True, data={"sources": [{"id": source, "display_path": f"fixture:{source}", "readable": True} for source in sorted(self._policy.allowed_sources)]})
        if tool == "export_fixture":
            self._expected_operations.append(call_id)
            value = self._broker.request("export", call_id, deadline, destination_id=arguments["destination_id"])
            if "error" in value:
                return _envelope(False, code=value["error"], message="Disposable fixture export refused.")
            return _envelope(True, data=value)
        source_id = arguments["source_id"]
        if source_id not in SOURCE_IDS:
            return _envelope(False, code="UNKNOWN_SOURCE", message="Unknown synthetic source.")
        self._expected_operations.append(call_id)
        response = self._broker.request("read", call_id, deadline, source_id=source_id)
        if "error" in response:
            return _envelope(False, code=response["error"], message="Synthetic broker refused operation.")
        raw_lines = response["lines"]
        generation = response["generation_id"]
        offsets = {}
        current_offset = 0
        for index, text in enumerate(raw_lines, 1):
            offsets[index] = current_offset
            current_offset += len(text.encode("utf-8")) + 1
        rows = [(index + 1, text) for index, text in enumerate(raw_lines)]
        since = arguments.get("since")
        until = arguments.get("until")
        if tool == "recent_lines":
            since = (datetime.fromisoformat(PINNED_CLOCK) - timedelta(seconds=arguments["since_seconds"])).isoformat()
        if since or until:
            lower = datetime.fromisoformat(since.replace("Z", "+00:00")) if since else None
            upper = datetime.fromisoformat(until.replace("Z", "+00:00")) if until else None
            rows = [(number, text) for number, text in rows if (lower is None or datetime.fromisoformat(text.split(" ", 1)[0]) >= lower) and (upper is None or datetime.fromisoformat(text.split(" ", 1)[0]) <= upper)]
        total_in_window = len(rows)
        matches = []
        groups = []
        next_cursor = None
        truncated = False
        if tool in {"tail", "recent_lines"}:
            limit = arguments.get("lines", arguments.get("max_lines", 200))
            truncated = len(rows) > limit
            rows = rows[-limit:]
        elif tool == "read_range":
            rows = [(number, text) for number, text in rows if arguments["start_line"] <= number <= arguments["end_line"]]
        elif tool in {"search", "find_literal"}:
            if tool == "search":
                # Validate syntax even on an empty source.
                _supported_match(arguments["pattern"], "")
                selected = [(number, text) for number, text in rows if _supported_match(arguments["pattern"], text)]
                if arguments.get("direction", "newest_first") == "newest_first":
                    selected.reverse()
                offset = self._offset(tool, arguments, generation)
            else:
                selected = [(number, text) for number, text in rows if arguments["needle"] in text]
                offset = 0
            limit = arguments.get("max_matches", 100)
            page = selected[offset:offset + limit]
            truncated = len(selected) > offset + limit
            if tool == "search" and truncated:
                next_cursor = self._cursor(tool, arguments, generation, offset + limit)
            match_numbers = {number for number, _ in page}
            matches = [{"line_no": number} for number, _ in page]
            context = arguments.get("context", 0)
            included = {index for number in match_numbers for index in range(max(1, number - context), min(len(raw_lines), number + context) + 1)}
            rows = [(number, text) for number, text in enumerate(raw_lines, 1) if number in included]
            if len(rows) > 500:
                rows = rows[:500]
                truncated = True
            # A match outside the capped response must not be advertised as returned.
            retained_numbers = {number for number, _ in rows}
            matches = [match for match in matches if match["line_no"] in retained_numbers]
        elif tool == "errors":
            selected = [(number, text) for number, text in rows if text.split(" ", 2)[1] in {"ERROR", "FATAL", "CRITICAL"}]
            offset = self._offset(tool, arguments, generation)
            rows = selected[offset:offset + 100]
            truncated = len(selected) > offset + 100
            if truncated:
                next_cursor = self._cursor(tool, arguments, generation, offset + 100)
            grouped = {}
            for number, text in rows:
                signature = text.split(" ", 2)[-1][:160]
                if signature not in grouped:
                    grouped[signature] = {"signature": signature, "level": text.split(" ", 2)[1], "first_in_coverage": self._line(number, text, byte_offset=offsets[number]), "occurrence_count_in_coverage": 0, "trace": []}
                grouped[signature]["occurrence_count_in_coverage"] += 1
            groups = list(grouped.values())
        elif tool == "error_counts":
            count_map: dict[str, int] = {}
            for _, text in rows:
                if time.monotonic() > deadline:
                    raise BrokerUnavailable("call deadline exceeded")
                parts = text.split(" ", 2)
                if parts[1] not in {"ERROR", "FATAL", "CRITICAL"}:
                    continue
                code = re.search(r"\bcode=([A-Za-z0-9_-]+)", text)
                key = parts[1] if arguments["group_by"] == "level" else code.group(1) if code else "UNKNOWN"
                count_map[key] = count_map.get(key, 0) + 1
            limit = arguments["max_groups"]
            groups = [{"key": key, "count_in_coverage": count} for key, count in sorted(count_map.items())[:limit]]
            truncated = len(count_map) > limit
            rows = []
        if time.monotonic() > deadline:
            raise BrokerUnavailable("call deadline exceeded")
        match_numbers = {item["line_no"] for item in matches}
        rendered = [self._line(number, text, context=bool(matches) and number not in match_numbers, byte_offset=offsets[number]) for number, text in rows]
        coverage = {"first_line": 1 if raw_lines else None, "last_line": len(raw_lines) or None, "bytes_read": response["bytes_read"], "total_lines": len(raw_lines), "complete": True, "window_lines": total_in_window, "scope": "bounded fixture scan", "platform_scope": self.platform_scope}
        return _envelope(True, source_id=source_id, generation_id=generation, data={"lines": rendered, "matches": matches, "groups": groups, "next_cursor": next_cursor}, truncated=truncated, coverage=coverage)

    def call(self, tool_name: str, raw_arguments: str) -> dict:
        started = time.monotonic()
        deadline = started + CALL_DEADLINE_SECONDS
        with self._counter_lock:
            sequence = len(self._call_ids) + 1
            call_id = f"{self.trial_id}:{sequence}"
            self._call_ids.append(call_id)
        raw_bytes = raw_arguments.encode("utf-8", errors="surrogatepass") if isinstance(raw_arguments, str) else b""
        event = {"trial_id": self.trial_id, "call_id": call_id, "sequence": sequence, "tool_name": tool_name, "raw_arguments": raw_arguments, "raw_hash": hashlib.sha256(raw_bytes).hexdigest(), "typed_arguments": None, "typed_hash": None, "validation": "invalid", "gate_classification": "unknown", "enforcement_mode": self.mode, "gate_decision": "not_evaluated", "gate_reason": "validation not completed", "dispatched": False, "executed": False, "output_hash": None}
        queued = self._slots.acquire(blocking=False)
        active = False
        result: dict
        try:
            if not queued:
                result = _envelope(False, code="BUSY", message="Four active and sixteen queued calls already admitted.")
            elif self._closed:
                result = _envelope(False, code="INTERNAL_ERROR", message="Server trial is closed.")
            else:
                active = self._active.acquire(timeout=max(0.0, deadline - time.monotonic()))
                if not active:
                    result = _envelope(False, code="BUSY", message="Call queue deadline exceeded.")
                else:
                    arguments, typed_hash = parse_arguments(tool_name, raw_arguments)
                    event.update(typed_arguments=arguments, typed_hash=typed_hash, validation="valid")
                    decision = self._policy.evaluate(tool_name, arguments)
                    event.update(gate_classification=decision.classification, gate_decision=decision.decision, gate_reason=decision.reason)
                    if decision.decision == "deny":
                        result = _envelope(False, code="POLICY_DENIED", message=decision.reason, policy=True)
                    else:
                        event["dispatched"] = True
                        result = self._execute(tool_name, arguments, call_id, deadline)
                        event["executed"] = result["ok"]
        except InvalidArguments as exc:
            code = "INVALID_CURSOR" if str(exc) == "INVALID_CURSOR" else "INVALID_PATTERN" if "pattern syntax" in str(exc) or "anchors permitted" in str(exc) else "INVALID_ARGUMENT"
            result = _envelope(False, code=code, message=str(exc))
        except BrokerUnavailable as exc:
            result = _envelope(False, code="LIMIT_EXCEEDED" if "deadline" in str(exc) else "INTERNAL_ERROR", message=str(exc))
        except (ValueError, TypeError, KeyError, OverflowError, UnicodeError):
            result = _envelope(False, code="INTERNAL_ERROR", message="Bounded synthetic execution failed.")
        finally:
            if active:
                self._active.release()
            if queued:
                self._slots.release()
        result["hint"] = f"M5 {self.platform_scope} fixture; platform acceptance pending."
        if tool_name in {"list_sources", "tail", "search", "read_range", "errors"}:
            result["s1_envelope"] = _s1_projection(result)
        # Budget complete JSON-RPC content+structured envelope, including escaping.
        # The adapter independently verifies its actual final encoded frame as well.
        if len(canonical({"jsonrpc": "2.0", "id": "x" * 128, "result": {"content": [{"type": "text", "text": canonical(result).decode("ascii")}], "structuredContent": result, "isError": not result["ok"]}})) > MAX_FRAME_BYTES:
            result = _envelope(False, code="LIMIT_EXCEEDED", message="Complete serialized JSON-RPC frame would exceed 32 KiB.")
            if tool_name in {"list_sources", "tail", "search", "read_range", "errors"}:
                result["s1_envelope"] = _s1_projection(result)
        event["output_hash"] = digest(result)
        event["duration_seconds"] = time.monotonic() - started
        return {"event": event, "result": result}

    def capture_wire(self, payload: bytes, call_id: str | None = None) -> None:
        """Called by runner after receiving result; never from a tool handler."""
        if call_id is None:
            if not self._call_ids:
                raise ValueError("no call to associate with response bytes")
            call_id = self._call_ids[-1]
        self._observer.capture_wire(call_id, payload)

    def observe(self) -> dict:
        return self._observer.observe(tuple(self._call_ids), self._broker.alive, tuple(self._expected_operations))

    def close(self) -> None:
        self._closed = True
        self._broker.close()

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        self.close()
