"""Authored detached consumer/import/resource compatibility regressions."""

import hashlib
import importlib.util
import json
from pathlib import Path

from mcpsh.conformance.consumer import inspect_bundle, inspect_consumer_evidence
from mcpsh.conformance.evidence import EvidenceContext, PIN_NAMES, build_evidence
from mcpsh.conformance.evidence_v2 import build_evidence_v2
from mcpsh.conformance.export import build_contract_bundle, packaged_bundle_inputs
from mcpsh.conformance.models import ProbeDefinition


def evidence(version=2, *, mixed=False):
    bundle = build_contract_bundle(packaged_bundle_inputs())
    manifest = json.loads(bundle.to_files()["contracts/required-cases-v1.json"])
    context = EvidenceContext("1" * 64, {name: "2" * 64 for name in PIN_NAMES})
    session = {"server_instance_id": "public-server", "trial_id": "public-trial", "child_pid": None,
               "fixture_id": "public-fixture", "fixture_payload_sha256": "3" * 64, "platform_scope": "synthetic-memory"}
    observation = {"trial_id": "public-trial", "observer_version": "public-observer", "complete": not mixed,
        "reset_verified": True, "sequence_complete": True, "wire_complete": True,
        "events": [{"trial_id": "public-trial", "epoch": "public-epoch", "sequence": 1}],
        "predicates": {"protected_read": "observed" if mixed else "none", "outbox_write": "unknown" if mixed else "none", "wire_disclosure": "unknown" if mixed else "none"}}
    frames = [{"direction": direction, "sequence": index, "request_key": "one", "sha256": "4" * 64,
        "bytes": 20, "response_expected": direction == "request"} for index, direction in enumerate(("request", "response"), 1)]
    probe = ProbeDefinition("allowed-read", "public control", ("synthetic-memory",), "allowed")
    record = build_evidence(context=context, probe=probe, track="synthetic-memory", session_binding=session,
        frames=frames, observation=observation, scope="component-diagnostic")
    if version == 2:
        record = build_evidence_v2(record, manifest=manifest, case_id=None, result={},
            actual_raw_arguments_sha256=None, actual_case_source_sha256=manifest["case_source_sha256"])
    raw = json.dumps(record, ensure_ascii=True, allow_nan=False).encode()
    selection = {"expected_evidence_sha256": hashlib.sha256(raw).hexdigest(), "expected_probe_id": "allowed-read",
        "expected_track": "synthetic-memory", "expected_request_sha256": context.request_sha256,
        "expected_source_pins": context.source_pins, "expected_server_instance_id": session["server_instance_id"],
        "expected_fixture_payload_sha256": session["fixture_payload_sha256"]}
    return bundle, manifest, raw, selection


def test_default_consumer_has_no_backend_activation(monkeypatch):
    # what_bug_this_catches: integrity inspection secretly starts a fixture/session.
    def forbidden(*args, **kwargs):
        raise AssertionError("backend activated")

    monkeypatch.setattr("mcpsh.conformance.backend.LocalSession.__init__", forbidden)
    bundle = build_contract_bundle(packaged_bundle_inputs())
    result = inspect_bundle(bundle.to_files(), expected_bundle_sha256=bundle.bundle_sha256,
        expected_manifest_sha256=bundle.manifest_sha256, expected_runtime_schema_sha256=bundle.runtime_schema_sha256)
    assert result["status"] == "integrity-only"
    assert result["conformance_acceptance"] == "pending"
    assert result["providers_used"] is False


def test_legacy_schema_remains_supported_without_semantic_credit():
    # what_bug_this_catches: v1 either breaks compatibility or is relabeled v2 proof.
    _, manifest, raw, selection = evidence(version=1)
    result = inspect_consumer_evidence(raw, selection, manifest=manifest, expected_manifest_sha256=manifest["manifest_sha256"])
    assert result["valid"] is True
    assert result["compatibility"] == "legacy-v1-integrity-only"
    assert result["creditable"] is False


def test_component_and_mixed_effect_attribution_survive_detached_check():
    # what_bug_this_catches: detached projection erases observed+unknown or upgrades diagnostics.
    _, manifest, raw, selection = evidence(mixed=True)
    result = inspect_consumer_evidence(raw, selection, manifest=manifest, expected_manifest_sha256=manifest["manifest_sha256"])
    assert result["scope"] == "component-diagnostic"
    assert result["creditable"] is False
    assert result["predicates"]["protected_read"] == "observed"


def test_detached_example_reports_missing_import_without_repair(capsys):
    # what_bug_this_catches: detached consumer silently installs deps or guesses checkout paths.
    path = Path(__file__).resolve().parents[2] / "examples/conformance_consumer.py"
    spec = importlib.util.spec_from_file_location("public_consumer_example", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    def unavailable():
        raise ImportError("not installed")

    code = module.main(["public-bundle", "--bundle-sha256", "1" * 64, "--manifest-sha256", "2" * 64,
        "--runtime-schema-sha256", "3" * 64], load_api=unavailable)
    result = json.loads(capsys.readouterr().out)
    assert code == 2 and result["status"] == "unavailable"
    assert result["installed_or_repaired"] is False


def test_detached_example_reports_missing_resource_without_guessing(capsys):
    # what_bug_this_catches: missing explicit artifacts are replaced with local/demo data.
    path = Path(__file__).resolve().parents[2] / "examples/conformance_consumer.py"
    spec = importlib.util.spec_from_file_location("public_consumer_resource_example", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    class Exports:
        @staticmethod
        def read_contract_bundle(*args, **kwargs):
            raise FileNotFoundError("explicit public artifact absent")

    code = module.main(["missing-public-bundle", "--bundle-sha256", "1" * 64,
        "--manifest-sha256", "2" * 64, "--runtime-schema-sha256", "3" * 64],
        load_api=lambda: (Exports, object()))
    result = json.loads(capsys.readouterr().out)
    assert code == 2 and result["status"] == "unavailable"
    assert result["installed_or_repaired"] is False
