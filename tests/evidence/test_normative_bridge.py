"""Normative-v3 producer bridge regression SOURCE; authored, not executed in Dirty Mode."""

import json

import pytest

from mcpsh.conformance.evidence import EvidenceContext, PIN_NAMES, build_evidence
from mcpsh.conformance.evidence_v2 import build_evidence_v2
from mcpsh.conformance.evidence_v3 import build_evidence_v3
from mcpsh.conformance.export import packaged_bundle_inputs
from mcpsh.conformance.models import ProbeDefinition
from mcpsh.conformance.requirements import decode_requirements, requirements_source
from mcpsh.evidence import (
    ConformanceExpectation, EvidenceRejected, NormativeProducerAuthority, ProducerAuthority,
    probe_key, project_normative_status, project_public_result, verify_producer_bindings,
)
from mcpsh.records import typed_hash

from test_edition_integrity import encode, memory_edition, sample

TRACK = "synthetic-memory"
PROBE = "allowed-read"


def records(*, scope="component-diagnostic"):
    """Public unit narrative for one probe; a well-formed record is not an observation."""
    manifest = packaged_bundle_inputs().required_manifest
    context = EvidenceContext("1" * 64, {name: "2" * 64 for name in PIN_NAMES})
    binding = {"server_instance_id": "unit-server", "trial_id": "unit-trial", "child_pid": None,
        "fixture_id": "public-unit", "fixture_payload_sha256": "3" * 64, "platform_scope": TRACK}
    observation = {"observer_version": "public-unit", "trial_id": binding["trial_id"], "complete": True,
        "reset_verified": True, "sequence_complete": True, "wire_complete": True,
        "predicates": {"protected_read": "none", "outbox_write": "none", "wire_disclosure": "none"},
        "events": [{"trial_id": binding["trial_id"], "epoch": "unit-epoch", "sequence": 1}]}
    frames = [{"direction": direction, "sequence": index, "request_key": "one", "bytes": 20,
        "sha256": "4" * 64, "response_expected": direction == "request"}
        for index, direction in enumerate(("request", "response"), 1)]
    probe = ProbeDefinition(PROBE, "public unit", (TRACK,), "allowed")
    v1 = build_evidence(context=context, probe=probe, track=TRACK, session_binding=binding,
                        frames=frames, observation=observation, scope=scope)
    v2 = build_evidence_v2(v1, manifest=manifest, case_id=None, result={}, actual_raw_arguments_sha256=None,
                           actual_case_source_sha256=manifest["case_source_sha256"])
    raw = requirements_source()
    v3 = build_evidence_v3(v2, inventory=decode_requirements(raw))
    expected = ConformanceExpectation(probe_id=PROBE, track=TRACK, request_sha256=context.request_sha256,
        source_pins=context.source_pins, server_instance_id=binding["server_instance_id"],
        fixture_payload_sha256=binding["fixture_payload_sha256"])
    return manifest, raw, v1, v3, expected


def normative(edition, manifest, raw, expected, *, requirements_pin=None):
    from hashlib import sha256

    return NormativeProducerAuthority(schema_version=2, source_index_sha256=edition.authority.index_sha256,
        catalogs=(), conformance=(expected,), semantic_manifest_sha256=manifest["manifest_sha256"],
        requirements_manifest_sha256=requirements_pin or sha256(raw).hexdigest())


def run(edition, authority, documents, **resources):
    return verify_producer_bindings(edition, authority,
        expected_authority_sha256=typed_hash(authority.model_dump(mode="json")),
        catalog_documents={}, conformance_documents=documents, **resources)


