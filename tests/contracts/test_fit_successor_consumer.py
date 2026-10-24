"""Source regressions for the publisher-side retrospective fit writer.

Authored during Dirty Mode construction and not yet run. The D7 planner, payload
builder and existing reader are replaced with stubs so these cases pin only the
writer's own contract: pending means no write, pin mismatches reject, parent bytes
stay untouched and the original UNKNOWN edition stays linked.
"""

from types import SimpleNamespace
import hashlib
import json

import pytest

import mcpsh.runner.fit_successor as writer
from mcpsh.evidence import EvidenceRejected
from mcpsh.evidence.fit_reverification import FitReverificationPlan

PARENT_ID = "public-parent-unknown"
SUCCESSOR_ID = "public-successor"


def _index(name):
    return (json.dumps({"edition_id": name}) + "\n").encode()


SUCCESSOR_INDEX = _index(SUCCESSOR_ID)


def _authority(edition_id, index_sha256):
    return SimpleNamespace(edition_id=edition_id, index_sha256=index_sha256)


def _parent(tmp_path):
    root = tmp_path / "parent"
    root.mkdir()
    (root / "EDITION.json").write_bytes(_index(PARENT_ID))
    # Original capture with an UNKNOWN fit row: must never be rewritten in place.
    (root / "token-fit.json").write_bytes(b'{"attempts":[{"attempt_id":"a1","state":"unknown"}]}\n')
    return root


def _summary(state):
    return {"state": state, "plan_id": "1" * 64, "successor_index_sha256": hashlib.sha256(SUCCESSOR_INDEX).hexdigest(),
            "parent_index_sha256": "2" * 64, "retrospective": True,
            "fit": {"complete": False, "attempts": [{"attempt_id": "a1", "state": "unknown",
                                                     "reasons": ["retrospective_authority_pending"]}]},
            "candidate_fit": {"complete": True, "attempts": [{"attempt_id": "a1", "state": "verified-fit-only",
                                                              "reasons": []}]},
            "dispatch_authorized": False, "billing_verified": False,
            "new_model_attempts": 0, "new_charge_microunits": 0}


def _successor_authority():
    return {"index_sha256": hashlib.sha256(SUCCESSOR_INDEX).hexdigest(), "edition_id": SUCCESSOR_ID}


def _install(monkeypatch, *, plan, payloads=None, planner_error=None, calls=None):
    calls = calls if calls is not None else {}
    parent_authority = _authority(PARENT_ID, "3" * 64)

    def read_edition(root, *, authority):
        calls.setdefault("reads", []).append((root, authority))
        return SimpleNamespace(validate=lambda: None)

    def planner(parent, **kwargs):
        calls["planner"] = kwargs
        if planner_error:
            raise planner_error
        return plan

    def build(given):
        calls["built"] = given
        return dict(payloads)

    def parse(model_type, value):
        if model_type is writer.EditionAuthority:
            return SimpleNamespace(**value)
        return SimpleNamespace(model_type=model_type.__name__, value=value)

    monkeypatch.setattr(writer, "read_edition", read_edition)
    monkeypatch.setattr(writer, "plan_fit_reverification", planner)
    monkeypatch.setattr(writer, "build_fit_reverification_payloads", build)
    monkeypatch.setattr(writer, "model", parse)
    return parent_authority, calls


def _run(tmp_path, parent_authority, *, receipt=None, receipt_pin=None, destination=None):
    return writer.run_fit_successor(
        parent_root=tmp_path / "parent", parent_authority=parent_authority,
        fit_authority_value={"authority": "public"}, expected_fit_authority_sha256="4" * 64,
        expectations=[{"attempt_id": "a1"}], parent_journal_bytes=b'{"event":"public"}\n',
        destination=destination or tmp_path / "private" / SUCCESSOR_ID,
        receipt_value=receipt, expected_receipt_sha256=receipt_pin)


def _ready_payloads():
    return {"EDITION.json": SUCCESSOR_INDEX, "fit-parent.json": b'{"archive":"original"}\n',
            "fit-reverification.json": b'{"kind":"RETROSPECTIVE-FIT-EVIDENCE-ONLY"}\n',
            "token-fit.json": b'{"expectations":[]}\n', "trials.jsonl": b'{"trial":1}\n'}


