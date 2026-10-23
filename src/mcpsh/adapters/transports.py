"""Concrete non-streaming HTTP/tool codecs. Nothing sends on import.

Official wire references are recorded in adapters/README.md. Use only through
BudgetedLiveTransport, which admits/reserves/journals before calling send().
"""

from dataclasses import dataclass, field
from copy import deepcopy
from hashlib import sha256
import json
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

MAX_RESPONSE_BYTES = 1024 * 1024
ADAPTER_REVISION = "mcpsh-http-tools-v2"


def encode_wire(wire: dict[str, Any]) -> bytes:
    """The one HTTP body encoder, shared by preview, token fit, hashes and send."""
    return json.dumps(wire, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")


def _duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key in provider response")
        result[key] = value
    return result


def decode_json(raw: bytes) -> Any:
    def nonfinite(value: str) -> None:
        raise ValueError("nonfinite JSON in provider response")
    return json.loads(raw.decode("utf-8"), object_pairs_hook=_duplicates, parse_constant=nonfinite)


def raw_value(text: str, path: list[str | int]) -> str:
    """Preserve Anthropic input object's lexical bytes, not a re-serialization."""
    decoder = json.JSONDecoder()

    def whitespace(index: int) -> int:
        while index < len(text) and text[index].isspace():
            index += 1
        return index

    def locate(index: int, remaining: list[str | int]) -> tuple[int, int]:
        index = whitespace(index)
        if not remaining:
            _, end = decoder.raw_decode(text, index)
            return index, end
        component, rest = remaining[0], remaining[1:]
        if isinstance(component, str) and text[index] == "{":
            index = whitespace(index + 1)
            while text[index] != "}":
                key, end = decoder.raw_decode(text, index)
                index = whitespace(end)
                if text[index] != ":":
                    raise ValueError("invalid JSON object separator")
                index = whitespace(index + 1)
                if key == component:
                    return locate(index, rest)
                _, index = decoder.raw_decode(text, index)
                index = whitespace(index)
                if text[index] == ",":
                    index = whitespace(index + 1)
        elif type(component) is int and text[index] == "[":
            index = whitespace(index + 1)
            current = 0
            while text[index] != "]":
                if current == component:
                    return locate(index, rest)
                _, index = decoder.raw_decode(text, index)
                index = whitespace(index)
                if text[index] == ",":
                    index = whitespace(index + 1)
                current += 1
        raise ValueError("provider JSON argument path missing")

    start, end = locate(0, path)
    return text[start:end]


@dataclass(frozen=True)
class HTTPReply:
    status: int
    raw: bytes
    request_id: str | None


class TransportFailure(RuntimeError):
    def __init__(self, category: str, *, transient: bool = False, reply: HTTPReply | None = None):
        super().__init__(category)
        self.category, self.transient, self.reply = category, transient, reply


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req: Any, fp: Any, code: int, msg: str, headers: Any, newurl: str) -> None:
        raise TransportFailure("redirect_refused")


