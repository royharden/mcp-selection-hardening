"""Calibration producer/consumer regression SOURCE, not executed during Dirty Mode."""

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from mcpsh.calibration import (
    DevelopmentCase, DraftArm, DraftPilotManifest, planned_caps, threshold_proposal,
)
from mcpsh.calibration.models import CLASSES


def publisher_module():
    path = Path(__file__).resolve().parents[2] / "scripts/eval.py"
    spec = importlib.util.spec_from_file_location("public_test_eval_publisher", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def draft_manifest():
    return DraftPilotManifest(
        arms=(DraftArm(slot="public-arm-a"), DraftArm(slot="public-arm-b")),
        cases=tuple(DevelopmentCase(task_id="public-" + name, task_class=name) for name in CLASSES),
        development_input_sha256="a" * 64,
    )


def test_real_pilot_planner_envelope_is_accepted_without_dispatch():
    """what_bug_this_catches: eval expected inner model, but pilot.py emits an envelope."""
    publisher = publisher_module()
    draft = draft_manifest()
    envelope = {"manifest": draft.model_dump(mode="json"), "planned_caps": planned_caps(draft),
                "threshold_proposal": threshold_proposal().model_dump(mode="json")}
    parsed = publisher.pilot_draft(json.dumps(envelope).encode())
    assert parsed == draft
    assert parsed.mode == "draft-no-dispatch"
    assert parsed.authorized_spend_receipt is None


def test_cached_draft_metadata_cannot_change_typed_counts():
    """what_bug_this_catches: cached proposed counts become authority through coercion."""
    publisher = publisher_module()
    draft = draft_manifest()
    caps = planned_caps(draft)
    caps["task_runs"] = str(caps["task_runs"])
    envelope = {"manifest": draft.model_dump(mode="json"), "planned_caps": caps,
                "threshold_proposal": threshold_proposal().model_dump(mode="json")}
    with pytest.raises(ValueError, match="cached"):
        publisher.pilot_draft(json.dumps(envelope).encode())


def test_full36_bridge_does_not_reach_any_callback_without_closed_mode(monkeypatch):
    """what_bug_this_catches: even a fake runner was invoked before runtime admission."""
    from mcpsh.runner import development

    def forbidden(*args, **kwargs):
        raise AssertionError("unauthorized callback/orchestrator was reached")

    monkeypatch.setattr(development, "execute_development_protocol", forbidden)
    admission = SimpleNamespace(authorized=False, dirty_mode_closed=False)
    with pytest.raises(ValueError, match="runtime grant"):
        development.execute_admitted_development_protocol(
            None, admission=admission, clock=forbidden, manifest=None, cases={},
            selector_factory=forbidden, attempt_mapper=forbidden, row_sink=forbidden)