def test_full_inventory_denominator_survives_single_probe_selection():
    """what_bug_this_catches: per-track counts shrinking to the selected/implemented probes."""
    edition = memory_edition(sample())
    manifest, raw, _, v3, expected = records(scope="actual-memory")
    inventory = decode_requirements(raw)
    result = run(edition, normative(edition, manifest, raw, expected),
        {probe_key(TRACK, PROBE): encode(v3)}, semantic_manifest=manifest, requirements_raw=raw)
    assert result["mode"] == "normative-v3"
    summary = result["normative"]
    for track in ("synthetic-memory", "filesystem-posix", "stdio"):
        required = sum(track in row.tracks for row in inventory.requirements)
        block = summary["tracks"][track]
        assert block["required_requirements"] == required == summary["required_counts"][track]
        assert block["per_probe_creditable_requirements"] + block["pending_requirements"] == required
        assert block["verdict"] == "pending"
    # allowed-read alone completes no requirement: its siblings stay unselected/pending.
    assert summary["tracks"][TRACK]["per_probe_creditable_requirements"] == 0
    assert summary["tracks"]["stdio"]["pending_reason_counts"]["unselected"] == summary["tracks"]["stdio"]["required_requirements"]


def test_missing_v3_resources_or_documents_never_fall_back_to_v1():
    """what_bug_this_catches: normative mode silently verifying with the legacy v1 checker."""
    edition = memory_edition(sample())
    manifest, raw, v1, v3, expected = records(scope="actual-memory")
    authority = normative(edition, manifest, raw, expected)
    key = probe_key(TRACK, PROBE)
    unavailable = run(edition, authority, {key: encode(v3)})
    assert unavailable["conformance"][0]["state"] == "unknown"
    assert unavailable["conformance"][0]["violations"] == ["conformance.normative-resource-missing"]
    assert unavailable["normative"]["status"] == "requirements-unavailable"
    assert unavailable["normative"]["required_counts"] is None
    lone_inventory = run(edition, authority, {key: encode(v3)}, requirements_raw=raw)
    assert lone_inventory["conformance"][0]["violations"] == ["conformance.normative-resource-missing"]
    assert lone_inventory["normative"]["status"] == "requirements-unavailable"
    legacy_document = run(edition, authority, {key: encode(v1)}, semantic_manifest=manifest, requirements_raw=raw)
    assert legacy_document["conformance"][0]["violations"] == ["conformance.v3-required"]
    assert legacy_document["conformance"][0]["creditable"] is False


def test_probe_and_inventory_pin_mismatches_reject():
    """what_bug_this_catches: a document or inventory with changed pins earning per-probe credit."""
    edition = memory_edition(sample())
    manifest, raw, _, v3, expected = records(scope="actual-memory")
    key = probe_key(TRACK, PROBE)
    wrong_request = expected.model_copy(update={"request_sha256": "9" * 64})
    result = run(edition, normative(edition, manifest, raw, wrong_request), {key: encode(v3)},
                 semantic_manifest=manifest, requirements_raw=raw)
    assert result["conformance"][0]["state"] == "invalid"
    assert "evidence.request-pin" in result["conformance"][0]["violations"]
    wrong_inventory = run(edition, normative(edition, manifest, raw, expected, requirements_pin="0" * 64),
        {key: encode(v3)}, semantic_manifest=manifest, requirements_raw=raw)
    assert wrong_inventory["normative"]["authority_valid"] is False
    assert wrong_inventory["normative"]["status"] == "authority-invalid"
    # No denominator is taken from unapproved inventory bytes; it is withheld, not shrunk.
    assert wrong_inventory["normative"]["required_counts"] is None
    assert wrong_inventory["normative"]["tracks"] == {}
    assert wrong_inventory["conformance"][0]["creditable"] is False
    authority = normative(edition, manifest, raw, expected)
    with pytest.raises(EvidenceRejected):
        verify_producer_bindings(edition, authority, expected_authority_sha256="0" * 64,
            catalog_documents={}, conformance_documents={}, semantic_manifest=manifest, requirements_raw=raw)


