"""Keyless selectors and approval-gated live transport contracts.

This is an M5-owned fallback, not a vendored complete S3 controller. Provider
transports are injected only after separate environment and spending approval.
"""

from dataclasses import dataclass
from copy import deepcopy
import json
import re
from typing import Any, Callable

PUBLIC_FIELDS = ("task_id", "user_request", "allowed_source_ids", "fixture_ref")


def public_task(task: dict[str, Any]) -> dict[str, Any]:
    """Allowlist projection is the only task view accepted by live serialization."""
    return {key: deepcopy(task[key]) for key in PUBLIC_FIELDS if key in task}


class ReplaySelector:
    provenance = "scripted-development-replay"

    def __init__(self, calls: list[dict[str, Any]]):
        self.calls = deepcopy(calls)

    def select(self, task: dict[str, Any], catalog: list[dict[str, Any]], history: list[dict[str, Any]]) -> list[dict[str, str]]:
        del task, catalog
        if history:
            return []
        result = []
        for call in self.calls:
            arguments = call.get("arguments", "{}")
            if not isinstance(arguments, str):
                arguments = json.dumps(arguments, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
            result.append({"name": str(call["name"]), "arguments": arguments})
        return result


class AbstainSelector:
    provenance = "deterministic-abstain-control"

    def select(self, task: dict[str, Any], catalog: list[dict[str, Any]], history: list[dict[str, Any]]) -> list[dict[str, str]]:
        return []


class KeywordSelector:
    """Name/request lexical baseline with stable ID ties and no oracle access."""

    provenance = "deterministic-name-keyword-control"

    def select(self, task: dict[str, Any], catalog: list[dict[str, Any]], history: list[dict[str, Any]]) -> list[dict[str, str]]:
        if history:
            return []
        public = public_task(task)
        request = str(public.get("user_request", "")).casefold()
        if re.search(r"\b(?:no tool|do not call|abstain|refuse)\b", request):
            return []
        tokens = set(re.findall(r"[a-z0-9]+", request))
        scored = [(len(tokens & set(re.findall(r"[a-z0-9]+", item["name"].casefold()))), item["name"]) for item in catalog]
        if not scored:
            return []
        score, name = sorted(scored, key=lambda row: (-row[0], row[1]))[0]
        if score == 0 or name == "export_fixture":
            return []
        sources = public.get("allowed_source_ids", [])
        source = sources[0] if sources else None
        if name != "list_sources" and source is None:
            return []
        arguments: dict[str, Any] = {} if name == "list_sources" else {"source_id": source}
        quoted = re.search(r"[\"']([^\"']+)[\"']", str(public.get("user_request", "")))
        literal = quoted.group(1) if quoted else "ERROR"
        arguments.update({"tail": {"lines": 2}, "search": {"pattern": literal}, "read_range": {"start_line": 1, "end_line": 2}, "recent_lines": {"since_seconds": 3600, "max_lines": 20}, "find_literal": {"needle": literal, "max_matches": 20}, "error_counts": {"group_by": "level", "max_groups": 20}}.get(name, {}))
        return [{"name": name, "arguments": json.dumps(arguments, separators=(",", ":"))}]


@dataclass(frozen=True)
class LiveArm:
    provider: str
    family: str
    model: str
    key_environment_name: str


# Family/provider slots are source configuration, not approved models or prices.
LIVE_ARM_SLOTS = (
    {"provider": "openai", "family": "openai-gpt", "model_environment_name": "MCPSH_OPENAI_MODEL", "key_environment_name": "OPENAI_API_KEY"},
    {"provider": "anthropic", "family": "anthropic-claude", "model_environment_name": "MCPSH_ANTHROPIC_MODEL", "key_environment_name": "ANTHROPIC_API_KEY"},
)


class LiveDispatchDenied(RuntimeError):
    pass


class LiveSelector:
    provenance = "live-provider-transport"

    def __init__(self, arm: LiveArm, transport: Callable[[dict[str, Any]], dict[str, Any]] | None = None, approval: dict[str, Any] | None = None):
        self.arm, self.transport, self.approval = arm, transport, deepcopy(approval)
        self._conversation: list[dict[str, Any]] = []
        self._consumed_history = 0
        self._pending_calls: list[dict[str, str]] = []
        self._turns = 0
        self._call_count = 0
        self.last_response: dict[str, Any] | None = None

    def select(self, task: dict[str, Any], catalog: list[dict[str, Any]], history: list[dict[str, Any]]) -> list[dict[str, str]]:
        approval = self.approval or {}
        if approval.get("mode") != "live" or approval.get("authorized") is not True:
            raise LiveDispatchDenied("explicit live approval is required; replay is not live evidence")
        if approval.get("provider") != self.arm.provider or approval.get("model") != self.arm.model or approval.get("family") != self.arm.family:
            raise LiveDispatchDenied("approved exact provider/model/family identity does not match")
        if not approval.get("price_snapshot_hash") or not approval.get("budget_reservation_id") or not approval.get("corpus_seal_hash"):
            raise LiveDispatchDenied("price, budget reservation and corpus seal are required")
        if self.transport is None:
            raise LiveDispatchDenied("no approved provider transport is configured")
        if self._turns >= 3 or len(history) < self._consumed_history:
            raise LiveDispatchDenied("turn cap reached or selector reused across trials")
        additions = history[self._consumed_history:]
        if len(additions) != len(self._pending_calls):
            raise LiveDispatchDenied("every prior provider call requires one ordered captured result")
        for item, pending in zip(additions, self._pending_calls):
            call = item.get("call", {})
            if item.get("role") != "tool" or call.get("name") != pending["name"] or call.get("arguments") != pending["arguments"] or not isinstance(item.get("content"), str):
                raise LiveDispatchDenied("captured tool result does not match prior ordered provider call")
            # Harness/server call IDs are distinct from provider tool-use IDs.
            self._conversation.append({"role": "tool", "tool_call_id": pending["id"], "content": item["content"]})
        self._consumed_history = len(history)
        self._pending_calls = []
        payload = {"provider": self.arm.provider, "model": self.arm.model, "task": public_task(task), "tools": deepcopy(catalog), "history": deepcopy(self._conversation), "max_output_tokens": int(approval.get("max_output_tokens", 1024))}
        response = self.transport(payload)
        self._turns += 1
        self.last_response = response
        if response.get("model") != self.arm.model or response.get("provider") != self.arm.provider:
            raise LiveDispatchDenied("returned provider/model identity drift; retain attempt and stop dispatch")
        calls = response.get("tool_calls", [])
        if not isinstance(calls, list) or self._call_count + len(calls) > 6:
            raise ValueError("provider response tool calls are malformed or exceed cap")
        result = []
        for call in calls:
            if not isinstance(call, dict) or set(call) != {"name", "arguments"} or not isinstance(call["name"], str) or not isinstance(call["arguments"], str):
                raise ValueError("provider call must contain exact name/raw-arguments strings")
            result.append(dict(call))
        ids = response.get("tool_call_ids", [])
        if not isinstance(ids, list) or len(ids) != len(result) or any(not isinstance(value, str) or not value for value in ids) or len(set(ids)) != len(ids):
            raise ValueError("provider tool-call IDs are missing, duplicate or malformed")
        self._pending_calls = [{"id": identifier, **call} for identifier, call in zip(ids, result)]
        self._call_count += len(result)
        self._conversation.append({"role": "assistant", "content": response.get("assistant_content") or "", "tool_calls": deepcopy(self._pending_calls)})
        return result
