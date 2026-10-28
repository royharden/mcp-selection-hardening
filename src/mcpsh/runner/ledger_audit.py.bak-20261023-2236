"""Explicit saved-ledger consumer. The accounting owner is the sole read authority."""

from dataclasses import dataclass

from mcpsh.records import canonical_json, strict_json_loads


def admit_ledger_authority(raw: bytes):
    """The caller must first check its external raw pin; never generate one here."""
    from mcpsh.accounting.report import LedgerAuditAuthority

    return LedgerAuditAuthority.model_validate_json(canonical_json(strict_json_loads(raw)))


@dataclass(frozen=True)
class OfflineLedgerAudit:
    result: dict
    private_report: dict


def assemble_ledger_audit(path, *, edition, authority, billing_evidence=()) -> OfflineLedgerAudit:
    """Trusted callers establish billing witnesses externally; standalone CLI omits them."""
    from mcpsh.accounting.report import audit_ledger, project_ledger_audit_status

    report = audit_ledger(path, edition=edition, authority=authority, billing_evidence=billing_evidence)
    index, manifest, trials, _, _ = edition.validate()
    by_id = {trial.outcome.trial_id: trial for trial in trials}
    rows, missing = [], []
    for trial_id in index.scheduled_trial_ids:
        trial = by_id.get(trial_id)
        if trial is None:
            rows.append({"outcome": {"trial_id": trial_id}, "record_state": "unknown"})
            missing.append({"trial_id": trial_id, "state": "unknown", "reasons": ["source_trial_unavailable"]})
        else:
            rows.append({"outcome": trial.outcome.model_dump(mode="json"), "repeat": trial.repeat,
                         "private_trial": trial.model_dump(mode="json")})
    status = project_ledger_audit_status(report)
    result = {"schema_version": 1, "banner": "Read-only ledger evidence; independent acceptance pending",
              "execution_state": "ledger-audit-draft", "platform_scope": index.platform_scope,
              "manifest": manifest.model_dump(mode="json"), "rows": rows, "summary": [],
              "scheduled_trials": len(index.scheduled_trial_ids), "scored_trials": len(trials),
              "unknown_trials": missing, "ledger_audit": report,
              "ledger_audit_status": status, "acceptance_verdict": "pending",
              "limitations": ["Original trials and full private ledger report retained.",
                              "Snapshot identity is separate from freshness and billing authority.",
                              "Unknown/unallocated/reused records never become free or independent samples."]}
    return OfflineLedgerAudit(result, report)