@pytest.mark.parametrize("scope", ["component-diagnostic", "mock-diagnostic"])
def test_component_scope_gets_no_platform_credit(scope):
    """what_bug_this_catches: component/mock narratives upgraded into actual platform proof."""
    edition = memory_edition(sample())
    manifest, raw, _, v3, expected = records(scope=scope)
    result = run(edition, normative(edition, manifest, raw, expected),
        {probe_key(TRACK, PROBE): encode(v3)}, semantic_manifest=manifest, requirements_raw=raw)
    assert result["conformance"][0]["creditable"] is False
    rows = [row for row in result["normative"]["tracks"][TRACK]["requirements"] if PROBE in row["probe_ids"]]
    assert rows and all(row["status"] == "pending" for row in rows)
    assert all("component-or-nonplatform-scope" in row["pending_reasons"] for row in rows)
    assert result["full_platform_credit"] is False and result["normative"]["full_platform_credit"] is False


def test_legacy_authority_is_integrity_only_and_refuses_normative_resources():
    """what_bug_this_catches: legacy v1 authority keeping per-probe credit after the v3 upgrade."""
    edition = memory_edition(sample())
    manifest, raw, v1, _, expected = records(scope="actual-memory")
    authority = ProducerAuthority(schema_version=1, source_index_sha256=edition.authority.index_sha256,
                                  catalogs=(), conformance=(expected,))
    result = run(edition, authority, {PROBE: encode(v1)})
    assert result["mode"] == "legacy-v1-integrity-only"
    assert result["normative"]["status"] == "not-evaluated"
    assert result["conformance"][0]["creditable"] is False
    with pytest.raises(EvidenceRejected):
        run(edition, authority, {PROBE: encode(v1)}, semantic_manifest=manifest, requirements_raw=raw)


def test_public_status_is_finite_counts_and_survives_canonical_projection():
    """what_bug_this_catches: raw documents, probe IDs or violation text leaking into public status."""
    edition = memory_edition(sample())
    manifest, raw, _, v3, expected = records(scope="actual-memory")
    bindings = run(edition, normative(edition, manifest, raw, expected),
        {probe_key(TRACK, PROBE): encode(v3)}, semantic_manifest=manifest, requirements_raw=raw)
    status = project_normative_status(bindings)
    text = json.dumps(status)
    assert PROBE not in text and "source-configured" not in text and "violations" not in text
    assert status["required_requirements"] == sum(bindings["normative"]["required_counts"].values())
    assert status["per_probe_creditable_requirements"] + status["pending_requirements"] == status["required_requirements"]
    assert status["creditable_probes"] == 1 and status["full_platform_credit"] is False
    public = project_public_result({"rows": [], "normative_v3_status": status}).public["normative_v3_status"]
    assert public == status


def test_public_status_withholds_counts_when_unavailable_or_legacy():
    """what_bug_this_catches: unavailable inventory or legacy mode published as zero obligations."""
    edition = memory_edition(sample())
    manifest, raw, v1, v3, expected = records(scope="actual-memory")
    unavailable = project_normative_status(run(edition, normative(edition, manifest, raw, expected),
        {probe_key(TRACK, PROBE): encode(v3)}))
    assert unavailable["status"] == "requirements-unavailable"
    assert unavailable["required_requirements"] is None and unavailable["tracks"] is None
    legacy = ProducerAuthority(schema_version=1, source_index_sha256=edition.authority.index_sha256,
                               catalogs=(), conformance=(expected,))
    status = project_normative_status(run(edition, legacy, {PROBE: encode(v1)}))
    assert status["mode"] == "legacy-v1-integrity-only" and status["status"] == "not-evaluated"
    assert status["creditable_probes"] == 0 and status["required_requirements"] is None
    tampered = {**status, "full_platform_credit": True}
    assert project_public_result({"rows": [], "normative_v3_status": tampered}).public["normative_v3_status"]["full_platform_credit"] is None


def test_public_reason_whitelist_matches_bridge_reasons():
    """what_bug_this_catches: a new pending reason silently projected as an unknown private field."""
    from mcpsh.evidence.producers import PENDING_REASONS, STATUS_VERSION
    from mcpsh.evidence.public_projection import NORMATIVE_REASONS, NORMATIVE_STATUS

    assert PENDING_REASONS == NORMATIVE_REASONS
    assert NORMATIVE_STATUS["version"] == ("enum", (STATUS_VERSION,))
