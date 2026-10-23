"""Regression SOURCE; authored under Dirty Mode and deliberately not executed."""

from copy import deepcopy
import json

import pytest

from mcpsh.accounting import CostLedger
from mcpsh.adapters.live import BudgetedLiveTransport, DatedTokenPrices, LiveTransportError
from mcpsh.adapters.transports import HTTPReply, ProviderTransport, TransportFailure


class ScriptedWire(ProviderTransport):
    provider = "openai"

    def __init__(self, script):
        super().__init__(lambda: "fake-not-a-key", "https://example.invalid/never-send",
                         network_enabled=True)
        self.provider = "openai"
        self.script, self.sent = list(script), []

    def prepare(self, payload):
        return deepcopy(payload)

    def send(self, wire):
        self.sent.append(deepcopy(wire))
        event = self.script.pop(0)
        if callable(event):
            event = event()
        if isinstance(event, BaseException):
            raise event
        return HTTPReply(200, json.dumps(event).encode(), "fake-request")

    def parse(self, reply):
        return json.loads(reply.raw)

    def selection_candidates(self, reply):
        value = json.loads(reply.raw)
        if isinstance(value, dict) and "provider" in value and isinstance(value.get("tool_calls"), list):
            return {"tool_calls": deepcopy(value["tool_calls"]),
                    "tool_call_ids": deepcopy(value.get("tool_call_ids", []))}, True
        return super().selection_candidates(reply)


def response(*, known=True, model="model-v1"):
    return {"provider": "openai", "model": model, "usage": {},
            "input_tokens": 2 if known else None, "output_tokens": 1 if known else None,
            "tool_calls": [], "tool_call_ids": [], "response_id": "fake-response"}


def explicit_transient_usage():
    body = {"model": "model-v1", "usage": {"prompt_tokens": 2, "completion_tokens": 0}}
    return TransportFailure("rate_limit", transient=True,
                            reply=HTTPReply(429, json.dumps(body).encode(), "fake-rate-limit"))


def make_controller(tmp_path, script, *, cap=3, retry=True, ledger=None, journal=None):
    wire = ScriptedWire(script)
    grant = {"authorized": True, "dirty_mode_closed": True, "network_allowed": True,
             "mode": "live", "provider": "openai", "family": "family-a", "model": "model-v1",
             "expires_at": "2999-01-01T00:00:00+00:00", "budget_reservation_id": "trial-a",
             "corpus_seal_hash": "a" * 64, "price_snapshot_hash": "b" * 64,
             "token_counter_version": "fake-v1", "endpoint_url": wire.endpoint_url,
             "max_model_requests": cap, "max_input_tokens": 20, "max_output_tokens": 10,
             "allow_one_transient_retry": retry}
    ledger = ledger or CostLedger(tmp_path / "cost.sqlite", 1000)
    prices = DatedTokenPrices("b" * 64, "2026-10-23", 1000000, 1000000)
    controller = BudgetedLiveTransport(wire, ledger, grant, prices, lambda body: 5,
                                        journal or (lambda event: None))
    payload = {"provider": "openai", "model": "model-v1", "max_output_tokens": 10,
               "task": {}, "tools": [], "history": []}
    return controller, wire, payload


def test_current_prepared_reservation_does_not_block_first_send(tmp_path):
    """what_bug_this_catches: counting our own prepared NULL cost as prior liability."""
    controller, wire, payload = make_controller(tmp_path, [response()])
    controller(payload)
    assert len(wire.sent) == 1
    assert controller.ledger.summary()["unknown_attempts"] == 0
    controller.assert_dispatch_allowed()


def test_retry_consumes_actual_request_cap(tmp_path):
    """what_bug_this_catches: a cap of one permitting a second physical HTTP send."""
    controller, wire, payload = make_controller(tmp_path, [explicit_transient_usage(), response()], cap=1)
    with pytest.raises(LiveTransportError):
        controller(payload)
    assert len(wire.sent) == 1
    assert controller.ledger.dispatch_count("trial-a") == 1


def test_expiry_is_rechecked_between_transient_attempts(tmp_path):
    """what_bug_this_catches: retry after the approved receipt expired during attempt one."""
    controller, wire, payload = make_controller(tmp_path, [])

    def expire_then_fail():
        controller.approval["expires_at"] = "2000-01-01T00:00:00+00:00"
        return explicit_transient_usage()

    wire.script = [expire_then_fail, response()]
    with pytest.raises(LiveTransportError):
        controller(payload)
    assert len(wire.sent) == 1


def test_known_transient_retry_is_recorded_and_bounded(tmp_path):
    """what_bug_this_catches: removing legitimate known-usage transient retry support."""
    controller, wire, payload = make_controller(tmp_path, [explicit_transient_usage(), response()])
    controller(payload)
    assert len(wire.sent) == 2
    assert controller.ledger.dispatch_count("trial-a") == 2
    assert len(controller.attempts) == 2
    assert controller.ledger.summary()["settled_microunits"] == 5


