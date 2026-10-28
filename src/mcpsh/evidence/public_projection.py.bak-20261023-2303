"""Versioned, pure record allowlists for all public result views.

The private result remains authoritative. Unknown/private fields are not recursively
copied. This is a bounded projection contract, not universal confidentiality proof.
"""

from dataclasses import dataclass
import hashlib
import json
import math
import re

VERSION = "mcpsh-public-result-v1"
MAX_ROWS = 5000
MAX_ITEMS = 65536
MAX_STRING_BYTES = 1024 * 1024
MAX_PUBLIC_BYTES = 64 * 1024 * 1024
TOOLS = frozenset({"list_sources", "tail", "search", "read_range", "errors",
                   "recent_lines", "find_literal", "error_counts", "export_fixture"})
CONTROL_SELECTORS = frozenset({"scripted-replay", "scripted-development-replay", "keyword", "abstain", "deny-all"})
FAILURE_CODES = frozenset({"task_deadline_exceeded", "selector_invalid_call_batch", "selector_invalid_call",
    "observer_fault_unsupported", "token_fit_lineage_incomplete",
    "selector_invalid_call_types", "call_limit_exceeded", "turn_limit_reached", "observation_incomplete",
    "selected_response_unavailable", "selected_response_incomplete", "selected_batch_not_list",
    "selected_journal_count_cap", "selected_journal_byte_cap", "selected_batch_not_json",
    "selection_journal_unavailable_or_incomplete", "runner_stopped_before_dispatch",
    "selector_rejected_before_dispatch", "usage_unknown", "identity_drift", "rate_limit",
    "transient_transport", "selection_capture_incomplete", "reservation_overrun"})


class ProjectionRejected(ValueError):
    """Safe failure: retain private inputs; never publish a silently truncated edition."""


@dataclass(frozen=True)
class IdentifierDisclosure:
    namespace: str
    private_id: str
    public_label: str


@dataclass(frozen=True)
class ProjectionPolicy:
    scope: str = "strict"
    qualification: str | None = None
    input_pins: tuple[tuple[str, str], ...] = ()
    identifiers: tuple[IdentifierDisclosure, ...] = ()


@dataclass(frozen=True)
class PublicProjection:
    public: dict
    private_diagnostics: dict


def E(*values):
    return ("enum", values)


def A(namespace):
    return ("alias", namespace)


def L(spec):
    return ("list", spec)


def M(namespace, spec):
    return ("map", namespace, spec)


COUNT, NUMBER, BOOLEAN, HASH = "count", "number", "boolean", "hash"
EFFECT = E("none", "observed", "unknown")
BASIS = E("non-model", "dated-price-estimate", "provider-billed", "unknown")
UTILITY = E("semantic-v2", "legacy-call-proxy-v1")
METRIC = {"numerator": COUNT, "denominator": COUNT, "rate": NUMBER, "low": NUMBER,
          "high": NUMBER, "value": NUMBER, "status": E("available", "N/A", "unknown")}
OUTCOME = {
    "trial_id": A("trial"), "task_id": A("task"), "condition": E("clean", "ambiguous", "poisoned", "control"),
    "cell": E("C0", "C1", "C2", "control"), "selector": "selector",
    "execution_mode": E("replay", "live"), "provider_id": E("openai", "anthropic"),
    "model_id": A("model"), "model_attempt_ids": L(A("attempt")), "selection_success": BOOLEAN,
    "utility_success": BOOLEAN, "utility_status": E("success", "failure", "unknown"), "utility_basis": UTILITY,
    "utility_evidence_ids": L(A("utility-evidence")), "prohibited_intent": BOOLEAN,
    "validated_prohibited_attempts": COUNT, "gate_classified_prohibited_calls": COUNT,
    "blocked_prohibited_calls": COUNT, "gate_false_negative_calls": COUNT, "effect": EFFECT,
    "observation_complete": BOOLEAN, "scheduled": BOOLEAN, "call_count": COUNT,
    "selected_call_count": COUNT, "selected_calls_hash": HASH, "selection_journal_complete": BOOLEAN,
    "failures": L("failure"), "cost_microunits": COUNT,
    "cost_status": E("non-model", "settled", "unknown", "reserved"), "cost_basis": BASIS,
    "trace_hash": HASH, "observation_hash": HASH, "latency_seconds": NUMBER,
}
TRACE = {"trial_id": A("trial"), "turn_id": COUNT, "call_id": A("call"), "sequence": COUNT,
    "tool_name": "tool", "raw_hash": HASH, "typed_hash": HASH,
    "validation": E("valid", "invalid", "unavailable"),
    "gate_classification": E("prohibited", "permitted", "legitimate", "unknown"),
    "enforcement_mode": E("permissive", "hardened", "deny-all"),
    "gate_decision": E("allow", "deny", "not_evaluated", "unknown"),
    "dispatched": BOOLEAN, "executed": BOOLEAN, "output_hash": HASH,
    "model_attempt_id": A("attempt"), "selection_id": A("selection")}
SELECTED = {"trial_id": A("trial"), "turn_id": COUNT, "selection_id": A("selection"), "sequence": COUNT,
    "tool_name": "tool", "raw_arguments_hash": HASH, "raw_call_hash": HASH, "typed_hash": HASH,
    "validation": E("valid", "invalid", "unavailable"),
    "disposition": E("selected", "sent-to-server", "rejected-before-dispatch"),
    "rejection_reason": "failure", "server_call_id": A("call"), "model_attempt_id": A("attempt"),
    "provider_call_id": A("provider-call")}
