"""Budgeted provider controller, inactive without explicit runtime admission."""

from dataclasses import dataclass
from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any, Callable
from uuid import uuid4

from mcpsh.accounting import CostLedger
from .transports import AnthropicMessagesTransport, ProviderTransport, TransportFailure, body_hash


def _integer(value: Any, label: str, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        raise ValueError(label + " must be an integer within the approved bound")
    return value


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class DatedTokenPrices:
    snapshot_hash: str
    dated_at: str
    input_microunits_per_million: int
    output_microunits_per_million: int
    cached_read_microunits_per_million: int | None = None
    cache_creation_microunits_per_million: int | None = None

    def maximum(self, input_tokens: int, output_tokens: int) -> int:
        rates = [self.input_microunits_per_million]
        rates += [rate for rate in (self.cached_read_microunits_per_million, self.cache_creation_microunits_per_million) if rate is not None]
        for rate in rates + [self.output_microunits_per_million]:
            _integer(rate, "price")
        return (input_tokens * max(rates) + output_tokens * self.output_microunits_per_million + 999999) // 1000000

    def estimate(self, provider: str, response: dict[str, Any]) -> int | None:
        """Dated token-price estimate, explicitly not a provider billing receipt."""
        usage = response.get("usage") or {}
        input_tokens, output_tokens = response.get("input_tokens"), response.get("output_tokens")
        if type(input_tokens) is not int or type(output_tokens) is not int or min(input_tokens, output_tokens) < 0:
            return None
        cached, created = 0, 0
        if provider == "openai":
            cached = (usage.get("prompt_tokens_details") or {}).get("cached_tokens", 0)
            if type(cached) is not int or cached < 0 or cached > input_tokens:
                return None
            input_tokens -= cached
        elif provider == "anthropic":
            cached = usage.get("cache_read_input_tokens", 0)
            created = usage.get("cache_creation_input_tokens", 0)
        if type(cached) is not int or type(created) is not int or min(cached, created) < 0:
            return None
        if cached and self.cached_read_microunits_per_million is None:
            return None
        if created and self.cache_creation_microunits_per_million is None:
            return None
        value = input_tokens * self.input_microunits_per_million + output_tokens * self.output_microunits_per_million
        value += cached * (self.cached_read_microunits_per_million or 0)
        value += created * (self.cache_creation_microunits_per_million or 0)
        return (value + 999999) // 1000000


class LiveTransportError(RuntimeError):
    """A failed scheduled request remains in attempts; raw data stay private."""


class BudgetedLiveTransport:
    """Callable normalized transport consumed by LiveSelector.

    token_counter(wire_body) must count all provider overhead/tools/history with
    its approved version. journal(event) persists private request/response bodies
    outside public results; unavailable journal refuses admission. No defaults
    invent model IDs, prices, credentials or permission to send.
    """

    def __init__(self, wire_transport: ProviderTransport, ledger: CostLedger, approval: dict[str, Any], prices: DatedTokenPrices, token_counter: Callable[[dict[str, Any]], int], journal: Callable[[dict[str, Any]], None]):
        self.wire_transport, self.ledger, self.approval = wire_transport, ledger, dict(approval)
        self.prices, self.token_counter, self.journal = prices, token_counter, journal
        self.attempts: list[dict[str, Any]] = []
        self.last_response: dict[str, Any] | None = None
        self._requests = 0

    def _admit(self, payload: dict[str, Any]) -> tuple[dict[str, Any], int]:
        grant = self.approval
        if any(grant.get(key) is not True for key in ("authorized", "dirty_mode_closed", "network_allowed")) or grant.get("mode") != "live":
            raise LiveTransportError("live admission/Dirty Mode closure/network authorization required")
        if grant.get("provider") != self.wire_transport.provider or payload.get("provider") != grant.get("provider") or payload.get("model") != grant.get("model"):
            raise LiveTransportError("exact provider/model admission mismatch")
        if not all(grant.get(key) for key in ("family", "model", "budget_reservation_id", "corpus_seal_hash", "price_snapshot_hash", "token_counter_version")):
            raise LiveTransportError("incomplete live approval")
        if grant["price_snapshot_hash"] != self.prices.snapshot_hash or not self.prices.dated_at:
            raise LiveTransportError("dated price snapshot mismatch")
        if grant.get("endpoint_url") != self.wire_transport.endpoint_url or not self.wire_transport.network_enabled:
            raise LiveTransportError("approved endpoint/network transport mismatch")
        if isinstance(self.wire_transport, AnthropicMessagesTransport) and (not self.wire_transport.api_version or grant.get("api_version") != self.wire_transport.api_version):
            raise LiveTransportError("approved Anthropic API version mismatch")
        cap = _integer(grant.get("max_model_requests"), "model request cap", 1)
        if self._requests >= cap:
            raise LiveTransportError("model request cap reached")
        max_input = _integer(grant.get("max_input_tokens"), "input token cap", 1)
        max_output = _integer(grant.get("max_output_tokens"), "output token cap", 1)
        if payload.get("max_output_tokens") != max_output:
            raise LiveTransportError("output token bound mismatch")
        wire = self.wire_transport.prepare(payload)
        counted = _integer(self.token_counter(wire), "full wire token count")
        if counted > max_input:
            raise LiveTransportError("complete tool/history request exceeds input token cap")
        return wire, self.prices.maximum(max_input, max_output)

    def __call__(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.last_response = None
        wire, maximum_attempt_cost = self._admit(payload)
        allow_retry = self.approval.get("allow_one_transient_retry") is True
        operation_id = self.approval["budget_reservation_id"] + ":" + str(uuid4())
        request_hash = body_hash(wire)
        self.ledger.reserve(operation_id, maximum_attempt_cost * (2 if allow_retry else 1), {"price_snapshot_hash": self.prices.snapshot_hash, "provider": payload["provider"], "model": payload["model"], "request_hash": request_hash, "includes_retry": allow_retry})
        self._requests += 1
        for attempt_index in range(2 if allow_retry else 1):
            attempt_id = operation_id + ":attempt-" + str(attempt_index + 1)
            row: dict[str, Any] = {"attempt_id": attempt_id, "request_id": str(uuid4()), "response_id": None, "raw_request_hash": request_hash, "raw_response_hash": None, "provider": payload["provider"], "requested_model": payload["model"], "returned_model": None, "started_at": _now(), "finished_at": None, "status": "admitted", "dispatch_status": "not_started", "usage": {}, "cost_microunits": None, "cost_kind": "unknown", "settlement_reference": attempt_id, "operation_id": operation_id, "price_snapshot_hash": self.prices.snapshot_hash}
            self.ledger.begin_attempt(operation_id, attempt_id, payload["provider"], payload["model"])
            self.attempts.append(row)
            reply = None
            try:
                # Journal before network. Credentials are headers and never enter it.
                self.journal({"event": "request", "attempt": dict(row), "wire_body": deepcopy(wire)})
                row["dispatch_status"] = "transport_entered_delivery_unknown"
                reply = self.wire_transport.send(wire)
                row["dispatch_status"] = "response_received"
                row["raw_response_hash"] = sha256(reply.raw).hexdigest()
                row["provider_request_id"] = reply.request_id
                self.journal({"event": "raw_response", "attempt_id": attempt_id, "raw_response_bytes": reply.raw, "raw_response_hash": row["raw_response_hash"]})
                response = self.wire_transport.parse(reply)
                row.update({"response_id": response.get("response_id"), "returned_model": response.get("model"), "usage": response.get("usage") or {}})
                cost = self.prices.estimate(payload["provider"], response)
                self.ledger.settle(attempt_id, cost, row["usage"])
                row.update({"cost_microunits": cost, "cost_kind": "dated-price-estimate" if cost is not None else "unknown", "finished_at": _now(), "status": "completed" if cost is not None else "completed_usage_unknown"})
                if response.get("provider") != payload["provider"] or response.get("model") != payload["model"]:
                    row["status"] = "identity_drift"
                    raise LiveTransportError("returned provider/model identity drift; dispatch stopped")
                if response.get("stop_reason") in {"length", "max_tokens", "content_filter"}:
                    row["status"] = "truncated_or_filtered"
                    raise LiveTransportError("provider response truncated/filtered; no semantic retry")
                response.update({"attempt_id": attempt_id, "raw_response_hash": row["raw_response_hash"], "raw_request_hash": request_hash, "cost_microunits": cost, "cost_kind": row["cost_kind"], "settlement_reference": attempt_id})
                self.last_response = response
                self.journal({"event": "settled", "attempt": dict(row)})
                # A previous unknown retry attempt must keep the whole reserve.
                pending = [item for item in self.attempts if item["operation_id"] == operation_id and item["cost_microunits"] is None]
                if not pending:
                    self.ledger.finish(operation_id)
                return response
            except BaseException as error:
                if isinstance(error, TransportFailure) and error.reply is not None:
                    reply = error.reply
                    row["dispatch_status"] = "response_received"
                elif isinstance(error, TransportFailure) and error.category in {"network_disabled", "invalid_approved_endpoint", "credential_unavailable", "approved_api_version_required"}:
                    row["dispatch_status"] = "not_sent"
                if reply is not None:
                    row["raw_response_hash"] = sha256(reply.raw).hexdigest()
                if row["finished_at"] is None:
                    self.ledger.settle(attempt_id, None, row["usage"])
                    row.update({"status": error.category if isinstance(error, TransportFailure) else "invalid_or_failed_response", "finished_at": _now()})
                # Journal exceptions must never trigger unrecorded provider retries.
                self.journal({"event": "failed", "attempt": dict(row), "raw_response_bytes": reply.raw if reply else None})
                if isinstance(error, TransportFailure) and error.transient and allow_retry and attempt_index == 0:
                    reason = "rate_limit" if error.category == "rate_limit" else "transient_transport"
                    self.ledger.allow_transport_retry(attempt_id, reason)
                    continue
                if isinstance(error, (KeyboardInterrupt, SystemExit)):
                    raise
                raise LiveTransportError("provider attempt failed; preserved cost/usage status: " + row["status"]) from None
        raise LiveTransportError("transient retry allowance exhausted")

    def cost_summary(self) -> dict[str, Any]:
        return self.ledger.summary()
