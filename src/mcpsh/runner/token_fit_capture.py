"""Bounded private journal handoff; no tokenizer, proof authority or dispatch."""

import hashlib
from pathlib import Path

from mcpsh.records import canonical_json, strict_json_loads, typed_hash


def read_private_provider_journal(path: Path, *, maximum_bytes=512 * 1024 * 1024,
                                  maximum_events=120000):
    """Read an explicitly owned journal in order, or reject without truncation."""
    if path.is_symlink():
        raise ValueError("private provider journal cannot be a symlink")
    events, total, digest = [], 0, hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            line = handle.readline(8 * 1024 * 1024 + 1)
            if not line:
                break
            total += len(line)
            if (len(line) > 8 * 1024 * 1024 or not line.endswith(b"\n")
                    or total > maximum_bytes or len(events) >= maximum_events):
                raise ValueError("private journal incomplete or exceeds bounded handoff; preserve original")
            digest.update(line)
            event = strict_json_loads(line)
            if type(event) is not dict:
                raise ValueError("private journal row must be a complete JSON object")
            events.append(event)
    return events, digest.hexdigest()


def pinned_fit_expectations(value, *, expected_typed_sha256: str):
    """The expected pin comes from the independent consumer, never event hashes."""
    from mcpsh.evidence.token_fit import FitExpectation

    if type(value) is not list or len(value) > 30000:
        raise ValueError("bounded independently selected fit expectation array required")
    normalized = [FitExpectation.model_validate_json(canonical_json(row)).model_dump(mode="json")
                  for row in value]
    if typed_hash(normalized) != expected_typed_sha256:
        raise ValueError("fit expectations differ from external typed authority pin")
    return normalized


def capture_fit_handoff(journal_events, *, expectations=None, expected_typed_sha256=None):
    from mcpsh.evidence.token_fit import capture_token_fit_bundle

    if expectations is None:
        if expected_typed_sha256 is not None:
            raise ValueError("external expectation pin requires its independently selected records")
        selected = []
    else:
        selected = pinned_fit_expectations(expectations, expected_typed_sha256=expected_typed_sha256)
    # Every actual proof and prepared request survives, including preflight and
    # unattributed legacy events. An empty expectation list grants no fit credit.
    return capture_token_fit_bundle(journal_events, expectations=selected)


def public_fit_status(*, attempts_total: int, trials_without_attempts: int,
                      journal_sha256=None, bundle=None, lineage=None):
    """Counts retain all attempts; fit-only diagnostics cannot authorize billing."""
    if type(attempts_total) is not int or attempts_total < 0 or type(trials_without_attempts) is not int or trials_without_attempts < 0:
        raise ValueError("non-negative integer fit status counts required")
    if lineage is not None:
        # The lineage verifier owns the attempt denominator; a caller count cannot shrink
        # it (hiding unknown attempts) or pad it (a negative/odd unknown count).
        if type(lineage) is not dict or type(lineage.get("attempts")) is not list or attempts_total != len(lineage["attempts"]):
            raise ValueError("fit status attempt count differs from the verified lineage denominator")
        no_attempts = lineage.get("trials_without_attempts")
        if no_attempts is not None and (type(no_attempts) is not list or trials_without_attempts != len(no_attempts)):
            raise ValueError("fit status trial count differs from the verified lineage")
    verified = sum(row.get("state") == "verified-fit-only" for row in lineage["attempts"]) if lineage else 0
    return {"version": "m5-token-fit-status-1",
            "status": "verified-fit-only" if lineage and lineage.get("complete") is True else "unknown",
            "complete": bool(lineage and lineage.get("complete") is True),
            "attempts_total": attempts_total, "attempts_verified": verified,
            "attempts_unknown": attempts_total - verified,
            "trials_without_attempts": trials_without_attempts,
            "journal_sha256": journal_sha256,
            "bundle_typed_sha256": typed_hash(bundle) if bundle is not None else None,
            "expectations_sha256": lineage.get("expectations_sha256") if lineage else None,
            "live_admission": False, "billing_verified": False}
