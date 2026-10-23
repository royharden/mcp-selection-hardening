"""Descriptive per-task counts and family-clustered paired uncertainty."""

import math
import json
import random
from collections import defaultdict
from statistics import mean
from typing import Any


def wilson(successes: int, total: int) -> dict[str, Any]:
    if not 0 <= successes <= total:
        raise ValueError("invalid binomial counts")
    if total == 0:
        return {"numerator": 0, "denominator": 0, "rate": None, "low": None, "high": None}
    z = 1.959963984540054
    rate = successes / total
    denominator = 1 + z * z / total
    center = (rate + z * z / (2 * total)) / denominator
    radius = z * math.sqrt(rate * (1 - rate) / total + z * z / (4 * total * total)) / denominator
    return {"numerator": successes, "denominator": total, "rate": rate,
            "low": max(0.0, center - radius), "high": min(1.0, center + radius)}


def aggregate_outcomes(outcomes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for item in outcomes:
        groups[(item["selector"], item["condition"], item["cell"],
                item.get("utility_basis", "legacy-call-proxy-v1"))].append(item)
    summaries = []
    for (selector, condition, cell, utility_basis), rows in sorted(groups.items()):
        observable = [row for row in rows if row["observation_complete"]]
        observed = sum(row["effect"] == "observed" for row in rows)
        observed_complete = sum(row["effect"] == "observed" for row in observable)
        attempts = sum(row["validated_prohibited_attempts"] for row in rows)
        blocks = sum(row["blocked_prohibited_calls"] for row in rows)
        latency = sorted(row["latency_seconds"] for row in rows)
        percentile = lambda q: latency[max(0, math.ceil(q * len(latency)) - 1)]
        summaries.append({
            "selector": selector, "condition": condition, "cell": cell,
            "scheduled_trials": len(rows), "raw_calls": sum(row["call_count"] for row in rows),
            "selected_calls_recorded": sum(row.get("selected_call_count") or 0 for row in rows),
            "unknown_selected_count_trials": sum(row.get("selected_call_count") is None for row in rows),
            "incomplete_selection_journals": sum(row.get("selection_journal_complete") is not True
                                                 for row in rows),
            "selection": wilson(sum(row["selection_success"] for row in rows), len(rows)),
            # All-scheduled success lower bound; unknowns are disclosed, not converted
            # into known negative judgments or dropped from the denominator.
            "utility": wilson(sum(row["utility_success"] is True for row in rows), len(rows)),
            "utility_basis": utility_basis,
            "utility_unknown_trials": sum(row["utility_success"] is None for row in rows),
            "utility_known": wilson(sum(row["utility_success"] is True for row in rows),
                                    sum(row["utility_success"] is not None for row in rows)),
            "intent": wilson(sum(row["prohibited_intent"] for row in rows), len(rows)),
            "validated_prohibited_calls": attempts, "blocked_prohibited_calls": blocks,
            "block_coverage": None if attempts == 0 else blocks / attempts,
            "gate_false_negative_calls": sum(row["gate_false_negative_calls"] for row in rows),
            "effects_observed": observed, "effects_unknown": sum(
                row["effect"] == "unknown" for row in rows),
            "incomplete_observations": len(rows) - len(observable),
            "effect_observable": wilson(observed_complete, len(observable)),
            "effect_all_scheduled_lower_bound": observed / len(rows),
            "failed_trials": sum(bool(row["failures"]) for row in rows),
            "family_count": len({row["family_id"] for row in rows}),
            "p50_seconds": percentile(0.5), "p95_seconds": percentile(0.95),
            "cost_microunits": sum(row["cost_microunits"] or 0 for row in rows),
            "unknown_cost_trials": sum(row["cost_microunits"] is None for row in rows),
            "cost_basis": sorted({row.get("cost_basis", "unknown") for row in rows}),
            "interval_kind": "95% descriptive Wilson; repeated variants clustered",
        })
    return summaries


def _resample_family_deltas(deltas: list[float], seed: int) -> dict[str, float]:
    """Shared existing percentile-bootstrap math; fixed 10,000 whole-family draws."""
    rng = random.Random(seed)
    estimates = sorted(mean(rng.choices(deltas, k=len(deltas))) for _ in range(10000))
    return {"difference": mean(deltas), "low": estimates[250], "high": estimates[9750]}


def compare_paired_families(design, *, scored_outcomes, observed_rows, before: str,
                            after: str, metric: str = "utility_success", models=None,
                            conditions=None, family_support=None,
                            expected_family_support_sha256: str | None = None,
                            independence_authenticated: bool = False):
    """Strict paired family-cluster comparison over all externally scheduled evidence.

    Family-support authentication is a trusted caller decision, never inferred from
    a supplied hash or a unique label. This function performs no authentication/I/O.
    """
    from .design import PairedComparison, audit_schedule, pairing_inputs, record_hash

    audit = audit_schedule(design, scored_outcomes=scored_outcomes, observed_rows=observed_rows)
    selected_models = tuple(design.model_family_by_id) if models is None else models
    selected_conditions = ("clean", "ambiguous", "poisoned") if conditions is None else conditions
    # Validate selector/metric arguments even when evidence is incomplete.
    inputs = pairing_inputs(design, observed_rows, before=before, after=after, metric=metric,
                            models=selected_models, conditions=selected_conditions)
    base = {"audit": audit, "before": before, "after": after, "metric": metric,
            "seed": design.seed, "models": selected_models, "conditions": selected_conditions,
            "expected_pairs": inputs["expected_pairs"], "family_label_count": 0,
            "supported_observable_families": 0, "support_binding": "absent",
            "missing_pair_members": inputs["missing_pair_members"],
            "unknown_pair_members": inputs["unknown_pair_members"],
            "failed_pair_members": audit.failed_scored_rows,
            "legacy_utility_pair_members": audit.utility_basis_counts.get("legacy-call-proxy-v1", 0)
            if metric == "utility_success" else 0}
    if audit.status != "complete":
        return PairedComparison(**base, interpretation="incomplete")
    inputs = pairing_inputs(design, observed_rows, before=before, after=after, metric=metric,
                            models=selected_models, conditions=selected_conditions)
    base.update({key: inputs[key] for key in ("expected_pairs", "missing_pair_members",
                "unknown_pair_members", "failed_pair_members", "legacy_utility_pair_members")})
    families = inputs["families"]
    base["family_label_count"] = len(families)
    support = "absent"
    supported = set()
    if family_support is not None:
        declared = family_support.supported_family_ids
        if (family_support.schedule_sha256 != record_hash(design)
                or record_hash(family_support) != expected_family_support_sha256
                or len(declared) != len(set(declared)) or set(declared) - set(families)):
            support = "invalid"
        else:
            support = "verified" if independence_authenticated else "pinned-unverified"
            if independence_authenticated:
                supported = set(declared)
    base.update(support_binding=support, supported_observable_families=len(supported))
    descriptive = {}
    for cell, values in inputs["values"].items():
        known = [value for value in values if value is not None]
        successes = sum(value is True for value in known)
        descriptive[cell] = {"kind": "descriptive-Wilson-not-cluster-inference",
            "known": wilson(successes, len(known)), "scheduled_denominator": inputs["expected_pairs"],
            "unknown_members": inputs["expected_pairs"] - len(known),
            "all_scheduled_success_lower_bound": successes / inputs["expected_pairs"]
            if inputs["expected_pairs"] else None}
    if (inputs["missing_pair_members"] or inputs["unknown_pair_members"]
            or inputs["failed_pair_members"] or inputs["legacy_utility_pair_members"]):
        return PairedComparison(**base, descriptive=descriptive,
                                interpretation="legacy-proxy" if inputs["legacy_utility_pair_members"]
                                else "incomplete")
    deltas = [mean(families[family]) for family in sorted(families) if families[family]]
    if not deltas:
        return PairedComparison(**base, descriptive=descriptive, interpretation="incomplete")
    interval = _resample_family_deltas(deltas, design.seed)
    interpretation = ("family-paired" if len(supported) >= 20 and supported == set(families)
                      and support == "verified" else "exploratory")
    return PairedComparison(**base, **interval, descriptive=descriptive, interpretation=interpretation)


def paired_family_bootstrap(outcomes: list[dict[str, Any]], *, before: str, after: str,
                            metric: str = "utility_success", seed: int = 1729,
                            resamples: int = 10000, design=None, observed_rows=None,
                            family_support=None, expected_family_support_sha256=None,
                            independence_authenticated: bool = False) -> dict[str, Any]:
    """Compatible entry point; outcome-only legacy rows cannot establish pairing.

    Repeat IDs/platform metadata must come from the explicit observed-row contract.
    No repeat is guessed from a trial ID or supplied by looking at the design.
    """
    if metric not in ("utility_success", "selection_success", "prohibited_intent", "effect_observed"):
        raise ValueError("unsupported paired metric")
    if resamples != 10000:
        raise ValueError("paired-family-cluster-v2 fixes 10000 resamples")
    if design is not None and observed_rows is not None:
        from mcpsh.records import TrialOutcome

        if seed != design.seed:
            raise ValueError("comparison seed differs from pinned design")
        scored = tuple(row if type(row) is TrialOutcome else TrialOutcome.model_validate_json(
            json.dumps(row)) for row in outcomes)
        report = compare_paired_families(design, scored_outcomes=scored,
            observed_rows=observed_rows, before=before, after=after, metric=metric,
            family_support=family_support, expected_family_support_sha256=expected_family_support_sha256,
            independence_authenticated=independence_authenticated).model_dump(mode="json")
        return {**report, "family_count": report["family_label_count"],
                "missing_pairs": report["missing_pair_members"],
                "unknown_metric_trials": report["unknown_pair_members"]}
    relevant = [row for row in outcomes if row.get("cell") in (before, after)]
    return {"version": "paired-family-cluster-v2", "before": before, "after": after,
            "metric": metric, "seed": seed, "resamples": 10000,
            "family_count": 0, "observed_family_labels": len({row.get("family_id") for row in relevant}),
            "missing_pairs": None, "unknown_metric_trials": sum(row.get(metric) is None for row in relevant),
            "utility_bases": sorted({row.get("utility_basis", "legacy-call-proxy-v1") for row in relevant}),
            "interpretation": "incomplete", "difference": None, "low": None, "high": None,
            "limitation": "Explicit external schedule and private repeat/platform metadata are required."}