PREDICATES = {key: EFFECT for key in ("protected_read", "wire_disclosure", "outbox_write")}
OBSERVATION = {"observer_version": A("version"), "trial_id": A("trial"),
    "fixture_payload_sha256": HASH, "platform_scope": E("synthetic-memory", "filesystem-posix"),
    "complete": BOOLEAN, "predicates": PREDICATES, "protected_read_count": COUNT,
    "before_hash": HASH, "after_hash": HASH, "sequence_complete": BOOLEAN,
    "wire_complete": BOOLEAN, "reset_verified": BOOLEAN, "fixture_reset_verified": BOOLEAN,
    "failure": "failure", "failures": L("failure")}
USAGE = {key: COUNT for key in ("prompt_tokens", "completion_tokens", "input_tokens", "output_tokens",
    "total_tokens", "cache_read_input_tokens", "cache_creation_input_tokens")}
USAGE.update(prompt_tokens_details={"cached_tokens": COUNT},
             completion_tokens_details={"reasoning_tokens": COUNT, "accepted_prediction_tokens": COUNT,
                                        "rejected_prediction_tokens": COUNT})
ATTEMPT = {"attempt_id": A("attempt"), "request_id": A("request"), "response_id": A("response"),
    "provider_id": E("openai", "anthropic"), "provider": E("openai", "anthropic"),
    "requested_model_id": A("model"), "returned_model_id": A("model"), "requested_model": A("model"),
    "returned_model": A("model"), "trial_id": A("trial"), "turn_id": COUNT,
    "status": E("admitted", "completed", "completed_usage_unknown", "identity_drift", "truncated_or_filtered",
                "selection_capture_incomplete", "invalid_or_failed_response", "rate_limit", "http_error",
                "transient_transport", "reservation_overrun", "sent", "prepared", "unknown", "settled"),
    "dispatch_status": E("not_started", "not_sent", "transport_entered_delivery_unknown", "response_received"),
    "usage": USAGE, "cost_microunits": COUNT, "cost_kind": BASIS, "cost_basis": BASIS,
    "settlement_reference": A("settlement"), "operation_id": A("operation"),
    "reserved_microunits": COUNT, "price_snapshot_hash": HASH}
FINAL = {"available": BOOLEAN, "complete": BOOLEAN,
    "stop_reason": E("stop", "end_turn", "stop_sequence", "refusal", "length", "max_tokens", "content_filter"),
    "model_attempt_id": A("attempt")}
CAPTURE = {"call_id": A("call"), "sequence": COUNT, "tool_name": "tool",
           "available": BOOLEAN, "output_hash": HASH, "model_attempt_id": A("attempt")}
REUSE = {"kind": E("reused-evidence"), "source_index_sha256": HASH, "source_manifest_sha256": HASH,
    "source_trial_id": A("trial"), "source_row_sha256": HASH, "source_outcome_sha256": HASH,
    "original_cost_microunits": COUNT, "original_cost_basis": BASIS,
    "new_charge_microunits": COUNT, "independent_new_sample": BOOLEAN}
ROW = {"outcome": OUTCOME, "repeat": COUNT, "trace": L(TRACE), "selected_calls": L(SELECTED),
    "selection_journal_complete": BOOLEAN, "observation": OBSERVATION,
    "model_attempts": L(ATTEMPT), "accounting_attempts": L(ATTEMPT), "accounting": L(ATTEMPT),
    "final_response": FINAL, "result_captures": L(CAPTURE), "reuse": REUSE,
    "catalog_hash": HASH, "fixture_payload_hash": HASH, "normalization_diff_hash": HASH,
    "scripted_response_sha256": HASH, "scripted_fixture_sha256": HASH,
    "final_response_hash": HASH, "matches_recorded_outcome": BOOLEAN,
    "reproduction_state": E("partial", "recomputed", "unknown"), "missing_evidence": L("failure")}
SCRIPTED = {"provenance": E("scripted-development-replay"), "episode_id": A("episode"),
    "scripted_fixture_sha256": HASH, "source_file_sha256": HASH, "turn_id": COUNT,
    "source_pin_basis": E("caller-declared-public-package-pin", "embedded-script-only"),
    "scripted_response_sha256": HASH, "episode_exhausted": BOOLEAN, "final_response": FINAL}
ROW.update(scripted_response=SCRIPTED, scripted_provenance=SCRIPTED)
ROW.update(scripted_responses=L(SCRIPTED), replay_role=E("baseline", "diagnostic", "control"),
    replay_episode_id=A("episode"), observer_fault_status=E("unsupported", "not-requested"),
    platform_scope=E("synthetic-memory", "filesystem-posix"), model_family_id=A("model-family"))
SUMMARY = {key: COUNT for key in ("scheduled_trials", "raw_calls", "selected_calls_recorded",
    "unknown_selected_count_trials", "incomplete_selection_journals", "utility_unknown_trials",
    "validated_prohibited_calls", "blocked_prohibited_calls", "gate_false_negative_calls", "effects_observed",
    "effects_unknown", "incomplete_observations", "failed_trials", "family_count", "cost_microunits", "unknown_cost_trials")}
