"""Full-wire input-fit proofs from externally approved counters, never estimates.

No default tokenizer, provider SDK, credential callback or request encoder.
This module supplies one admission predicate, never spend/network authorization.
"""

from copy import deepcopy
from datetime import datetime
import re
from typing import Any, Callable

from mcpsh.catalog.provider_contract import audit_provider_catalog, decode_wire_body
from mcpsh.records.hashing import canonical_json, typed_hash

PROOF_VERSION = "m5-full-wire-token-fit-1"
APPROVAL_VERSION = "m5-token-fit-approval-1"
COUNTER_SCOPE = "full-provider-request-including-overhead"
MAX_PROOF_BYTES = 32_768
APPROVAL_FIELDS = {
    "version", "approval_id", "authorized", "provider", "model_id", "adapter_revision",
    "adapter_sha256", "tokenizer_id", "tokenizer_sha256", "counter_scope",
    "input_token_cap", "output_token_cap", "context_window_cap", "settings_sha256",
    "catalog_typed_sha256", "expires_at", "max_proof_age_seconds",
}
COUNTER_FIELDS = {"input_tokens", "raw_body_sha256", "tokenizer_id", "tokenizer_sha256",
                  "model_id", "counter_scope", "exact"}
PROOF_FIELDS = {"version", "status", "reasons", "live_admission", "provider_billing_tokens",
                "created_at", "bindings", "counter_receipt", "input_tokens", "proof_sha256", "scope"}


def _digest(value: Any) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _time(value: str) -> datetime:
    if not isinstance(value, str) or len(value) > 64:
        raise ValueError("explicit timestamp required")
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("timestamp timezone required")
    return result


def _bindings(encoded_body: bytes, *, artifact: dict[str, Any], provider: str,
              model_id: str, adapter_revision: str, adapter_sha256: str,
              approval: dict[str, Any], expected_approval_sha256: str,
              trial_id: str, turn_id: int, at_time: str) -> tuple[dict[str, Any], dict[str, Any]]:
    if (not isinstance(approval, dict) or set(approval) != APPROVAL_FIELDS
            or len(canonical_json(approval).encode("utf-8")) > MAX_PROOF_BYTES
            or not _digest(expected_approval_sha256)
            or typed_hash(approval) != expected_approval_sha256
            or approval["version"] != APPROVAL_VERSION or approval["authorized"] is not True):
        raise ValueError("externally pinned exact approval unavailable")
    for key in ("approval_id", "tokenizer_id"):
        if not isinstance(approval[key], str) or not 1 <= len(approval[key]) <= 256:
            raise ValueError("approval/counter identity unavailable")
    if not _digest(approval["tokenizer_sha256"]) or approval["counter_scope"] != COUNTER_SCOPE:
        raise ValueError("full-provider-overhead counter identity required")
    for key in ("input_token_cap", "output_token_cap", "context_window_cap", "max_proof_age_seconds"):
        if type(approval[key]) is not int or not 1 <= approval[key] < 2**63:
            raise ValueError("exact positive approved caps required")
    if approval["max_proof_age_seconds"] > 300:
        raise ValueError("proof freshness cap exceeds supported bound")
    if _time(at_time) >= _time(approval["expires_at"]):
        raise ValueError("token-fit approval expired")
    if (not isinstance(trial_id, str) or not 1 <= len(trial_id) <= 256
            or type(turn_id) is not int or not 1 <= turn_id <= 3):
        raise ValueError("exact trial/turn identity required")
    audit = audit_provider_catalog(artifact, encoded_body, provider=provider, model_id=model_id,
                                   adapter_revision=adapter_revision, adapter_sha256=adapter_sha256)
    if audit["status"] != "valid":
        raise ValueError("full-wire catalog parity is not valid")
    for key, selected in (("provider", provider), ("model_id", model_id),
                          ("adapter_revision", adapter_revision), ("adapter_sha256", adapter_sha256),
                          ("settings_sha256", audit["settings_sha256"]),
                          ("catalog_typed_sha256", audit["catalog_pins"]["typed_sha256"])):
        if approval[key] != selected:
            raise ValueError("approval does not bind selected wire/settings/catalog/adapter/model")
    body = decode_wire_body(encoded_body)
    output_cap = body["max_completion_tokens" if provider == "openai" else "max_tokens"]
    if output_cap > approval["output_token_cap"]:
        raise ValueError("wire output cap exceeds approval")
    bindings = {
        "approval_sha256": expected_approval_sha256, "approval_id": approval["approval_id"],
        "provider": provider, "model_id": model_id, "adapter_revision": adapter_revision,
        "adapter_sha256": adapter_sha256, "raw_body_sha256": audit["raw_body_sha256"],
        "typed_body_sha256": audit["typed_body_sha256"], "body_bytes": len(encoded_body),
        "settings_sha256": audit["settings_sha256"],
        "catalog_typed_sha256": audit["catalog_pins"]["typed_sha256"],
        "history_sha256": typed_hash({"messages": body["messages"], "system": body.get("system")}),
        "trial_id": trial_id, "turn_id": turn_id,
        "tokenizer_id": approval["tokenizer_id"], "tokenizer_sha256": approval["tokenizer_sha256"],
        "counter_scope": COUNTER_SCOPE, "input_token_cap": approval["input_token_cap"],
        "output_token_cap": output_cap, "context_window_cap": approval["context_window_cap"],
    }
    return bindings, audit


