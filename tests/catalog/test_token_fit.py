"""Full-wire proof regressions with explicit fake counters; authored, never run.

These synthetic counter receipts are test doubles, not provider tokenization.
D7 actual pure-preview supplies bytes. No test-side request encoder is added.
"""

from copy import deepcopy
import json

from mcpsh.adapters.transports import ADAPTER_REVISION, OpenAIChatTransport
from mcpsh.catalog.artifacts import build_catalog_artifact
from mcpsh.catalog.provider_contract import audit_provider_catalog
from mcpsh.catalog.token_fit import (
    APPROVAL_VERSION, COUNTER_SCOPE, build_token_fit_proof, verify_token_fit_proof,
)
from mcpsh.records.hashing import raw_hash, typed_hash


def setup():
    def forbidden_credential():
        raise AssertionError("proof source test accessed credentials")

    artifact = build_catalog_artifact()
    payload = {"provider": "openai", "model": "synthetic-model", "task": {"user_request": "Inspect diagnostics"},
               "tools": artifact["catalog"], "history": [], "max_output_tokens": 64}
    preview = OpenAIChatTransport(credential=forbidden_credential).preview_request(
        payload, adapter_sha256="a" * 64)
    body = preview["encoded_body"]
    audit = audit_provider_catalog(artifact, body, provider="openai", model_id="synthetic-model",
                                   adapter_revision=ADAPTER_REVISION, adapter_sha256="a" * 64)
    approval = {
        "version": APPROVAL_VERSION, "approval_id": "synthetic-counter-approval",
        "authorized": True, "provider": "openai", "model_id": "synthetic-model",
        "adapter_revision": ADAPTER_REVISION, "adapter_sha256": "a" * 64,
        "tokenizer_id": "fake-counter-for-source-tests-only", "tokenizer_sha256": "b" * 64,
        "counter_scope": COUNTER_SCOPE, "input_token_cap": 10, "output_token_cap": 64,
        "context_window_cap": 100, "settings_sha256": audit["settings_sha256"],
        "catalog_typed_sha256": audit["catalog_pins"]["typed_sha256"],
        "expires_at": "2027-01-01T00:00:00Z", "max_proof_age_seconds": 30,
    }
    args = {"artifact": artifact, "provider": "openai", "model_id": "synthetic-model",
            "adapter_revision": ADAPTER_REVISION, "adapter_sha256": "a" * 64,
            "approval": approval, "expected_approval_sha256": typed_hash(approval),
            "trial_id": "public-synthetic-trial", "turn_id": 1,
            "at_time": "2026-10-23T00:00:00Z"}
    return body, args


def counter(approval, value=3):
    def count(exact_body):
        assert isinstance(exact_body, bytes)
        return value
    return count


def verify(proof, body, args, journal_pin):
    return verify_token_fit_proof(proof, body, expected_proof_sha256=journal_pin, **args)


def test_exact_body_proof_retains_identity_and_never_grants_dispatch():
    # what_bug_this_catches: abstract request counts promoted into provider admission.
    body, args = setup()
    received = []
    def exact_counter(raw):
        assert raw is body
        received.append(raw)
        return 3  # Explicit synthetic test double, not provider tokenization.
    proof = build_token_fit_proof(body, tokenizer=exact_counter, **args)
    assert received == [body]
    assert proof["status"] == "fits"
    assert proof["bindings"]["raw_body_sha256"] == raw_hash(body)
    assert proof["live_admission"] is False
    assert proof["provider_billing_tokens"] == "unverified"
    journal_pin = proof["proof_sha256"]  # Captured from trusted fresh-counter path.
    assert verify(proof, body, args, journal_pin)["fits"] is True


def test_missing_or_unrepresentable_counter_never_becomes_zero_tokens():
    # what_bug_this_catches: missing/boolean count treated as free budget headroom.
    body, args = setup()
    for callback in (None, counter(args["approval"], True), counter(args["approval"], 0),
                     lambda body: {"input_tokens": 3}):
        proof = build_token_fit_proof(body, tokenizer=callback, **args)
        assert proof["status"] == "unknown"
        assert proof["input_tokens"] is None
        assert verify(proof, body, args, proof["proof_sha256"])["valid"] is False


def test_changed_history_and_turn_cannot_reuse_old_fit_proof():
    # what_bug_this_catches: initial catalog-only count reused after tool replies grow.
    body, args = setup()
    proof = build_token_fit_proof(body, tokenizer=counter(args["approval"]), **args)
    journal_pin = proof["proof_sha256"]
    changed = json.loads(body)
    changed["messages"].append({"role": "tool", "tool_call_id": "public-id", "content": "x" * 200})
    assert verify(proof, json.dumps(changed).encode(), args, journal_pin)["valid"] is False
    turn_two = {**args, "turn_id": 2}
    assert verify(proof, body, turn_two, journal_pin)["valid"] is False


def test_unpinned_approval_prevents_counter_callback():
    # what_bug_this_catches: a caller-authored receipt becoming its own authority.
    body, args = setup()
    bad = {**args, "expected_approval_sha256": "c" * 64}
    def forbidden(body):
        raise AssertionError("counter must not execute for unapproved bindings")
    proof = build_token_fit_proof(body, tokenizer=forbidden, **bad)
    assert proof["status"] == "invalid"


def test_input_and_reserved_output_context_limits_both_apply():
    # what_bug_this_catches: input-only proof ignoring reserved model output context.
    body, args = setup()
    assert build_token_fit_proof(body, tokenizer=counter(args["approval"], 11), **args)["status"] == "exceeds"
    approval = {**args["approval"], "context_window_cap": 65}
    adjusted = {**args, "approval": approval, "expected_approval_sha256": typed_hash(approval)}
    assert build_token_fit_proof(body, tokenizer=counter(approval, 3), **adjusted)["status"] == "exceeds"


def test_stale_mutated_or_unpinned_proof_is_rejected():
    # what_bug_this_catches: expired/modified serialized fit receipts reused at send.
    body, args = setup()
    proof = build_token_fit_proof(body, tokenizer=counter(args["approval"]), **args)
    journal_pin = proof["proof_sha256"]
    assert verify(proof, body, {**args, "at_time": "2026-10-23T00:01:00Z"}, journal_pin)["valid"] is False
    changed = deepcopy(proof)
    changed["input_tokens"] = 0
    changed["counter_receipt"]["input_tokens"] = 0
    changed["proof_sha256"] = typed_hash({k: v for k, v in changed.items() if k != "proof_sha256"})
    assert verify(changed, body, args, journal_pin)["valid"] is False
    assert verify_token_fit_proof(proof, body, expected_proof_sha256="c" * 64, **args)["valid"] is False