SUMMARY.update(selector="selector", condition=OUTCOME["condition"], cell=OUTCOME["cell"], utility_basis=UTILITY,
    selection=METRIC, utility=METRIC, utility_known=METRIC, intent=METRIC, effect_observable=METRIC,
    block_coverage=NUMBER, effect_all_scheduled_lower_bound=NUMBER, p50_seconds=NUMBER, p95_seconds=NUMBER,
    cost_basis=L(BASIS))
PRICES = {key: COUNT for key in ("input_microunits_per_million", "output_microunits_per_million",
    "cached_read_microunits_per_million", "cache_creation_microunits_per_million")}
PRICES["snapshot_hash"] = HASH
MANIFEST = {key: HASH for key in ("code_hash", "lock_hash", "protocol_hash", "task_hash", "catalog_hash",
    "policy_hash", "scorer_hash", "observer_hash", "split_hash")}
MANIFEST.update(schema_version=COUNT, edition_id=A("edition"), mode=E("replay", "live"),
    platform_scope=E("synthetic-memory", "filesystem-posix"), seed=COUNT, model_ids=L(A("model")),
    returned_model_ids=L(A("model")), matrix=L(OUTCOME["cell"]), max_turns=COUNT, max_calls=COUNT,
    prices=M("model", PRICES), settings={"corpus_phase": E("development", "development-pilot", "heldout", "retired"),
        "repeats": COUNT, "live_requests": COUNT, "task_deadline_seconds": NUMBER,
        "fixtures_sha256": HASH, "treatments_sha256": HASH, "replay_episodes_sha256": HASH})
PAIRED = {"selector": "selector", "model_id": A("model"), "condition": OUTCOME["condition"],
    "before": OUTCOME["cell"], "after": OUTCOME["cell"],
    "metric": E("utility_success", "selection_success", "prohibited_intent"),
    **{key: COUNT for key in ("seed", "family_count", "missing_pairs", "resamples", "unknown_metric_trials")},
    "utility_bases": L(UTILITY), "interpretation": E("incomplete", "exploratory", "family-paired"),
    "difference": NUMBER, "low": NUMBER, "high": NUMBER}
LINT_COUNTS = {**{key: COUNT for key in ("TP", "FP", "FN", "TN", "scored")}, "precision": METRIC, "recall": METRIC}
LINT_RULE = {"unknown_labels": COUNT, "unreviewed_or_unconfirmed": COUNT,
    "provisional_all_labels": LINT_COUNTS, "confirmed_labels": LINT_COUNTS,
    "bypass_diagnostics": L({"case_id": A("lint-case"), "status": E("known", "unknown", "scored"),
        "classification": E("TP", "FP", "FN", "TN"), "detected": BOOLEAN})}
LINT_LABELS = {"version": A("version"), "lint_version": A("version"), "scheduled": COUNT, "unknown": COUNT,
    "per_rule": M("rule", LINT_RULE), "cases": L({"case_id": A("lint-case"), "rule": A("rule"),
        "kind": E("label", "bypass"), "status": E("scored", "unknown"), "classification": E("TP", "FP", "FN", "TN"),
        "review_status": E("confirmed", "unreviewed", "unconfirmed"), "detected": BOOLEAN})}
NORMALIZATION = {"version": A("version"), "normalizer_version": A("version"),
    "status": E("ineligible", "verified-source-invariants", "invalid-repair"),
    **{key: HASH for key in ("before_sha256", "after_sha256", "immutable_before_sha256", "immutable_after_sha256",
        "trusted_map_sha256", "schema_before_sha256", "schema_after_sha256")},
    "ids_before": L("tool"), "ids_after": L("tool"), "no_suppression": BOOLEAN,
    "input_unmutated": BOOLEAN, "metadata_only": BOOLEAN}
PILOT_ARM = {"arm_slot": A("arm"), **{key: COUNT for key in ("scheduled_task_runs", "supplied_task_runs",
    "missing_task_runs", "known_utility_trials", "unknown_utility_trials", "successful_utility_trials",
    "model_outputs", "semantic_invalid_outputs", "request_attempts", "transport_failed_attempts")},
    **{key: NUMBER for key in ("semantic_invalid_rate", "transport_failure_rate", "bernoulli_utility_variance")},
    "utility_wilson": METRIC, "proposes_five_repeats": BOOLEAN, "requires_transport_repair": BOOLEAN}
PILOT = {"schema_version": COUNT, "evidence_state": E("no-evidence", "incomplete", "supplied-complete"),
    "execution_mode": E("replay", "live"), "manifest_sha256": HASH, "input_evidence_sha256": HASH,
    "arms": L(PILOT_ARM), "proposed_repeats_for_both_arms": COUNT, "absolute_utility_floor": NUMBER,
    "dispatch_authorized": BOOLEAN}
THRESHOLD = {"schema_version": COUNT, "status": E("approval-needed"), "absolute_utility_floor": NUMBER,
    "paired_retention_margin": NUMBER, "full_development_cases_required": COUNT,
    "proposed_repeats_for_both_arms": COUNT, "pilot_summary_sha256": HASH, "dispatch_authorized": BOOLEAN}
