"""Keyless deterministic pilot design; no provider/runner/broker imports."""

from mcpsh.records import typed_hash

from .models import CLASSES, DevelopmentCase, DraftArm, DraftPilotManifest, ThresholdProposal


def plan_pilot(*, development_cases: tuple[DevelopmentCase, ...],
               development_input_sha256: str, arms: tuple[DraftArm, DraftArm] | None = None,
               selected_task_ids: tuple[str, ...] | None = None,
               seed: int = 1729) -> DraftPilotManifest:
    """Pick one public development case/class; held-out data is not accepted here."""
    if len(development_cases) != 36 or len({c.task_id for c in development_cases}) != 36:
        raise ValueError("the full 36-case public development inventory is required")
    by_id = {case.task_id: case for case in development_cases}
    counts = {name: sum(case.task_class == name for case in development_cases) for name in CLASSES}
    if any(count != 6 for count in counts.values()):
        raise ValueError("expected six development cases per declared class")
    if selected_task_ids is None:
        selected = tuple(min((c for c in development_cases if c.task_class == name),
                             key=lambda case: case.task_id) for name in CLASSES)
    else:
        if len(selected_task_ids) != 6 or len(set(selected_task_ids)) != 6:
            raise ValueError("exactly six unique development task IDs required")
        if set(selected_task_ids) - set(by_id):
            raise ValueError("selected case is outside the public development inventory")
        selected = tuple(by_id[task_id] for task_id in selected_task_ids)
    return DraftPilotManifest(
        arms=arms or (DraftArm(slot="arm-a"), DraftArm(slot="arm-b")),
        cases=selected, development_input_sha256=development_input_sha256, seed=seed,
    )


def planned_caps(manifest: DraftPilotManifest) -> dict[str, int | bool | str]:
    """Conservative planned counts, not usage, token fit, prices or approval."""
    runs = len(manifest.cases) * len(manifest.arms) * len(manifest.conditions) * len(
        manifest.cells) * manifest.repeats
    requests = runs * manifest.maximum_turns
    attempts = requests * (1 + manifest.maximum_retry_per_request)
    return {"basis": "planned-upper-bound-not-measured", "task_runs": runs,
            "maximum_model_requests": requests, "maximum_request_attempts": attempts,
            "input_token_reservation_upper_bound": attempts * manifest.planned_input_token_cap,
            "output_token_reservation_upper_bound": attempts * manifest.planned_output_token_cap,
            "token_fit_verified": False, "dispatch_authorized": False}


def threshold_proposal(summary=None) -> ThresholdProposal:
    """Never invent or auto-lower an absolute floor from poor pilot utility."""
    return ThresholdProposal(
        utility_floor_rationale=(
            "Pending full-36 public development semantic-utility evidence, task difficulty, "
            "legitimate no-tool cases, baseline/deny-all contrast and independent approval. "
            "Poor observed utility does not authorize lowering a floor. Pilot decisions "
            "propose repeats only; they do not approve the live matrix or held-out corpus."
        ),
        proposed_repeats_for_both_arms=3 if summary is None else summary.proposed_repeats_for_both_arms,
        pilot_summary_sha256=None if summary is None else typed_hash(summary.model_dump(mode="json")),
    )
