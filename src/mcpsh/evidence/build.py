"""Private in-memory adapter for D1's sole edition publisher; never writes files."""

import hashlib
import json

from .models import EditionIndex
from .reader import EvidenceRejected, MAX_INDEX_BYTES, MAX_LINE_BYTES, MAX_TOTAL_BYTES, model, strict_json

ROW_FIELDS = {
    "outcome", "trace", "results", "observation", "public_task", "catalog_hash",
    "fixture_ref", "fixture_payload_hash", "final_response", "final_response_hash",
    "result_captures", "model_attempts", "accounting_attempts",
    "normalization_diff_hash", "metadata_diffs",
    "selected_calls", "selection_journal_complete",
    "repeat",
    "reuse",
}


def encode(value) -> bytes:
    return (json.dumps(value, sort_keys=True, ensure_ascii=True, allow_nan=False,
                       separators=(",", ":")) + "\n").encode()


def build_edition_payloads(result: dict, *, candidate_commit: str, revision: int,
                           reserved_by_operation: dict[str, int] | None = None,
                           oracle_package_bytes: bytes | None = None) -> dict[str, bytes]:
    """Return proposed PRIVATE artifacts; externally pin EDITION.json before reading.

    Optional oracle bytes must be explicitly supplied by an authorized custodian.
    No path/default discovers private custody, and callers must not write these raw
    sidecars under a public result directory. This function grants no read authority.
    """
    manifest = result["manifest"]
    records, observations = [], []
    reserved = reserved_by_operation or {}
    for row in result["rows"]:
        if set(row) - ROW_FIELDS:
            raise EvidenceRejected("unsupported source row revision; no silent field discard")
        outcome = row["outcome"]
        costs = []
        for item in row.get("accounting_attempts", []):
            costs.append({"attempt_id": item["attempt_id"], "operation_id": item["operation_id"],
                          "status": item["status"], "dispatch_status": item["dispatch_status"],
                          "cost_microunits": item.get("cost_microunits"),
                          "cost_basis": item.get("cost_kind", "unknown"),
                          "settlement_reference": item.get("settlement_reference"),
                          "reserved_microunits": reserved.get(item["operation_id"])})
        record = {"outcome": outcome, "trace": row.get("trace"), "results": row.get("results"),
                  "repeat": row.get("repeat"),
                  "reuse": row.get("reuse"),
                  "selected_calls": row.get("selected_calls"),
                  "selection_journal_complete": row.get("selection_journal_complete"),
                  "fixture_ref": row.get("fixture_ref"), "fixture_payload_hash": row.get("fixture_payload_hash"),
                  "catalog_hash": row.get("catalog_hash"), "normalization_diff_hash": row.get("normalization_diff_hash"),
                  "model_attempts": row.get("model_attempts", []), "accounting": costs,
                  "final_response": row.get("final_response"), "result_captures": row.get("result_captures")}
        records.append(encode(record))
        if row.get("observation") is not None:
            observations.append(encode({"trial_id": outcome["trial_id"],
                "platform_scope": manifest["platform_scope"],
                "observer_code_hash": manifest["observer_hash"], "observation": row["observation"]}))
    if any(len(line) > MAX_LINE_BYTES for line in records + observations):
        raise EvidenceRejected("normalized evidence row exceeds byte cap")
    payloads = {"MANIFEST.json": encode(manifest), "trials.jsonl": b"".join(records)}
    if observations:
        payloads["observers.jsonl"] = b"".join(observations)
    if oracle_package_bytes is not None:
        strict_json(oracle_package_bytes)
        payloads["oracles.json"] = oracle_package_bytes

    def pin(name):
        raw = payloads[name]
        return {"path": name, "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}

    index = {"kind": "mcpsh-evidence-edition", "schema_version": 1, "revision": revision,
             "edition_id": manifest["edition_id"], "candidate_commit": candidate_commit,
             "mode": manifest["mode"], "platform_scope": manifest["platform_scope"],
             "input_pins": {key: manifest[key] for key in (
                 "code_hash", "lock_hash", "protocol_hash", "task_hash", "catalog_hash",
                 "policy_hash", "scorer_hash", "observer_hash", "split_hash")},
             "manifest": pin("MANIFEST.json"), "trials": pin("trials.jsonl"),
             "observers": pin("observers.jsonl") if observations else None,
             "oracles": pin("oracles.json") if oracle_package_bytes is not None else None,
             "scheduled_trial_ids": [row["outcome"]["trial_id"] for row in result["rows"]],
             "empirical_verdict": "pending", "product_verdict": "pending"}
    model(EditionIndex, index)
    payloads["EDITION.json"] = encode(index)
    if len(payloads["EDITION.json"]) > MAX_INDEX_BYTES or sum(len(raw) for raw in payloads.values()) > MAX_TOTAL_BYTES:
        raise EvidenceRejected("proposed evidence edition exceeds total byte cap")
    return payloads