DEVELOPMENT_GROUP = {key: COUNT for key in ("scheduled", "supplied", "missing", "semantic_known",
    "semantic_successes", "semantic_unknown_or_proxy", "legacy_proxy_trials", "legacy_proxy_successes",
    "failed_trials", "scheduled_failure_records", "unknown_cost_trials", "incomplete_observations",
    "unknown_selection_trials")}
DEVELOPMENT_GROUP.update(arm_slot=A("arm"), selector="selector", condition=OUTCOME["condition"],
    cell=OUTCOME["cell"], task_class=E("all", "discovery", "tail", "search", "range", "error_inspection", "no_tool"),
    all_scheduled_utility_lower_bound=NUMBER, known_semantic_utility=METRIC)
DEVELOPMENT = {key: COUNT for key in ("schema_version", "scheduled_slots", "supplied_slots", "missing_slots",
    "failed_slots", "unknown_cost_slots", "incomplete_observation_slots", "proposed_repeats_for_both_arms")}
DEVELOPMENT.update(evidence_state=PILOT["evidence_state"], plan_sha256=HASH, settings_sha256=HASH,
    outcomes_sha256=HASH, groups=L(DEVELOPMENT_GROUP),
    repeat_diagnostics=M("arm", {key: PILOT_ARM[key] for key in ("semantic_invalid_rate", "transport_failure_rate",
        "bernoulli_utility_variance", "proposes_five_repeats", "requires_transport_repair")}),
    paired_retention=L({"arm_slot": A("arm"), "interval": PAIRED,
        "decision": E("pending", "inconclusive", "fail", "pass"),
        "family_independence": E("not-established-public-development")}),
    next_action=E("collect-development-evidence", "repair-and-repilot", "request-repeat-approval", "request-independent-floor-review"),
    absolute_utility_floor=NUMBER, independent_approval=E(), dispatch_authorized="false-only")
DEVELOPMENT["repeat_diagnostics"][2]["missing_attempt_counter_rows"] = COUNT
DEVELOPMENT_THRESHOLD = {"status": E("approval-needed"), "plan_sha256": HASH,
    "settings_sha256": HASH, "full36_summary_sha256": HASH, "outcomes_sha256": HASH,
    "absolute_utility_floor": NUMBER, "proposed_repeats_for_both_arms": COUNT,
    "independent_approval": E(), "retention_decision": E("pending", "inconclusive", "fail", "pass"),
    "uncertainty_rule": E("pending-independent-approval")}
LEDGER_AUDIT = {"schema_version": COUNT, "scope": E("read-only-authoritative-ledger-snapshot"),
    "complete": BOOLEAN, "experiment_id": A("experiment"), "source_sha256": HASH,
    "edition_index_sha256": HASH, "logical_snapshot_sha256": HASH, "snapshot_pin_matches": BOOLEAN,
    "snapshot_kind": E("read-transaction", "immutable-file"), "concurrent_change_observed": BOOLEAN,
    "freshness_claim": "false-only", "database_mutated": "false-only", "publication_performed": "false-only",
    "scheduled_trials": COUNT, "diagnostics": L("failure"), "missing_attempt_ids": L(A("attempt")),
    "unallocated_dispatch_attempt_ids": L(A("attempt")),
    "totals": {**{key: COUNT for key in ("budget_microunits", "recorded_known_microunits", "committed_microunits",
        "available_microunits", "unknown_attempts")}, "cost_basis": E("recorded-ledger-amounts-not-provider-billing")},
    "operations": L({"id": A("operation"), "reserved": COUNT,
        "status": E("reserved", "inflight", "finished", "overrun", "cancelled"),
        "known_recorded_microunits": COUNT, "unknown_attempts": COUNT, "reservation_retained": BOOLEAN,
        "reasons": L("failure")}),
    "attempts": L({"attempt_id": A("attempt"), "operation_id": A("operation"),
        "provider": E("openai", "anthropic"), "model_id": A("model"),
        "ledger_status": E("prepared", "sent", "unknown", "settled", "retryable"),
        "dispatch_recorded": BOOLEAN, "dispatch_scope": A("dispatch-scope"),
        "trial_id": A("trial"), "task_id": A("task"), "turn_id": COUNT,
        "recorded_microunits": COUNT, "recorded_cost_basis": BASIS, "price_snapshot_hash": HASH,
        "unknown_liability": BOOLEAN, "billed_microunits": COUNT, "billing_receipt_sha256": HASH,
        "billing_basis": BASIS, "state": E("verified-snapshot-row", "unknown"), "reasons": L("failure")}),
    "reuse": L({"trial_id": A("trial"), "task_id": A("task"), "source_index_sha256": HASH,
        "source_trial_id": A("trial"), "original_cost_microunits": COUNT, "original_cost_basis": BASIS,
        "new_charge_microunits": COUNT, "independent_new_sample": "false-only"}),
    "trial_audit": L({"trial_id": A("trial"), "task_id": A("task"), "model_id": A("model"),
        "attempt_ids": L(A("attempt")), "recorded_outcome_cost_microunits": COUNT,
        "recorded_outcome_cost_basis": BASIS, "reused_evidence": BOOLEAN,
        "independent_new_sample": "false-only", "ledger_missing_attempt_ids": L(A("attempt"))}),
    "non_model": L({"id": A("non-model-event"), "category": E("replay", "keyword", "abstain")}),
    "dispatches": L({"attempt_id": A("attempt"), "scope": A("dispatch-scope")}),
    "dispatch_stops": L({"reason": "failure"})}
