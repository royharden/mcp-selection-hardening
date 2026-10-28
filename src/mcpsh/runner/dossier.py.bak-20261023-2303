"""Offline D4/D7 consumer: preserve original evidence, never authenticate JSON."""

from dataclasses import dataclass

from mcpsh.records import canonical_json, strict_json_loads, typed_hash


def admit_dossier_metadata(authority_raw: bytes, sources_raw: bytes, *, expected_typed_authority_sha256: str):
    """Call only after independently checking both raw-file pins; no edition read."""
    from mcpsh.evaluation.acceptance_evidence import AcceptanceSources, DossierAuthority

    authority = DossierAuthority.model_validate_json(canonical_json(strict_json_loads(authority_raw)))
    sources = AcceptanceSources.model_validate_json(canonical_json(strict_json_loads(sources_raw)))
    if typed_hash(authority.model_dump(mode="json")) != expected_typed_authority_sha256:
        raise ValueError("dossier authority differs from external typed pin")
    return authority, sources


@dataclass(frozen=True)
class OfflineDossier:
    result: dict
    private_dossier: dict


def assemble_offline_dossier(edition, *, authority, expected_typed_authority_sha256,
                             sources, now, threshold_attachment=None) -> OfflineDossier:
    from mcpsh.evaluation.acceptance_evidence import (
        DossierAuthentication, assemble_acceptance_dossier,
    )

    dossier = assemble_acceptance_dossier(
        edition, authority=authority, expected_authority_sha256=expected_typed_authority_sha256,
        sources=sources, authentication=DossierAuthentication(),
        threshold_attachment=threshold_attachment, now=now)
    index, manifest, trials, _, _ = edition.validate()
    # Preserve original ordered source rows; a missing scheduled slot is explicit,
    # never an invented failed/successful TrialOutcome or reduced denominator.
    by_id = {trial.outcome.trial_id: trial for trial in trials}
    rows, missing = [], []
    for trial_id in index.scheduled_trial_ids:
        trial = by_id.get(trial_id)
        if trial is None:
            rows.append({"outcome": {"trial_id": trial_id}, "record_state": "unknown"})
            missing.append({"trial_id": trial_id, "state": "unknown", "reasons": ["source_trial_unavailable"]})
        else:
            rows.append({"outcome": trial.outcome.model_dump(mode="json"),
                         "private_trial": trial.model_dump(mode="json"), "repeat": trial.repeat})
    # Both public basis slots are always present: an absent basis is a true zero count of
    # supplied outcomes, not an unknown, and must not project to null.
    bases = {"semantic-v2": 0, "legacy-call-proxy-v1": 0}
    for outcome in dossier.outcomes:
        bases[outcome.utility_basis] = bases.get(outcome.utility_basis, 0) + 1
    status = {"version": dossier.version, "source_index_sha256": dossier.source_index_sha256,
              "authority_binding": dossier.authority_binding, "authentication": dossier.authentication,
              "inspection_complete": dossier.inspection_complete, "recommendation": dossier.recommendation,
              "scheduled_trials": len(index.scheduled_trial_ids), "supplied_outcomes": len(dossier.outcomes),
              "missing_trials": len(missing), "utility_basis_counts": bases,
              "runtime_authorized": False, "independent_product_acceptance": "pending"}
    return OfflineDossier(
        {"schema_version": 1, "banner": "Offline acceptance evidence; independent acceptance pending",
         "execution_state": "acceptance-dossier-draft", "platform_scope": index.platform_scope,
         "manifest": manifest.model_dump(mode="json"), "rows": rows, "summary": [],
         # The dossier never rescores; supplied rows are not scored trials.
         "scheduled_trials": len(index.scheduled_trial_ids), "scored_trials": None,
         "unknown_trials": missing, "acceptance_dossier_status": status,
         "acceptance_verdict": "pending",
         "limitations": ["Original evidence retained; no rescore or replacement rows.",
                         "CLI authentication/custody/independence confirmations remain false.",
                         "Pins bind metadata, never actor authority or truthful execution."]},
        dossier.model_dump(mode="json"))
