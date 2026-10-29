"""Immutable retrospective fit proposals. Pure bytes in/out; D1 owns all writing.

Original UNKNOWN captures never gain authority through an authority-file swap.
A distinct successor archives their exact bytes, then binds a complete externally
selected expectation set and separately pinned retrospective receipt. No counter,
proof builder, journal writer, dispatch, new sample, cost or billing is introduced.
"""

import base64
from dataclasses import dataclass
import hashlib
import json
from typing import Literal

from pydantic import Field

from mcpsh.records import typed_hash
from mcpsh.records.models import Record

from .build import encode
from .models import EditionAuthority, InputPins
from .reader import EvidenceRejected, MAX_TOTAL_BYTES, VerifiedEdition, model, strict_json
from .token_fit import TokenFitBundle, _verify_token_fit_records, capture_token_fit_bundle
from mcpsh.adapters.transports import encode_wire


class FitReverificationAuthority(Record):
    parent_index_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    parent_manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    parent_token_fit_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    parent_journal_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    parent_candidate_commit: str = Field(pattern=r"^[0-9a-f]{40}$")
    executed_input_pins: InputPins
    settings_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    prices_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    verification_source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    verification_candidate_commit: str = Field(pattern=r"^[0-9a-f]{40}$")
    expectations_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    successor_edition_id: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]*$")
    successor_revision: int = Field(ge=2)
    selection_provenance: Literal["independent-retrospective-selection"]
    selection_reference: str = Field(min_length=1, max_length=256)
    authenticated: bool = False


class FitReverificationReceipt(Record):
    plan_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    authority_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    successor_index_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    verification_source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    retrospective: Literal[True] = True
    authenticated: bool = False
    independent_selection_confirmed: bool = False
    dispatch_authorized: Literal[False] = False
    new_model_attempts: Literal[0] = 0
    new_charge_microunits: Literal[0] = 0
    billing_authorized: Literal[False] = False


class ArchivedArtifact(Record):
    role: str = Field(min_length=1, max_length=64)
    chunks: tuple[str, ...] = Field(max_length=2048)


class FitParentArchive(Record):
    schema_version: Literal[1]
    authority: EditionAuthority
    index_chunks: tuple[str, ...] = Field(max_length=16)
    artifacts: tuple[ArchivedArtifact, ...] = Field(max_length=8)
    journal_chunks: tuple[str, ...] = Field(max_length=2048)


class FitReverificationLineage(Record):
    schema_version: Literal[1]
    kind: Literal["RETROSPECTIVE-FIT-EVIDENCE-ONLY"]
    plan_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    authority: FitReverificationAuthority
    authority_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    parent_archive_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    original_trials_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    expectations_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    pre_send_admission_claim: Literal[False]
    dispatch_authorized: Literal[False]
    new_model_attempts: Literal[0]
    new_charge_microunits: Literal[0]
    billing_verified: Literal[False]


@dataclass(frozen=True)
class FitReverificationPlan:
    state: str
    summary_bytes: bytes
    candidate_payloads: tuple[tuple[str, bytes], ...] = ()
    successor_authority_bytes: bytes | None = None


def _chunks(raw):
    return [base64.b64encode(raw[start:start + 49152]).decode("ascii")
            for start in range(0, len(raw), 49152)]


def _unchunks(chunks):
    try:
        raw = b"".join(base64.b64decode(item, validate=True) for item in chunks)
    except (ValueError, TypeError):
        raise EvidenceRejected("invalid parent byte archive") from None
    if len(raw) > MAX_TOTAL_BYTES:
        raise EvidenceRejected("parent byte archive exceeds cap")
    return raw


def _journal_capture(raw):
    if type(raw) is not bytes or not raw or len(raw) > 32 * 1024 * 1024 or not raw.endswith(b"\n"):
        raise EvidenceRejected("complete bounded original private journal bytes required")
    lines = raw.splitlines()
    if len(lines) > 120000 or any(not line for line in lines):
        raise EvidenceRejected("original journal incomplete or exceeds row cap")
    # Existing capture adapter, not a second journal or proof calculator.
    events = [strict_json(line) for line in lines]
    if any(type(event) is not dict for event in events):
        raise EvidenceRejected("original journal contains a non-object record")
    return capture_token_fit_bundle(events, expectations=[])


