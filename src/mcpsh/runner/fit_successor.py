"""Publisher-side writer for D7's pure retrospective fit planner.

`scripts/eval.py --mode fit-reverify` is the only caller. The original edition is
read through the existing reader and never written. Without a separately pinned
receipt the plan stays pending and nothing is written; the pending view drops the
uncredited candidate fit so no verified fit state escapes. No new attempts, charge,
dispatch, pre-send admission or numeric result publication is introduced here.
"""

from dataclasses import dataclass
import hashlib
import json
import re
import tempfile
from pathlib import Path

from mcpsh.evidence import EditionAuthority, EvidenceRejected, read_edition
from mcpsh.evidence.fit_reverification import (
    FitReverificationAuthority, FitReverificationReceipt,
    build_fit_reverification_payloads, plan_fit_reverification,
)
from mcpsh.evidence.reader import model

SUCCESSOR_DIRECTORY = "normalized"
PROPOSED_AUTHORITY = "successor-authority.proposed.json"
PLAN_RECORD = "fit-plan.json"
_REQUIRED_LINEAGE = ("EDITION.json", "fit-parent.json", "fit-reverification.json", "token-fit.json")
_ARTIFACT_NAME = re.compile(r"[A-Za-z0-9_-]+\.(?:json|jsonl)")


@dataclass(frozen=True)
class FitSuccessorOutcome:
    state: str  # "pending" or "written"
    plan: dict
    destination: Path | None = None
    written: tuple[str, ...] = ()


def _encode(value) -> bytes:
    return (json.dumps(value, ensure_ascii=True, allow_nan=False, separators=(",", ":")) + "\n").encode("ascii")


def _pending_view(summary: dict) -> dict:
    """Credited fit only; candidate rows stay inside the planner, never published."""
    view = {key: value for key, value in summary.items() if key != "candidate_fit"}
    view.update(state="pending", credited=False, retrospective=True, dispatch_authorized=False,
                new_model_attempts=0, new_charge_microunits=0, billing_verified=False)
    fit = view.get("fit")
    if isinstance(fit, dict):
        fit = {**fit, "complete": False}
        if isinstance(fit.get("attempts"), list):
            fit["attempts"] = [{**row, "state": "unknown"} if row.get("state") == "verified-fit-only" else row
                               for row in fit["attempts"]]
        view["fit"] = fit
    return view


def _outside(child: Path, parent: Path) -> bool:
    return child != parent and parent not in child.parents and child not in parent.parents


def _parent_snapshot(root: Path) -> dict[str, str]:
    return {path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(root.rglob("*")) if path.is_file()}


def run_fit_successor(*, parent_root: Path, parent_authority: EditionAuthority, fit_authority_value,
                      expected_fit_authority_sha256: str, expectations, parent_journal_bytes: bytes,
                      destination: Path, receipt_value=None,
                      expected_receipt_sha256: str | None = None) -> FitSuccessorOutcome:
    """Raw file pins are checked by the caller; typed pins are checked by D7's planner.

    A written successor is re-read from disk through the existing reader under the
    planner's successor authority, and the parent root is rehashed to prove the
    original edition (including any UNKNOWN fit rows) was not modified.
    """
    if (receipt_value is None) != (expected_receipt_sha256 is None):
        raise EvidenceRejected("retrospective receipt and its independent typed pin travel together")
    parent_root, destination = Path(parent_root).resolve(), Path(destination).resolve()
    if not _outside(destination, parent_root):
        raise EvidenceRejected("successor destination must be disjoint from the immutable parent edition")
    if destination.exists():
        raise EvidenceRejected("successor publication already exists; choose a fresh ID")
    before = _parent_snapshot(parent_root)
    parent = read_edition(parent_root, authority=parent_authority)
    authority = model(FitReverificationAuthority, fit_authority_value)
    receipt = model(FitReverificationReceipt, receipt_value) if receipt_value is not None else None
    plan = plan_fit_reverification(parent, authority=authority,
                                   expected_authority_sha256=expected_fit_authority_sha256,
                                   expectations=expectations, parent_journal_bytes=parent_journal_bytes,
                                   receipt=receipt, expected_receipt_sha256=expected_receipt_sha256)
    summary = json.loads(plan.summary_bytes)
    if plan.state != "ready-for-separate-writer" or receipt is None:
        return FitSuccessorOutcome("pending", _pending_view(summary))
    payloads = build_fit_reverification_payloads(plan)
    if any(name not in payloads for name in _REQUIRED_LINEAGE):
        raise EvidenceRejected("successor must link original archive, lineage and capture")
    if any(not _ARTIFACT_NAME.fullmatch(name) for name in payloads):
        raise EvidenceRejected("successor artifact name is outside the private flat schema")
    successor_authority = model(EditionAuthority, json.loads(plan.successor_authority_bytes))
    if (successor_authority.edition_id != destination.name
            or successor_authority.edition_id == parent_authority.edition_id
            or successor_authority.index_sha256 == parent_authority.index_sha256
            or successor_authority.index_sha256 != hashlib.sha256(payloads["EDITION.json"]).hexdigest()):
        raise EvidenceRejected("successor identity collides with or detaches from the original edition")
    destination.parent.mkdir(parents=True, exist_ok=True)
    # Stage beside the destination; only a validated successor is renamed into place.
    staging = Path(tempfile.mkdtemp(prefix=".stage-" + destination.name + "-", dir=destination.parent))
    normalized = staging / SUCCESSOR_DIRECTORY
    normalized.mkdir(exist_ok=False)
    for name, raw in payloads.items():
        with (normalized / name).open("xb") as handle:
            handle.write(raw)
    with (staging / PROPOSED_AUTHORITY).open("xb") as handle:
        # Proposal only: a trusted caller must still select this authority externally.
        handle.write(plan.successor_authority_bytes)
    record = {**summary, "state": "written", "credited": True, "successor_directory": SUCCESSOR_DIRECTORY,
              "parent_index_sha256": parent_authority.index_sha256,
              "successor_authority_proposed_sha256": hashlib.sha256(plan.successor_authority_bytes).hexdigest()}
    with (staging / PLAN_RECORD).open("xb") as handle:
        handle.write(_encode(record))
    read_edition(normalized, authority=successor_authority).validate()
    if _parent_snapshot(parent_root) != before:
        raise EvidenceRejected("original parent edition bytes changed during successor publication")
    if destination.exists():
        raise EvidenceRejected("successor publication appeared during staging; staging preserved")
    staging.rename(destination)
    return FitSuccessorOutcome("written", record, destination, tuple(sorted(payloads)))