@dataclass
class ProviderTransport:
    credential: Callable[[], str] = field(repr=False)
    endpoint_url: str
    timeout_seconds: float = 30
    network_enabled: bool = False
    provider: str = field(init=False, default="")

    def prepare(self, payload: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError

    def headers(self, key: str) -> dict[str, str]:
        raise NotImplementedError

    def preview_request(self, payload: dict[str, Any], *, adapter_sha256: str) -> dict[str, Any]:
        """Pure preview; source pin is supplied by verified admission, not guessed here.

        This method neither reads a source file nor evaluates credentials or headers.
        D1 already owns actual source closure verification before later admission.
        """
        if not isinstance(adapter_sha256, str) or len(adapter_sha256) != 64 or any(ch not in "0123456789abcdef" for ch in adapter_sha256):
            raise ValueError("explicit verified adapter source SHA256 required")
        if payload.get("provider") != self.provider or not isinstance(payload.get("model"), str):
            raise ValueError("preview requires exact provider/model input")
        wire = self.prepare(deepcopy(payload))
        return {"encoded_body": encode_wire(wire), "provider": self.provider,
                "model_id": payload["model"], "endpoint_url": self.endpoint_url,
                "settings": {**deepcopy({key: value for key, value in wire.items() if key not in {"messages", "tools", "model"}}),
                             "http_timeout_seconds": self.timeout_seconds,
                             "api_version": getattr(self, "api_version", None)},
                "adapter_revision": ADAPTER_REVISION, "adapter_sha256": adapter_sha256,
                "source_pin_basis": "externally-verified-admission-pin"}

    def parse(self, reply: HTTPReply) -> dict[str, Any]:
        raise NotImplementedError

    def selection_candidates(self, reply: HTTPReply) -> tuple[dict[str, Any] | None, bool]:
        """Recover all candidate wrappers before codec validation, never dispatch them.

        Arguments from OpenAI remain provider argument strings; Anthropic object
        inputs use lexical slices. Outer wrappers are explicitly reconstructed JSON,
        not a claim that they are the original response bytes.
        """
        if len(reply.raw) > MAX_RESPONSE_BYTES:
            return None, False
        try:
            document = decode_json(reply.raw)
            calls, ids, complete = [], [], True
            if not isinstance(document, dict):
                return None, False
            if self.provider == "openai":
                choices = document.get("choices")
                if not isinstance(choices, list) or len(choices) != 1 or not isinstance(choices[0], dict):
                    return None, False
                message = choices[0].get("message")
                if not isinstance(message, dict):
                    return None, False
                entries = message.get("tool_calls", [])
                if entries is None:
                    entries = []
                if not isinstance(entries, list):
                    return {"tool_calls": [entries], "tool_call_ids": [None]}, False
                for entry in entries:
                    function = entry.get("function") if isinstance(entry, dict) else None
                    if not isinstance(function, dict):
                        calls.append(entry)
                        ids.append(entry.get("id") if isinstance(entry, dict) else None)
                        complete = False
                        continue
                    calls.append({"name": function.get("name"), "arguments": function.get("arguments")})
                    identifier = entry.get("id")
                    ids.append(identifier)
                    complete = complete and entry.get("type") == "function" and isinstance(identifier, str) and bool(identifier)
            elif self.provider == "anthropic":
                entries = document.get("content")
                if not isinstance(entries, list):
                    return None, False
                for index, entry in enumerate(entries):
                    if not isinstance(entry, dict):
                        calls.append(entry)
                        ids.append(None)
                        complete = False
                    elif entry.get("type") == "tool_use":
                        calls.append({"name": entry.get("name"), "arguments": raw_value(reply.raw.decode("utf-8"), ["content", index, "input"])})
                        identifier = entry.get("id")
                        ids.append(identifier)
                        complete = complete and isinstance(identifier, str) and bool(identifier)
                    elif entry.get("type") not in {"text", "thinking", "redacted_thinking"}:
                        calls.append(entry)
                        ids.append(entry.get("id"))
                        complete = False
            else:
                return None, False
            string_ids = [identifier for identifier in ids if isinstance(identifier, str)]
            complete = complete and len(set(string_ids)) == len(string_ids)
            return {"tool_calls": calls, "tool_call_ids": ids}, bool(complete)
        except (ValueError, TypeError, UnicodeError, RecursionError, IndexError, KeyError):
            return None, False

    def failure_usage(self, reply: HTTPReply, requested_model: str) -> dict[str, Any] | None:
        """Optional explicit usage on a failed response; never assume zero billing."""
        try:
            document = decode_json(reply.raw)
        except (ValueError, UnicodeError):
            return None
        if not isinstance(document, dict) or document.get("model") != requested_model:
            return None
        usage = document.get("usage")
        if not isinstance(usage, dict):
            return None
        input_key, output_key = (("prompt_tokens", "completion_tokens")
                                 if self.provider == "openai" else ("input_tokens", "output_tokens"))
        return {"usage": usage, "input_tokens": usage.get(input_key),
                "output_tokens": usage.get(output_key)}

    def send(self, wire: dict[str, Any]) -> HTTPReply:
        if not self.network_enabled:
            raise TransportFailure("network_disabled")
        target = urlsplit(self.endpoint_url)
        if target.scheme != "https" or not target.hostname or target.username or target.password or target.query or target.fragment:
            raise TransportFailure("invalid_approved_endpoint")
        key = self.credential()
        if not isinstance(key, str) or not key or "\n" in key or "\r" in key:
            raise TransportFailure("credential_unavailable")
        body = encode_wire(wire)
        request = Request(self.endpoint_url, data=body, headers=self.headers(key), method="POST")
        # Disable redirects and implicit retries. The budgeted controller owns retry.
        try:
            with build_opener(NoRedirect()).open(request, timeout=self.timeout_seconds) as response:
                raw = response.read(MAX_RESPONSE_BYTES + 1)
                reply = HTTPReply(response.status, raw, response.headers.get("x-request-id") or response.headers.get("request-id"))
                if len(raw) > MAX_RESPONSE_BYTES:
                    raise TransportFailure("response_byte_cap", reply=reply)
                return reply
        except HTTPError as error:
            try:
                raw = error.read(MAX_RESPONSE_BYTES + 1)
                reply = HTTPReply(error.code, raw, error.headers.get("x-request-id") or error.headers.get("request-id"))
            finally:
                error.close()
            raise TransportFailure("rate_limit" if error.code == 429 else "http_error", transient=error.code == 429 or 500 <= error.code <= 599, reply=reply) from None
        except (URLError, TimeoutError, OSError):
            raise TransportFailure("transient_transport", transient=True) from None


@dataclass
class OpenAIChatTransport(ProviderTransport):
    endpoint_url: str = "https://api.openai.com/v1/chat/completions"
    provider: str = field(init=False, default="openai")

    def headers(self, key: str) -> dict[str, str]:
        return {"Authorization": "Bearer " + key, "Content-Type": "application/json"}

    def prepare(self, payload: dict[str, Any]) -> dict[str, Any]:
        messages: list[dict[str, Any]] = [{"role": "user", "content": json.dumps(payload["task"], ensure_ascii=False, allow_nan=False)}]
        for item in payload.get("history", []):
            role = item.get("role")
            if role not in {"user", "assistant", "tool"}:
                raise ValueError("unsupported public history role")
            message = {"role": role, "content": item.get("content") or ""}
            if role == "tool":
                message["tool_call_id"] = item["tool_call_id"]
            if role == "assistant" and item.get("tool_calls"):
                message["tool_calls"] = [{"id": call["id"], "type": "function", "function": {"name": call["name"], "arguments": call["arguments"]}} for call in item["tool_calls"]]
            messages.append(message)
        return {"model": payload["model"], "messages": messages, "tools": [{"type": "function", "function": {"name": tool["name"], "description": tool["description"], "parameters": tool["inputSchema"], "strict": False}} for tool in payload["tools"]], "tool_choice": "auto", "max_completion_tokens": payload["max_output_tokens"], "stream": False, "n": 1}

    def parse(self, reply: HTTPReply) -> dict[str, Any]:
        document = decode_json(reply.raw)
        choices = document.get("choices")
        if not isinstance(choices, list) or len(choices) != 1:
            raise ValueError("expected one completion choice")
        choice = choices[0]
        message = choice.get("message", {})
        calls, ids = [], []
        for call in message.get("tool_calls") or []:
            function = call.get("function", {})
            if call.get("type") != "function" or not isinstance(call.get("id"), str) or not isinstance(function.get("name"), str) or not isinstance(function.get("arguments"), str):
                raise ValueError("invalid function tool call envelope")
            calls.append({"name": function["name"], "arguments": function["arguments"]})
            ids.append(call["id"])
        usage = document.get("usage") or {}
        return {"provider": self.provider, "model": document.get("model"), "response_id": document.get("id"), "request_id": reply.request_id, "tool_calls": calls, "tool_call_ids": ids, "usage": usage, "input_tokens": usage.get("prompt_tokens"), "output_tokens": usage.get("completion_tokens"), "stop_reason": choice.get("finish_reason"), "refusal": message.get("refusal"), "assistant_content": message.get("content"), "arguments_representation": "provider-argument-string", "wire_schema": "openai-chat-tools-v1"}


@dataclass
class AnthropicMessagesTransport(ProviderTransport):
    endpoint_url: str = "https://api.anthropic.com/v1/messages"
    api_version: str = ""
    provider: str = field(init=False, default="anthropic")

    def headers(self, key: str) -> dict[str, str]:
        if not self.api_version:
            raise TransportFailure("approved_api_version_required")
        return {"x-api-key": key, "anthropic-version": self.api_version, "Content-Type": "application/json"}

    def prepare(self, payload: dict[str, Any]) -> dict[str, Any]:
        messages: list[dict[str, Any]] = [{"role": "user", "content": json.dumps(payload["task"], ensure_ascii=False, allow_nan=False)}]
        for item in payload.get("history", []):
            role = item.get("role")
            if role == "tool":
                block = {"type": "tool_result", "tool_use_id": item["tool_call_id"], "content": item.get("content") or ""}
                # Group adjacent results so they immediately follow tool_use blocks.
                if messages[-1]["role"] == "user" and isinstance(messages[-1]["content"], list):
                    messages[-1]["content"].append(block)
                else:
                    messages.append({"role": "user", "content": [block]})
            elif role in {"user", "assistant"}:
                content = []
                if item.get("content"):
                    content.append({"type": "text", "text": item["content"]})
                for call in item.get("tool_calls", []):
                    arguments = decode_json(call["arguments"].encode())
                    if not isinstance(arguments, dict):
                        raise ValueError("Anthropic tool input must be an object")
                    content.append({"type": "tool_use", "id": call["id"], "name": call["name"], "input": arguments})
                messages.append({"role": role, "content": content or [{"type": "text", "text": ""}]})
            else:
                raise ValueError("unsupported public history role")
        return {"model": payload["model"], "messages": messages, "tools": [{"name": tool["name"], "description": tool["description"], "input_schema": tool["inputSchema"]} for tool in payload["tools"]], "tool_choice": {"type": "auto"}, "max_tokens": payload["max_output_tokens"], "stream": False}

    def parse(self, reply: HTTPReply) -> dict[str, Any]:
        document = decode_json(reply.raw)
        content = document.get("content")
        if not isinstance(content, list):
            raise ValueError("message content must be a list")
        calls, ids, text = [], [], []
        for index, block in enumerate(content):
            if block.get("type") == "tool_use":
                if not isinstance(block.get("name"), str) or not isinstance(block.get("id"), str) or not isinstance(block.get("input"), dict):
                    raise ValueError("invalid tool_use envelope")
                calls.append({"name": block["name"], "arguments": raw_value(reply.raw.decode("utf-8"), ["content", index, "input"])})
                ids.append(block["id"])
            elif block.get("type") == "text":
                text.append(str(block.get("text", "")))
        usage = document.get("usage") or {}
        return {"provider": self.provider, "model": document.get("model"), "response_id": document.get("id"), "request_id": reply.request_id, "tool_calls": calls, "tool_call_ids": ids, "usage": usage, "input_tokens": usage.get("input_tokens"), "output_tokens": usage.get("output_tokens"), "stop_reason": document.get("stop_reason"), "refusal": document.get("stop_reason") == "refusal", "assistant_content": "\n".join(text), "arguments_representation": "provider-json-object-raw-slice", "wire_schema": "anthropic-messages-tools-v1"}


def body_hash(wire: dict[str, Any]) -> str:
    return sha256(encode_wire(wire)).hexdigest()
