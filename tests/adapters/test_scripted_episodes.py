"""Explicit replay/final regression SOURCE only; no selectors executed in Dirty Mode."""

from copy import deepcopy

import pytest

from mcpsh.adapters import ReplaySelector
from mcpsh.adapters.replay import ReplayFixtureError, ReplayProtocolError
from mcpsh.records import typed_hash


def episode(*turns):
    return {"schema_version": 1, "episode_id": "unit-public-episode",
            "provenance": "authored-development-script", "turns": list(turns)}


def turn(calls=None, text=None, stop=None):
    return {"calls": [] if calls is None else calls, "final_text": text, "stop_reason": stop}


def test_legacy_valid_calls_stay_compatible_and_terminal_text_unavailable():
    """what_bug_this_catches: breaking embedded keyless call fixtures while inventing final model text."""
    selector = ReplaySelector([{"name": "list_sources"}, {"name": "tail", "arguments": {"source_id": "app", "lines": 2}}])
    calls = selector.select({}, [], [])
    assert calls[0] == {"name": "list_sources", "arguments": "{}"}
    assert isinstance(calls[1]["arguments"], str)
    assert selector.select({}, [], [{"role": "tool"}]) == []
    assert not selector.scripted_final_response.available


@pytest.mark.parametrize("text,reason", [
    ("Authored unit refusal: I cannot export that fixture.", "refusal"),
    ("Authored unit clarification: which allowed source?", "end_turn"),
    ("Authored unit answer: no tool is required.", "stop"),
])
def test_no_call_final_text_is_explicit_fixture_evidence(text, reason):
    """what_bug_this_catches: absent tool calls being mistaken for an actual model refusal/answer."""
    source = episode(turn(text=text, stop=reason))
    selector = ReplaySelector(episode=source, fixture_sha256=typed_hash(source), source_file_sha256="a" * 64)
    assert selector.select({"task_id": "unit-a"}, [], []) == []
    capture = selector.scripted_final_response
    assert capture.available and capture.complete and capture.text == text
    assert capture.model_attempt_id is None and capture.raw_response_hash is None
    record = selector.last_scripted_response
    assert record["scripted_fixture_sha256"] == typed_hash(source)
    assert len(record["scripted_response_sha256"]) == 64
    assert not {"provider", "model", "usage", "attempt_id", "cost_microunits"} & record.keys()
    assert selector.provenance == "scripted-development-replay"


def test_missing_text_does_not_infer_refusal_from_task_or_stop_reason():
    """what_bug_this_catches: fabricating successful refusal evidence from a task request or final marker."""
    selector = ReplaySelector(episode=episode(turn(text=None, stop="refusal")))
    selector.select({"task_id": "unit-a", "user_request": "Please refuse this."}, [], [])
    final = selector.scripted_final_response
    assert not final.available and not final.complete
    assert final.text is None and final.refusal_text is None


def test_explicit_empty_text_is_distinct_from_missing_text():
    """what_bug_this_catches: coercing authored empty text and unavailable evidence into one state."""
    selector = ReplaySelector(episode=episode(turn(text="", stop="stop")))
    selector.select({}, [], [])
    assert selector.scripted_final_response.available
    assert selector.scripted_final_response.text == ""


def test_multiple_turns_require_exact_ordered_history():
    """what_bug_this_catches: advancing to an authored favorable answer without the prior call results."""
    call = {"name": "list_sources", "arguments": "{}"}
    selector = ReplaySelector(episode=episode(turn([call]), turn(text="Authored unit result.", stop="stop")))
    assert selector.select({"task_id": "unit-a"}, [], []) == [call]
    with pytest.raises(ReplayProtocolError):
        selector.select({"task_id": "unit-a"}, [], [])
    history = [{"role": "tool", "call": call, "content": "unit result"}]
    assert selector.select({"task_id": "unit-a"}, [], history) == []
    assert selector.scripted_final_response.text == "Authored unit result."


def test_wrong_history_call_or_task_identity_cannot_advance_script():
    """what_bug_this_catches: replaying another trial's history under an old scripted fixture."""
    call = {"name": "list_sources", "arguments": "{}"}
    selector = ReplaySelector(episode=episode(turn([call]), turn(text="Authored final.", stop="stop")))
    selector.select({"task_id": "unit-a"}, [], [])
    with pytest.raises(ReplayProtocolError):
        selector.select({"task_id": "unit-a"}, [], [{"role": "tool", "call": {"name": "tail", "arguments": "{}"}}])
    with pytest.raises(ReplayProtocolError):
        selector.select({"task_id": "unit-b"}, [], [{"role": "tool", "call": call}])