def _check_parent(parent, authority, original, journal):
    index, manifest, trials, _, _ = parent.validate()
    if index.fit_reverification is not None:
        raise EvidenceRejected("nested retrospective authority changes require separate scope")
    if (authority.parent_index_sha256 != parent.authority.index_sha256
            or authority.parent_manifest_sha256 != parent.authority.manifest_sha256
            or index.token_fit is None or authority.parent_token_fit_sha256 != index.token_fit.sha256
            or authority.parent_candidate_commit != index.candidate_commit
            or authority.executed_input_pins != index.input_pins
            or authority.settings_sha256 != typed_hash(manifest.settings)
            or authority.prices_sha256 != typed_hash(manifest.prices)
            or authority.parent_journal_sha256 != hashlib.sha256(journal).hexdigest()
            or authority.successor_edition_id == index.edition_id
            or authority.successor_revision <= index.revision):
        raise EvidenceRejected("retrospective authority changes original identity/source/config/price")
    captured = _journal_capture(journal)
    if (typed_hash(captured["events"]) != typed_hash([item.model_dump(mode="json", exclude_unset=True) for item in original.events])
            or typed_hash(captured["requests"]) != typed_hash([item.model_dump(mode="json", exclude_unset=True) for item in original.requests])
            or any(encode_wire(new["wire_body"]) != encode_wire(old.wire_body)
                for new, old in zip(captured["requests"], original.requests, strict=True))):
        raise EvidenceRejected("original private journal differs from immutable captured requests/proofs")
    return index, manifest, trials


