"""Public producer reconciliation regression SOURCE; never run in Dirty Mode."""

import json

from mcpsh.evidence.public_projection import project_public_result


def test_full36_missing_semantics_keeps_scheduled_denominators_and_draft_pins():
    # what_bug_this_catches: development-summary producer fields silently omitted.
    result = {"rows": [], "summary": [], "execution_state": "development-summary-draft",
        "development_summary": {"scheduled_slots": 1944, "supplied_slots": 3,
            "missing_slots": 1941, "evidence_state": "incomplete", "dispatch_authorized": False,
            "groups": [{"scheduled": 36, "supplied": 1, "missing": 35,
                "semantic_known": 0, "semantic_unknown_or_proxy": 36, "condition": "clean",
                "cell": "C1", "task_class": "all", "selector": "model", "arm_slot": "private-arm"}]},
        "development_threshold_proposal": {"status": "approval-needed", "absolute_utility_floor": None,
            "independent_approval": None, "retention_decision": "pending", "rationale": "PRIVATE_RATIONALE"},
        "input_pins": {"plan_sha256": "a" * 64, "outcomes_sha256": "b" * 64, "failures_sha256": None}}
    public = project_public_result(result).public
    assert public["execution_state"] == "development-summary-draft"
    assert public["development_summary"]["scheduled_slots"] == 1944
    assert public["development_summary"]["groups"][0]["semantic_unknown_or_proxy"] == 36
    assert public["development_threshold_proposal"]["absolute_utility_floor"] is None
    assert public["input_pins"]["plan_sha256"] == "a" * 64
    assert "PRIVATE_RATIONALE" not in json.dumps(public)


def test_scripted_text_and_approval_private_while_replay_roles_and_fit_states_survive():
    # what_bug_this_catches: private raw replay text leaked or diagnostic roles dropped.
    private = "PRIVATE_SCRIPT_APPROVAL_BODY"
    result = {"rows": [{"outcome": {"trial_id": "t", "failures": ["observer_fault_unsupported"]},
        "replay_role": "diagnostic", "replay_episode_id": "private-episode",
        "observer_fault_status": "unsupported", "observer_fault_request": private,
        "scripted_responses": [{"provenance": "scripted-development-replay", "turn_id": 1,
            "scripted_response_sha256": "a" * 64, "final_response": {"available": True, "text": private}}]}],
        "summary": [], "replay_design": {"baseline_tasks": 36, "baseline_rows": 324,
            "control_rows": 108, "diagnostic_episodes": 4, "diagnostic_rows": 12},
        "token_fit_lineage": {"complete": False, "live_admission": False, "billing_verified": False,
            "attempts": [{"state": "unknown", "attempt_id": "a", "trial_id": "t",
                "approval": private, "body": private, "proof_sha256": "b" * 64}]}}
    public = project_public_result(result).public
    assert private not in json.dumps(public)
    assert public["rows"][0]["replay_role"] == "diagnostic"
    assert public["rows"][0]["observer_fault_status"] == "unsupported"
    assert public["rows"][0]["outcome"]["failures"] == ["observer_fault_unsupported"]
    assert public["replay_design"]["baseline_tasks"] == 36
    assert public["token_fit_lineage"]["attempts"][0]["state"] == "unknown"


