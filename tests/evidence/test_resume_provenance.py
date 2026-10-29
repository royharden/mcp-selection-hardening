"""Provenance/projection regression SOURCE; generated narratives are not real effects."""

from copy import deepcopy
import hashlib
import json

import pytest

from mcpsh.evidence import (
    CatalogExpectation, CatalogPins, ConformanceExpectation, EvidenceRejected,
    ProducerAuthority, project_resume_plan, validate_resume_lineage, verify_producer_bindings,
)
from mcpsh.records import typed_hash

from test_edition_integrity import change_trial, encode, memory_edition, pin, sample, strict_json
from test_selected_resume import plan, rerun_request


def complete_parent():
    payloads = sample(oracle=True)
    observation = {"observer_version": "synthetic-unit-observer", "trial_id": "trial-a",
        "platform_scope": "synthetic-memory", "complete": True,
        "predicates": {"protected_read": "none", "outbox_write": "none", "wire_disclosure": "none"},
        "protected_read_count": 0, "outbox_hashes": {}, "sequence_complete": True,
        "wire_complete": True, "reset_verified": True,
        "events": [{"trial_id": "trial-a", "epoch": "synthetic-epoch", "sequence": 1,
                    "kind": "fixture_ready", "fixture_hash": "a" * 64, "counters_zero": True}],
        "wire_observations": []}
    obs = strict_json(payloads["observers.jsonl"])
    obs["observation"] = observation
    payloads["observers.jsonl"] = encode(obs)
    def outcome(row):
        row["outcome"].update(observation_complete=True, effect="none", failures=[],
            observation_hash=typed_hash(observation), selection_success=True, utility_success=True,
            utility_status="success")
    change_trial(payloads, outcome)
    index = strict_json(payloads["EDITION.json"])
    index["observers"] = pin(payloads["observers.jsonl"], "observers.jsonl")
    payloads["EDITION.json"] = encode(index)
    return payloads


def successor_payloads(payloads, authority, proposal, *, reuse=False):
    result = deepcopy(payloads)
    index = strict_json(result["EDITION.json"])
    row = strict_json(result["trials.jsonl"])
    original = proposal.retained_trials[0]
    target_id = proposal.actions[0].target_trial_id
    row["outcome"]["trial_id"] = target_id
    if reuse:
        row.update(trace=None, results=None, selected_calls=None, selection_journal_complete=None,
                   model_attempts=[], accounting=[], final_response=None, result_captures=None,
                   reuse={"kind": "reused-evidence", "source_index_sha256": proposal.parent_index_sha256,
                          "source_manifest_sha256": index["manifest"]["sha256"],
                          "source_trial_id": original.trial_id, "source_row_sha256": original.source_row_sha256,
                          "source_outcome_sha256": original.original_outcome_sha256,
                          "original_cost_microunits": original.cost_microunits,
                          "original_cost_basis": original.cost_basis, "new_charge_microunits": 0,
                          "independent_new_sample": False})
        index["observers"] = None
    else:
        observation = strict_json(result["observers.jsonl"])
        observation["trial_id"] = target_id
        result["observers.jsonl"] = encode(observation)
        index["observers"] = pin(result["observers.jsonl"], "observers.jsonl")
    result["MANIFEST.json"] = authority.target_manifest_json.encode()
    result["trials.jsonl"] = encode(row)
    index.update(edition_id="dev-successor", revision=2, scheduled_trial_ids=[target_id])
    index["manifest"] = pin(result["MANIFEST.json"], "MANIFEST.json")
    index["trials"] = pin(result["trials.jsonl"], "trials.jsonl")
    result["EDITION.json"] = encode(index)
    return result


def reuse_proposal(parent):
    authority, receipt = rerun_request(parent)
    slot = authority.schedule[0].model_copy(update={"action": "reuse"})
    receipt = receipt.model_copy(update={"action": "reuse", "reason": "reuse-complete-evidence"})
    authority = authority.model_copy(update={"schedule": (slot,),
        "receipt_sha256": (typed_hash(receipt.model_dump(mode="json")),)})
    return authority, plan(parent, authority, (receipt,))


