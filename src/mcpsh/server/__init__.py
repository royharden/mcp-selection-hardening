"""M5 synthetic reference, not an accepted S1 filesystem reader or SDK release."""

from datetime import datetime, timedelta
import base64
import hashlib
import hmac
import json
import secrets
import threading
import time

from mcpsh.broker import (
    CALL_DEADLINE_SECONDS, MAX_FRAME_BYTES,
    SYNTHETIC_CANARY, BrokerUnavailable, FixtureBroker, canonical, digest,
)
from mcpsh.observer import EffectObserver
from mcpsh.broker.fixtures import normalize_fixture_payload, fixture_payload_hash, protected_sentinels
from mcpsh.policy import AccessPolicy, POLICY_VERSION, redact
from .validation import InvalidArguments, parse_arguments
from .admission import AdmissionRefused, CallAdmission, CallCancelled
from .matching import PATTERN_GRAMMAR_VERSION, PatternSyntaxError, compile_pattern
from .parsing import LOG_PARSER_VERSION, parse_log_line

SERVER_VERSION = "m5-reference-v2"


def redact_public(value, fixture_payload: dict | None = None):
    """Bounded JSON projection: preserve raw trace hashes, remove protected text."""
    sentinels = protected_sentinels(fixture_payload)
    if fixture_payload is None:
        sentinels = (*sentinels, SYNTHETIC_CANARY)
    def project(item):
        if isinstance(item, str):
            return redact(item, "hardened", sentinels)
        if isinstance(item, (list, tuple)):
            return [project(child) for child in item]
        if isinstance(item, dict):
            return {project(key): project(child) for key, child in item.items()}
        return item
    return project(value)