def test_missing_receipt_stays_pending_and_writes_nothing(tmp_path, monkeypatch):
    _parent(tmp_path)
    (tmp_path / "private").mkdir()
    plan = FitReverificationPlan("pending", json.dumps(_summary("pending")).encode())
    parent_authority, calls = _install(monkeypatch, plan=plan)
    outcome = _run(tmp_path, parent_authority)
    assert outcome.state == "pending" and outcome.destination is None and outcome.written == ()
    assert not (tmp_path / "private" / SUCCESSOR_ID).exists()
    assert "built" not in calls
    assert calls["planner"]["receipt"] is None and calls["planner"]["expected_receipt_sha256"] is None
    # No credited fit state escapes a pending plan.
    assert "candidate_fit" not in outcome.plan and outcome.plan["credited"] is False
    assert all(row["state"] != "verified-fit-only" for row in outcome.plan["fit"]["attempts"])
    assert outcome.plan["new_model_attempts"] == outcome.plan["new_charge_microunits"] == 0
    assert outcome.plan["dispatch_authorized"] is False


def test_receipt_without_planner_authentication_stays_pending(tmp_path, monkeypatch):
    _parent(tmp_path)
    (tmp_path / "private").mkdir()
    plan = FitReverificationPlan("pending", json.dumps(_summary("pending")).encode())
    parent_authority, calls = _install(monkeypatch, plan=plan)
    outcome = _run(tmp_path, parent_authority, receipt={"authenticated": False}, receipt_pin="5" * 64)
    assert outcome.state == "pending" and "built" not in calls
    assert not (tmp_path / "private" / SUCCESSOR_ID).exists()


@pytest.mark.parametrize("receipt, pin", [({"authenticated": True}, None), (None, "5" * 64)])
def test_receipt_and_typed_pin_must_travel_together(tmp_path, monkeypatch, receipt, pin):
    _parent(tmp_path)
    parent_authority, calls = _install(monkeypatch, plan=None)
    with pytest.raises(EvidenceRejected, match="travel together"):
        _run(tmp_path, parent_authority, receipt=receipt, receipt_pin=pin)
    assert "planner" not in calls


def test_planner_pin_mismatch_rejects_without_writing(tmp_path, monkeypatch):
    _parent(tmp_path)
    (tmp_path / "private").mkdir()
    error = EvidenceRejected("retrospective receipt differs from selected plan/index/source")
    parent_authority, _ = _install(monkeypatch, plan=None, planner_error=error)
    with pytest.raises(EvidenceRejected, match="differs from selected plan"):
        _run(tmp_path, parent_authority, receipt={"authenticated": True}, receipt_pin="5" * 64)
    assert not (tmp_path / "private" / SUCCESSOR_ID).exists()


def test_destination_inside_parent_is_refused(tmp_path, monkeypatch):
    root = _parent(tmp_path)
    parent_authority, calls = _install(monkeypatch, plan=None)
    with pytest.raises(EvidenceRejected, match="disjoint"):
        _run(tmp_path, parent_authority, destination=root / "successor")
    assert "reads" not in calls and not (root / "successor").exists()


def test_ready_successor_written_parent_untouched_and_original_linked(tmp_path, monkeypatch):
    root = _parent(tmp_path)
    (tmp_path / "private").mkdir()
    before = {path.name: path.read_bytes() for path in root.iterdir()}
    plan = FitReverificationPlan("ready-for-separate-writer", json.dumps(_summary("ready-for-separate-writer")).encode(),
                                 successor_authority_bytes=json.dumps(_successor_authority()).encode())
    parent_authority, calls = _install(monkeypatch, plan=plan, payloads=_ready_payloads())
    outcome = _run(tmp_path, parent_authority, receipt={"authenticated": True}, receipt_pin="5" * 64)
    assert outcome.state == "written"
    normalized = outcome.destination / writer.SUCCESSOR_DIRECTORY
    assert {path.name for path in normalized.iterdir()} == set(_ready_payloads())
    # Original archive/lineage are written byte-exact; the parent root is unchanged.
    assert (normalized / "fit-parent.json").read_bytes() == _ready_payloads()["fit-parent.json"]
    assert {path.name: path.read_bytes() for path in root.iterdir()} == before
    assert b'"state":"unknown"' in (root / "token-fit.json").read_bytes()
    # Successor is re-read from its staged copy under its own authority, after the parent read.
    staged = calls["reads"][1][0]
    assert calls["reads"][0][0] == root.resolve()
    assert staged.name == writer.SUCCESSOR_DIRECTORY and staged.parent.name.startswith(".stage-")
    assert calls["reads"][1][1].edition_id == SUCCESSOR_ID
    assert outcome.plan["parent_index_sha256"] == parent_authority.index_sha256
    assert (outcome.destination / writer.PROPOSED_AUTHORITY).exists()