def test_threshold_and_fit_status_preserve_safe_bindings_without_authority_or_family_text():
    # what_bug_this_catches: final publisher status disappearing or exposing private family/approval data.
    result = {"rows": [{"outcome": {"trial_id": "t"}, "platform_scope": "synthetic-memory",
        "model_family_id": "PRIVATE_FAMILY"}], "summary": [],
        "threshold_approval_status": {"version": "threshold-binding-v1", "disposition": "pending",
            "metadata_binding": "bound", "external_authorization": "not-confirmed",
            "context_sha256": "c" * 64, "runtime_authorized": False,
            "independent_product_acceptance": "pending", "raw_decision": "PRIVATE_APPROVAL"},
        "token_fit_status": {"version": "m5-token-fit-status-1", "status": "unknown", "complete": False,
            "attempts_total": 6, "attempts_verified": 0, "attempts_unknown": 6,
            "trials_without_attempts": 1, "journal_sha256": "d" * 64,
            "live_admission": False, "billing_verified": False}}
    public = project_public_result(result).public
    assert public["token_fit_status"]["attempts_unknown"] == 6
    assert public["token_fit_status"]["journal_sha256"] == "d" * 64
    assert public["threshold_approval_status"]["external_authorization"] == "not-confirmed"
    assert public["threshold_approval_status"]["runtime_authorized"] is False
    assert public["rows"][0]["platform_scope"] == "synthetic-memory"
    assert "PRIVATE_FAMILY" not in json.dumps(public)
    assert "PRIVATE_APPROVAL" not in json.dumps(public)
    result["threshold_approval_status"]["runtime_authorized"] = True
    result["token_fit_status"]["live_admission"] = True
    rejected_flags = project_public_result(result).public
    assert rejected_flags["threshold_approval_status"]["runtime_authorized"] is None
    assert rejected_flags["token_fit_status"]["live_admission"] is None


def test_ledger_projection_keeps_unknown_amounts_and_reuse_without_metadata_leak():
    # what_bug_this_catches: financial raw metadata leaked or unknowns recast as zero.
    private = "PRIVATE_LEDGER_METADATA"
    result = {"rows": [], "summary": [], "ledger_audit": {"scope": "read-only-authoritative-ledger-snapshot",
        "complete": False, "scheduled_trials": 36, "totals": {"unknown_attempts": 1,
            "recorded_known_microunits": 2, "committed_microunits": 20,
            "cost_basis": "recorded-ledger-amounts-not-provider-billing"},
        "attempts": [{"attempt_id": private, "recorded_microunits": None,
            "unknown_liability": True, "usage": {"text": private}, "billing_basis": "unknown"}],
        "operations": [{"id": private, "reserved": 20, "status": "cancelled",
            "reservation_retained": True, "metadata": {"token": private}}],
        "reuse": [{"new_charge_microunits": 0, "independent_new_sample": False}]}}
    public = project_public_result(result).public["ledger_audit"]
    assert private not in json.dumps(public)
    assert public["scheduled_trials"] == 36
    assert public["attempts"][0]["recorded_microunits"] is None
    assert public["operations"][0]["reservation_retained"] is True
    assert public["reuse"][0]["independent_new_sample"] is False


def test_dossier_and_ledger_status_views_retain_scheduled_unknown_counts():
    # what_bug_this_catches: new CLI views dropping entire pending evidence status objects.
    for state, key, value in (
        ("acceptance-dossier-draft", "acceptance_dossier_status", {
            "version": "verified-edition-acceptance-v1", "authority_binding": "pinned",
            "authentication": "unconfirmed", "recommendation": "collect-required-evidence",
            "scheduled_trials": 36, "supplied_outcomes": 35, "missing_trials": 1,
            "utility_basis_counts": {"semantic-v2": 35, "legacy-call-proxy-v1": 0},
            "runtime_authorized": False, "private_dossier": "PRIVATE_DOSSIER"}),
        ("ledger-audit-draft", "ledger_audit_status", {
            "version": "m5-ledger-audit-status-1", "status": "unknown", "scheduled_trials": 36,
            "unknown_liabilities": 1, "missing_attempts": 2, "retained_reservations": 1,
            "cost_bases": ["unknown", "dated-price-estimate"], "source_sha256": "a" * 64,
            "runtime_authorized": False, "database_mutated": False, "raw_db": "PRIVATE_DB"}),
    ):
        public = project_public_result({"rows": [], "summary": [], "execution_state": state, key: value}).public
        assert public["execution_state"] == state
        assert public[key]["scheduled_trials"] == 36
        assert public[key]["runtime_authorized"] is False
        assert "PRIVATE_" not in json.dumps(public)
