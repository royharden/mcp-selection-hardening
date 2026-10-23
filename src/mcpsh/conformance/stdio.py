"""Bounded raw stdio probe transport, activated only by an approved request.

Only the bundled conformance host can be launched. No configurable executable,
shell command, remote endpoint or inherited credential environment is admitted.
"""

import hashlib
import importlib.util
import json
import os
import queue
import subprocess
import sys
import threading
import time
from pathlib import Path

from .backend import BackendUnavailable, UnsupportedTrack

MAX_FRAME = 32 * 1024
PROTOCOL_VERSION = "2025-11-25"


def encode_frame(value):
    return json.dumps(value, ensure_ascii=True, allow_nan=False,
                      separators=(",", ":")).encode("utf-8") + b"\n"


def decode_frame(raw):
    from mcpsh.records import strict_json_loads

    if not isinstance(raw, bytes) or not raw.endswith(b"\n") or len(raw) > MAX_FRAME:
        raise ValueError("incomplete or oversized protocol frame")
    frame = strict_json_loads(raw.decode("utf-8", "strict"))
    if type(frame) is not dict or frame.get("jsonrpc") != "2.0":
        raise ValueError("stdout must contain JSON-RPC objects only")
    if "method" not in frame and ("id" not in frame or ("result" in frame) == ("error" in frame)):
        raise ValueError("response requires ID and exactly one result/error")
    return frame


def structured_tool_result(frame):
    """Protocol errors and structured execution errors are separate outcomes."""
    if "error" in frame:
        error = frame["error"]
        if type(error) is not dict or type(error.get("code")) is not int or not isinstance(error.get("message"), str):
            raise ValueError("invalid protocol error envelope")
        return {"kind": "protocol-error", "code": error["code"]}
    result = frame.get("result")
    if type(result) is not dict or type(result.get("content")) is not list:
        raise ValueError("tool response requires content")
    structured = result.get("structuredContent")
    if type(structured) is not dict or type(structured.get("ok")) is not bool:
        raise ValueError("M5 structured tool result missing")
    if result.get("isError", False) is not (not structured["ok"]):
        raise ValueError("structured execution status contradicts isError")
    texts = [item.get("text") for item in result["content"] if isinstance(item, dict) and item.get("type") == "text"]
    from mcpsh.records import strict_json_loads

    if not texts or not any(strict_json_loads(text) == structured for text in texts if isinstance(text, str)):
        raise ValueError("text and structured result disagree")
    return {"kind": "tool-result", "ok": structured["ok"],
            "error_code": (structured.get("error") or {}).get("code"), "structured": structured}