def plan_fit_reverification(parent: VerifiedEdition, *, authority: FitReverificationAuthority | None,
                           expected_authority_sha256: str | None, expectations,
                           parent_journal_bytes: bytes | None,
                           receipt: FitReverificationReceipt | None = None,
                           expected_receipt_sha256: str | None = None) -> FitReverificationPlan:
    """Prepare reviewable candidate bytes; only separate external receipt enables handoff.

Receipt identity lives outside the indexed edition, avoiding a circular hash of
an index which contains a receipt of its own index hash. Flags default false;
the caller must independently authenticate metadata and select both pins.
"""
    index, _, _, _, _ = parent.validate()
    raw_fit = dict(parent.artifacts).get("token_fit")
    if authority is None or expected_authority_sha256 is None or parent_journal_bytes is None or raw_fit is None:
        return FitReverificationPlan("pending", encode({"state": "pending", "retrospective": True,
            "reason": "original_capture_journal_or_external_authority_unavailable",
            "parent_index_sha256": parent.authority.index_sha256, "dispatch_authorized": False}))
    authority = model(FitReverificationAuthority, authority.model_dump(mode="json"))
    if typed_hash(authority.model_dump(mode="json")) != expected_authority_sha256:
        raise EvidenceRejected("retrospective selection differs from external authority pin")
    original = model(TokenFitBundle, strict_json(raw_fit))
    index, manifest, trials = _check_parent(parent, authority, original, parent_journal_bytes)
    replacement = strict_json(raw_fit)
    replacement["expectations"] = expectations
    selected = model(TokenFitBundle, replacement)
    selected_values = [item.model_dump(mode="json") for item in selected.expectations]
    if typed_hash(selected_values) != authority.expectations_sha256:
        raise EvidenceRejected("retrospective expectation selection differs from external pin")
    required = {item.attempt_id for trial in trials for item in trial.model_attempts} | {item.attempt_id for item in original.requests}
    identities = [item.attempt_id for item in selected.expectations]
    if len(set(identities)) != len(identities) or set(identities) != required:
        return FitReverificationPlan("pending", encode({"state": "pending", "retrospective": True,
            "reason": "full_original_attempt_expectation_coverage_required",
            "original_attempts": len(required), "selected_expectations": len(identities), "dispatch_authorized": False}))
    # Capture byte archive preserves originals, including rows/failures/unknowns.
    archive = encode({"schema_version": 1, "authority": parent.authority.model_dump(mode="json"),
        "index_chunks": _chunks(parent.index_bytes),
        "artifacts": [{"role": role, "chunks": _chunks(raw)} for role, raw in parent.artifacts],
        "journal_chunks": _chunks(parent_journal_bytes)})
    core = {"schema_version": 1, "kind": "RETROSPECTIVE-FIT-EVIDENCE-ONLY",
        "authority": authority.model_dump(mode="json"), "authority_sha256": expected_authority_sha256,
        "parent_archive_sha256": hashlib.sha256(archive).hexdigest(),
        "original_trials_sha256": index.trials.sha256, "expectations_sha256": authority.expectations_sha256,
        "pre_send_admission_claim": False, "dispatch_authorized": False, "new_model_attempts": 0,
        "new_charge_microunits": 0, "billing_verified": False}
    plan_id = typed_hash(core)
    lineage = encode({**core, "plan_id": plan_id})
    manifest_value = strict_json(dict(parent.artifacts)["manifest"])
    manifest_value["edition_id"] = authority.successor_edition_id
    by_role = dict(parent.artifacts)
    by_role.update(manifest=encode(manifest_value), fit_parent=archive, fit_reverification=lineage,
        token_fit=(json.dumps(replacement, ensure_ascii=True, allow_nan=False, separators=(",", ":")) + "\n").encode())
    names = {"manifest": "MANIFEST.json", "trials": "trials.jsonl", "observers": "observers.jsonl",
        "oracles": "oracles.json", "token_fit": "token-fit.json", "fit_parent": "fit-parent.json",
        "fit_reverification": "fit-reverification.json"}
    successor_index = strict_json(parent.index_bytes)
    successor_index.update(edition_id=authority.successor_edition_id, revision=authority.successor_revision)
    for role, raw in by_role.items():
        successor_index[role] = {"path": names[role], "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
    raw_index = encode(successor_index)
    index_pin = hashlib.sha256(raw_index).hexdigest()
    proposed = {names[role]: raw for role, raw in by_role.items()}
    proposed["EDITION.json"] = raw_index
    if (sum(len(raw) for raw in proposed.values()) > MAX_TOTAL_BYTES
            or any(len(raw) > 32 * 1024 * 1024 for raw in by_role.values())):
        raise EvidenceRejected("retrospective successor exceeds bounded edition size; no partial archive")
    fit = _verify_token_fit_records(index, trials, selected, authority.expectations_sha256)
    fit.update(scope="retrospective-fit-only", retrospective=True, pre_send_admission_claim=False)
    ready = False
    parsed_receipt = None
    if receipt is not None:
        parsed_receipt = model(FitReverificationReceipt, receipt.model_dump(mode="json"))
        if (expected_receipt_sha256 is None or typed_hash(parsed_receipt.model_dump(mode="json")) != expected_receipt_sha256
                or parsed_receipt.plan_id != plan_id or parsed_receipt.authority_sha256 != expected_authority_sha256
                or parsed_receipt.successor_index_sha256 != index_pin
                or parsed_receipt.verification_source_sha256 != authority.verification_source_sha256):
            raise EvidenceRejected("retrospective receipt differs from selected plan/index/source")
        ready = authority.authenticated and parsed_receipt.authenticated and parsed_receipt.independent_selection_confirmed
    successor_authority = {**parent.authority.model_dump(mode="json"),
        "index_sha256": index_pin, "manifest_sha256": successor_index["manifest"]["sha256"],
        "edition_id": authority.successor_edition_id, "revision": authority.successor_revision,
        "token_fit_expectations_sha256": authority.expectations_sha256,
        "fit_reverification_receipt": parsed_receipt.model_dump(mode="json") if parsed_receipt else None,
        "fit_reverification_receipt_sha256": expected_receipt_sha256}
    credited_fit = fit if ready else {**fit, "complete": False,
        "attempts": [{**row, "state": "unknown" if row["state"] == "verified-fit-only" else row["state"],
            "reasons": [*row["reasons"], "retrospective_authority_pending"]} for row in fit["attempts"]]}
    return FitReverificationPlan("ready-for-separate-writer" if ready else "pending",
        encode({"state": "ready-for-separate-writer" if ready else "pending", "plan_id": plan_id,
            "successor_index_sha256": index_pin, "parent_index_sha256": parent.authority.index_sha256,
            "retrospective": True, "fit": credited_fit, "candidate_fit": fit,
            "dispatch_authorized": False, "billing_verified": False,
            "new_model_attempts": 0, "new_charge_microunits": 0}),
        tuple(proposed.items()), encode(successor_authority))


def validate_fit_successor(authority, index, artifacts):
    """Existing reader's structural bridge; authentic custody remains external."""
    has_lineage = "fit_reverification" in artifacts or "fit_parent" in artifacts
    if not has_lineage:
        if authority.fit_reverification_receipt is not None or authority.fit_reverification_receipt_sha256 is not None:
            raise EvidenceRejected("original edition cannot acquire retrospective authority by replacement")
        return
    if not {"fit_reverification", "fit_parent", "token_fit"} <= set(artifacts):
        raise EvidenceRejected("retrospective successor requires complete original archive and lineage")
    lineage = model(FitReverificationLineage, strict_json(artifacts["fit_reverification"]))
    archive = model(FitParentArchive, strict_json(artifacts["fit_parent"]))
    parent = VerifiedEdition(archive.authority, _unchunks(archive.index_chunks),
        tuple((item.role, _unchunks(item.chunks)) for item in archive.artifacts))
    original_raw = dict(parent.artifacts).get("token_fit")
    if original_raw is None:
        raise EvidenceRejected("archived parent lacks original token-fit capture")
    original = model(TokenFitBundle, strict_json(original_raw))
    old_index, _, trials = _check_parent(parent, lineage.authority, original, _unchunks(archive.journal_chunks))
    core = lineage.model_dump(mode="json")
    claimed = core.pop("plan_id")
    if (typed_hash(core) != claimed or typed_hash(lineage.authority.model_dump(mode="json")) != lineage.authority_sha256
            or hashlib.sha256(artifacts["fit_parent"]).hexdigest() != lineage.parent_archive_sha256
            or artifacts["trials"] != dict(parent.artifacts)["trials"]
            or lineage.original_trials_sha256 != old_index.trials.sha256
            or index.scheduled_trial_ids != old_index.scheduled_trial_ids
            or index.candidate_commit != old_index.candidate_commit or index.input_pins != old_index.input_pins):
        raise EvidenceRejected("retrospective successor altered original bytes/schedule/source")
    for role, raw in parent.artifacts:
        if role not in {"manifest", "token_fit"} and artifacts.get(role) != raw:
            raise EvidenceRejected("retrospective successor dropped or changed original artifact bytes")
    if set(artifacts) != set(dict(parent.artifacts)) | {"fit_parent", "fit_reverification"}:
        raise EvidenceRejected("retrospective successor added/removed original evidence roles")
    new_manifest = strict_json(artifacts["manifest"])
    old_manifest = strict_json(dict(parent.artifacts)["manifest"])
    new_manifest["edition_id"] = old_manifest["edition_id"]
    if typed_hash(new_manifest) != typed_hash(old_manifest):
        raise EvidenceRejected("retrospective successor changed original execution settings/prices")
    replacement = model(TokenFitBundle, strict_json(artifacts["token_fit"]))
    if (replacement.events != original.events or replacement.requests != original.requests
            or any(encode_wire(new.wire_body) != encode_wire(old.wire_body)
                for new, old in zip(replacement.requests, original.requests, strict=True))
            or typed_hash([item.model_dump(mode="json") for item in replacement.expectations]) != lineage.expectations_sha256
            or lineage.expectations_sha256 != lineage.authority.expectations_sha256
            or authority.token_fit_expectations_sha256 != lineage.expectations_sha256):
        raise EvidenceRejected("retrospective successor mutated original capture or substituted selection")
    required = {item.attempt_id for trial in trials for item in trial.model_attempts} | {item.attempt_id for item in original.requests}
    identities = [item.attempt_id for item in replacement.expectations]
    if len(set(identities)) != len(identities) or set(identities) != required:
        raise EvidenceRejected("retrospective successor cherry-picks original attempts")
    if authority.fit_reverification_receipt is None:
        raise EvidenceRejected("retrospective receipt unavailable; authority remains pending")
    receipt = model(FitReverificationReceipt, authority.fit_reverification_receipt)
    if (typed_hash(receipt.model_dump(mode="json")) != authority.fit_reverification_receipt_sha256
            or receipt.plan_id != claimed or receipt.authority_sha256 != lineage.authority_sha256
            or receipt.successor_index_sha256 != authority.index_sha256
            or receipt.verification_source_sha256 != lineage.authority.verification_source_sha256
            or index.edition_id != lineage.authority.successor_edition_id
            or index.revision != lineage.authority.successor_revision
            or not lineage.authority.authenticated or not receipt.authenticated
            or not receipt.independent_selection_confirmed):
        raise EvidenceRejected("retrospective receipt authentication/selection/index/source unconfirmed")


def build_fit_reverification_payloads(plan: FitReverificationPlan) -> dict[str, bytes]:
    """No writer action or approval implied. Caller separately authorizes destination."""
    if plan.state != "ready-for-separate-writer" or plan.successor_authority_bytes is None:
        raise EvidenceRejected("retrospective proposal pending independent receipt")
    payloads = dict(plan.candidate_payloads)
    if len(payloads) != len(plan.candidate_payloads):
        raise EvidenceRejected("duplicate proposed artifact path")
    raw_index = payloads["EDITION.json"]
    index_value = strict_json(raw_index)
    authority = model(EditionAuthority, strict_json(plan.successor_authority_bytes))
    artifacts = tuple((role, payloads[pin["path"]]) for role, pin in index_value.items()
        if role in {"manifest", "trials", "observers", "oracles", "token_fit", "fit_parent", "fit_reverification"} and pin is not None)
    VerifiedEdition(authority, raw_index, artifacts).validate()
    if set(payloads) != {"EDITION.json", *(index_value[role]["path"] for role, _ in artifacts)}:
        raise EvidenceRejected("unbound proposed payload")
    summary = strict_json(plan.summary_bytes)
    if summary["successor_index_sha256"] != authority.index_sha256:
        raise EvidenceRejected("retrospective candidate differs from reviewed plan")
    return payloads
