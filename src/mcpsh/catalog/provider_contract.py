"""Pure audits of supplied actual wire bytes, never a second request encoder.

Structural parity is not provider execution, model/tool interoperability or
independent acceptance. No HTTP, credential access or tokenizer is imported.
"""

import re
from typing import Any

from mcpsh.catalog.artifacts import artifact_pins, validate_catalog_artifact
from mcpsh.records.hashing import raw_hash, strict_json_loads, typed_hash

CONTRACT_VERSION = "m5-provider-catalog-parity-1"
MAX_WIRE_BYTES = 4_194_304
BODY_FIELDS = {
    "openai": {"model", "messages", "tools", "tool_choice", "max_completion_tokens",
               "stream", "n"},
    "anthropic": {"model", "messages", "tools", "tool_choice", "max_tokens", "stream", "system"},
}


def decode_wire_body(encoded_body: bytes) -> dict[str, Any]:
    """Strict transport identity; do not reserialize before handing bytes here."""
    if not isinstance(encoded_body, bytes) or not 0 < len(encoded_body) <= MAX_WIRE_BYTES:
        raise ValueError("exact nonempty bounded encoded bytes required")
    try:
        body = strict_json_loads(encoded_body.decode("utf-8", errors="strict"))
        if not isinstance(body, dict):
            raise ValueError("wire body must be a JSON object")
        typed_hash(body)  # Reject invalid scalars/nonfinite/cyclic typed input.
        return body
    except (ValueError, TypeError, RecursionError, OverflowError) as exc:
        raise ValueError("invalid encoded wire body") from exc


def wire_settings(body: dict[str, Any]) -> dict[str, Any]:
    """Only a projection/hash helper; history/tools still belong in full-body proof."""
    return {key: value for key, value in body.items() if key not in {"messages", "tools", "system"}}