NORMATIVE_REASONS = ("requirements-authority-invalid", "unselected", "missing-evidence", "invalid-evidence",
                     "component-or-nonplatform-scope", "incomplete-or-unknown-observation")
NORMATIVE_TRACK = {"required_scope": E("actual-memory", "actual-posix", "actual-stdio"),
    **{key: COUNT for key in ("required_requirements", "per_probe_creditable_requirements",
                              "pending_requirements", "selected_probe_count")},
    "pending_reason_counts": {key: COUNT for key in NORMATIVE_REASONS}, "verdict": E("pending")}
# Mirrors evidence.producers.project_normative_status; finite counts/bases/pins, no documents.
NORMATIVE_STATUS = {"version": E("m5-normative-v3-status-1"),
    "mode": E("normative-v3", "legacy-v1-integrity-only"),
    "status": E("evaluated", "authority-invalid", "requirements-unavailable", "not-evaluated"),
    "basis": E("fixed-normative-inventory", "legacy-v1-authority"),
    "inventory_version": E("m5-conformance-boundaries-v1"),
    **{key: HASH for key in ("inventory_sha256", "requirements_manifest_sha256", "semantic_manifest_sha256",
                             "source_index_sha256", "authority_sha256")},
    "authority_valid": BOOLEAN,
    **{key: COUNT for key in ("selected_probe_count", "unmapped_selected_probes", "creditable_probes",
        "required_requirements", "per_probe_creditable_requirements", "pending_requirements")},
    "probe_states": {key: COUNT for key in ("verified", "invalid", "unknown")},
    "tracks": {track: NORMATIVE_TRACK for track in ("synthetic-memory", "filesystem-posix", "stdio")},
    "full_platform_credit": "false-only", "suite_acceptance": E("pending"), "product_verdict": E("pending")}
ACCEPTANCE = {"schema_version": COUNT, "manifest_sha256": HASH, "outcomes_sha256": HASH,
    "recommendation": E("do-not-accept", "collect-required-evidence", "exploratory-only", "eligible-for-independent-review"),
    "independent_product_acceptance": E("pending"), "criteria": L({"criterion_id": A("criterion"),
        "verdict": E("pass", "fail", "inconclusive", "pending"), "reason": "failure"})}
ACTION = {"source_trial_id": A("trial"), "target_trial_id": A("trial"),
    "action": E("reuse", "dispatch-unstarted", "successor-rerun"), "state": E("proposed", "pending"),
    "source_row_sha256": HASH, "independent_new_sample": BOOLEAN, "new_reservation_microunits": COUNT,
    "new_charge_microunits": COUNT, "reasons": L("failure")}
RESUME = {"schema_version": COUNT, "plan_id": HASH, "parent_index_sha256": HASH, "authority_sha256": HASH,
    "target_manifest_sha256": HASH, "state": E("proposal-ready", "pending"), "actions": L(ACTION),
    "unresolved_attempt_ids": L(A("attempt")), "original_known_cost_microunits": COUNT,
    "original_unknown_cost_trial_ids": L(A("trial")), "unattributed_unknown_trial_ids": L(A("trial")),
    "proposed_new_reservation_microunits": COUNT, "dispatch_performed": BOOLEAN, "publication_performed": BOOLEAN,
    "reasons": L("failure"), "retained_trials": L({"trial_id": A("trial"), "task_id": A("task"),
        "condition": OUTCOME["condition"], "cell": OUTCOME["cell"], "selector": "selector",
        "model_id": A("model"), "repeat": COUNT, "source_row_sha256": HASH,
        "original_outcome_sha256": HASH, "selected_calls_hash": HASH,
        "model_attempt_ids": L(A("attempt")), "observation_hash": HASH,
        "cost_microunits": COUNT, "cost_basis": BASIS, "failed": BOOLEAN})}


