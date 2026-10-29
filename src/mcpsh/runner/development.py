"""Full36 protocol bridge to an explicitly admitted runner; no default dispatch."""

from dataclasses import dataclass
import json
from typing import Any, Callable

from mcpsh.calibration import (
    CalibrationOutcome, DevelopmentProtocolPlan, PilotObservation, ProtocolAdmission,
    ProtocolRun, execute_development_protocol,
)
from mcpsh.records import ExperimentManifest, OracleCase, PublicTaskCase, TrialOutcome, typed_hash

from .engine import run_trial


@dataclass(frozen=True)
class DevelopmentExecution:
    protocol_run: ProtocolRun
    private_rows: tuple[dict[str, Any], ...]


def execute_admitted_development_protocol(
    plan: DevelopmentProtocolPlan, *, admission: ProtocolAdmission, clock,
    manifest: ExperimentManifest, cases: dict[str, tuple[PublicTaskCase, OracleCase]],
    selector_factory: Callable[[str | None, str], Any],
    attempt_mapper: Callable[[Any, dict, Any], PilotObservation] | None = None,
    fixture_map: dict[str, dict] | None = None,
    filesystem_factory: Callable[[str, dict | None], dict] | None = None,
    row_sink: Callable[[Any, dict], None] | None = None,
) -> DevelopmentExecution:
    """Inject the existing guarded source runner into the frozen calibration API.

    No model/cost/output counters are guessed. A live model slot requires an
    explicit mapper over actual captured evidence; deterministic controls are
    always non-model replay. The calibration orchestrator checks closed Dirty
    Mode, pilot pins, expiry and scheduled provenance before each callback.
    """
    if not admission.authorized or not admission.dirty_mode_closed:
        raise ValueError("development callback execution requires a later explicit runtime grant")
    if manifest.mode != admission.execution_mode:
        raise ValueError("experiment and calibration execution provenance differ")
    if (manifest.seed, manifest.max_turns, manifest.max_calls) != (
        plan.settings.seed, plan.settings.maximum_turns, plan.settings.maximum_calls
    ) or manifest.settings.get("repeats", 3) != plan.settings.repeats:
        raise ValueError("admitted experiment settings differ from the full36 plan")
    if manifest.settings.get("development_input_sha256") != plan.development_input_sha256:
        raise ValueError("public development inventory differs from the admitted experiment")
    if set(cases) != {case.task_id for case in plan.cases}:
        raise ValueError("exact public full36 task/oracle join required")
    for task_id, (task, oracle) in cases.items():
        if task_id != task.task_id or task.task_id != oracle.task_id or oracle.split != "development":
            raise ValueError("calibration cannot load held-out/retired or mismatched labels")
        if oracle.utility_version != "semantic-v2" or oracle.utility_spec is None:
            raise ValueError("semantic-v2 development labels are required; no call-proxy promotion")
    if typed_hash([cases[case.task_id][0].model_dump(mode="json") for case in plan.cases]) != manifest.task_hash:
        raise ValueError("full36 public tasks differ from the admitted manifest")
    if fixture_map is not None and set(fixture_map) != {task.fixture_ref for task, _ in cases.values()}:
        raise ValueError("exact prevalidated synthetic fixture map is required")
    if manifest.mode == "live" and attempt_mapper is None:
        raise ValueError("live calibration requires actual typed attempt/output counters before dispatch")
    if manifest.mode == "live" and (fixture_map is None or admission.model_dispatch_approval_id != manifest.budget_receipt):
        raise ValueError("live calibration requires the already-admitted fixture map and dispatch receipt")
    if manifest.platform_scope == "filesystem-posix" and filesystem_factory is None:
        raise ValueError("fresh explicitly approved POSIX fixtures are required per slot")
    if manifest.platform_scope == "synthetic-memory" and filesystem_factory is not None:
        raise ValueError("memory calibration cannot receive a host filesystem factory")
    arms = {arm.slot: arm for arm in plan.arms}
    rows = []

    def callback(slot):
        from mcpsh.adapters import AbstainSelector, KeywordSelector
        from mcpsh.catalog.artifacts import build_catalog_artifact

        task, oracle = cases[slot.task_id]
        arm = arms[slot.arm_slot]
        artifact = build_catalog_artifact(slot.condition, ordering_seed=plan.settings.seed,
                                          normalized=slot.cell == "C2")
        if slot.selector == "model":
            selector = selector_factory(arm.model_id, slot.slot_id)
            execution_mode = manifest.mode
            selector_name = arm.model_id or slot.arm_slot
        else:
            selector = AbstainSelector() if slot.selector == "abstain" else KeywordSelector()
            execution_mode, selector_name = "replay", slot.selector
        payload = fixture_map[task.fixture_ref] if fixture_map is not None else None
        config = filesystem_factory(slot.slot_id, payload) if filesystem_factory else None
        mode = "deny-all" if slot.selector == "deny-all" else (
            "permissive" if slot.cell == "C0" else "hardened")
        row = run_trial(task=task, oracle=oracle, selector=selector, catalog=artifact["catalog"],
                        trial_id=slot.slot_id, condition=slot.condition, cell=slot.cell, mode=mode,
                        selector_name=selector_name, execution_mode=execution_mode,
                        max_turns=plan.settings.maximum_turns, max_calls=plan.settings.maximum_calls,
                        manifest=manifest if execution_mode == "live" else None,
                        platform_scope=manifest.platform_scope, filesystem_config=config,
                        fixture_payload=payload, repeat=slot.repeat)
        rows.append(row)
        if row_sink is not None:
            row_sink(slot, row)
        counters = None
        if slot.selector == "model" and attempt_mapper is not None:
            counters = attempt_mapper(slot, row, arm)
            if type(counters) is not PilotObservation or counters.evidence_sha256 != typed_hash(row):
                raise ValueError("typed attempt counters must bind the actual captured row")
        return CalibrationOutcome(slot_id=slot.slot_id, settings_sha256=plan.settings_sha256,
            evidence_sha256=typed_hash(row), outcome_sha256=typed_hash(row["outcome"]),
            outcome=TrialOutcome.model_validate_json(json.dumps(row["outcome"])),
            attempts=counters)

    result = execute_development_protocol(plan, runner=callback, admission=admission, clock=clock)
    return DevelopmentExecution(protocol_run=result, private_rows=tuple(rows))
