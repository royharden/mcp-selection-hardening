"""Fit-lineage regression SOURCE only; fake counters, no current execution."""

from copy import deepcopy
import hashlib
import json
from types import SimpleNamespace as NS

import pytest

from mcpsh.adapters.transports import ADAPTER_REVISION, OpenAIChatTransport, encode_wire
from mcpsh.catalog.artifacts import build_catalog_artifact
from mcpsh.catalog.provider_contract import audit_provider_catalog
from mcpsh.catalog.token_fit import APPROVAL_VERSION, COUNTER_SCOPE, build_token_fit_proof
from mcpsh.evidence.token_fit import capture_token_fit_bundle, verify_token_fit_lineage
from mcpsh.records import typed_hash


def sample():
    artifact = build_catalog_artifact()
    preview = OpenAIChatTransport(credential=lambda: (_ for _ in ()).throw(
        AssertionError("no credentials"))).preview_request({"provider": "openai", "model": "fake",
        "task": {"user_request": "List sources"}, "tools": artifact["catalog"],
        "history": [], "max_output_tokens": 10}, adapter_sha256="a" * 64)
    body = preview["encoded_body"]
    audit = audit_provider_catalog(artifact, body, provider="openai", model_id="fake",
        adapter_revision=ADAPTER_REVISION, adapter_sha256="a" * 64)
    approval = {"version": APPROVAL_VERSION, "approval_id": "fake-approval", "authorized": True,
        "provider": "openai", "model_id": "fake", "adapter_revision": ADAPTER_REVISION,
        "adapter_sha256": "a" * 64, "tokenizer_id": "explicit-fake", "tokenizer_sha256": "b" * 64,
        "counter_scope": COUNTER_SCOPE, "input_token_cap": 100, "output_token_cap": 10,
        "context_window_cap": 200, "settings_sha256": audit["settings_sha256"],
        "catalog_typed_sha256": audit["catalog_pins"]["typed_sha256"],
        "expires_at": "2027-01-01T00:00:00Z", "max_proof_age_seconds": 30}
    args = dict(artifact=artifact, provider="openai", model_id="fake", adapter_revision=ADAPTER_REVISION,
        adapter_sha256="a" * 64, approval=approval, expected_approval_sha256=typed_hash(approval),
        trial_id="trial", turn_id=1, at_time="2026-10-23T00:00:00Z")
    proof = build_token_fit_proof(body, tokenizer=lambda raw: 3, **args)
    digest = hashlib.sha256(body).hexdigest()
    expected = {key: value for key, value in args.items() if key != "at_time"}
    expected.update(checked_at=args["at_time"], attempt_id="attempt", operation_id="op",
        proof_sha256=proof["proof_sha256"], raw_request_sha256=digest)
    events = [{"event": "request", "attempt": {"attempt_id": "attempt", "operation_id": "op",
        "raw_request_hash": digest}, "wire_body": json.loads(body)},
        {"event": "token_fit_proof", "trial_id": "trial", "turn_id": 1, "proof": proof,
        "proof_sha256": proof["proof_sha256"], "phase": "pre-send", "attempt_id": "attempt",
        "operation_id": "op", "checked_at": args["at_time"], "raw_request_sha256": digest}]
    return capture_token_fit_bundle(events, expectations=[expected])


def edition(bundle, *, pin=True, retry=False):
    # Synthetic structural parent stub: real edition.validate is independently covered.
    attempts = [NS(attempt_id="attempt", trial_id="trial", turn_id=1,
                   provider_id="openai", requested_model_id="fake")]
    if retry:
        attempts.append(NS(attempt_id="retry", trial_id="trial", turn_id=1,
                           provider_id="openai", requested_model_id="fake"))
    trial = NS(outcome=NS(trial_id="trial"), reuse=None, model_attempts=attempts,
        accounting=[NS(attempt_id=a.attempt_id, operation_id="op", raw_request_sha256=None) for a in attempts])
    return NS(validate=lambda: (NS(mode="live", scheduled_trial_ids=("trial",), fit_reverification=None), None, [trial], (), None),
        artifacts=(("token_fit", json.dumps(bundle).encode()),),
        authority=NS(token_fit_expectations_sha256=typed_hash(bundle["expectations"]) if pin else None))


def test_valid_external_fit_is_never_spending_or_billing_authority():
    # what_bug_this_catches: diagnostic False mistaken for paid admission / billing truth.
    report = verify_token_fit_lineage(edition(sample()))
    assert report["complete"] is True
    assert report["attempts"][0]["state"] == "verified-fit-only"
    assert report["live_admission"] is report["billing_verified"] is False


@pytest.mark.parametrize("mutation", ["missing", "duplicate", "legacy", "body", "trial", "turn",
    "operation", "proof-pin", "approval-pin", "counter", "expired", "stale", "order", "unbound"])
def test_malformed_stale_unattributed_and_wrong_parent_proofs_do_not_fit(mutation):
    # what_bug_this_catches: raw proofs silently dropped or attributed to the wrong retry.
    bundle = sample()
    event, expected = bundle["events"][0], bundle["expectations"][0]
    if mutation == "missing": bundle["events"] = []
    elif mutation == "duplicate": bundle["events"].append(deepcopy(event))
    elif mutation == "legacy": event["phase"] = None
    elif mutation == "body": bundle["requests"][0]["wire_body"]["messages"].append({"role": "user", "content": "changed"})
    elif mutation == "trial": event["trial_id"] = "other"
    elif mutation == "turn": event["turn_id"] = 2
    elif mutation == "operation": event["operation_id"] = "other"
    elif mutation == "proof-pin": expected["proof_sha256"] = "c" * 64
    elif mutation == "approval-pin": expected["expected_approval_sha256"] = "c" * 64
    elif mutation == "counter":
        expected["approval"]["tokenizer_id"] = "different-counter"
        expected["expected_approval_sha256"] = typed_hash(expected["approval"])
    elif mutation in {"expired", "stale"}:
        event["checked_at"] = expected["checked_at"] = ("2028-01-01T00:00:00Z" if mutation == "expired" else "2026-10-23T00:01:00Z")
    elif mutation == "order": event["journal_sequence"] = 1
    elif mutation == "unbound":
        extra = deepcopy(event); extra["attempt_id"] = "orphan"; bundle["events"].append(extra)
    report = verify_token_fit_lineage(edition(bundle))
    assert report["complete"] is False
    assert len(report["attempts"]) == 1


def test_current_proof_never_covers_retry_or_self_authorizes():
    # what_bug_this_catches: trial+turn-only lookup making one proof cover two sends.
    report = verify_token_fit_lineage(edition(sample(), retry=True))
    assert [r["state"] for r in report["attempts"]] == ["verified-fit-only", "unknown"]
    assert verify_token_fit_lineage(edition(sample(), pin=False))["complete"] is False


def test_capture_and_serialization_preserve_exact_wire_order():
    # what_bug_this_catches: generic sorted edition encoder mutating paid HTTP bytes.
    bundle = sample()
    body = encode_wire(bundle["requests"][0]["wire_body"])
    assert hashlib.sha256(body).hexdigest() == bundle["requests"][0]["raw_request_sha256"]
    assert encode_wire(json.loads(json.dumps(bundle))["requests"][0]["wire_body"]) == body


def test_rehashed_mutation_cannot_replace_external_pin():
    # what_bug_this_catches: proof field copied into expected_proof_sha256 as authority.
    bundle = sample()
    bundle["events"][0]["proof"]["input_tokens"] = 1
    assert verify_token_fit_lineage(edition(bundle))["complete"] is False
