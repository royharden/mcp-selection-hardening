"""Retrospective successor regression SOURCE; no helper/proof/test execution now."""

from dataclasses import replace
import hashlib
import json

import pytest

from mcpsh.evidence import EvidenceRejected, VerifiedEdition, inspect_edition
from mcpsh.evidence.fit_reverification import (
    FitReverificationAuthority, FitReverificationReceipt, build_fit_reverification_payloads,
    plan_fit_reverification,
)
from mcpsh.evidence.reader import model, strict_json
from mcpsh.evidence.models import EditionAuthority
from mcpsh.evidence.token_fit import verify_token_fit_lineage
from mcpsh.records import typed_hash

from test_edition_integrity import authority_for, sample as edition_sample
from test_token_fit_lineage import sample as fit_sample


def encode(value):
    # Preserve actual wire key order. This is synthetic source fixture encoding only.
    return (json.dumps(value, ensure_ascii=True, separators=(",", ":")) + "\n").encode()


def setup(*, unknown=False):
    payloads = edition_sample(live=True)
    index = strict_json(payloads["EDITION.json"])
    manifest = strict_json(payloads["MANIFEST.json"])
    row = strict_json(payloads["trials.jsonl"])
    manifest["model_ids"] = ["fake"]
    row["outcome"].update(trial_id="trial", model_id="fake", selector="fake", model_attempt_ids=["attempt"])
    row["model_attempts"][0].update(trial_id="trial", attempt_id="attempt", requested_model_id="fake",
        returned_model_id="fake", settlement_reference="attempt")
    row["accounting"][0].update(attempt_id="attempt", operation_id="op", settlement_reference="attempt")
    if unknown:
        row["outcome"].update(cost_microunits=None, cost_status="unknown", cost_basis="unknown")
        row["accounting"][0].update(cost_microunits=None, cost_basis="unknown")
    # Old sample observer is only a partial empty observation; use its actual trial identity.
    observer = strict_json(payloads["observers.jsonl"])
    observer["trial_id"] = "trial"
    bundle = fit_sample()
    selected = bundle["expectations"]
    bundle["expectations"] = []
    request = bundle["requests"][0]
    event = {key: value for key, value in bundle["events"][0].items() if key != "journal_sequence"}
    journal = encode({"event": "request", "attempt": {"attempt_id": "attempt", "operation_id": "op",
        "raw_request_hash": request["raw_request_sha256"]}, "wire_body": request["wire_body"]}) + encode(event)
    payloads.update({"MANIFEST.json": encode(manifest), "trials.jsonl": encode(row),
        "observers.jsonl": encode(observer), "token-fit.json": encode(bundle)})
    for role, name in (("manifest", "MANIFEST.json"), ("trials", "trials.jsonl"),
                       ("observers", "observers.jsonl"), ("token_fit", "token-fit.json")):
        raw = payloads[name]
        index[role] = {"path": name, "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
    index["scheduled_trial_ids"] = ["trial"]
    payloads["EDITION.json"] = encode(index)
    parent = VerifiedEdition(authority_for(payloads), payloads["EDITION.json"], tuple(
        (role, payloads[index[role]["path"]]) for role in ("manifest", "trials", "observers", "token_fit")))
    parsed_index, parsed_manifest, *_ = parent.validate()
    authority = FitReverificationAuthority(parent_index_sha256=parent.authority.index_sha256,
        parent_manifest_sha256=parent.authority.manifest_sha256,
        parent_token_fit_sha256=parsed_index.token_fit.sha256, parent_journal_sha256=hashlib.sha256(journal).hexdigest(),
        parent_candidate_commit=parsed_index.candidate_commit, executed_input_pins=parsed_index.input_pins,
        settings_sha256=typed_hash(parsed_manifest.settings), prices_sha256=typed_hash(parsed_manifest.prices),
        verification_source_sha256="e" * 64, verification_candidate_commit="f" * 40,
        expectations_sha256=typed_hash(selected), successor_edition_id="retrospective-a", successor_revision=2,
        selection_provenance="independent-retrospective-selection", selection_reference="synthetic-independent-selection",
        authenticated=True)  # Explicit fake external custody in this source fixture only.
    return parent, authority, selected, journal


def plan(parent, authority, selected, journal, **kwargs):
    return plan_fit_reverification(parent, authority=authority,
        expected_authority_sha256=typed_hash(authority.model_dump(mode="json")), expectations=selected,
        parent_journal_bytes=journal, **kwargs)


def ready(parent, authority, selected, journal):
    proposed = plan(parent, authority, selected, journal)
    summary = strict_json(proposed.summary_bytes)
    receipt = FitReverificationReceipt(plan_id=summary["plan_id"],
        authority_sha256=typed_hash(authority.model_dump(mode="json")),
        successor_index_sha256=summary["successor_index_sha256"],
        verification_source_sha256=authority.verification_source_sha256,
        authenticated=True, independent_selection_confirmed=True)
    return plan(parent, authority, selected, journal, receipt=receipt,
        expected_receipt_sha256=typed_hash(receipt.model_dump(mode="json")))


def successor(prepared):
    payloads = build_fit_reverification_payloads(prepared)
    index = strict_json(payloads["EDITION.json"])
    authority = model(EditionAuthority, strict_json(prepared.successor_authority_bytes))
    return VerifiedEdition(authority, payloads["EDITION.json"], tuple(
        (role, payloads[value["path"]]) for role, value in index.items() if role in {
            "manifest", "trials", "observers", "oracles", "token_fit", "fit_parent", "fit_reverification"}
        and value is not None))


def test_original_unknown_immutable_and_receipt_required_before_payload_handoff():
    # what_bug_this_catches: authority-file swap retroactively converting original UNKNOWN to paid admission.
    parent, authority, selected, journal = setup()
    before = (parent.index_bytes, parent.artifacts)
    proposal = plan(parent, authority, selected, journal)
    assert proposal.state == "pending"
    with pytest.raises(EvidenceRejected): build_fit_reverification_payloads(proposal)
    prepared = ready(parent, authority, selected, journal)
    new = successor(prepared)
    new.validate()
    result = verify_token_fit_lineage(new)
    assert result["complete"] is True and result["retrospective"] is True
    assert result["scope"] == "retrospective-fit-only"
    assert result["pre_send_admission_claim"] is result["live_admission"] is result["billing_verified"] is False
    assert verify_token_fit_lineage(parent)["complete"] is False
    assert (parent.index_bytes, parent.artifacts) == before
    assert dict(new.artifacts)["trials"] == dict(parent.artifacts)["trials"]


def test_partial_selection_cannot_cherry_pick_successes_or_drop_attempts():
    # what_bug_this_catches: independent expectations supplied only for successful sends.
    parent, authority, selected, journal = setup()
    changed = authority.model_copy(update={"expectations_sha256": typed_hash([])})
    partial = plan(parent, changed, [], journal)
    assert partial.state == "pending" and not partial.candidate_payloads


def test_unknown_cost_liabilities_survive_fit_reverification():
    # what_bug_this_catches: proven request fit settling missing usage as a free request.
    parent, authority, selected, journal = setup(unknown=True)
    new = successor(ready(parent, authority, selected, journal))
    row = new.validate()[2][0]
    assert row.outcome.cost_microunits is row.accounting[0].cost_microunits is None
    assert row.outcome.cost_status == "unknown"
    assert inspect_edition(new)["evidence_complete"] is False


@pytest.mark.parametrize("kind", ["source", "candidate", "price", "settings", "journal", "wrong-time"])
def test_wrong_pins_journal_and_proof_time_do_not_gain_retrospective_credit(kind):
    # what_bug_this_catches: source/config/price or request-time drift concealed by new receipt.
    parent, authority, selected, journal = setup()
    if kind == "source":
        authority = authority.model_copy(update={"executed_input_pins": authority.executed_input_pins.model_copy(update={"code_hash": "9" * 64})})
    elif kind == "candidate": authority = authority.model_copy(update={"parent_candidate_commit": "9" * 40})
    elif kind == "price": authority = authority.model_copy(update={"prices_sha256": "9" * 64})
    elif kind == "settings": authority = authority.model_copy(update={"settings_sha256": "9" * 64})
    elif kind == "journal": journal = journal.replace(b'"phase":"pre-send"', b'"phase":"preflight"')
    else:
        selected[0]["checked_at"] = "2028-01-01T00:00:00Z"
        authority = authority.model_copy(update={"expectations_sha256": typed_hash(selected)})
        proposed = plan(parent, authority, selected, journal)
        assert strict_json(proposed.summary_bytes)["fit"]["complete"] is False
        return
    with pytest.raises(EvidenceRejected): plan(parent, authority, selected, journal)


def test_changed_parent_bytes_cannot_be_repaired_by_successor():
    # what_bug_this_catches: removed attempt/failure rows passed under old immutable parent pin.
    parent, authority, selected, journal = setup()
    altered = tuple((role, raw + b" " if role == "trials" else raw) for role, raw in parent.artifacts)
    with pytest.raises(EvidenceRejected): plan(replace(parent, artifacts=altered), authority, selected, journal)


def test_receipt_defaults_unconfirmed_and_forbids_spend_or_new_billing():
    # what_bug_this_catches: structural receipt hash interpreted as authenticated spend permission.
    parent, authority, selected, journal = setup()
    proposed = plan(parent, authority, selected, journal)
    summary = strict_json(proposed.summary_bytes)
    receipt = FitReverificationReceipt(plan_id=summary["plan_id"], authority_sha256=typed_hash(authority.model_dump(mode="json")),
        successor_index_sha256=summary["successor_index_sha256"], verification_source_sha256=authority.verification_source_sha256)
    assert plan(parent, authority, selected, journal, receipt=receipt,
        expected_receipt_sha256=typed_hash(receipt.model_dump(mode="json"))).state == "pending"
    bad = receipt.model_dump(mode="json"); bad["dispatch_authorized"] = True
    with pytest.raises(EvidenceRejected): model(FitReverificationReceipt, bad)
    bad = receipt.model_dump(mode="json"); bad["new_charge_microunits"] = 1
    with pytest.raises(EvidenceRejected): model(FitReverificationReceipt, bad)


def test_receipt_on_original_index_is_rejected_not_a_reverification_successor():
    # what_bug_this_catches: original authority replaced without archived successor evidence lineage.
    parent, authority, selected, journal = setup()
    prepared = ready(parent, authority, selected, journal)
    approved = strict_json(prepared.successor_authority_bytes)
    swapped = parent.authority.model_copy(update={key: approved[key] for key in (
        "token_fit_expectations_sha256", "fit_reverification_receipt", "fit_reverification_receipt_sha256")})
    with pytest.raises(EvidenceRejected): replace(parent, authority=swapped).validate()


def test_duplicate_reuse_rows_survive_without_new_attempts_or_billing():
    # what_bug_this_catches: retrospective selection removing repeated reuse or treating it as new paid samples.
    parent, authority, selected, journal = setup()
    artifacts = dict(parent.artifacts)
    original = strict_json(artifacts["trials"])
    rows = [original]
    for identity in ("reuse-one", "reuse-two"):
        row = json.loads(json.dumps(original))
        row["outcome"].update(trial_id=identity, model_attempt_ids=[])
        row.update(trace=None, results=None, selected_calls=None, selection_journal_complete=None,
            model_attempts=[], accounting=[], final_response=None, result_captures=None,
            reuse={"kind": "reused-evidence", "source_index_sha256": "8" * 64,
                "source_manifest_sha256": "7" * 64, "source_trial_id": "old-trial",
                "source_row_sha256": "6" * 64, "source_outcome_sha256": "5" * 64,
                "original_cost_microunits": 2, "original_cost_basis": "dated-price-estimate",
                "new_charge_microunits": 0, "independent_new_sample": False})
        rows.append(row)
    artifacts["trials"] = b"".join(encode(row) for row in rows)
    index = strict_json(parent.index_bytes)
    index["scheduled_trial_ids"] = [row["outcome"]["trial_id"] for row in rows]
    index["trials"].update(bytes=len(artifacts["trials"]), sha256=hashlib.sha256(artifacts["trials"]).hexdigest())
    new_index = encode(index)
    parent = VerifiedEdition(parent.authority.model_copy(update={"index_sha256": hashlib.sha256(new_index).hexdigest()}),
        new_index, tuple(artifacts.items()))
    authority = authority.model_copy(update={"parent_index_sha256": parent.authority.index_sha256})
    result = successor(ready(parent, authority, selected, journal))
    assert dict(result.artifacts)["trials"] == artifacts["trials"]
    result_rows = result.validate()[2]
    assert len(result_rows) == 3
    assert sum(len(row.model_attempts) for row in result_rows) == 1
    assert all(row.reuse.new_charge_microunits == 0 and row.reuse.independent_new_sample is False
               for row in result_rows if row.reuse is not None)
