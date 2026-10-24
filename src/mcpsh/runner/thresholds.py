"""Typed metadata consumer; identity pins never authenticate their own authors."""

from dataclasses import dataclass

from mcpsh.records import canonical_json


@dataclass(frozen=True)
class ThresholdAssessment:
    private_report: object
    public_status: dict
    approved_thresholds: object | None


def assess_threshold_metadata(packet: dict, *, current_inputs, now,
                              expected_context_sha256: str,
                              reviewer_metadata: bytes | None = None,
                              expected_reviewer_sha256: str | None = None,
                              integrator_metadata: bytes | None = None,
                              expected_integrator_sha256: str | None = None,
                              external_confirmation=None,
                              external_confirmation_verified: bool = False,
                              fresh_custody_confirmed: bool = False) -> ThresholdAssessment:
    """A trusted admission owner supplies current pins and external confirmations.

    Files/JSON cannot set the two confirmation booleans. Defaults preserve pending
    status; only D4's revalidating producer may return an ApprovedThresholds record.
    No clock, file, floor, reviewer identity or authorization is generated here.
    """
    from mcpsh.calibration.approvals import (
        ThresholdContext, ThresholdInputs, project_approved_thresholds,
        project_threshold_status, validate_threshold_approval,
    )
    from mcpsh.calibration.protocol_models import DevelopmentSummary, FullDevelopmentProposal

    if type(packet) is not dict or set(packet) != {"proposal", "summary", "context"}:
        raise ValueError("exact threshold proposal/summary/context packet required")
    if not isinstance(current_inputs, ThresholdInputs):
        raise ValueError("independently supplied typed current threshold inputs required")
    inputs = dict(
        proposal=FullDevelopmentProposal.model_validate_json(canonical_json(packet["proposal"])),
        summary=DevelopmentSummary.model_validate_json(canonical_json(packet["summary"])),
        context=ThresholdContext.model_validate_json(canonical_json(packet["context"])),
        current_inputs=current_inputs, now=now, expected_context_sha256=expected_context_sha256,
        reviewer_metadata=reviewer_metadata, expected_reviewer_sha256=expected_reviewer_sha256,
        integrator_metadata=integrator_metadata, expected_integrator_sha256=expected_integrator_sha256,
        external_confirmation=external_confirmation,
        external_confirmation_verified=external_confirmation_verified,
        fresh_custody_confirmed=fresh_custody_confirmed)
    report = validate_threshold_approval(**inputs)
    return ThresholdAssessment(report, project_threshold_status(report),
                               project_approved_thresholds(**inputs))
