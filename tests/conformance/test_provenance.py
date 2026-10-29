"""Authored closed-schema regressions; no execution/acceptance claims."""

from mcpsh.conformance.evidence import PIN_NAMES, digest, verify_evidence
from mcpsh.conformance.models import ConformanceReport, ProbeResult, Status


def document():
    record = {"schema_version": 1, "probe_id": "allowed-read", "track": "synthetic-memory",
        "scope": "actual-memory", "request_sha256": "1" * 64,
        "source_pins": {name: "2" * 64 for name in PIN_NAMES},
        "session": {"server_instance_id": "owned-one", "trial_id": "trial-one", "child_pid": None,
                    "fixture_id": "public-fixture", "fixture_payload_sha256": "3" * 64,
                    "platform_scope": "synthetic-memory"},
        "frames": [{"direction": "request", "sequence": 1, "request_key": "one", "sha256": "4" * 64, "bytes": 20, "response_expected": True},
                   {"direction": "response", "sequence": 2, "request_key": "one", "sha256": "5" * 64, "bytes": 40, "response_expected": False}],
        "observation": {"observer_version": "public-control-v1", "trial_id": "trial-one", "epoch": "epoch-one",
            "complete": True, "reset_verified": True, "sequence_complete": True, "wire_complete": True,
            "predicates": {"protected_read": "none", "outbox_write": "none", "wire_disclosure": "none"},
            "broker_event_count": 3, "last_sequence": 3, "events_sha256": "6" * 64}, "checks": {}}
    return seal(record)


def seal(record):
    record["record_sha256"] = digest({key: value for key, value in record.items() if key != "record_sha256"})
    return record


def verify(record):
    return verify_evidence(record, expected_probe_id="allowed-read", expected_track="synthetic-memory",
        expected_request_sha256="1" * 64, expected_source_pins={name: "2" * 64 for name in PIN_NAMES},
        expected_server_instance_id="owned-one", expected_fixture_payload_sha256="3" * 64)


def test_positive_structural_control():
    # what_bug_this_catches: verifier rejects every record and has no useful positive.
    assert verify(document())["creditable"] is True


def test_omitted_reply_cannot_earn_credit():
    # what_bug_this_catches: one good response hides an omitted second request.
    record = document()
    record["frames"].append({"direction": "request", "sequence": 3, "request_key": "two",
        "sha256": "7" * 64, "bytes": 10, "response_expected": True})
    result = verify(seal(record))
    assert result["creditable"] is False
    assert "frames.omitted-response" in result["violations"]


def test_wrong_broker_attribution_rejects():
    # what_bug_this_catches: another process/fixture observation satisfies this trial.
    record = document()
    record["observation"]["trial_id"] = "different-server"
    assert verify(seal(record))["valid"] is False


def test_component_control_is_diagnostic_only():
    # what_bug_this_catches: synthetic fault channel counted as actual backend proof.
    record = document()
    record["scope"] = "component-diagnostic"
    result = verify(seal(record))
    assert result["valid"] is True
    assert result["creditable"] is False


def test_mixed_observed_unknown_retains_known_effect():
    # what_bug_this_catches: incomplete observations erase an already witnessed leak.
    record = document()
    record["observation"]["complete"] = False
    record["observation"]["predicates"] = {"protected_read": "observed", "outbox_write": "unknown", "wire_disclosure": "unknown"}
    result = verify(seal(record))
    assert result["valid"] is True
    assert result["creditable"] is False
    assert result["predicates"]["protected_read"] == "observed"


def test_extra_raw_payload_field_is_rejected():
    # what_bug_this_catches: unknown fields bypass the bounded public projection.
    record = document()
    record["session"]["raw_fixture"] = "untrusted"
    assert verify(seal(record))["valid"] is False


def test_malformed_scope_returns_rejection_instead_of_crashing():
    # what_bug_this_catches: null scope escapes closed-schema validation by exception.
    record = document()
    record["scope"] = None
    assert verify(seal(record))["valid"] is False


def test_pass_status_without_provenance_never_completes_platform():
    # what_bug_this_catches: report aggregation ignores missing required source proof.
    report = ConformanceReport((ProbeResult("one", "synthetic-memory", Status.PASS, True, "ok"),),
        ("synthetic-memory",), ("one",), True, "public-approval")
    assert report.to_dict()["platforms"]["synthetic-memory"]["verdict"] == "pending"


def test_omitted_required_probe_cannot_be_hidden_by_full_suite_flag():
    # what_bug_this_catches: a report drops required rows after they were scheduled.
    report = ConformanceReport((ProbeResult("allowed-read", "synthetic-memory", Status.PASS,
        True, "ok", {"verification": {"creditable": True}}),), ("synthetic-memory",),
        ("allowed-read",), True, "public-approval")
    assert report.to_dict()["platforms"]["synthetic-memory"]["verdict"] == "pending"