def test_unknown_success_blocks_next_turn_and_new_controller(tmp_path):
    """what_bug_this_catches: a fresh selector/controller bypassing an unknown-cost hold."""
    controller, wire, payload = make_controller(tmp_path, [response(known=False), response()])
    controller(payload)
    with pytest.raises(LiveTransportError):
        controller.assert_dispatch_allowed()
    restarted, restarted_wire, payload = make_controller(
        tmp_path, [response()], ledger=CostLedger(tmp_path / "cost.sqlite", 1000))
    with pytest.raises(LiveTransportError):
        restarted(payload)
    assert len(wire.sent) == 1
    assert not restarted_wire.sent
    assert restarted.ledger.summary()["committed_microunits"] == 60


def test_timeout_without_usage_never_spends_retry(tmp_path):
    """what_bug_this_catches: assuming timeout or HTTP error means zero billable usage."""
    controller, wire, payload = make_controller(
        tmp_path, [TransportFailure("transient_transport", transient=True), response()])
    with pytest.raises(LiveTransportError):
        controller(payload)
    assert len(wire.sent) == 1
    assert controller.ledger.summary()["unknown_attempts"] == 1


@pytest.mark.parametrize("change", ["identity", "price", "token", "authorization"])
def test_mutations_after_request_journal_are_checked_before_send(tmp_path, change):
    """what_bug_this_catches: treating pre-reservation admission as an actual-send grant."""
    controller, wire, payload = make_controller(tmp_path, [response()])

    def mutate(event):
        if event["event"] != "request":
            return
        if change == "identity":
            controller.approval["model"] = "another-model"
        elif change == "price":
            controller.approval["price_snapshot_hash"] = "c" * 64
        elif change == "token":
            controller.token_counter = lambda body: 999
        else:
            controller.approval["authorized"] = False

    controller.journal = mutate
    with pytest.raises(LiveTransportError):
        controller(payload)
    assert not wire.sent


def test_identity_drift_is_not_semantically_retried(tmp_path):
    """what_bug_this_catches: retrying away an unfavorable returned-model mismatch."""
    controller, wire, payload = make_controller(tmp_path, [response(model="wrong-model"), response()])
    with pytest.raises(LiveTransportError):
        controller(payload)
    assert len(wire.sent) == 1
    assert controller.attempts[0]["status"] == "identity_drift"


def test_failed_codec_retains_all_candidates_and_snapshot_resets(tmp_path):
    """what_bug_this_catches: failed codec dropping seven selections or leaking a stale batch."""
    document = {"choices": [{"message": {"tool_calls": [
        {"id": f"p-{number}", "type": "function", "function": {"name": "export_fixture", "arguments": "{}"}}
        for number in range(7)]}}]}
    controller, wire, payload = make_controller(tmp_path, [document])
    def invalid_codec(reply):
        raise ValueError("synthetic codec rejection")
    wire.parse = invalid_codec
    with pytest.raises(LiveTransportError):
        controller(payload)
    batch = controller.last_selection_batch
    assert len(batch["tool_calls"]) == 7 and controller.selection_batch_complete
    batch["tool_calls"].clear()
    assert len(controller.last_selection_batch["tool_calls"]) == 7
    with pytest.raises(AttributeError):
        controller.last_selection_batch = {}
    with pytest.raises(LiveTransportError):
        controller(payload)
    assert controller.last_selection_batch is None and not controller.selection_batch_complete


def test_preview_uses_actual_encoder_without_credentials():
    """what_bug_this_catches: catalog audits/token fit inspecting a second abstract request builder."""
    from mcpsh.adapters.transports import OpenAIChatTransport, encode_wire
    def forbidden_credential():
        raise AssertionError("preview must never inspect credentials")
    wire = OpenAIChatTransport(credential=forbidden_credential)
    payload = {"provider": "openai", "model": "fake-model", "max_output_tokens": 10,
               "task": {"user_request": "synthetic α"}, "tools": [], "history": []}
    preview = wire.preview_request(payload, adapter_sha256="a" * 64)
    assert preview["encoded_body"] == encode_wire(wire.prepare(payload))
    assert preview["model_id"] == "fake-model" and preview["provider"] == "openai"
    assert preview["adapter_revision"] == "mcpsh-http-tools-v2"
    assert "Authorization" not in preview


def test_counter_receives_same_encoded_body_as_send(tmp_path):
    """what_bug_this_catches: a token counter omitting tools/history/provider encoding overhead."""
    from mcpsh.adapters.transports import encode_wire
    controller, wire, payload = make_controller(tmp_path, [response()])
    counted = []
    def counter(body):
        assert isinstance(body, bytes)
        counted.append(body)
        return 5
    controller.token_counter = counter
    controller(payload)
    assert counted and all(body == encode_wire(wire.sent[0]) for body in counted)