def _count(receipt: Any, bindings: dict[str, Any]) -> int:
    if (not isinstance(receipt, dict) or set(receipt) != COUNTER_FIELDS
            or receipt["exact"] is not True or type(receipt["input_tokens"]) is not int
            or not 1 <= receipt["input_tokens"] < 2**63):
        raise ValueError("exact bounded counter receipt unavailable")
    for key in ("raw_body_sha256", "tokenizer_id", "tokenizer_sha256", "model_id", "counter_scope"):
        if receipt[key] != bindings[key]:
            raise ValueError("counter receipt identity/scope differs")
    return receipt["input_tokens"]


def _status(count: int, bindings: dict[str, Any]) -> str:
    return "fits" if (count <= bindings["input_token_cap"]
                      and count + bindings["output_token_cap"] <= bindings["context_window_cap"]) else "exceeds"


def _seal(proof: dict[str, Any]) -> dict[str, Any]:
    proof["proof_sha256"] = typed_hash(proof)
    return proof


def build_token_fit_proof(encoded_body: bytes, *, artifact: dict[str, Any], provider: str,
                          model_id: str, adapter_revision: str, adapter_sha256: str,
                          approval: dict[str, Any], expected_approval_sha256: str,
                          tokenizer: Callable[[bytes], int] | None,
                          trial_id: str, turn_id: int, at_time: str) -> dict[str, Any]:
    """Invoke only an explicitly injected approved pure full-wire counter.

    The trusted operator supplies the callable corresponding to the approval's
    code hash. A hash label is not introspective proof of callable implementation.
    Unknown/unrepresentable counters block fit; no fallback estimate is used.
    """
    proof: dict[str, Any] = {
        "version": PROOF_VERSION, "status": "invalid", "reasons": [],
        "scope": "full-wire-input-fit-only",
        "live_admission": False, "provider_billing_tokens": "unverified",
        "created_at": at_time if isinstance(at_time, str) and len(at_time) <= 64 else None,
        "bindings": {}, "counter_receipt": None, "input_tokens": None,
    }
    try:
        bindings, _ = _bindings(
            encoded_body, artifact=artifact, provider=provider, model_id=model_id,
            adapter_revision=adapter_revision, adapter_sha256=adapter_sha256,
            approval=approval, expected_approval_sha256=expected_approval_sha256,
            trial_id=trial_id, turn_id=turn_id, at_time=at_time)
        proof["bindings"] = bindings
    except (ValueError, TypeError, KeyError, RecursionError, OverflowError):
        proof["reasons"] = ["invalid or unavailable externally approved wire/identity bindings"]
        return _seal(proof)
    if tokenizer is None or not callable(tokenizer):
        proof.update(status="unknown", reasons=["approved full-wire counter unavailable"])
        return _seal(proof)
    try:
        raw_count = tokenizer(encoded_body)
        # Exact same callback contract as the controller: byte body in, integer
        # count out. Identity/scope come from the externally pinned approval,
        # never from an invented provider tokenizer or a dictionary estimate.
        if type(raw_count) is not int or not 1 <= raw_count < 2**63:
            raise ValueError("counter returned an unrepresentable count")
        receipt = {"input_tokens": raw_count, "exact": True,
                   **{key: bindings[key] for key in (
                       "raw_body_sha256", "tokenizer_id", "tokenizer_sha256", "model_id", "counter_scope")}}
        count = _count(receipt, bindings)
        proof.update(status=_status(count, bindings), counter_receipt=deepcopy(receipt), input_tokens=count)
        if proof["status"] == "exceeds":
            proof["reasons"] = ["input cap or input-plus-output context limit exceeded"]
    except Exception:
        # Counter failure is an unknown bound, not a zero/free request. No error
        # text or partial tokenizer/provider payload is copied into public proof.
        proof.update(status="unknown", reasons=["counter failed or returned an unrepresentable exact count"])
    return _seal(proof)