def test_reuse_is_reference_not_new_live_sample_or_billing():
    """what_bug_this_catches: cloning old attempts into a second edition and charging them twice."""
    payloads = complete_parent()
    parent = memory_edition(payloads)
    authority, proposal = reuse_proposal(parent)
    assert proposal.state == "proposal-ready"
    successor = memory_edition(successor_payloads(payloads, authority, proposal, reuse=True))
    report = validate_resume_lineage(parent, successor, proposal, expected_plan_id=proposal.plan_id)
    assert report["resume_disposition"] == "linked"
    assert report["reused_evidence_trials"] == 1
    assert report["independent_new_live_samples"] == 0
    assert report["reused_new_charge_microunits"] == 0


def test_reuse_rejects_relabeling_an_original_bad_outcome():
    """what_bug_this_catches: changing a parent's utility/intent result while keeping its reuse label."""
    payloads = complete_parent()
    parent = memory_edition(payloads)
    authority, proposal = reuse_proposal(parent)
    target = successor_payloads(payloads, authority, proposal, reuse=True)
    change_trial(target, lambda row: row["outcome"].update(utility_success=False, utility_status="failure"))
    with pytest.raises(EvidenceRejected):
        validate_resume_lineage(parent, memory_edition(target), proposal, expected_plan_id=proposal.plan_id)


def test_stale_reuse_row_pin_cannot_be_rebound_to_new_index():
    """what_bug_this_catches: content rehashing hiding a stale reference to the parent row."""
    payloads = complete_parent()
    parent = memory_edition(payloads)
    authority, proposal = reuse_proposal(parent)
    target = successor_payloads(payloads, authority, proposal, reuse=True)
    change_trial(target, lambda row: row["reuse"].update(source_row_sha256="0" * 64))
    with pytest.raises(EvidenceRejected):
        validate_resume_lineage(parent, memory_edition(target), proposal, expected_plan_id=proposal.plan_id)


def test_public_projection_does_not_publish_private_ids_or_receipt_text():
    """what_bug_this_catches: public resume JSON echoing selected/oracle/provider identifiers."""
    parent = memory_edition(sample())
    authority, receipt = rerun_request(parent)
    marker = "SYNTHETIC_DO_NOT_PUBLISH"
    slot = authority.schedule[0].model_copy(update={"target_trial_id": marker})
    receipt = receipt.model_copy(update={"target_trial_id": marker, "receipt_id": marker})
    authority = authority.model_copy(update={"schedule": (slot,),
        "receipt_sha256": (typed_hash(receipt.model_dump(mode="json")),)})
    proposal = plan(parent, authority, (receipt,))
    public = project_resume_plan(proposal, expected_plan_id=proposal.plan_id)
    private = project_resume_plan(proposal, expected_plan_id=proposal.plan_id, public=False)
    assert marker not in json.dumps(public)
    assert marker in json.dumps(private)
    assert public["retained_failed_trials"] == 1


def test_projection_rejects_crash_replay_with_modified_plan_id():
    """what_bug_this_catches: a stale/mutated plan being published under an old idempotency key."""
    parent = memory_edition(sample())
    authority, receipt = rerun_request(parent)
    proposal = plan(parent, authority, (receipt,))
    mutated = proposal.model_copy(update={"proposed_new_reservation_microunits": 999})
    with pytest.raises(EvidenceRejected):
        project_resume_plan(mutated, expected_plan_id=proposal.plan_id)


