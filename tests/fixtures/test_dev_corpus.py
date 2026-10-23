"""Public corpus regression source; not run during Dirty Mode construction."""

from hashlib import sha256
import json
from pathlib import Path

import pytest

from mcpsh.catalog.dev_corpus import (
    EPISODES, FILES, FIXTURES, MANIFEST, ORACLES, TASKS,
    corpus_pins, parse_dev_corpus, public_task_projection, replay_episode_projection,
    replay_selector_kwargs,
)

ROOT = Path(__file__).resolve().parents[2]


def source_bytes():
    return {name: (ROOT / name).read_bytes() for name in FILES}


def parse(files):
    return parse_dev_corpus(files, expected_manifest_sha256=sha256(files[MANIFEST]).hexdigest())


def repin(files, name, value):
    result = dict(files)
    result[name] = value if isinstance(value, bytes) else (
        json.dumps(value, ensure_ascii=True, indent=2) + "\n").encode()
    manifest = json.loads(result[MANIFEST])
    manifest["raw_sha256"][name] = sha256(result[name]).hexdigest()
    result[MANIFEST] = (json.dumps(manifest, indent=2) + "\n").encode()
    return result


def test_complete_public_package_has_all36_and_replay_only_provenance():
    # what_bug_this_catches: a class/case silently disappearing in development evaluation.
    package = parse(source_bytes())
    assert corpus_pins(package)["cases"] == 36
    assert corpus_pins(package)["episodes"] == 46
    assert {row["oracle"]["utility_version"] for row in package["oracle_package"]["cases"]} == {"semantic-v2"}
    assert all(episode["provenance"]["model_generated"] is False for episode in package["episodes"])


def test_call_only_proxy_or_missing_content_predicate_is_rejected_after_repin():
    # what_bug_this_catches: successful call shape silently replacing result utility.
    files = source_bytes()
    package = json.loads(files[ORACLES])
    package["cases"][0]["oracle"]["utility_spec"]["result_predicates"] = []
    with pytest.raises(ValueError):
        parse(repin(files, ORACLES, package))


def test_wrong_clean_script_does_not_replace_canonical_selection_truth():
    # what_bug_this_catches: a drifted demo script silently becoming expected utility.
    files = source_bytes()
    tasks = json.loads(files[TASKS])
    tasks[0]["scripted_calls"] = [{"name": "tail", "arguments": '{"source_id":"app","lines":1}'}]
    with pytest.raises(ValueError):
        parse(repin(files, TASKS, tasks))


def test_missing_case_and_duplicate_fixture_are_not_filled_by_defaults():
    # what_bug_this_catches: fallback data hiding an incomplete task/fixture join.
    files = source_bytes()
    tasks = json.loads(files[TASKS])[:-1]
    with pytest.raises(ValueError):
        parse(repin(files, TASKS, tasks))
    fixtures = json.loads(files[FIXTURES])
    fixtures[-1]["fixture_ref"] = fixtures[0]["fixture_ref"]
    with pytest.raises(ValueError):
        parse(repin(files, FIXTURES, fixtures))


def test_manifest_pin_and_raw_hash_both_matter():
    # what_bug_this_catches: a self-described manifest accepted as external authority.
    files = source_bytes()
    with pytest.raises(ValueError):
        parse_dev_corpus(files, expected_manifest_sha256="0" * 64)
    files[TASKS] = b" " + files[TASKS]
    with pytest.raises(ValueError):
        parse(files)


def test_malformed_raw_intent_and_duplicate_calls_survive_projection():
    # what_bug_this_catches: replay repairing malformed raw arguments or deduplicating calls.
    package = parse(source_bytes())
    malformed = replay_episode_projection(package, "dev-tail-04--duplicate-json-key-intent")
    assert malformed["calls"][0]["arguments"].count('"destination_id"') == 2
    assert sha256(malformed["calls"][0]["arguments"].encode()).hexdigest() == malformed["raw_argument_sha256"][0]
    duplicate = replay_episode_projection(package, "dev-tail-03--duplicate")
    assert duplicate["calls"][0] == duplicate["calls"][1]
    assert len(duplicate["calls"]) == 2


def test_missing_final_and_observer_request_are_not_observed_evidence():
    # what_bug_this_catches: no-call scripts inventing refusals or safe observer results.
    package = parse(source_bytes())
    missing = replay_episode_projection(package, "dev-no_tool-03--missing-final")
    assert missing["scripted_final"] is None
    unknown = replay_episode_projection(package, "dev-tail-06--unknown-observer-control")
    assert unknown["observer_fault_request"] == "omit-server-end-event"
    assert "observation" not in unknown and "result_captures" not in unknown


def test_public_task_projection_cannot_carry_oracle_or_fixture_sentinel():
    # what_bug_this_catches: author labels reaching selectors via whole-wrapper serialization.
    package = parse(source_bytes())
    public = public_task_projection(package, "dev-discovery-01")
    assert set(public) == {"task_id", "user_request", "allowed_source_ids", "fixture_ref"}
    assert "utility_spec" not in json.dumps(public)
    assert "PUBLIC_SYNTHETIC_SENTINEL" not in json.dumps(public)


def test_exact_d7_projection_separates_script_hash_from_physical_fixture():
    # what_bug_this_catches: D2 fixture payload hash supplied as D7 script identity.
    package = parse(source_bytes())
    episode_id = "dev-no_tool-03--missing-final"
    kwargs = replay_selector_kwargs(package, episode_id)
    assert set(kwargs) == {"episode", "fixture_sha256", "source_file_sha256"}
    assert kwargs["episode"]["turns"][0]["final_text"] is None
    assert kwargs["fixture_sha256"] != replay_episode_projection(package, episode_id)["fixture_payload_sha256"]
    assert kwargs["source_file_sha256"] == sha256(source_bytes()[EPISODES]).hexdigest()


def test_duplicate_json_keys_and_forged_live_provenance_are_rejected():
    # what_bug_this_catches: permissive decoding or flag coercion relabeling scripts live.
    files = source_bytes()
    token = b'"version": "m5-dev-replay-episodes-1"'
    duplicate = files[EPISODES].replace(token, token + b", " + token, 1)
    with pytest.raises(ValueError):
        parse(repin(files, EPISODES, duplicate))
    files = source_bytes()
    episodes = json.loads(files[EPISODES])
    episodes["episodes"][0]["provenance"]["model_generated"] = 0
    with pytest.raises(ValueError):
        parse(repin(files, EPISODES, episodes))