def verify_token_fit_proof(proof: dict[str, Any], encoded_body: bytes, *, artifact: dict[str, Any],
                           provider: str, model_id: str, adapter_revision: str, adapter_sha256: str,
                           approval: dict[str, Any], expected_approval_sha256: str,
                           expected_proof_sha256: str, trial_id: str, turn_id: int,
                           at_time: str) -> dict[str, Any]:
    """Rebind a journal-pinned proof to actual current-turn bytes without recounting.

    The expected proof hash must come from the trusted counter/journal path,
    never be read from the submitted proof as its own verification authority.
    """
    result = {"version": PROOF_VERSION, "valid": False, "fits": False,
              "live_admission": False, "reasons": []}
    try:
        if (not isinstance(proof, dict) or set(proof) != PROOF_FIELDS
                or len(canonical_json(proof).encode("utf-8")) > MAX_PROOF_BYTES
                or proof["version"] != PROOF_VERSION or proof["live_admission"] is not False
                or proof["scope"] != "full-wire-input-fit-only"
                or proof["provider_billing_tokens"] != "unverified"
                or not _digest(expected_proof_sha256)
                or proof["proof_sha256"] != expected_proof_sha256
                or typed_hash({key: value for key, value in proof.items() if key != "proof_sha256"})
                != expected_proof_sha256):
            raise ValueError("proof identity differs from trusted external journal pin")
        bindings, _ = _bindings(
            encoded_body, artifact=artifact, provider=provider, model_id=model_id,
            adapter_revision=adapter_revision, adapter_sha256=adapter_sha256,
            approval=approval, expected_approval_sha256=expected_approval_sha256,
            trial_id=trial_id, turn_id=turn_id, at_time=at_time)
        if typed_hash(bindings) != typed_hash(proof["bindings"]):
            raise ValueError("proof belongs to a different body/history/turn or approval")
        age = (_time(at_time) - _time(proof["created_at"])).total_seconds()
        if not 0 <= age <= approval["max_proof_age_seconds"]:
            raise ValueError("proof is stale or future-dated")
        count = _count(proof["counter_receipt"], bindings)
        status = _status(count, bindings)
        if type(proof["input_tokens"]) is not int or proof["input_tokens"] != count or proof["status"] != status:
            raise ValueError("proof count/fit disposition differs")
        result.update(valid=True, fits=status == "fits")
        if status != "fits":
            result["reasons"] = ["approved input/context cap exceeded"]
    except (ValueError, TypeError, KeyError, RecursionError, OverflowError):
        result["reasons"] = ["unknown, stale, mismatched or unpinned token-fit proof"]
    return result