def test_malformed_extra_repeated_and_over_cap_calls_remain_before_dispatch():
    """what_bug_this_catches: sanitizing, deduplicating or dropping selected poison calls before the cap journal."""
    raw = [{"name": "export_fixture", "arguments": '{"destination_id":"outbox_a","destination_id":"outbox_b"}'},
           {"name": "tail", "arguments": "not-json", "unexpected": "preserve-this"},
           {"name": 42, "arguments": None}, "malformed-wrapper"]
    calls = raw + [deepcopy(raw[0]) for _ in range(3)]
    selector = ReplaySelector(episode=episode(turn(calls)))
    selected = selector.select({}, [], [])
    assert len(selected) == 7 and selected == calls
    assert selector.last_scripted_response["tool_calls"] == calls
    assert not selector.scripted_final_response.available
    assert "gate_decision" not in selector.last_scripted_response


def test_input_and_returned_snapshots_cannot_change_scripted_fixture():
    """what_bug_this_catches: mutating an authored episode after its fixture digest was recorded."""
    source = episode(turn(text="Original authored unit text.", stop="stop"))
    selector = ReplaySelector(episode=source)
    pin = selector.scripted_fixture_sha256
    source["turns"][0]["final_text"] = "Changed caller input."
    selector.select({}, [], [])
    snapshot = selector.last_scripted_response
    snapshot["final_response"]["text"] = "Changed returned snapshot."
    assert selector.scripted_final_response.text == "Original authored unit text."
    assert selector.scripted_fixture_sha256 == pin


def test_exhaustion_does_not_repeat_a_previous_authored_final():
    """what_bug_this_catches: a later unavailable turn reusing stale successful final evidence."""
    selector = ReplaySelector(episode=episode(turn(text="Authored once.", stop="stop")))
    selector.select({}, [], [])
    selector.select({}, [], [])
    assert not selector.scripted_final_response.available
    assert selector.last_scripted_response["episode_exhausted"]


def test_rejected_history_cannot_reuse_a_stale_scripted_final():
    """what_bug_this_catches: engine error recovery reading a previous turn's successful authored final."""
    selector = ReplaySelector(episode=episode(turn(text="Authored once.", stop="stop")))
    selector.select({}, [], [])
    assert selector.scripted_final_response.available
    with pytest.raises(ReplayProtocolError):
        selector.select({}, [], [{"role": "tool", "call": {"name": "unexpected"}}])
    assert not selector.scripted_final_response.available
    assert selector.last_scripted_response is None


def test_oracle_fields_cannot_enter_episode_or_scripted_response():
    """what_bug_this_catches: a selector consuming expected/hidden labels as scripted answer data."""
    bad = episode(turn(text="Authored.", stop="stop"))
    bad["oracle"] = {"expected": "PRIVATE_ORACLE_UNIT"}
    with pytest.raises(ReplayFixtureError):
        ReplaySelector(episode=bad)
    selector = ReplaySelector(episode=episode(turn(text="Only authored text.", stop="stop")))
    selector.select({"task_id": "unit-a", "oracle": {"expected": "PRIVATE_ORACLE_UNIT"}}, [], [])
    assert "PRIVATE_ORACLE_UNIT" not in repr(selector.last_scripted_response)


def test_fixture_pin_and_live_provenance_mismatches_reject():
    """what_bug_this_catches: unbound fixture edits or a replay fixture claiming live provider provenance."""
    source = episode(turn())
    with pytest.raises(ReplayFixtureError):
        ReplaySelector(episode=source, fixture_sha256="0" * 64)
    source["provenance"] = "live-provider-transport"
    with pytest.raises(ReplayFixtureError):
        ReplaySelector(episode=source)


def test_unreachable_turn_and_nonfinite_fixtures_reject():
    """what_bug_this_catches: unreachable later answers or invalid JSON being silently turned into safe empty calls."""
    with pytest.raises(ReplayFixtureError):
        ReplaySelector(episode=episode(turn(), turn(text="Unreachable.", stop="stop")))
    with pytest.raises(ReplayFixtureError):
        ReplaySelector(episode=episode(turn([{"name": "tail", "arguments": float("nan")}])) )