def _log_fields(text: str) -> tuple[str | None, str | None, str]:
    parsed = parse_log_line(text)
    return parsed.timestamp, parsed.level, parsed.message


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
    """Compatibility wrapper for the explicit versioned literal-pattern grammar."""
    return compile_pattern(pattern).matches(text)


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
    def __init__(self, mode: str = "hardened", allowed_sources=("app",), trial_id: str = "development", custom_redactions=(), platform_scope: str = "synthetic-memory", filesystem_config: dict | None = None, fixture_payload: dict | None = None):
        self._policy = AccessPolicy(mode, tuple(allowed_sources))
        self._fixture_payload = normalize_fixture_payload(fixture_payload)
        self.fixture_payload_sha256 = fixture_payload_hash(self._fixture_payload)
        self._source_ids = frozenset(self._fixture_payload["source_lines"])
        self._sentinels = protected_sentinels(self._fixture_payload)
        self._clock = self._fixture_payload["clock"]
        if not self._policy.allowed_sources.issubset(self._source_ids):
            raise ValueError("configured source does not exist in synthetic fixture")
        if fixture_payload is not None and self._policy.allowed_sources != frozenset(self._fixture_payload["allowed_source_ids"]):
            raise ValueError("task source policy differs from trusted fixture payload")
        if type(trial_id) is not str or not 1 <= len(trial_id) <= 128:
            raise ValueError("invalid trial ID")
        self._custom_redactions = tuple(custom_redactions)
        redact("", mode, self._sentinels, self._custom_redactions)
        self.trial_id = trial_id
        import uuid
        self.instance_id = uuid.uuid4().hex
        self.platform_scope = platform_scope
        self._broker = FixtureBroker(trial_id, platform_scope=platform_scope, filesystem_config=filesystem_config, fixture_payload=self._fixture_payload)
        self.fixture_id = filesystem_config["fixture_id"] if platform_scope == "filesystem-posix" else self._broker.epoch
        self._observer = EffectObserver(self._broker.observation_connection, trial_id, self._broker.epoch, platform_scope=platform_scope, sentinels=self._sentinels, fixture_payload_sha256=self.fixture_payload_sha256)
        self._admission = CallAdmission()
        self._trusted_conformance_session = None
        self._counter_lock = threading.Lock()
        self._call_ids: list[str] = []
        self._expected_operations: list[str] = []
        self._call_journal: list[dict] = []
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
        timestamp, level, _ = _log_fields(text)
        return {"line_no": number, "byte_offset": byte_offset, "timestamp": timestamp, "level": level, "timestamp_inherited": False, "level_inherited": False, "text": redact(text, self.mode, self._sentinels, self._custom_redactions), "context": context, "omitted": None}

    def _execute(self, tool: str, arguments: dict, call_id: str, deadline: float) -> dict:
        pattern = compile_pattern(arguments["pattern"]) if tool == "search" else None
        if tool == "list_sources":
            return _envelope(True, data={"sources": [{"id": source, "display_path": f"fixture:{source}", "readable": True} for source in sorted(self._policy.allowed_sources)]})
        if tool == "export_fixture":
            self._expected_operations.append(call_id)
            value = self._broker.request("export", call_id, deadline, destination_id=arguments["destination_id"])
            if "error" in value:
                return _envelope(False, code=value["error"], message="Disposable fixture export refused.")
            return _envelope(True, data=value)
        source_id = arguments["source_id"]
        if source_id not in self._source_ids:
            return _envelope(False, code="UNKNOWN_SOURCE", message="Unknown synthetic source.")
        self._expected_operations.append(call_id)
        response = self._broker.request("read", call_id, deadline, source_id=source_id)
        if "error" in response:
            return _envelope(False, code=response["error"], message="Synthetic broker refused operation.")
        raw_lines = response["lines"]
        generation = response["generation_id"]
        parsed_lines = {number: parse_log_line(text) for number, text in enumerate(raw_lines, 1)}
        format_counts = {}
        for value in parsed_lines.values():
            format_counts[value.format] = format_counts.get(value.format, 0) + 1
        parsing_coverage = {
            "version": LOG_PARSER_VERSION, "scope": "bounded-source-scan",
            "format_counts": format_counts,
            "unclassified_level_lines": sum(value.level is None for value in parsed_lines.values()),
            "untimestamped_lines": sum(value.timestamp is None for value in parsed_lines.values()),
            "unsupported_field_lines": sum(bool(value.unsupported) for value in parsed_lines.values()),
            "unclassified_code_error_lines": sum(value.level in {"ERROR", "FATAL", "CRITICAL"} and value.code is None for value in parsed_lines.values()),
        }
        offsets = {}
        current_offset = 0
        for index, text in enumerate(raw_lines, 1):
            offsets[index] = current_offset
            current_offset += len(text.encode("utf-8")) + 1
        rows = [(index + 1, text) for index, text in enumerate(raw_lines)]
        since = arguments.get("since")
        until = arguments.get("until")
        excluded_untimestamped = 0
        if tool == "recent_lines":
            since = (datetime.fromisoformat(self._clock) - timedelta(seconds=arguments["since_seconds"])).isoformat()
        if since or until:
            lower = datetime.fromisoformat(since.replace("Z", "+00:00")) if since else None
            upper = datetime.fromisoformat(until.replace("Z", "+00:00")) if until else None
            filtered = []
            for number, text in rows:
                timestamp = parsed_lines[number].timestamp
                if timestamp is None:
                    excluded_untimestamped += 1
                    continue
                parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                if (lower is None or parsed >= lower) and (upper is None or parsed <= upper):
                    filtered.append((number, text))
            rows = filtered
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
                selected = [(number, text) for number, text in rows if pattern.matches(text)]
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
            selected = [(number, text) for number, text in rows if parsed_lines[number].level in {"ERROR", "FATAL", "CRITICAL"}]
            offset = self._offset(tool, arguments, generation)
            rows = selected[offset:offset + 100]
            truncated = len(selected) > offset + 100
            if truncated:
                next_cursor = self._cursor(tool, arguments, generation, offset + 100)
            grouped = {}
            for number, text in rows:
                signature = parsed_lines[number].message[:160]
                if signature not in grouped:
                    grouped[signature] = {"signature": signature, "level": parsed_lines[number].level, "first_in_coverage": self._line(number, text, byte_offset=offsets[number]), "occurrence_count_in_coverage": 0, "trace": []}
                grouped[signature]["occurrence_count_in_coverage"] += 1
            groups = list(grouped.values())
        elif tool == "error_counts":
            count_map: dict[str, int] = {}
            for number, text in rows:
                if time.monotonic() > deadline:
                    raise BrokerUnavailable("call deadline exceeded")
                level = parsed_lines[number].level
                if level not in {"ERROR", "FATAL", "CRITICAL"}:
                    continue
                code = parsed_lines[number].code
                key = level if arguments["group_by"] == "level" else code if code is not None else "UNKNOWN"
                count_map[key] = count_map.get(key, 0) + 1
            limit = arguments["max_groups"]
            groups = [{"key": key, "count_in_coverage": count} for key, count in sorted(count_map.items())[:limit]]
            truncated = len(count_map) > limit
            rows = []
        if time.monotonic() > deadline:
            raise BrokerUnavailable("call deadline exceeded")
        match_numbers = {item["line_no"] for item in matches}
        rendered = []
        for number, text in rows:
            if time.monotonic() >= deadline:
                raise BrokerUnavailable("call deadline exceeded while rendering bounded lines")
            rendered.append(self._line(number, text, context=bool(matches) and number not in match_numbers, byte_offset=offsets[number]))
        semantic_complete = parsing_coverage["unclassified_level_lines"] == 0 and parsing_coverage["unsupported_field_lines"] == 0
        if tool == "error_counts" and arguments["group_by"] == "code":
            semantic_complete = semantic_complete and parsing_coverage["unclassified_code_error_lines"] == 0
        coverage = {"first_line": 1 if raw_lines else None, "last_line": len(raw_lines) or None, "bytes_read": response["bytes_read"], "total_lines": len(raw_lines), "complete": True, "window_lines": total_in_window, "excluded_untimestamped": excluded_untimestamped, "scope": "bounded fixture scan", "platform_scope": self.platform_scope, "parsing": parsing_coverage, "semantic_complete": semantic_complete, "counts_scope": "recognized-error-levels-in-bounded-coverage"}
        data = {"lines": rendered, "matches": matches, "groups": groups, "next_cursor": next_cursor, "parser_version": LOG_PARSER_VERSION}
        if tool == "search":
            data["pattern_grammar_version"] = PATTERN_GRAMMAR_VERSION
        return _envelope(True, source_id=source_id, generation_id=generation, data=data, truncated=truncated, coverage=coverage)

    def call(self, tool_name: str, raw_arguments: str, *, request_id: str | int | None = None) -> dict:
        started = time.monotonic()
        deadline = started + CALL_DEADLINE_SECONDS
        with self._counter_lock:
            sequence = len(self._call_ids) + 1
            call_id = f"{self.trial_id}:{sequence}"
            self._call_ids.append(call_id)
        raw_bytes = raw_arguments.encode("utf-8", errors="surrogatepass") if isinstance(raw_arguments, str) else b""
        event = {"trial_id": self.trial_id, "server_instance_id": self.instance_id, "request_id": request_id, "call_id": call_id, "sequence": sequence, "tool_name": tool_name, "raw_arguments": raw_arguments, "raw_hash": hashlib.sha256(raw_bytes).hexdigest(), "typed_arguments": None, "typed_hash": None, "validation": "invalid", "gate_classification": "unknown", "enforcement_mode": self.mode, "gate_decision": "not_evaluated", "gate_reason": "validation not completed", "dispatched": False, "executed": False, "cancelled": False, "output_hash": None}
        state = None
        result: dict
        try:
            if self._closed:
                result = _envelope(False, code="INTERNAL_ERROR", message="Server trial is closed.")
            else:
                state = self._admission.enter(call_id, request_id, deadline)
                arguments, typed_hash = parse_arguments(tool_name, raw_arguments)
                event.update(typed_arguments=arguments, typed_hash=typed_hash, validation="valid")
                decision = self._policy.evaluate(tool_name, arguments)
                event.update(gate_classification=decision.classification, gate_decision=decision.decision, gate_reason=decision.reason)
                if decision.decision == "deny":
                    result = _envelope(False, code="POLICY_DENIED", message=decision.reason, policy=True)
                else:
                    control = self._trusted_conformance_session
                    if control is not None:
                        control._before_execution(state)
                    with self._admission.condition:
                        if state["cancelled"]:
                            raise CallCancelled("call cancelled before broker dispatch")
                    if time.monotonic() >= deadline:
                        raise BrokerUnavailable("call deadline exceeded before dispatch")
                    event["dispatched"] = True
                    result = self._execute(tool_name, arguments, call_id, deadline)
                    event["executed"] = result["ok"]
        except AdmissionRefused as exc:
            result = _envelope(False, code="BUSY", message=str(exc))
        except CallCancelled as exc:
            event["cancelled"] = True
            result = _envelope(False, code="INTERNAL_ERROR", message=str(exc))
        except PatternSyntaxError as exc:
            result = _envelope(False, code="INVALID_PATTERN", message=str(exc))
        except InvalidArguments as exc:
            code = "INVALID_CURSOR" if str(exc) == "INVALID_CURSOR" else "INVALID_PATTERN" if "pattern syntax" in str(exc) or "anchors permitted" in str(exc) else "INVALID_ARGUMENT"
            result = _envelope(False, code=code, message=str(exc))
        except BrokerUnavailable as exc:
            result = _envelope(False, code="LIMIT_EXCEEDED" if "deadline" in str(exc) else "INTERNAL_ERROR", message=str(exc))
        except (ValueError, TypeError, KeyError, OverflowError, UnicodeError):
            result = _envelope(False, code="INTERNAL_ERROR", message="Bounded synthetic execution failed.")
        finally:
            if state is not None:
                event["cancelled"] = bool(state["cancelled"])
            self._admission.release(call_id)
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
        packet = {"event": event, "result": result}
        with self._counter_lock:
            self._call_journal.append(packet)
            self._call_journal = self._call_journal[-128:]
        return packet

    def _notify_cancellation(self, request_id: str | int, wire_payload: bytes) -> dict | None:
        """Protocol transport only: bind cancellation to an actual received frame."""
        if type(wire_payload) is not bytes or len(wire_payload) > MAX_FRAME_BYTES:
            raise ValueError("bounded cancellation frame required")
        frame = json.loads(wire_payload)
        value = frame.get("params", {}).get("requestId")
        if frame.get("method") != "notifications/cancelled" or type(value) is not type(request_id) or value != request_id:
            raise ValueError("cancellation frame does not address this request")
        state = self._admission.cancel(request_id, hashlib.sha256(wire_payload).hexdigest())
        if state is not None:
            self._observer.capture_cancellation(state["call_id"], request_id, wire_payload)
        return state

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
        self._admission.close()
        control = self._trusted_conformance_session
        if control is not None:
            control.close()
        self._broker.close()

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        self.close()
