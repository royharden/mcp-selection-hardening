"""Lazy SDK-v2 adapter with bounded exact-wire guards.

Source compatibility is provisional: select an exact SDK/protocol lock and run a
stdio smoke/conformance pass after Dirty Mode. No SDK import or process starts at
module import. The input guard rejects duplicate/nonfinite JSON before the SDK
can coerce it, and retains exact argument substrings for the server journal.
"""

import hashlib
import json
import sys

from mcpsh.broker import MAX_FRAME_BYTES, canonical
from . import ReferenceServer, SERVER_VERSION
from .validation import _reject_constant, _unique_object


def _member(text: str, key_path: tuple[str, ...]) -> str:
    """Find an exact member slice in already-validated JSON, without rewriting."""
    decoder = json.JSONDecoder()
    position = 0
    while position < len(text) and text[position].isspace():
        position += 1
    if position >= len(text) or text[position] != "{":
        raise ValueError("object member required")
    position += 1
    while position < len(text):
        while position < len(text) and text[position].isspace():
            position += 1
        if text[position] == "}":
            break
        key, position = decoder.raw_decode(text, position)
        while text[position].isspace():
            position += 1
        if text[position] != ":":
            raise ValueError("invalid JSON object")
        position += 1
        while text[position].isspace():
            position += 1
        start = position
        _, position = decoder.raw_decode(text, position)
        if key == key_path[0]:
            value = text[start:position]
            return _member(value, key_path[1:]) if len(key_path) > 1 else value
        while text[position].isspace():
            position += 1
        if text[position] == ",":
            position += 1
            continue
        break
    raise KeyError("JSON member missing")


class _WireGuard:
    def __init__(self, reference: ReferenceServer):
        self.reference = reference
        self.pending: dict[str, dict] = {}
        self.raw_frames: list[dict] = []
        self.input_complete = True

    def receive(self, payload: bytes) -> str:
        if len(payload) > MAX_FRAME_BYTES or not payload.endswith(b"\n"):
            self.input_complete = False
            self.raw_frames.append({"raw_hash": hashlib.sha256(payload).hexdigest(), "raw_hex": payload.hex(), "status": "frame_invalid"})
            self.raw_frames = self.raw_frames[-128:]
            raise ValueError("complete input frame exceeds 32 KiB or is unterminated")
        try:
            text = payload.decode("utf-8", errors="strict")
            frame = json.loads(text, object_pairs_hook=_unique_object, parse_constant=_reject_constant)
            if type(frame) is not dict:
                raise ValueError("JSON-RPC object required")
            if frame.get("method") == "tools/call":
                request_id = canonical(frame.get("id")).decode("ascii")
                if request_id in self.pending or len(self.pending) >= 20:
                    raise ValueError("duplicate request ID or queue cap")
                if type(frame.get("id")) not in {int, str} or len(str(frame["id"])) > 128:
                    raise ValueError("request ID limit")
                arguments = _member(text, ("params", "arguments"))
                self.pending[request_id] = {"raw_arguments": arguments, "call_id": None}
            self.raw_frames.append({"raw_hash": hashlib.sha256(payload).hexdigest(), "bytes": len(payload), "status": "parsed"})
            self.raw_frames = self.raw_frames[-128:]
            return text
        except (ValueError, TypeError, KeyError, UnicodeError, RecursionError):
            self.input_complete = False
            self.raw_frames.append({"raw_hash": hashlib.sha256(payload).hexdigest(), "raw_hex": payload.hex(), "status": "protocol_invalid"})
            self.raw_frames = self.raw_frames[-128:]
            raise


async def serve_stdio(mode: str = "hardened", allowed_sources=("app",), trial_id: str = "stdio-development", platform_scope: str = "synthetic-memory", filesystem_config: dict | None = None) -> None:
    """Future activation entrypoint; no host listener, only process stdin/stdout."""
    try:
        import anyio
        import mcp_types as types
        from mcp.server.lowlevel import Server
        from mcp.server.stdio import stdio_server
    except ImportError as exc:
        raise RuntimeError("Optional MCP SDK v2 is unavailable; install and lock it only after authorized activation.") from exc
    from mcpsh.catalog import build_catalog
    from mcpsh.catalog.schemas import schema_for

    reference = ReferenceServer(mode=mode, allowed_sources=allowed_sources, trial_id=trial_id, platform_scope=platform_scope, filesystem_config=filesystem_config)
    guard = _WireGuard(reference)
    input_file = anyio.wrap_file(sys.stdin.buffer)
    output_file = anyio.wrap_file(sys.stdout.buffer)

    class GuardedInput:
        def __aiter__(self):
            return self

        async def __anext__(self):
            payload = await input_file.readline(MAX_FRAME_BYTES + 1)
            if not payload:
                raise StopAsyncIteration
            return guard.receive(payload)

    class GuardedOutput:
        async def write(self, text: str):
            payload = text.encode("utf-8")
            if len(payload) > MAX_FRAME_BYTES:
                guard.input_complete = False
                raise ValueError("complete output frame exceeds 32 KiB")
            frame = json.loads(text)
            written = await output_file.write(payload)
            await output_file.flush()
            key = canonical(frame.get("id")).decode("ascii")
            pending = guard.pending.pop(key, None)
            if pending and pending["call_id"]:
                reference.capture_wire(payload, pending["call_id"])
            return written

        async def flush(self):
            await output_file.flush()

    async def list_tools(_context, _parameters):
        return types.ListToolsResult.model_validate({"tools": build_catalog("clean")})

    async def call_tool(context, parameters):
        key = canonical(context.request_id).decode("ascii")
        pending = guard.pending.get(key)
        if pending is None:
            raise ValueError("exact raw request provenance unavailable")
        packet = await anyio.to_thread.run_sync(reference.call, parameters.name, pending["raw_arguments"])
        pending["call_id"] = packet["event"]["call_id"]
        result = packet["result"]
        return types.CallToolResult.model_validate({"content": [{"type": "text", "text": canonical(result).decode("ascii")}], "structuredContent": result, "isError": not result["ok"]})

    server = Server("m5-synthetic-reference", version=SERVER_VERSION, on_list_tools=list_tools, on_call_tool=call_tool, get_tool_input_schema=lambda name: schema_for(name))
    try:
        async with stdio_server(stdin=GuardedInput(), stdout=GuardedOutput()) as (read_stream, write_stream):
            await server.run(read_stream, write_stream, server.create_initialization_options())
    finally:
        reference.close()


def main() -> None:
    import asyncio
    asyncio.run(serve_stdio())


if __name__ == "__main__":
    main()