def audit_provider_catalog(artifact: dict[str, Any], encoded_body: bytes | None, *,
                           provider: str, model_id: str, adapter_revision: str,
                           adapter_sha256: str) -> dict[str, Any]:
    result: dict[str, Any] = {
        "version": CONTRACT_VERSION, "scope": "source-wire-structure-only",
        "status": "unavailable", "reasons": [], "provider": provider,
        "model_id": model_id, "adapter_revision": adapter_revision,
        "adapter_sha256": adapter_sha256, "provider_interoperability": "unverified",
    }
    if not isinstance(provider, str) or provider not in BODY_FIELDS:
        result.update(status="unsupported", reasons=["unsupported provider wire dialect"])
        return result
    if (not isinstance(model_id, str) or not model_id or len(model_id) > 256
            or not isinstance(adapter_revision, str) or not adapter_revision
            or len(adapter_revision) > 256 or not isinstance(adapter_sha256, str)
            or re.fullmatch(r"[0-9a-f]{64}", adapter_sha256) is None):
        result["reasons"] = ["exact model/adapter identity unavailable"]
        return result
    if encoded_body is None:
        result["reasons"] = ["actual encoded body unavailable"]
        return result
    try:
        if validate_catalog_artifact(artifact):
            raise ValueError("invalid canonical artifact")
        body = decode_wire_body(encoded_body)
        result.update(raw_body_sha256=raw_hash(encoded_body), typed_body_sha256=typed_hash(body),
                      settings_sha256=typed_hash(wire_settings(body)),
                      catalog_pins=artifact_pins(artifact))
        if set(body) - BODY_FIELDS[provider]:
            result.update(status="unsupported", reasons=["unmodeled request settings in this codec version"])
            return result
        if body.get("model") != model_id:
            raise ValueError("wire model differs from selected exact model")
        if (not isinstance(body.get("messages"), list) or not body["messages"]
                or any(not isinstance(message, dict) for message in body["messages"])):
            raise ValueError("messages must retain ordered nonempty objects")
        if body.get("stream") is not False:
            result.update(status="unsupported", reasons=["streaming dialect not audited"])
            return result
        cap_key = "max_completion_tokens" if provider == "openai" else "max_tokens"
        if type(body.get(cap_key)) is not int or body[cap_key] < 1:
            raise ValueError("output token cap must be an exact positive integer")
        if provider == "openai":
            if type(body.get("n")) is not int or body["n"] != 1 or body.get("tool_choice") != "auto":
                raise ValueError("single-choice auto-tool contract changed")
        elif typed_hash(body.get("tool_choice")) != typed_hash({"type": "auto"}):
            raise ValueError("auto-tool contract changed")
        tools = body.get("tools")
        if not isinstance(tools, list) or len(tools) != 9:
            raise ValueError("wire catalog must contain all nine tools")
        projected = []
        for tool in tools:
            if not isinstance(tool, dict):
                raise ValueError("wire tool must be an object")
            if provider == "openai":
                if set(tool) != {"type", "function"} or tool["type"] != "function":
                    raise ValueError("invalid function wrapper")
                function = tool["function"]
                if not isinstance(function, dict) or set(function) != {
                    "name", "description", "parameters", "strict"
                }:
                    raise ValueError("function fields differ")
                if function["strict"] is not False:
                    result.update(status="unsupported", reasons=["strict-mode schema rewrite not audited"])
                    return result
                projected.append({"name": function["name"], "description": function["description"],
                                  "inputSchema": function["parameters"]})
            else:
                if set(tool) != {"name", "description", "input_schema"}:
                    raise ValueError("Anthropic tool fields differ")
                projected.append({"name": tool["name"], "description": tool["description"],
                                  "inputSchema": tool["input_schema"]})
        expected = [{"name": tool["name"], "description": tool["description"],
                     "inputSchema": tool["inputSchema"]} for tool in artifact["catalog"]]
        if typed_hash(projected) != typed_hash(expected):
            raise ValueError("wire names/order/descriptions/typed schema semantics differ")
        result.update(status="valid", reasons=[], projected_catalog_sha256=typed_hash(projected),
                      tools_checked=9, annotation_projection="advisory hints not represented by these codecs")
    except (ValueError, TypeError, KeyError, RecursionError, OverflowError):
        result.update(status="invalid", reasons=["malformed or mismatched wire/catalog contract"])
    return result


def audit_call_projection(expected_calls: Any, actual_calls: Any) -> dict[str, Any]:
    """Golden decoded-call parity, preserving order, types and multiplicity.

    Decode provider responses with their actual codecs before this comparison.
    This helper does not manufacture provider responses or validate real effects.
    """
    result: dict[str, Any] = {"version": CONTRACT_VERSION, "status": "invalid",
                              "scope": "decoded-call-golden-only"}
    try:
        for calls in (expected_calls, actual_calls):
            if not isinstance(calls, list) or len(calls) > 256:
                raise ValueError("bounded ordered call lists required")
            for call in calls:
                if (not isinstance(call, dict) or set(call) != {"name", "arguments"}
                        or not isinstance(call["name"], str) or not call["name"]
                        or not isinstance(call["arguments"], dict)):
                    raise ValueError("exact decoded name/argument object required")
        expected_hash, actual_hash = typed_hash(expected_calls), typed_hash(actual_calls)
        call_hashes = [typed_hash(call) for call in actual_calls]
        result.update(status="valid" if expected_hash == actual_hash else "invalid",
                      expected_sha256=expected_hash, actual_sha256=actual_hash,
                      expected_count=len(expected_calls), actual_count=len(actual_calls),
                      extra_count=max(0, len(actual_calls) - len(expected_calls)),
                      missing_count=max(0, len(expected_calls) - len(actual_calls)),
                      repeated_actual_count=len(call_hashes) - len(set(call_hashes)))
    except (ValueError, TypeError, KeyError, RecursionError, OverflowError):
        result["reason"] = "malformed decoded golden call projection"
    return result
