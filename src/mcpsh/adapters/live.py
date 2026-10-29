"""Budgeted provider controller, inactive without explicit runtime admission."""

from dataclasses import dataclass
from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any, Callable
from uuid import uuid4

from mcpsh.accounting import BudgetDenied, CostLedger
from .transports import AnthropicMessagesTransport, ProviderTransport, TransportFailure, body_hash, encode_wire


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

    token_counter(encoded_body: bytes) must count all provider overhead/tools/history with
    its approved version. journal(event) persists private request/response bodies
    outside public results; unavailable journal refuses admission. No defaults
    invent model IDs, prices, credentials or permission to send.
    """

    def __init__(self, wire_transport: ProviderTransport, ledger: CostLedger, approval: dict[str, Any], prices: DatedTokenPrices, token_counter: Callable[[bytes], int], journal: Callable[[dict[str, Any]], None]):
        self.wire_transport, self.ledger, self.approval = wire_transport, ledger, dict(approval)
        self.prices, self.token_counter, self.journal = prices, token_counter, journal
        self.attempts: list[dict[str, Any]] = []
        self.last_response: dict[str, Any] | None = None
        self._halt_reason: str | None = None
        self._last_selection_batch: dict[str, Any] | None = None
        self._selection_batch_complete = False

    @property
    def last_selection_batch(self) -> dict[str, Any] | None:
        """Read-only defensive snapshot for D1's failed-codec selection journal."""
        return deepcopy(self._last_selection_batch)

    @property
    def selection_batch_complete(self) -> bool:
        return self._selection_batch_complete

    def _check_approval(self) -> None:
        grant = self.approval
        if self._halt_reason:
            raise LiveTransportError("controller dispatch stopped: " + self._halt_reason)
        if any(grant.get(key) is not True for key in ("authorized", "dirty_mode_closed", "network_allowed")) or grant.get("mode") != "live":
            raise LiveTransportError("live admission/Dirty Mode closure/network authorization required")
        expires_at = grant.get("expires_at")
        if not isinstance(expires_at, str):
            raise LiveTransportError("explicit approval expiry required")
        try:
            expires = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
        except ValueError:
            raise LiveTransportError("invalid approval expiry") from None
        if expires.tzinfo is None or datetime.now(timezone.utc) >= expires:
            raise LiveTransportError("approval expired or has no timezone")
        if grant.get("provider") != self.wire_transport.provider:
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
        if self.ledger.dispatch_count(grant["budget_reservation_id"]) >= cap:
            raise LiveTransportError("model request cap reached")

    def assert_dispatch_allowed(self) -> None:
        """Runner API: check before each model turn; never excludes prior liability."""
        try:
            self._check_approval()
            self.ledger.assert_dispatch_allowed()
        except (BudgetDenied, ValueError) as error:
            raise LiveTransportError("dispatch admission denied: " + type(error).__name__) from None

    def _admit(self, payload: dict[str, Any], *, operation_id: str | None = None,
               prepared_attempt_id: str | None = None) -> tuple[dict[str, Any], int]:
        self._check_approval()
        grant = self.approval
        if payload.get("provider") != grant.get("provider") or payload.get("model") != grant.get("model"):
            raise LiveTransportError("exact provider/model admission mismatch")
        self.ledger.assert_dispatch_allowed(current_operation_id=operation_id,
                                            prepared_attempt_id=prepared_attempt_id)
        max_input = _integer(grant.get("max_input_tokens"), "input token cap", 1)
        max_output = _integer(grant.get("max_output_tokens"), "output token cap", 1)
        if payload.get("max_output_tokens") != max_output:
            raise LiveTransportError("output token bound mismatch")
        wire = self.wire_transport.prepare(payload)
        bind = getattr(self.token_counter, "bind_dispatch_context", None)
        if bind is not None:
            bind(phase="preflight" if prepared_attempt_id is None else "pre-send",
                 attempt_id=prepared_attempt_id, operation_id=operation_id)
        counted = _integer(self.token_counter(encode_wire(wire)), "full encoded wire token count")
        if counted > max_input:
            raise LiveTransportError("complete tool/history request exceeds input token cap")
        maximum = self.prices.maximum(max_input, max_output)
        # Counting may take time or invoke a caller-supplied counter. Recheck after it.
        self._check_approval()
        return wire, maximum

    def __call__(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.last_response = None
        self._last_selection_batch = None
        self._selection_batch_complete = False
        self.assert_dispatch_allowed()
        try:
            wire, maximum_attempt_cost = self._admit(payload)
        except (BudgetDenied, ValueError) as error:
            raise LiveTransportError("request admission denied: " + type(error).__name__) from None
        allow_retry = self.approval.get("allow_one_transient_retry") is True
        operation_id = self.approval["budget_reservation_id"] + ":" + str(uuid4())
        request_hash = body_hash(wire)
        self.ledger.reserve(operation_id, maximum_attempt_cost * (2 if allow_retry else 1), {"price_snapshot_hash": self.prices.snapshot_hash, "provider": payload["provider"], "model": payload["model"], "request_hash": request_hash, "includes_retry": allow_retry})
        for attempt_index in range(2 if allow_retry else 1):
            self._last_selection_batch = None
            self._selection_batch_complete = False
            attempt_id = operation_id + ":attempt-" + str(attempt_index + 1)
            row: dict[str, Any] = {"attempt_id": attempt_id, "request_id": str(uuid4()), "response_id": None, "raw_request_hash": request_hash, "raw_response_hash": None, "provider": payload["provider"], "requested_model": payload["model"], "returned_model": None, "started_at": _now(), "finished_at": None, "status": "admitted", "dispatch_status": "not_started", "usage": {}, "cost_microunits": None, "cost_kind": "unknown", "settlement_reference": attempt_id, "operation_id": operation_id, "price_snapshot_hash": self.prices.snapshot_hash}
            self.ledger.begin_attempt(operation_id, attempt_id, payload["provider"], payload["model"])
            self.attempts.append(row)
            reply = None
            try:
                # Journal before network. Credentials are headers and never enter it.
                self.journal({"event": "request", "attempt": dict(row), "wire_body": deepcopy(wire)})
                # Current reserve/prepared record is legitimate, prior unknown usage is not.
                rechecked, rechecked_cost = self._admit(payload, operation_id=operation_id,
                                                       prepared_attempt_id=attempt_id)
                if body_hash(rechecked) != request_hash or rechecked_cost != maximum_attempt_cost:
                    raise LiveTransportError("approved wire body or maximum price changed before send")
                self.ledger.authorize_dispatch(operation_id, attempt_id,
                    scope=self.approval["budget_reservation_id"],
                    max_requests=self.approval["max_model_requests"])
                row["dispatch_status"] = "transport_entered_delivery_unknown"
                reply = self.wire_transport.send(wire)
                row["dispatch_status"] = "response_received"
                row["raw_response_hash"] = sha256(reply.raw).hexdigest()
                row["provider_request_id"] = reply.request_id
                self.journal({"event": "raw_response", "attempt_id": attempt_id, "raw_response_bytes": reply.raw, "raw_response_hash": row["raw_response_hash"]})
                batch, complete = self.wire_transport.selection_candidates(reply)
                if batch is not None:
                    self._last_selection_batch = {"attempt_id": attempt_id, **deepcopy(batch)}
                    self._selection_batch_complete = complete
                response = self.wire_transport.parse(reply)
                row.update({"response_id": response.get("response_id"), "returned_model": response.get("model"), "usage": response.get("usage") or {}})
                cost = self.prices.estimate(payload["provider"], response)
                self.ledger.settle(attempt_id, cost, row["usage"])
                row.update({"cost_microunits": cost, "cost_kind": "dated-price-estimate" if cost is not None else "unknown", "finished_at": _now(), "status": "completed" if cost is not None else "completed_usage_unknown"})
                if cost is not None and cost > maximum_attempt_cost:
                    row["status"] = "reservation_overrun"
                    raise LiveTransportError("actual usage estimate exceeds approved per-attempt maximum")
                if response.get("provider") != payload["provider"] or response.get("model") != payload["model"]:
                    row["status"] = "identity_drift"
                    raise LiveTransportError("returned provider/model identity drift; dispatch stopped")
                if response.get("stop_reason") in {"length", "max_tokens", "content_filter"}:
                    row["status"] = "truncated_or_filtered"
                    raise LiveTransportError("provider response truncated/filtered; no semantic retry")
                if not self._selection_batch_complete:
                    row["status"] = "selection_capture_incomplete"
                    raise LiveTransportError("candidate capture incomplete; raw response remains private evidence")
                response.update({"attempt_id": attempt_id, "raw_response_hash": row["raw_response_hash"], "raw_request_hash": request_hash, "cost_microunits": cost, "cost_kind": row["cost_kind"], "settlement_reference": attempt_id})
                self.last_response = response
                self.journal({"event": "settled", "attempt": dict(row)})
                # A previous unknown retry attempt must keep the whole reserve.
                pending = [item for item in self.attempts if item["operation_id"] == operation_id and item["cost_microunits"] is None]
                if not pending:
                    self.ledger.finish(operation_id)
                else:
                    self._halt_reason = "usage_unknown"
                    self.ledger.halt_dispatch("usage_unknown")
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
                    # A failed HTTP response may explicitly report attributable usage.
                    # A timeout, absent usage or malformed body never means zero cost.
                    failed_usage = None
                    if isinstance(error, TransportFailure) and reply is not None:
                        failed_usage = self.wire_transport.failure_usage(reply, payload["model"])
                    cost = self.prices.estimate(payload["provider"], failed_usage) if failed_usage else None
                    if failed_usage:
                        row["usage"] = failed_usage["usage"]
                    self.ledger.settle(attempt_id, cost, row["usage"])
                    row["cost_microunits"] = cost
                    row["cost_kind"] = "dated-price-estimate" if cost is not None else "unknown"
                    row.update({"status": error.category if isinstance(error, TransportFailure) else "invalid_or_failed_response", "finished_at": _now()})
                # Journal exceptions must never trigger unrecorded provider retries.
                self.journal({"event": "failed", "attempt": dict(row), "raw_response_bytes": reply.raw if reply else None})
                if (isinstance(error, TransportFailure) and error.transient and allow_retry
                        and attempt_index == 0 and row["cost_microunits"] is not None
                        and row["cost_microunits"] <= maximum_attempt_cost):
                    reason = "rate_limit" if error.category == "rate_limit" else "transient_transport"
                    self.ledger.allow_transport_retry(attempt_id, reason)
                    continue
                self._halt_reason = row["status"]
                self.ledger.halt_dispatch(row["status"])
                if isinstance(error, (KeyboardInterrupt, SystemExit)):
                    raise
                raise LiveTransportError("provider attempt failed; preserved cost/usage status: " + row["status"]) from None
        raise LiveTransportError("transient retry allowance exhausted")

    def cost_summary(self) -> dict[str, Any]:
        return self.ledger.summary()
