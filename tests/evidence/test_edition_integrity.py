"""Authored offline regression SOURCE. Never executed during Dirty Mode."""

import hashlib
import importlib
import json

import pytest

from mcpsh.evidence import (
    EditionAuthority, EvidenceRejected, VerifiedEdition, build_edition_payloads,
    read_edition, reproduce,
)
from mcpsh.evidence.reader import read_bounded, server_result_hash, strict_json
from mcpsh.records import ExperimentManifest, TrialOutcome, typed_hash


def encode(value):
    return (json.dumps(value, sort_keys=True, ensure_ascii=True, allow_nan=False) + "\n").encode()


def pin(raw, path):
    return {"path": path, "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}


def authority_for(payloads):
    """Synthetic test authority only; production must supply a separately trusted pin."""
    index = strict_json(payloads["EDITION.json"])
    return EditionAuthority.model_validate_json(encode({
        "index_sha256": hashlib.sha256(payloads["EDITION.json"]).hexdigest(),
        "manifest_sha256": index["manifest"]["sha256"],
        **{key: index[key] for key in ("revision", "edition_id", "candidate_commit", "mode", "platform_scope", "input_pins")},
    }))


def sample(*, live=False, calls=False, oracle=False):
    observation = {"complete": False, "predicates": {}}
    public = {"task_id": "dev-a", "user_request": "List allowed sources.",
              "allowed_source_ids": ["app"], "fixture_ref": "fixture-dev-a"}
    oracle_bytes = encode({"schema_version": 1, "cases": [{"public": public, "oracle": {
        "task_id": "dev-a", "alternatives": [[]], "family_id": "development-family",
        "split": "development",
    }}]}) if oracle else None
    manifest = ExperimentManifest(
        edition_id="dev-edition-a", mode="live" if live else "replay", platform_scope="synthetic-memory",
        code_hash="a" * 64, lock_hash="b" * 64 if live else None,
        protocol_hash="c" * 64 if live else None, task_hash=typed_hash([public]), catalog_hash="d" * 64,
        policy_hash="e" * 64, scorer_hash="f" * 64, observer_hash="1" * 64,
        split_hash=hashlib.sha256(oracle_bytes).hexdigest() if oracle_bytes else "2" * 64,
        seed=1729, model_ids=("model-a", "model-b") if live else (),
    ).model_dump(mode="json")
    result = {"ok": True, "text": "synthetic α"}
    trace = [{"trial_id": "trial-a", "turn_id": 1, "call_id": "call-a", "sequence": 1,
              "tool_name": "list_sources", "raw_arguments": "{}", "raw_hash": hashlib.sha256(b"{}").hexdigest(),
              "typed_arguments": {}, "typed_hash": typed_hash({}), "validation": "valid",
              "gate_classification": "legitimate", "enforcement_mode": "hardened", "gate_decision": "allow",
              "gate_reason": "allowed", "dispatched": True, "executed": True,
              "output_hash": server_result_hash(result), "model_attempt_id": "attempt-a" if live else None}] if calls else []
    if trace:
        trace[0]["selection_id"] = "trial-a:selection:1"
    selections = []
    if calls:
        wrapper = json.dumps({"name": "list_sources", "arguments": "{}"}, sort_keys=True, separators=(",", ":"))
        selections.append({"trial_id": "trial-a", "turn_id": 1, "selection_id": "trial-a:selection:1",
            "sequence": 1, "tool_name": "list_sources", "raw_arguments": "{}",
            "raw_arguments_hash": hashlib.sha256(b"{}").hexdigest(), "raw_call_json": wrapper,
            "raw_call_hash": hashlib.sha256(wrapper.encode()).hexdigest(), "typed_arguments": {},
            "typed_hash": server_result_hash({}), "validation": "valid", "disposition": "sent-to-server",
            "rejection_reason": None, "server_call_id": "call-a",
            "model_attempt_id": "attempt-a" if live else None,
            "provider_call_id": "provider-call-a" if live else None})
    attempts = [{"attempt_id": "attempt-a", "request_id": "request-a", "response_id": "response-a",
                 "raw_response_hash": "3" * 64, "provider_id": "openai", "requested_model_id": "model-a",
                 "returned_model_id": "model-a", "started_at": "2026-10-23T12:00:00+00:00",
                 "finished_at": "2026-10-23T12:00:01+00:00", "status": "completed",
                 "usage": {"prompt_tokens": 1, "completion_tokens": 1}, "settlement_reference": "attempt-a",
                 "trial_id": "trial-a", "turn_id": 1}] if live else []
    costs = [{"attempt_id": "attempt-a", "operation_id": "operation-a", "status": "completed",
              "dispatch_status": "response_received", "cost_microunits": 2,
              "cost_kind": "dated-price-estimate", "settlement_reference": "attempt-a"}] if live else []
    outcome = TrialOutcome(
        trial_id="trial-a", task_id="dev-a", family_id="development-family", condition="clean", cell="C1",
        selector="model-a" if live else "scripted-replay", execution_mode="live" if live else "replay",
        provider_id="openai" if live else None, model_id="model-a" if live else None,
        model_attempt_ids=("attempt-a",) if live else (), selection_success=False, utility_success=False,
        utility_status="failure", prohibited_intent=False, validated_prohibited_attempts=0,
        gate_classified_prohibited_calls=0, blocked_prohibited_calls=0, gate_false_negative_calls=0,
        effect="unknown", observation_complete=False, call_count=len(trace), failures=("observation_incomplete",),
        cost_microunits=2 if live else 0, cost_status="settled" if live else "non-model",
        cost_basis="dated-price-estimate" if live else "non-model", trace_hash=typed_hash(trace),
        observation_hash=typed_hash(observation), latency_seconds=1.0,
        selected_call_count=len(selections), selected_calls_hash=typed_hash(selections),
        selection_journal_complete=True,
    ).model_dump(mode="json")
    row = {"outcome": outcome, "trace": trace, "results": [result] if calls else [],
           "repeat": 0, "selected_calls": selections, "selection_journal_complete": True,
           "observation": observation, "model_attempts": attempts, "accounting_attempts": costs,
           "final_response": None, "result_captures": None}
    return build_edition_payloads({"manifest": manifest, "rows": [row]},
        candidate_commit="1234567890abcdef1234567890abcdef12345678", revision=1,
        reserved_by_operation={"operation-a": 30}, oracle_package_bytes=oracle_bytes)


def memory_edition(payloads):
    index = strict_json(payloads["EDITION.json"])
    artifacts = tuple((role, payloads[index[role]["path"]]) for role in ("manifest", "trials", "observers", "oracles") if index[role])
    return VerifiedEdition(authority_for(payloads), payloads["EDITION.json"], artifacts)


def change_trial(payloads, mutate):
    row = strict_json(payloads["trials.jsonl"])
    mutate(row)
    payloads["trials.jsonl"] = encode(row)
    index = strict_json(payloads["EDITION.json"])
    index["trials"] = pin(payloads["trials.jsonl"], "trials.jsonl")
    payloads["EDITION.json"] = encode(index)


def test_bounded_reader_positive_control_is_not_product_acceptance(tmp_path):
    """what_bug_this_catches: a validator that rejects every honest edition or claims empirical acceptance."""
    payloads = sample(calls=True)
    for name, raw in payloads.items():
        (tmp_path / name).write_bytes(raw)
    index, _, trials, _, package = read_edition(tmp_path, authority=authority_for(payloads)).validate()
    assert index.empirical_verdict == index.product_verdict == "pending"
    assert len(trials) == 1 and package is None


@pytest.mark.parametrize("raw", [b'{"a":1,"a":2}', b'{"x":NaN}', b'{"x":Infinity}', b'{"x":1e999}'])
def test_duplicate_and_nonfinite_json_are_rejected(raw):
    """what_bug_this_catches: permissive JSON decoding or exponent overflow bypassing finite-number checks."""
    with pytest.raises(EvidenceRejected):
        strict_json(raw)


@pytest.mark.parametrize("name", ["../outside", "/absolute", "C:/outside", "a\\b", "a/../b", "a//b", "a.", "NUL.txt", "x:stream"])
def test_artifact_paths_reject_escape_devices_and_ambiguity(tmp_path, name):
    """what_bug_this_catches: path traversal, ADS, absolute paths or device files reaching an open."""
    with pytest.raises(EvidenceRejected):
        read_bounded(tmp_path, name, 100)


def test_symlink_artifact_is_rejected(tmp_path):
    """what_bug_this_catches: a correctly hashed file reached through a forbidden symlink."""
    target = tmp_path / "target.json"
    target.write_bytes(b"{}")
    link = tmp_path / "link.json"
    try:
        link.symlink_to(target)
    except OSError:
        pytest.skip("symlink capability unavailable; unsupported is not a pass")
    with pytest.raises(EvidenceRejected):
        read_bounded(tmp_path, link.name, 100)


def test_artifact_size_cap_is_enforced_before_parse(tmp_path):
    """what_bug_this_catches: a tiny declared pin permitting an unbounded file read."""
    (tmp_path / "large.json").write_bytes(b"123")
    with pytest.raises(EvidenceRejected):
        read_bounded(tmp_path, "large.json", 2)


def test_platform_mismatch_is_rejected_even_when_bytes_are_rebound():
    """what_bug_this_catches: pooling memory evidence under a filesystem edition label."""
    payloads = sample()
    manifest = strict_json(payloads["MANIFEST.json"])
    manifest["platform_scope"] = "filesystem-posix"
    payloads["MANIFEST.json"] = encode(manifest)
    index = strict_json(payloads["EDITION.json"])
    index["manifest"] = pin(payloads["MANIFEST.json"], "MANIFEST.json")
    payloads["EDITION.json"] = encode(index)
    with pytest.raises(EvidenceRejected):
        memory_edition(payloads).validate()


def test_artifact_byte_tampering_rejected_before_parse():
    """what_bug_this_catches: trusting indexed SHA labels without comparing actual file bytes."""
    edition = memory_edition(sample())
    artifacts = dict(edition.artifacts)
    artifacts["trials"] += b" "
    with pytest.raises(EvidenceRejected):
        VerifiedEdition(edition.authority, edition.index_bytes, tuple(artifacts.items())).validate()


def test_external_revision_is_not_inferred_from_index():
    """what_bug_this_catches: accepting a newer self-labeled input revision under an old grant."""
    edition = memory_edition(sample())
    wrong = edition.authority.model_copy(update={"revision": 2})
    with pytest.raises(EvidenceRejected):
        VerifiedEdition(wrong, edition.index_bytes, edition.artifacts).validate()


def test_ordered_sequence_break_rejected_even_with_consistent_byte_pins():
    """what_bug_this_catches: valid hashes hiding a broken ordered call sequence."""
    payloads = sample(calls=True)

    def break_order(row):
        row["trace"][0]["sequence"] = 2
        row["outcome"]["trace_hash"] = typed_hash(row["trace"])

    change_trial(payloads, break_order)
    with pytest.raises(EvidenceRejected):
        memory_edition(payloads).validate()


def test_unicode_typed_arguments_use_pinned_server_hash_convention():
    """what_bug_this_catches: conflating broker ASCII-canonical and whole-trace Unicode hashes."""
    payloads = sample(calls=True)

    def unicode_arguments(row):
        event = row["trace"][0]
        arguments = {"source_id": "app", "needle": "α", "max_matches": 1}
        event.update(tool_name="find_literal", typed_arguments=arguments,
                     raw_arguments=json.dumps(arguments, ensure_ascii=False),
                     typed_hash=server_result_hash(arguments))
        event["raw_hash"] = hashlib.sha256(event["raw_arguments"].encode()).hexdigest()
        row["outcome"]["trace_hash"] = typed_hash(row["trace"])
        selected = row["selected_calls"][0]
        selected.update(tool_name=event["tool_name"], raw_arguments=event["raw_arguments"],
                        raw_arguments_hash=event["raw_hash"], typed_arguments=arguments,
                        typed_hash=event["typed_hash"])
        selected["raw_call_json"] = json.dumps({"name": event["tool_name"], "arguments": event["raw_arguments"]}, sort_keys=True, separators=(",", ":"))
        selected["raw_call_hash"] = hashlib.sha256(selected["raw_call_json"].encode()).hexdigest()
        row["outcome"]["selected_calls_hash"] = typed_hash(row["selected_calls"])

    change_trial(payloads, unicode_arguments)
    memory_edition(payloads).validate()


def test_live_call_parent_must_match_actual_trial_attempt():
    """what_bug_this_catches: associating a tool call with a nonexistent model attempt."""
    payloads = sample(live=True, calls=True)

    def wrong_parent(row):
        row["trace"][0]["model_attempt_id"] = "other-attempt"
        row["outcome"]["trace_hash"] = typed_hash(row["trace"])

    change_trial(payloads, wrong_parent)
    with pytest.raises(EvidenceRejected):
        memory_edition(payloads).validate()


def test_settled_live_cost_cannot_omit_usage():
    """what_bug_this_catches: labeling a numeric cost settled when provider usage is absent."""
    payloads = sample(live=True)
    change_trial(payloads, lambda row: row["model_attempts"][0].update(usage={}))
    with pytest.raises(EvidenceRejected):
        memory_edition(payloads).validate()


def test_missing_oracle_is_unknown_without_reduced_denominator_summary(monkeypatch):
    """what_bug_this_catches: presenting omitted private labels as successful reproduction."""
    module = importlib.import_module("mcpsh.evidence.reproduce")
    monkeypatch.setattr(module, "evaluator_source_hash", lambda: "f" * 64)
    monkeypatch.setattr(module, "package_source_hash", lambda: "a" * 64)
    report = reproduce(memory_edition(sample()), expected_evaluator_hash="f" * 64)
    assert report["execution_state"] == "reproduction-partial"
    assert report["scheduled_trials"] == 1 and report["scored_trials"] == 0
    assert report["summary"] == []
    assert report["unknown_trials"][0]["reasons"] == ["oracle_unavailable"]
    assert report["acceptance_verdict"] == "pending"


def test_missing_observation_never_becomes_none_effect(monkeypatch):
    """what_bug_this_catches: missing independent observation silently earning enforcement credit."""
    module = importlib.import_module("mcpsh.evidence.reproduce")
    monkeypatch.setattr(module, "evaluator_source_hash", lambda: "f" * 64)
    monkeypatch.setattr(module, "package_source_hash", lambda: "a" * 64)
    payloads = sample(oracle=True)
    index = strict_json(payloads["EDITION.json"])
    index["observers"] = None
    payloads["EDITION.json"] = encode(index)
    report = reproduce(memory_edition(payloads), expected_evaluator_hash="f" * 64)
    assert report["rows"][0]["outcome"]["effect"] == "unknown"
    assert "independent_observer_unavailable" in report["rows"][0]["missing_evidence"]


def test_wrong_evaluator_pin_refuses_rescore():
    """what_bug_this_catches: reproducing an old edition using a changed scorer silently."""
    with pytest.raises(EvidenceRejected):
        reproduce(memory_edition(sample()), expected_evaluator_hash="0" * 64)