def test_ready_payload_without_original_archive_is_rejected(tmp_path, monkeypatch):
    _parent(tmp_path)
    (tmp_path / "private").mkdir()
    payloads = _ready_payloads()
    del payloads["fit-parent.json"]
    plan = FitReverificationPlan("ready-for-separate-writer", json.dumps(_summary("ready-for-separate-writer")).encode(),
                                 successor_authority_bytes=json.dumps(_successor_authority()).encode())
    parent_authority, _ = _install(monkeypatch, plan=plan, payloads=payloads)
    with pytest.raises(EvidenceRejected, match="link original archive"):
        _run(tmp_path, parent_authority, receipt={"authenticated": True}, receipt_pin="5" * 64)
    assert not (tmp_path / "private" / SUCCESSOR_ID).exists()


def test_destination_name_must_equal_successor_edition_id(tmp_path, monkeypatch):
    _parent(tmp_path)
    (tmp_path / "private").mkdir()
    plan = FitReverificationPlan("ready-for-separate-writer", json.dumps(_summary("ready-for-separate-writer")).encode(),
                                 successor_authority_bytes=json.dumps(_successor_authority()).encode())
    parent_authority, _ = _install(monkeypatch, plan=plan, payloads=_ready_payloads())
    with pytest.raises(EvidenceRejected, match="collides"):
        _run(tmp_path, parent_authority, receipt={"authenticated": True}, receipt_pin="5" * 64,
             destination=tmp_path / "private" / "other-folder")
    assert list((tmp_path / "private").iterdir()) == []


def test_failed_successor_reread_leaves_no_published_destination(tmp_path, monkeypatch):
    _parent(tmp_path)
    (tmp_path / "private").mkdir()
    plan = FitReverificationPlan("ready-for-separate-writer", json.dumps(_summary("ready-for-separate-writer")).encode(),
                                 successor_authority_bytes=json.dumps(_successor_authority()).encode())
    parent_authority, calls = _install(monkeypatch, plan=plan, payloads=_ready_payloads())
    parent_read = writer.read_edition

    def reread_fails(root, *, authority):
        if calls.get("reads"):
            raise EvidenceRejected("successor index differs from externally approved byte pin")
        return parent_read(root, authority=authority)

    monkeypatch.setattr(writer, "read_edition", reread_fails)
    with pytest.raises(EvidenceRejected, match="approved byte pin"):
        _run(tmp_path, parent_authority, receipt={"authenticated": True}, receipt_pin="5" * 64)
    # Only a preserved hidden staging folder may remain; the published name never appears.
    assert not (tmp_path / "private" / SUCCESSOR_ID).exists()
    assert all(path.name.startswith(".stage-") for path in (tmp_path / "private").iterdir())


def test_successor_reusing_parent_identity_is_rejected(tmp_path, monkeypatch):
    _parent(tmp_path)
    (tmp_path / "private").mkdir()
    plan = FitReverificationPlan("ready-for-separate-writer", json.dumps(_summary("ready-for-separate-writer")).encode(),
                                 successor_authority_bytes=json.dumps({**_successor_authority(),
                                                                       "edition_id": PARENT_ID}).encode())
    parent_authority, _ = _install(monkeypatch, plan=plan, payloads=_ready_payloads())
    with pytest.raises(EvidenceRejected, match="collides"):
        _run(tmp_path, parent_authority, receipt={"authenticated": True}, receipt_pin="5" * 64)
    assert not (tmp_path / "private" / SUCCESSOR_ID).exists()
