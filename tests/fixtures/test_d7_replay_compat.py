"""Authored integration/failure regressions against D7's implemented interface.

No selector, model, fixture or test was invoked during Dirty Mode construction.
Future protocol-only mock histories here are not server/effect evidence.
"""

from copy import deepcopy
from hashlib import sha256
from pathlib import Path

import pytest

from mcpsh.adapters.replay import ReplayFixtureError, ReplayProtocolError, ReplaySelector
from mcpsh.catalog.dev_corpus import (
    EPISODES, FILES, MANIFEST, parse_dev_corpus, public_task_projection,
    replay_selector_kwargs, validate_selector_episode,
)
from mcpsh.records.hashing import strict_json_loads, typed_hash

ROOT = Path(__file__).resolve().parents[2]


def package():
    files = {name: (ROOT / name).read_bytes() for name in FILES}
    return parse_dev_corpus(files, expected_manifest_sha256=sha256(files[MANIFEST]).hexdigest())


def projected(identifier):
    data = package()
    kwargs = replay_selector_kwargs(data, identifier)
    task_id = identifier.split("--", 1)[0]
    return public_task_projection(data, task_id), kwargs


def test_every_authored_projection_matches_actual_constructor_and_script_pin():
    # what_bug_this_catches: unsupported stop/header/turn shape hidden by data-only checks.
    data = package()
    for source in data["episodes"]:
        kwargs = replay_selector_kwargs(data, source["episode_id"])
        validate_selector_episode(kwargs["episode"])
        selector = ReplaySelector(**kwargs)
        assert selector.scripted_fixture_sha256 == typed_hash(kwargs["episode"])
        assert selector.scripted_final_response.available is False


@pytest.mark.parametrize("identifier", ["dev-no_tool-01--clean", "dev-no_tool-02--clean",
                                      "dev-no_tool-03--clean"])
def test_explicit_terminal_text_is_scripted_and_has_no_provider_parent(identifier):
    # what_bug_this_catches: no-call final text fabricated as live ModelAttempt/response bytes.
    public, kwargs = projected(identifier)
    selector = ReplaySelector(**kwargs)
    assert selector.select(public, [], []) == []
    final = selector.scripted_final_response
    assert final.available is True and final.complete is True
    assert final.model_attempt_id is None and final.raw_response_hash is None
    assert selector.last_scripted_response["provenance"] == "scripted-development-replay"


@pytest.mark.parametrize("identifier", ["dev-no_tool-03--missing-final",
                                      "dev-no_tool-01--truncated-final", "dev-no_tool-02--missing-stop"])
def test_missing_or_nonterminal_final_never_becomes_complete(identifier):
    # what_bug_this_catches: treating any authored text/abstention as completed utility.
    public, kwargs = projected(identifier)
    selector = ReplaySelector(**kwargs)
    assert selector.select(public, [], []) == []
    assert selector.scripted_final_response.complete is False
    if identifier.endswith("missing-final"):
        assert selector.scripted_final_response.available is False


def test_answer_after_calls_is_a_reachable_history_checked_terminal_turn():
    # what_bug_this_catches: final text attached to a call turn remaining forever incomplete.
    public, kwargs = projected("dev-tail-01--result-then-final")
    assert len(kwargs["episode"]["turns"]) == 2
    selector = ReplaySelector(**kwargs)
    calls = selector.select(public, [], [])
    assert len(calls) == 1 and selector.scripted_final_response.available is False
    with pytest.raises(ReplayProtocolError):
        selector.select(public, [], [])
    mock_history = [{"role": "tool", "call": deepcopy(call)} for call in calls]
    assert selector.select(public, [], mock_history) == []
    assert selector.scripted_final_response.complete is True


def test_over_cap_and_malformed_selected_wrappers_are_not_repaired_or_dropped():
    # what_bug_this_catches: pre-cap journal denominator reduced by the episode adapter.
    for identifier in ("dev-tail-03--over-cap-journal", "dev-tail-04--malformed-wrapper"):
        public, kwargs = projected(identifier)
        expected = deepcopy(kwargs["episode"]["turns"][0]["calls"])
        selector = ReplaySelector(**kwargs)
        assert selector.select(public, [], []) == expected
        if identifier.endswith("over-cap-journal"):
            assert len(expected) == 7
        else:
            assert expected[1] == 17 and expected[0]["extra"] is True


def test_unsupported_stop_wrong_pin_and_unreachable_turn_are_failures():
    # what_bug_this_catches: provisional custom stop markers and self-described pins accepted.
    _, kwargs = projected("dev-no_tool-01--clean")
    wrong_stop = deepcopy(kwargs["episode"])
    wrong_stop["turns"][0]["stop_reason"] = "scripted-development-stop"
    with pytest.raises(ValueError):
        validate_selector_episode(wrong_stop)
    with pytest.raises(ReplayFixtureError):
        ReplaySelector(episode=wrong_stop)
    with pytest.raises(ReplayFixtureError):
        ReplaySelector(**{**kwargs, "fixture_sha256": "0" * 64})
    unreachable = deepcopy(kwargs["episode"])
    unreachable["turns"].append({"calls": [], "final_text": "Never reachable", "stop_reason": "stop"})
    with pytest.raises(ValueError):
        validate_selector_episode(unreachable)
    with pytest.raises(ReplayFixtureError):
        ReplaySelector(episode=unreachable)


def test_raw_strings_and_source_package_pin_remain_exact():
    # what_bug_this_catches: parsed/reserialized arguments substituted for authored malformed bytes.
    _, kwargs = projected("dev-tail-04--duplicate-json-key-intent")
    arguments = kwargs["episode"]["turns"][0]["calls"][0]["arguments"]
    assert arguments.count('"destination_id"') == 2
    assert kwargs["source_file_sha256"] == sha256((ROOT / EPISODES).read_bytes()).hexdigest()
    with pytest.raises(ValueError):
        strict_json_loads(arguments)


@pytest.mark.parametrize("change", ["boolean-version", "extra-field", "surrogate", "too-long-text"])
def test_preflight_and_actual_consumer_reject_invalid_outer_fields(change):
    # what_bug_this_catches: schema coercion or UTF-8 byte limits missed by preflight.
    _, kwargs = projected("dev-no_tool-01--clean")
    episode = deepcopy(kwargs["episode"])
    if change == "boolean-version":
        episode["schema_version"] = True
    elif change == "extra-field":
        episode["observed"] = True
    elif change == "surrogate":
        episode["turns"][0]["final_text"] = "\ud800"
    else:
        episode["turns"][0]["final_text"] = "\u00e9" * 32769
    with pytest.raises(ValueError):
        validate_selector_episode(episode)
    with pytest.raises((ReplayFixtureError, UnicodeError)):
        ReplaySelector(episode=episode)
