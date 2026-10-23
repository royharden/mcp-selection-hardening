"""Future injectable orchestration; no default runner, imports or dispatch backend."""

from collections.abc import Callable
from datetime import datetime

from mcpsh.records import typed_hash

from .protocol import validate_calibration_outcome, validate_protocol_plan
from .protocol_models import (
    CalibrationOutcome, CalibrationSlot, DevelopmentProtocolPlan,
    ProtocolAdmission, ProtocolFailure, ProtocolRun,
)


def execute_development_protocol(plan: DevelopmentProtocolPlan, *,
                                 runner: Callable[[CalibrationSlot], CalibrationOutcome],
                                 admission: ProtocolAdmission,
                                 clock: Callable[[], datetime]) -> ProtocolRun:
    """Only a later explicit grant may invoke an injected runner, including fakes.

    D1 owns actual runner/provider/fixture setup, per-attempt budget/identity checks
    and numeric publication. No callback was invoked during source construction.
    """
    validate_protocol_plan(plan)
    pin = typed_hash(plan.model_dump(mode="json"))
    expires = datetime.fromisoformat(admission.expires_at.replace("Z", "+00:00"))
    if (not admission.authorized or not admission.dirty_mode_closed or not admission.receipt_id
            or expires.tzinfo is None
            or admission.plan_sha256 != pin or admission.settings_sha256 != plan.settings_sha256
            or admission.pilot_summary_sha256 != plan.pilot_summary_sha256
            or plan.pilot_evidence_state != "supplied-complete" or plan.pilot_requires_transport_repair):
        raise ValueError("explicit current runtime grant and complete pinned pilot required before any callback")
    if admission.execution_mode == "live" and (
        not admission.model_dispatch_approval_id or plan.pilot_execution_mode != "live"
        or any(not arm.provider_id or not arm.model_id or not arm.family for arm in plan.arms)
    ):
        raise ValueError("live calibration needs separate actual model/budget admission and live pilot")
    results, failures = [], []
    stopped = False
    for slot in plan.slots:
        if stopped:
            failures.append(ProtocolFailure(slot_id=slot.slot_id, category="not-dispatched-after-stop"))
            continue
        try:
            now = clock()
            if now.tzinfo is None or now >= expires:
                raise ValueError("runtime admission expired before next scheduled slot")
            record = runner(slot)
            if type(record) is not CalibrationOutcome:
                raise ValueError("typed scored capture required")
            if record.slot_id != slot.slot_id:
                raise ValueError("runner returned evidence for another scheduled slot")
            validate_calibration_outcome(plan, record)
            if slot.selector == "model" and record.outcome.execution_mode != admission.execution_mode:
                raise ValueError("model execution provenance differs from admission")
            results.append(record)
            if (record.outcome.failures or not record.outcome.observation_complete
                    or record.outcome.utility_basis != "semantic-v2"
                    or record.outcome.utility_success is None
                    or record.outcome.selection_journal_complete is not True
                    or record.outcome.effect == "unknown"
                    or (slot.selector == "model" and record.attempts is None)
                    or record.outcome.cost_status in ("unknown", "reserved")):
                stopped = True
        except Exception as exc:
            failures.append(ProtocolFailure(slot_id=slot.slot_id, category=type(exc).__name__))
            stopped = True
    return ProtocolRun(plan_sha256=pin, outcomes=tuple(results), failures=tuple(failures),
                       state="partial" if stopped else "collected-not-accepted")
