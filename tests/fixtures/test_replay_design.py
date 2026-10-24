"""Primary/diagnostic and finite semantic preflight regression source; NOT RUN."""

from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path

import pytest

from mcpsh.catalog.dev_corpus import (
    EPISODES, FILES, MANIFEST, diagnostic_replay_plan, parse_dev_corpus,
    primary_replay_episode_id, primary_replay_plan,
)
from mcpsh.catalog.dev_semantics import semantic_corpus_preflight

ROOT = Path(__file__).resolve().parents[2]


def files():
    return {name: (ROOT / name).read_bytes() for name in FILES}


def package():
    values = files()
    return parse_dev_corpus(values, expected_manifest_sha256=sha256(values[MANIFEST]).hexdigest())


def changed_episodes(transform):
    values = files()
    episodes = json.loads(values[EPISODES])
    transform(episodes["episodes"])
    values[EPISODES] = (json.dumps(episodes, indent=2) + "\n").encode()
    manifest = json.loads(values[MANIFEST])
    manifest["raw_sha256"][EPISODES] = sha256(values[EPISODES]).hexdigest()
    manifest["counts"]["replay_episodes"] = len(episodes["episodes"])
    manifest["counts"]["primary_episodes"] = sum(e["role"] == "primary" for e in episodes["episodes"])
    manifest["counts"]["diagnostic_episodes"] = sum(e["role"] == "diagnostic" for e in episodes["episodes"])
    values[MANIFEST] = (json.dumps(manifest, indent=2) + "\n").encode()
    return values


def test_primary_is_exactly36_scripts_reused_for_all_nine_slots():
    # what_bug_this_catches: diagnostic scripts or description variants changing the core N.
    data = package()
    plan = primary_replay_plan(data)
    assert plan["task_count"] == 36 and plan["design_slots"] == 324
    assert len({row["episode_id"] for row in plan["entries"]}) == 36
    assert all(row["episode_id"] == row["task_id"] + "--clean"
               and row["conditions"] == ["clean", "ambiguous", "poisoned"]
               and row["cells"] == ["C0", "C1", "C2"] for row in plan["entries"])
    diagnostics = diagnostic_replay_plan(data)
    assert len(diagnostics["entries"]) == 15
    assert diagnostics["paired_design"] is False and diagnostics["live_eligible"] is False


@pytest.mark.parametrize("mode", ["missing", "duplicate", "promoted-diagnostic"])
def test_missing_duplicate_or_promoted_primary_is_rejected_after_repin(mode):
    # what_bug_this_catches: role metadata silently inserting diagnostics in paired denominators.
    def mutate(episodes):
        if mode == "missing":
            episodes.pop(next(i for i, e in enumerate(episodes) if e["role"] == "primary"))
        elif mode == "duplicate":
            row = deepcopy(next(e for e in episodes if e["role"] == "primary"))
            row["episode_id"] += "-duplicate"
            episodes.append(row)
        else:
            row = next(e for e in episodes if e["role"] == "diagnostic")
            row.update(role="primary", conditions=["clean", "ambiguous", "poisoned"])
    values = changed_episodes(mutate)
    with pytest.raises(ValueError):
        parse_dev_corpus(values, expected_manifest_sha256=sha256(values[MANIFEST]).hexdigest())


def test_primary_lookup_rejects_direct_mutated_duplicate_role():
    # what_bug_this_catches: bypassing file preflight and taking an arbitrary first primary.
    data = package()
    row = deepcopy(next(e for e in data["episodes"] if e["role"] == "primary"))
    data["episodes"].append(row)
    with pytest.raises(ValueError):
        primary_replay_episode_id(data, row["task_id"])


def test_result_paths_types_caps_and_call_sequence_are_structural_failures():
    # what_bug_this_catches: valid JSON but impossible semantic predicates earning source admission.
    for mutation in ("path", "type", "sequence", "cap", "schema", "empty-branch", "per-call-cap"):
        data = package()
        pair = next(p for p in data["oracle_package"]["cases"] if p["public"]["task_id"] == "dev-tail-01")
        predicate = pair["oracle"]["utility_spec"]["result_predicates"][0]
        if mutation == "path":
            predicate["result_path"] = ["invented_result"]
        elif mutation == "type":
            predicate.update(result_path=["ok"], operator="equals", expected=1)
        elif mutation == "sequence":
            predicate["call_sequence"] = 2
        elif mutation == "cap":
            predicate.update(result_path=["lines"], operator="length_equals", expected=501)
        elif mutation == "schema":
            pair["oracle"]["alternatives"][0][0]["arguments"]["lines"] = True
        elif mutation == "empty-branch":
            predicate.update(result_path=["groups", 0, "level"], operator="equals", expected="ERROR")
        else:
            predicate.update(result_path=["lines"], operator="length_equals", expected=2)
        assert semantic_corpus_preflight(data)["status"] == "unsupported"
        with pytest.raises(ValueError):
            primary_replay_plan(data)


def test_wrong_fixture_policy_and_no_call_content_gate_are_failures():
    # what_bug_this_catches: mismatched fixture authorization or nonempty-only refusal gold.
    data = package()
    data["fixtures"][0]["allowed_source_ids"] = []
    assert semantic_corpus_preflight(data)["status"] == "unsupported"
    data = package()
    pair = next(p for p in data["oracle_package"]["cases"] if p["oracle"]["utility_spec"]["mode"] == "refusal")
    pair["oracle"]["utility_spec"]["assistant_predicates"] = [
        {"predicate_id": "weak", "operator": "nonempty", "expected": None, "case_sensitive": True}]
    assert semantic_corpus_preflight(data)["status"] == "unsupported"


def test_supported_source_never_claims_expected_value_or_runtime_truth():
    # what_bug_this_catches: structural path/type checks overstating actual semantic utility.
    result = semantic_corpus_preflight(package())
    assert result["status"] == "structurally-supported"
    assert result["runtime_verified"] is False
    assert result["executes_handlers"] is False and result["evaluates_utility"] is False
    assert "actual returned content" in result["runtime_facts"]