class StdioSession:
    def __init__(self, request, track, probe, *, control=None):
        request.require_activation()
        if track != "stdio":
            raise UnsupportedTrack("stdio adapter supports only stdio")
        self.timeout = request.timeout_seconds
        if control is not None:
            raise ValueError("external control targets are forbidden; session owns its child pipes")
        self.control = None
        self.frames = []
        self.wire_receipts = []
        self.receipt_lock = threading.Lock()
        self.next_id = 1
        self.pending = {}
        self.cancelled = set()
        self.closed = False
        self.received = queue.Queue(maxsize=64)
        if importlib.util.find_spec("mcp") is None or importlib.util.find_spec("mcp_types") is None:
            raise BackendUnavailable("compatible official SDK is not installed")
        # Preserve only OS bootstrap variables; no provider/key environment is copied.
        child_env = {key: os.environ[key] for key in ("SYSTEMROOT", "WINDIR", "TEMP", "TMP") if key in os.environ}
        child_env["PYTHONPATH"] = str(Path(__file__).resolve().parents[2])
        from .channel import InheritedControl

        self.control = InheritedControl(request)
        try:
            arguments, options = self.control.child_arguments()
            if probe.semantic_case_id:
                arguments.extend(["--semantic-case", probe.semantic_case_id])
            self.process = subprocess.Popen([sys.executable, "-m", "mcpsh.conformance.stdio_host", *arguments,
                "--runtime-authorized", "--disposable-authorized", "--approval-id", request.approval_id],
                                            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                            stderr=subprocess.DEVNULL, env=child_env, shell=False, **options)
        except BaseException:
            self.control.close()
            raise
        self.reader = threading.Thread(target=self._read, daemon=True)
        try:
            self.reader.start()
            self.control.bind(self.process)
            if self.control.identity.get("stdio_reference_injected") is not True:
                raise BackendUnavailable("D2 stdio same-reference injection unavailable")
            response = self.rpc("initialize", {"protocolVersion": PROTOCOL_VERSION,
                "capabilities": {}, "clientInfo": {"name": "mcpsh-conformance", "version": "1"}})
            result = response.get("result", {})
            if result.get("protocolVersion") != PROTOCOL_VERSION:
                raise BackendUnavailable("negotiated SDK protocol is not the admitted probe version")
            if "tools" not in result.get("capabilities", {}):
                raise ValueError("server failed to advertise tools capability")
            self.send(encode_frame({"jsonrpc": "2.0", "method": "notifications/initialized"}))
        except BaseException:
            self.close()
            raise

    def _read(self):
        try:
            for _ in range(64):
                raw = self.process.stdout.readline(MAX_FRAME + 1)
                if not raw:
                    self.received.put_nowait(EOFError("stdio server exited"))
                    return
                frame = decode_frame(raw)
                self._receipt("response", raw, frame.get("id"))
                self.received.put_nowait((frame, hashlib.sha256(raw).hexdigest(), len(raw)))
        except (OSError, ValueError, UnicodeError, queue.Full) as exc:
            try:
                self.received.put_nowait(exc)
            except queue.Full:
                pass

    def send(self, raw):
        if not isinstance(raw, bytes) or len(raw) > MAX_FRAME + 1024:
            raise ValueError("probe transmission exceeds fixed injection cap")
        try:
            frame = json.loads(raw)
            request_id = frame.get("id")
        except (ValueError, TypeError):
            request_id = self.next_id - 1
        self._receipt("request", raw, request_id)
        done = threading.Event()
        errors = []

        def write():
            try:
                view = memoryview(raw)
                while view:
                    count = self.process.stdin.write(view)
                    if not count:
                        raise OSError("short stdio write")
                    view = view[count:]
                self.process.stdin.flush()
            except (OSError, ValueError) as exc:
                errors.append(exc)
            finally:
                done.set()

        threading.Thread(target=write, daemon=True).start()
        if not done.wait(self.timeout):
            self.close()
            raise TimeoutError("stdio write deadline")
        if errors:
            raise errors[0]

    def _receipt(self, direction, raw, request_id):
        key = json.dumps(request_id, ensure_ascii=True, separators=(",", ":"))
        with self.receipt_lock:
            if len(self.wire_receipts) >= 128:
                raise ValueError("wire receipt cap")
            self.wire_receipts.append({"direction": direction, "sequence": len(self.wire_receipts) + 1,
                "request_key": key, "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw),
                "response_expected": direction == "request" and request_id is not None})

    def receive(self, request_id):
        if request_id in self.pending:
            return self.pending.pop(request_id)
        deadline = time.monotonic() + self.timeout
        for _ in range(64):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("stdio response deadline")
            try:
                item = self.received.get(timeout=remaining)
            except queue.Empty as exc:
                raise TimeoutError("stdio response deadline") from exc
            if isinstance(item, BaseException):
                raise item
            frame, digest, size = item
            self.frames.append({"sha256": digest, "bytes": size})
            if "method" in frame:
                continue
            response_id = frame.get("id")
            if response_id in self.cancelled:
                continue
            if response_id == request_id and type(response_id) is type(request_id):
                return frame
            if response_id in self.pending:
                raise ValueError("duplicate response ID")
            self.pending[response_id] = frame
        raise ValueError("too many unsolicited stdio frames")

    def rpc(self, method, params=None):
        request_id = self.next_id
        self.next_id += 1
        frame = {"jsonrpc": "2.0", "id": request_id, "method": method}
        if params is not None:
            frame["params"] = params
        self.send(encode_frame(frame))
        return self.receive(request_id)

    def exercise(self, hook):
        if hook.startswith("semantic-stdio:"):
            from .semantics import get_case

            case_id = hook.split(":", 1)[1]
            case = get_case(case_id)
            request_id = self.next_id
            self.next_id += 1
            # Preserve the golden argument bytes, not a provider/SDK reserialization.
            raw = ('{"jsonrpc":"2.0","id":' + str(request_id) + ',"method":"tools/call",'
                '"params":{"name":' + json.dumps(case.call.tool) + ',"arguments":' + case.call.raw_arguments + '}}\n').encode("utf-8")
            self.send(raw)
            result = structured_tool_result(self.receive(request_id))
            evidence = self.evidence(valid=result.get("kind") == "tool-result")
            evidence.update(semantic_case_id=case_id, semantic_result=result.get("structured", {}),
                semantic_raw_arguments_sha256=hashlib.sha256(case.call.raw_arguments.encode("utf-8")).hexdigest())
            return evidence
        if hook == "stdio-catalog":
            from mcpsh.catalog.schemas import TOOL_SCHEMAS

            response = self.rpc("tools/list", {})
            tools = response.get("result", {}).get("tools", [])
            actual = {tool["name"]: tool.get("inputSchema") for tool in tools}
            return self.evidence(valid=len(tools) == 9 and actual == TOOL_SCHEMAS)
        if hook in {"stdio-success", "stdio-policy-error", "stdio-escaping"}:
            name = "tail" if hook == "stdio-policy-error" else "list_sources"
            args = {"source_id": "worker"} if name == "tail" else {}
            if hook == "stdio-escaping":
                name, args = "find_literal", {"source_id": "app", "needle": '"\\\t\u2028', "max_matches": 1}
            result = structured_tool_result(self.rpc("tools/call", {"name": name, "arguments": args}))
            if hook == "stdio-policy-error":
                valid = result.get("kind") == "tool-result" and result.get("error_code") == "POLICY_DENIED" and result.get("ok") is False
            else:
                valid = result.get("kind") == "tool-result" and result.get("ok") is True
            return self.evidence(valid=valid)
        if hook == "stdio-unknown-method":
            result = self.rpc("m5/unsupported", {})
            error = result.get("error", {})
            return self.evidence(valid=type(error.get("code")) is int and error.get("code") == -32601)
        if hook in {"stdio-duplicate", "stdio-nonfinite", "stdio-input-frame"}:
            request_id = self.next_id
            self.next_id += 1
            args = ('{"source_id":"app","source_id":"protected_fixture"}' if hook == "stdio-duplicate"
                    else '{"source_id":"app","lines":NaN}' if hook == "stdio-nonfinite"
                    else '{"source_id":"app","padding":"' + "x" * MAX_FRAME + '"}')
            raw = ('{"jsonrpc":"2.0","id":' + str(request_id) + ',"method":"tools/call",'
                   '"params":{"name":"tail","arguments":' + args + '}}\n').encode()
            self.send(raw)
            # A disconnect/timeout is unknown, never an invented structured refusal.
            frame = self.receive(request_id)
            return self.evidence(valid="error" in frame and type(frame["error"].get("code")) is int)
        if hook == "stdio-output-amplification":
            # Dedicated fixture has escaped multibyte/quote data. Assert actual frame size,
            # not just the handler's byte estimate; a structured LIMIT is acceptable.
            result = structured_tool_result(self.rpc("tools/call", {"name": "tail", "arguments": {"source_id": "app", "lines": 500}}))
            valid = result.get("kind") == "tool-result" and result.get("error_code") == "LIMIT_EXCEEDED"
            return self.evidence(valid=valid)
        if hook in {"stdio-cancellation", "stdio-concurrency"}:
            if self.control.identity.get("core_control_available") is not True:
                raise BackendUnavailable("requires D2 trusted in-flight barrier/occupancy and effect observation hook")
            from .protocol_controls import cancellation_control, concurrency_control

            control = cancellation_control if hook == "stdio-cancellation" else concurrency_control
            return control(self, self.control)
        raise BackendUnavailable("unknown stdio control")

    def evidence(self, *, valid):
        observation = self.control.observe() if self.control.identity.get("core_control_available") is True else {"complete": False}
        return {"evidence_source": "actual-local-stdio", "checks": {"protocol_contract": valid},
                "frames": list(self.frames), "protocol_version": PROTOCOL_VERSION,
                "host_identity": dict(self.control.identity), "observation": observation}

    def provenance(self):
        from .evidence import source_pins

        identity = self.control.identity
        return {"scope": "actual-stdio", "session": {
            "server_instance_id": identity["server_instance_id"], "child_pid": self.process.pid,
            "trial_id": identity["trial_id"],
            "fixture_id": identity["fixture_id"], "fixture_payload_sha256": identity["fixture_payload_sha256"],
            "platform_scope": identity["platform_scope"]}, "frames": [
                {**frame, "response_expected": False} if frame["direction"] == "request" and
                frame["request_key"] in {json.dumps(key) for key in self.cancelled} else dict(frame)
                for frame in self.wire_receipts],
            "source_pins": source_pins()}

    def close(self):
        if self.closed:
            return
        self.closed = True
        # Operate solely on the exact Popen child owned by this probe.
        try:
            if self.process.poll() is None:
                self.process.terminate()
                try:
                    self.process.wait(timeout=self.timeout)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.process.wait(timeout=self.timeout)
        finally:
            try:
                for handle in (self.process.stdin, self.process.stdout):
                    if handle is not None:
                        handle.close()
            finally:
                if self.control is not None:
                    self.control.close()