def conformance_document(*, scope="component-diagnostic", mixed=False):
    from mcpsh.conformance.evidence import digest
    pins = {key: "a" * 64 for key in ("server", "broker", "observer", "stdio", "conformance")}
    observation = {"observer_version": "unit-narrative-only", "trial_id": "probe-trial",
        "epoch": "unit-epoch", "complete": not mixed, "reset_verified": True,
        "sequence_complete": True, "wire_complete": not mixed,
        "predicates": {"protected_read": "observed" if mixed else "none",
                       "outbox_write": "none", "wire_disclosure": "unknown" if mixed else "none"},
        "broker_event_count": 1, "last_sequence": 1, "events_sha256": "b" * 64}
    value = {"schema_version": 1, "probe_id": "probe-a", "track": "synthetic-memory", "scope": scope,
        "request_sha256": "c" * 64, "source_pins": pins,
        "session": {"server_instance_id": "unit-instance", "trial_id": "probe-trial", "child_pid": None,
                    "fixture_id": "unit-fixture", "fixture_payload_sha256": "d" * 64,
                    "platform_scope": "synthetic-memory"},
        "frames": [{"direction": direction, "sequence": sequence, "request_key": "1",
                    "sha256": "e" * 64, "bytes": 1, "response_expected": True}
                   for sequence, direction in enumerate(("request", "response"), 1)],
        "observation": observation, "checks": {}}
    value["record_sha256"] = digest(value)
    expected = ConformanceExpectation(probe_id="probe-a", track="synthetic-memory",
        request_sha256="c" * 64, source_pins=pins, server_instance_id="unit-instance",
        fixture_payload_sha256="d" * 64)
    return value, expected


@pytest.mark.parametrize("scope", ["component-diagnostic", "mock-diagnostic"])
def test_component_and_mock_never_earn_actual_platform_credit(scope):
    """what_bug_this_catches: upgrading a source/component narrative to real platform proof."""
    edition = memory_edition(sample())
    document, expected = conformance_document(scope=scope)
    authority = ProducerAuthority(schema_version=1, source_index_sha256=edition.authority.index_sha256,
                                  catalogs=(), conformance=(expected,))
    result = verify_producer_bindings(edition, authority,
        expected_authority_sha256=typed_hash(authority.model_dump(mode="json")),
        catalog_documents={}, conformance_documents={"probe-a": encode(document)})
    assert not result["all_selected_probes_creditable"] and not result["full_platform_credit"]


def test_mixed_observed_unknown_keeps_observation_without_full_credit():
    """what_bug_this_catches: unknown wire evidence erasing an independently observed protected read."""
    edition = memory_edition(sample())
    document, expected = conformance_document(scope="actual-memory", mixed=True)
    authority = ProducerAuthority(schema_version=1, source_index_sha256=edition.authority.index_sha256,
                                  catalogs=(), conformance=(expected,))
    result = verify_producer_bindings(edition, authority,
        expected_authority_sha256=typed_hash(authority.model_dump(mode="json")),
        catalog_documents={}, conformance_documents={"probe-a": encode(document)})
    probe = result["conformance"][0]
    assert probe["predicates"]["protected_read"] == "observed"
    assert probe["predicates"]["wire_disclosure"] == "unknown"
    assert not probe["creditable"] and not result["full_platform_credit"]


def test_catalog_binding_checks_actual_d5_pins_and_trial_metadata():
    """what_bug_this_catches: accepting a separately valid catalog that was not used by this trial."""
    from mcpsh.catalog.artifacts import artifact_pins, build_catalog_artifact, serialize_catalog_artifact
    value = build_catalog_artifact("clean", ordering_seed=0)
    raw = serialize_catalog_artifact(value).encode()
    payloads = sample()
    change_trial(payloads, lambda row: row.update(catalog_hash=typed_hash(value["catalog"])))
    edition = memory_edition(payloads)
    pins = CatalogPins.model_validate_json(encode(artifact_pins(value, raw=raw)))
    authority = ProducerAuthority(schema_version=1, source_index_sha256=edition.authority.index_sha256,
        catalogs=(CatalogExpectation(trial_id="trial-a", pins=pins),), conformance=())
    result = verify_producer_bindings(edition, authority,
        expected_authority_sha256=typed_hash(authority.model_dump(mode="json")),
        catalog_documents={"trial-a": raw}, conformance_documents={})
    assert result["catalogs"][0]["state"] == "verified"
    wrong = verify_producer_bindings(edition, authority,
        expected_authority_sha256=typed_hash(authority.model_dump(mode="json")),
        catalog_documents={"trial-a": raw + b" "}, conformance_documents={})
    assert wrong["catalogs"][0]["state"] == "invalid"