class _Projector:
    def __init__(self, grants):
        self.grants = grants
        self.aliases, self.issues = [], []
        self.issue_count = 0
        self.alias_count = 0
        self.nodes = 0

    def issue(self, path, code):
        self.issue_count += 1
        if len(self.issues) < 2000:
            self.issues.append({"private_path": path[:1024], "code": code})

    def digest(self, value):
        if type(value) is str:
            raw = value.encode("utf-8", errors="surrogatepass")
        else:
            try:
                raw = json.dumps(value, ensure_ascii=True, sort_keys=True, allow_nan=False).encode()
            except (ValueError, TypeError, RecursionError):
                raw = b"unsupported-json-identity"
        if len(raw) > MAX_STRING_BYTES:
            raise ProjectionRejected("identity exceeds projection byte cap")
        return hashlib.sha256(raw).hexdigest()

    def alias(self, value, namespace):
        if value is None:
            return None
        fingerprint = self.digest(value)
        alias = self.grants.get((namespace, value)) if type(value) is str else None
        alias = alias or namespace + "-" + fingerprint
        self.alias_count += 1
        if len(self.aliases) < 20000:
            self.aliases.append({"namespace": namespace, "alias": alias,
                                 "private_id": value if type(value) is str else None, "sha256": fingerprint})
        return alias

    def field(self, value, spec, path):
        self.nodes += 1
        if self.nodes > 2000000:
            raise ProjectionRejected("projection node cap exceeded")
        if isinstance(spec, dict):
            if value is None:
                return None
            if type(value) is not dict:
                self.issue(path, "record-unavailable")
                return {key: self.field(None, child, path + "." + key) for key, child in spec.items()}
            for key in value.keys() - spec.keys():
                self.issue(path + "." + (key if type(key) is str else "non-string-key"), "private-or-unknown-field")
            return {key: self.field(value.get(key), child, path + "." + key) for key, child in spec.items()}
        if type(spec) is tuple:
            kind = spec[0]
            if kind == "alias":
                return self.alias(value, spec[1])
            if kind == "enum":
                if value is None:
                    return None
                if type(value) is str and value in spec[1]:
                    return value
                self.issue(path, "unrecognized-enum")
                return "unknown"
            if kind == "list":
                if value is None:
                    return None
                if type(value) not in (list, tuple) or len(value) > MAX_ITEMS:
                    raise ProjectionRejected("public list is malformed or exceeds cap")
                return [self.field(item if not isinstance(spec[1], dict) or type(item) is dict else {},
                                   spec[1], path + f"[{number}]") for number, item in enumerate(value)]
            if kind == "map":
                if value is None:
                    return None
                if type(value) is not dict or len(value) > MAX_ITEMS:
                    raise ProjectionRejected("public map is malformed or exceeds cap")
                if any(type(key) is not str for key in value):
                    raise ProjectionRejected("public identity map requires string keys")
                return {self.alias(key, spec[1]): self.field(item if not isinstance(spec[2], dict) or type(item) is dict else {},
                                                            spec[2], path + ".private-key")
                        for key, item in value.items()}
        if value is None:
            return None
        if spec == "false-only":
            valid = value is False
        elif spec == BOOLEAN:
            valid = type(value) is bool
        elif spec == COUNT:
            valid = type(value) is int and 0 <= value <= 2**63 - 1
        elif spec == NUMBER:
            valid = (type(value) is int and abs(value) <= 2**63 - 1) or (type(value) is float and math.isfinite(value))
        elif spec == HASH:
            valid = type(value) is str and re.fullmatch(r"[0-9a-f]{64}", value) is not None
        elif spec == "selector":
            return value if type(value) is str and value in CONTROL_SELECTORS else self.alias(value, "model")
        elif spec == "tool":
            return value if type(value) is str and value in TOOLS else self.alias(value, "tool")
        elif spec == "failure":
            if type(value) is str and value in FAILURE_CODES:
                return value
            if type(value) is str and value.startswith(("infrastructure:", "teardown:", "not_dispatched:", "live_dispatch_stopped:")):
                return value.split(":", 1)[0] + ":private-detail-" + self.digest(value)
            return "private-detail-" + self.digest(value)
        else:
            raise ProjectionRejected("unsupported projection schema")
        if not valid:
            self.issue(path, "invalid-scalar-retained-as-unknown")
            return None
        return value


def _qualified_grants(result, policy):
    manifest = result.get("manifest") if type(result.get("manifest")) is dict else {}
    settings = manifest.get("settings") if type(manifest.get("settings")) is dict else {}
    phase = settings.get("corpus_phase")
    if policy.scope == "strict":
        return {}, "strict"
    allowed_pins = {"task_hash", "split_hash", "catalog_hash"}
    if (policy.scope != "qualified-development" or policy.qualification != "public-development"
            or phase not in {"development", "development-pilot"} or not policy.input_pins
            or any(key not in allowed_pins or manifest.get(key) != value
                   or re.fullmatch(r"[0-9a-f]{64}", value) is None for key, value in policy.input_pins)):
        return {}, "strict-policy-fallback"
    grants = {}
    for grant in policy.identifiers:
        if grant.namespace not in {"task", "model", "trial", "edition", "arm", "rule"} or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,63}", grant.public_label) is None:
            raise ProjectionRejected("development identifier grant is malformed")
        key = (grant.namespace, grant.private_id)
        if key in grants or grant.public_label in grants.values():
            raise ProjectionRejected("duplicate development disclosure alias")
        grants[key] = grant.public_label
    return grants, "qualified-development"


def project_public_result(result: dict, *, policy: ProjectionPolicy | None = None,
                          fixture_map: dict | None = None) -> PublicProjection:
    """Preserve row/summary multiplicity and supplied metrics, never recompute scores."""
    if type(result) is not dict or "rows" not in result or type(result["rows"]) not in (list, tuple):
        raise ProjectionRejected("a structured result with explicit scheduled rows is required")
    rows, summaries = result.get("rows", []), result.get("summary", [])
    if len(rows) > MAX_ROWS or type(summaries) not in (list, tuple) or len(summaries) > MAX_ROWS:
        raise ProjectionRejected("result row/summary cap exceeded; private edition retained")
    grants, applied = _qualified_grants(result, policy or ProjectionPolicy())
    projector = _Projector(grants)
    public_rows = []
    for position, source in enumerate(rows):
        projected = projector.field(source if type(source) is dict else {}, ROW, f"rows[{position}]")
        if type(source) is not dict:
            projector.issue(f"rows[{position}]", "record-unavailable")
        if type(projected.get("outcome")) is not dict:
            projected["outcome"] = projector.field({}, OUTCOME, f"rows[{position}].outcome")
            projected["projection_error"] = "record-unavailable"
        if projected["outcome"].get("trial_id") is None:
            projected["outcome"]["trial_id"] = projector.alias(f"missing-row-{position}", "trial")
        public_rows.append(projected)
    root = {"schema_version": COUNT, "execution_state": E("replay-only", "partial", "live-complete",
        "reproduction-partial", "recomputed-offline", "pilot-summary-draft", "development-summary-draft",
        "acceptance-dossier-draft", "ledger-audit-draft"),
        "platform_scope": E("synthetic-memory", "filesystem-posix", "not-evaluated"),
        "development_only": BOOLEAN, "seed": COUNT, "live_model_runs": COUNT, "heldout_families": COUNT,
        "manifest": MANIFEST, "paired_comparisons": L(PAIRED), "raw_evidence_hash": HASH,
        "source_edition_sha256": HASH, "reproduction_evaluator_hash": HASH,
        "scheduled_trials": COUNT, "scored_trials": COUNT,
        "unknown_trials": L({"trial_id": A("trial"), "state": E("unknown", "partial"), "reasons": L("failure")}),
        "lint_controls": {"labels": LINT_LABELS, "normalization": {key: NORMALIZATION for key in ("clean", "ambiguous", "poisoned")},
            "inputs": {key: HASH for key in ("labels_sha256", "bypasses_sha256", "review_sha256")}},
        "pilot_summary": PILOT, "threshold_proposal": THRESHOLD, "acceptance_recommendation": ACCEPTANCE,
        "development_summary": DEVELOPMENT, "development_threshold_proposal": DEVELOPMENT_THRESHOLD,
        "threshold_approval_status": {"version": E("threshold-binding-v1"),
            "disposition": E("pending", "invalid", "eligible-for-separate-runtime-admission"),
            "metadata_binding": E("missing", "invalid", "bound"),
            "external_authorization": E("not-confirmed", "mismatched", "trusted-caller-confirmed"),
            "context_sha256": HASH, "reviewer_metadata_sha256": HASH, "integrator_metadata_sha256": HASH,
            "issue_codes": L("failure"), "approved_floor": NUMBER, "fresh_corpus_required": BOOLEAN,
            "runtime_authorized": "false-only", "independent_product_acceptance": E("pending")},
        "ledger_audit": LEDGER_AUDIT,
        "ledger_audit_status": {"version": E("m5-ledger-audit-status-1"),
            "status": E("verified-snapshot-only", "unknown"), "complete": BOOLEAN,
            **{key: HASH for key in ("edition_index_sha256", "source_sha256", "logical_snapshot_sha256")},
            "snapshot_pin_matches": BOOLEAN, "snapshot_kind": E("read-transaction", "immutable-file"),
            "concurrent_change_observed": BOOLEAN,
            **{key: COUNT for key in ("scheduled_trials", "attempts_total", "unknown_liabilities",
                "unallocated_attempts", "missing_attempts", "operations_total", "retained_reservations",
                "reuse_references", "non_model_events", "billed_attempts")},
            "cost_basis": E("recorded-ledger-amounts-not-provider-billing"), "cost_bases": L(BASIS),
            "freshness_claim": "false-only", "database_mutated": "false-only", "runtime_authorized": "false-only",
            "independent_product_acceptance": E("pending")},
        "acceptance_dossier_status": {"version": E("verified-edition-acceptance-v1"),
            "source_index_sha256": HASH, "authority_binding": E("missing", "mismatched", "pinned"),
            "authentication": E("unconfirmed", "trusted-caller-confirmed"), "inspection_complete": BOOLEAN,
            "recommendation": E("do-not-accept", "collect-required-evidence", "eligible-for-independent-review"),
            **{key: COUNT for key in ("scheduled_trials", "supplied_outcomes", "missing_trials")},
            "utility_basis_counts": {"semantic-v2": COUNT, "legacy-call-proxy-v1": COUNT},
            "runtime_authorized": "false-only", "independent_product_acceptance": E("pending")},
        "token_fit_status": {"version": E("m5-token-fit-status-1"),
            "status": E("verified-fit-only", "unknown"), "complete": BOOLEAN,
            **{key: COUNT for key in ("attempts_total", "attempts_verified", "attempts_unknown", "trials_without_attempts")},
            **{key: HASH for key in ("journal_sha256", "bundle_typed_sha256", "expectations_sha256")},
            "live_admission": "false-only", "billing_verified": "false-only"},
        "normative_v3_status": NORMATIVE_STATUS,
        "input_pins": {key: HASH for key in ("plan_sha256", "outcomes_sha256", "failures_sha256")},
        "development_input_pins": {"version": E("m5-dev-semantic-v2"), "manifest_sha256": HASH,
            "cases": COUNT, "episodes": COUNT, "scope": E("source-data-only; runtime-unverified"),
            "raw_sha256": {key: HASH for key in ("fixtures/dev/tasks.json", "gold/dev/oracles.json",
                "fixtures/dev/fixtures.json", "fixtures/dev/treatments.json", "fixtures/dev/replay-episodes.json",
                "fixtures/dev/corpus-manifest-v2.json")}},
        "replay_design": {key: COUNT for key in ("baseline_tasks", "baseline_rows", "control_rows",
            "diagnostic_episodes", "diagnostic_rows")},
        "token_fit_lineage": {"schema_version": COUNT, "scope": E("per-send-fit-lineage-only", "retrospective-fit-only"),
            "retrospective": BOOLEAN, "pre_send_admission_claim": "false-only", "complete": BOOLEAN,
            "live_admission": "false-only", "billing_verified": "false-only", "expectations_sha256": HASH,
            "attempts": L({"trial_id": A("trial"), "turn_id": COUNT, "attempt_id": A("attempt"),
                "state": E("unknown", "invalid", "verified-fit-only"), "reasons": L("failure"),
                "proof_sha256": HASH, "raw_request_sha256": HASH}),
            "unbound_events": L({"event_index": COUNT,
                "state": E("preflight-diagnostic", "unattributed-unknown"), "proof_sha256": HASH,
                "recorded_proof_status": E("fits", "exceeds", "unknown", "invalid"),
                "independently_verified": "false-only"}),
            "unallocated_attempt_ids": L(A("attempt")), "trials_without_attempts": L(A("trial"))},
        "resume_plan": RESUME}
    public = projector.field({key: value for key, value in result.items() if key not in {"rows", "summary"}}, root, "result")
    public.update(rows=public_rows, summary=[projector.field(row if type(row) is dict else {}, SUMMARY, f"summary[{i}]") for i, row in enumerate(summaries)],
        banner="MCP experiment evidence; independent acceptance pending", acceptance_verdict="pending",
        limitations=["Public record projection; original details remain private.",
                     "Unknown evidence remains unknown; structural integrity is not empirical acceptance.",
                     "Replay/live and memory/filesystem provenance remain distinct."],
        projection={"version": VERSION, "policy": applied, "rows_in": len(rows), "rows_out": len(public_rows),
                    "summary_in": len(summaries), "summary_out": len(summaries)})
    if public.get("development_threshold_proposal") is not None:
        public["development_threshold_proposal"]["proposal_authority"] = "unauthenticated-proposal"
    # Required render columns remain present; missing input metrics stay None, never zero.
    for row in public["summary"]:
        for key in ("selection", "utility", "intent"):
            if row[key] is None:
                row[key] = projector.field({}, METRIC, "summary.missing-metric")
    controls = public.get("lint_controls")
    if controls is None:
        public.pop("lint_controls", None)
    else:
        labels = controls.get("labels")
        if labels is None:
            controls["labels"] = {"per_rule": {}}
        elif labels.get("per_rule") is None:
            labels["per_rule"] = {}
        for record in controls["labels"]["per_rule"].values():
            for scope in ("provisional_all_labels", "confirmed_labels"):
                if record[scope] is None:
                    record[scope] = projector.field({}, LINT_COUNTS, "lint.missing-counts")
                for key in ("precision", "recall"):
                    if record[scope][key] is None:
                        record[scope][key] = projector.field({}, METRIC, "lint.missing-metric")
    from mcpsh.broker.fixtures import protected_sentinels
    from mcpsh.policy import redact
    from mcpsh.broker import SYNTHETIC_CANARY

    sentinels = [SYNTHETIC_CANARY]
    if fixture_map is not None:
        if type(fixture_map) is not dict or len(fixture_map) > 100:
            raise ProjectionRejected("trusted fixture map is malformed or exceeds cap")
        try:
            for payload in fixture_map.values():
                if payload is None:
                    raise ValueError("explicit trusted fixture payload required")
                sentinels.extend(protected_sentinels(payload))
        except (ValueError, TypeError, UnicodeError):
            raise ProjectionRejected("trusted fixture semantics could not be verified") from None

    fixed_words = set(TOOLS | CONTROL_SELECTORS)
    def register_fixed_words(spec):
        if isinstance(spec, dict):
            for child in spec.values():
                register_fixed_words(child)
        elif type(spec) is tuple:
            if spec[0] == "enum":
                fixed_words.update(spec[1])
            elif spec[0] == "list":
                register_fixed_words(spec[1])
            elif spec[0] == "map":
                register_fixed_words(spec[2])
    for schema in (root, ROW, SUMMARY):
        register_fixed_words(schema)

    def redact_values(value):
        if type(value) is str:
            redacted = redact(value, "hardened", tuple(sentinels))
            if redacted != value and value in fixed_words:
                raise ProjectionRejected("protected fixture text conflicts with a public enum")
            return redacted
        if type(value) is list:
            return [redact_values(item) for item in value]
        if type(value) is dict:
            if any(redact(key, "hardened", tuple(sentinels)) != key for key in value):
                raise ProjectionRejected("protected fixture text conflicts with public record keys")
            return {key: redact_values(item) for key, item in value.items()}
        return value
    public = redact_values(public)
    if len(json.dumps(public, ensure_ascii=True, allow_nan=False).encode()) > MAX_PUBLIC_BYTES:
        raise ProjectionRejected("public result byte cap exceeded; no partial publication")
    return PublicProjection(public, {"projection_version": VERSION, "policy_applied": applied,
        "private_identifier_links": projector.aliases, "private_field_diagnostics": projector.issues,
        "identifier_links_truncated": projector.alias_count > len(projector.aliases),
        "diagnostic_count": projector.issue_count, "source_rows": len(rows), "public_rows": len(public_rows),
        "source_summary_rows": len(summaries), "public_summary_rows": len(public["summary"]),
        "source_retained_unchanged": True})
