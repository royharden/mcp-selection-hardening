"""Bounded public-development data preflight/projections; no fixture execution.

This is not a second model/runner loader. D1 retains canonical record admission
and server-owned argument/fixture validation. Caller supplies authorized bytes.
"""

from copy import deepcopy
from datetime import datetime
from hashlib import sha256
import json
import re
from typing import Any

CORPUS_VERSION = "m5-dev-semantic-v2"
MANIFEST_VERSION = "m5-dev-corpus-manifest-3"
EPISODE_VERSION = "m5-dev-replay-episodes-2"
TASKS = "fixtures/dev/tasks.json"
ORACLES = "gold/dev/oracles.json"
FIXTURES = "fixtures/dev/fixtures.json"
TREATMENTS = "fixtures/dev/treatments.json"
EPISODES = "fixtures/dev/replay-episodes.json"
MANIFEST = "fixtures/dev/corpus-manifest-v2.json"
DATA_FILES = {TASKS, ORACLES, FIXTURES, TREATMENTS, EPISODES}
FILES = DATA_FILES | {MANIFEST}
PUBLIC_FIELDS = {"task_id", "user_request", "allowed_source_ids", "fixture_ref"}
CLASSES = {"discovery", "tail", "search", "range", "error_inspection", "no_tool"}
TOOLS = {"list_sources", "tail", "search", "read_range", "errors", "recent_lines",
         "find_literal", "error_counts", "export_fixture"}
ORACLE_FIELDS = {"task_id", "alternatives", "utility_alternatives", "required_output_text",
                 "utility_version", "utility_spec", "prohibited_source_ids", "prohibited_tools",
                 "family_id", "split", "attack_family"}
SPEC_FIELDS = {"mode", "result_predicates", "assistant_predicates", "combine",
               "require_final_response", "require_no_calls"}
EPISODE_FIELDS = {"episode_id", "task_id", "condition", "fixture_ref", "fixture_payload_sha256",
                  "calls", "raw_argument_sha256", "scripted_final", "observer_fault_request",
                  "observer_expectation", "provenance", "role", "conditions", "cells"}
PRIMARY_CONDITIONS = ["clean", "ambiguous", "poisoned"]
PRIMARY_CELLS = ["C0", "C1", "C2"]
REPLAY_DESIGN = {"primary_id_suffix": "--clean", "primary_conditions": PRIMARY_CONDITIONS,
                 "primary_cells": PRIMARY_CELLS, "diagnostics_are_paired": False,
                 "diagnostics_are_live_samples": False}
PROVENANCE = {"mode": "replay", "basis": "scripted-public-development",
              "model_generated": False, "cost_basis": "non-model",
              "execution": "source-authored-unexecuted"}
REPLAY_STOP_REASONS = {"stop", "end_turn", "stop_sequence", "refusal", "length",
                       "max_tokens", "content_filter"}
MAX_SELECTED_CALLS = 65536
MAX_SELECTOR_EPISODE_BYTES = 4 * 1024 * 1024


def _require(value: bool, code: str) -> None:
    if not value:
        raise ValueError("development corpus: " + code)


def _digest(value: Any) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _text(value: Any, cap: int, *, empty: bool = False) -> bool:
    return (isinstance(value, str) and (empty or bool(value))
            and len(value.encode("utf-8", errors="strict")) <= cap and "\x00" not in value)


def _typed_hash(value: Any) -> str:
    return sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False,
                            separators=(",", ":")).encode("utf-8")).hexdigest()


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        _require(key not in result, "duplicate JSON key")
        result[key] = value
    return result


def _nonfinite(_value):
    raise ValueError("development corpus: nonfinite JSON")


def _public(value: Any) -> None:
    _require(isinstance(value, dict) and set(value) == PUBLIC_FIELDS, "public field allowlist")
    _require(_text(value["task_id"], 256) and _text(value["user_request"], 65536)
             and _text(value["fixture_ref"], 64), "public text bounds")
    sources = value["allowed_source_ids"]
    _require(isinstance(sources, list) and all(isinstance(s, str) for s in sources)
             and len(sources) == len(set(sources)) and set(sources) <= {"app", "worker"},
             "public source policy")


def _raw_calls(calls: Any) -> None:
    _require(isinstance(calls, list) and len(calls) <= 6, "raw-call cap")
    for call in calls:
        _require(isinstance(call, dict) and set(call) == {"name", "arguments"}
                 and isinstance(call["name"], str) and call["name"] in TOOLS
                 and _text(call["arguments"], 65536, empty=True), "ordered raw-call shape")


def _argument_pins(calls: list[Any]) -> list[str | None]:
    # A malformed wrapper may have no original argument string. Do not fabricate
    # raw bytes by serializing an object or replacing it with an empty object.
    return [sha256(call["arguments"].encode("utf-8")).hexdigest()
            if isinstance(call, dict) and isinstance(call.get("arguments"), str) else None
            for call in calls]


def _validate_selector_episode(episode: Any) -> None:
    """Pure preflight of D7 implemented v1 outer contract; not selector execution.

    Call wrappers deliberately remain arbitrary finite JSON selections. D7 and
    the runner own their faithful pre-dispatch rejection/journal handling.
    """
    _require(isinstance(episode, dict) and set(episode) == {
        "schema_version", "episode_id", "provenance", "turns"
    } and type(episode["schema_version"]) is int and episode["schema_version"] == 1
             and episode["provenance"] == "authored-development-script"
             and isinstance(episode["episode_id"], str) and bool(episode["episode_id"])
             and len(episode["episode_id"].encode("utf-8")) <= 256, "D7 replay episode header")
    _require(len(json.dumps(episode, ensure_ascii=True, sort_keys=True, allow_nan=False,
                            separators=(",", ":")).encode("ascii")) <= MAX_SELECTOR_EPISODE_BYTES,
             "D7 replay snapshot byte cap")
    _typed_hash(episode)  # Reject invalid Unicode scalars, including malformed wrappers.
    turns = episode["turns"]
    _require(isinstance(turns, list) and 1 <= len(turns) <= 3, "D7 replay turn count")
    selected = 0
    for index, turn in enumerate(turns):
        _require(isinstance(turn, dict) and set(turn) == {"calls", "final_text", "stop_reason"}
                 and isinstance(turn["calls"], list), "D7 replay turn fields")
        selected += len(turn["calls"])
        _require(selected <= MAX_SELECTED_CALLS, "D7 selected-call journal cap")
        _require(bool(turn["calls"]) or index == len(turns) - 1, "unreachable authored replay turn")
        _require(turn["final_text"] is None or
                 (isinstance(turn["final_text"], str) and len(turn["final_text"].encode("utf-8")) <= 65536),
                 "D7 final text bounds")
        reason = turn["stop_reason"]
        _require(reason is None or (isinstance(reason, str) and reason in REPLAY_STOP_REASONS),
                 "D7 supported stop reason")


def validate_selector_episode(episode: Any) -> None:
    try:
        _validate_selector_episode(episode)
    except (TypeError, UnicodeError, RecursionError, OverflowError) as exc:
        raise ValueError("development corpus: invalid finite Unicode replay projection") from exc


def _selector_episode(source: dict[str, Any]) -> dict[str, Any]:
    final, calls = source["scripted_final"], deepcopy(source["calls"])
    _require(final is None or final["refusal_text"] is None,
             "separate refusal_text is not representable by scripted turn schema v1")
    terminal = {"calls": [], "final_text": None if final is None else final["text"],
                "stop_reason": None if final is None else final["stop_reason"]}
    if calls and final is not None:
        turns = [{"calls": calls, "final_text": None, "stop_reason": None}, terminal]
    else:
        turns = [{**terminal, "calls": calls}]
    episode = {"schema_version": 1, "episode_id": source["episode_id"],
               "provenance": "authored-development-script", "turns": turns}
    validate_selector_episode(episode)
    return episode


def _oracle(value: Any, task_id: str, task_class: str) -> None:
    _require(isinstance(value, dict) and set(value) == ORACLE_FIELDS, "oracle fields")
    _require(value["task_id"] == task_id and value["split"] == "development"
             and value["utility_version"] == "semantic-v2"
             and value["family_id"] == "development-template-" + task_class,
             "development semantic identity")
    prohibited = value["prohibited_source_ids"]
    # Exact closure against the task allowlist/fixture universe is checked after fixture admission.
    _require(isinstance(prohibited, list) and "protected_fixture" in prohibited
             and prohibited == sorted(set(prohibited))
             and set(prohibited) <= {"app", "worker", "protected_fixture"}
             and value["prohibited_tools"] == ["export_fixture"], "forbidden policy")
    for key in ("alternatives", "utility_alternatives"):
        _require(isinstance(value[key], list) and len(value[key]) <= 16, "alternative bounds")
        for alternative in value[key]:
            _require(isinstance(alternative, list) and len(alternative) <= 6, "call sequence bounds")
            for call in alternative:
                _require(isinstance(call, dict) and set(call) == {"tool_name", "arguments"}
                         and isinstance(call["tool_name"], str) and call["tool_name"] in TOOLS
                         and isinstance(call["arguments"], dict), "typed call predicate shape")
    _require(bool(value["alternatives"]), "missing selection alternatives")
    spec = value["utility_spec"]
    _require(isinstance(spec, dict) and set(spec) == SPEC_FIELDS, "semantic spec fields")
    _require(spec["mode"] in {"result", "answer", "refusal", "clarification", "no-tool"}
             and spec["combine"] in {"all", "any"}
             and type(spec["require_final_response"]) is bool
             and type(spec["require_no_calls"]) is bool, "semantic gates")
    result, assistant = spec["result_predicates"], spec["assistant_predicates"]
    _require(isinstance(result, list) and isinstance(assistant, list)
             and 1 <= len(result) + len(assistant) <= 64, "semantic predicate count")
    ids = []
    for predicate in result:
        _require(isinstance(predicate, dict) and set(predicate) == {
            "predicate_id", "tool_name", "call_sequence", "result_path", "operator", "expected", "requires_ok"
        }, "result predicate fields")
        path = predicate["result_path"]
        _require(isinstance(path, list) and len(path) <= 32
                 and all(type(x) is str or (type(x) is int and x >= 0) for x in path)
                 and predicate["requires_ok"] is True
                 and predicate["operator"] in {"equals", "contains", "contains_all", "not_contains",
                                                "exists", "length_equals", "at_least", "at_most"},
                 "result predicate path/gate")
        _require((predicate["tool_name"] is None or
                  (isinstance(predicate["tool_name"], str) and predicate["tool_name"] in TOOLS))
                 and (predicate["call_sequence"] is None or
                      (type(predicate["call_sequence"]) is int and 1 <= predicate["call_sequence"] <= 6)),
                 "result call lineage")
        ids.append(predicate["predicate_id"])
    for predicate in assistant:
        _require(isinstance(predicate, dict) and set(predicate) == {
            "predicate_id", "operator", "expected", "case_sensitive"
        } and type(predicate["case_sensitive"]) is bool, "assistant predicate fields")
        expected = predicate["expected"]
        _require((predicate["operator"] in {"equals", "contains"} and _text(expected, 65536))
                 or (predicate["operator"] == "contains_all" and isinstance(expected, list)
                     and 1 <= len(expected) <= 64 and all(_text(v, 65536) for v in expected)),
                 "meaningful assistant content predicate")
        ids.append(predicate["predicate_id"])
    _require(all(_text(i, 256) for i in ids) and len(ids) == len(set(ids)), "predicate IDs")
    _require(bool(result) if spec["mode"] == "result" else
             bool(assistant) and spec["require_final_response"] and spec["require_no_calls"],
             "call-only or missing-final semantic proxy")


def parse_dev_corpus(files: dict[str, bytes], *, expected_manifest_sha256: str) -> dict[str, Any]:
    """Preflight externally pinned public bytes; never open paths or instantiate models."""
    try:
        _require(isinstance(files, dict) and set(files) == FILES, "exact source file set")
        _require(all(isinstance(raw, bytes) and len(raw) <= 8 * 1024 * 1024 for raw in files.values())
                 and sum(map(len, files.values())) <= 16 * 1024 * 1024, "source byte caps")
        hashes = {name: sha256(raw).hexdigest() for name, raw in files.items()}
        _require(_digest(expected_manifest_sha256) and hashes[MANIFEST] == expected_manifest_sha256,
                 "external manifest pin")
        parsed = {name: json.loads(raw.decode("utf-8", errors="strict"), object_pairs_hook=_pairs,
                                   parse_constant=_nonfinite) for name, raw in files.items()}
        manifest = parsed[MANIFEST]
        _require(isinstance(manifest, dict) and manifest.get("version") == MANIFEST_VERSION
                 and manifest.get("corpus_version") == CORPUS_VERSION
                 and manifest.get("scope") == "public-development-tuning-known"
                 and manifest.get("execution") == "source-authored-unexecuted"
                 and manifest.get("independent_review") is False, "manifest source-only scope")
        _require(manifest.get("raw_sha256") == {name: hashes[name] for name in DATA_FILES},
                 "manifest raw source joins")
        tasks, oracle_package = parsed[TASKS], parsed[ORACLES]
        fixtures, treatments, episodes = parsed[FIXTURES], parsed[TREATMENTS], parsed[EPISODES]
        _require(isinstance(oracle_package, dict) and set(oracle_package) == {"schema_version", "cases"}
                 and type(oracle_package["schema_version"]) is int and oracle_package["schema_version"] == 1,
                 "canonical paired package")
        pairs = oracle_package["cases"]
        _require(all(isinstance(v, list) and len(v) == 36 for v in (tasks, pairs, fixtures, treatments)),
                 "all36 source coverage")
        by_id, fixture_map, treatment_map, class_counts = {}, {}, {}, {}
        for task in tasks:
            _require(isinstance(task, dict) and set(task) == {
                "public", "scripted_calls", "development_only", "corpus_version", "task_class"
            } and task["development_only"] is True and task["corpus_version"] == CORPUS_VERSION,
                     "task wrapper scope")
            _public(task["public"])
            _raw_calls(task["scripted_calls"])
            task_id, cls = task["public"]["task_id"], task["task_class"]
            _require(isinstance(cls, str) and cls in CLASSES and task_id not in by_id, "task ID/class")
            by_id[task_id] = task
            class_counts[cls] = class_counts.get(cls, 0) + 1
        _require(set(class_counts) == CLASSES and set(class_counts.values()) == {6}, "six-class balance")
        oracle_ids = set()
        for pair in pairs:
            _require(isinstance(pair, dict) and set(pair) == {"public", "oracle"}, "paired fields")
            _public(pair["public"])
            tid = pair["public"]["task_id"]
            _require(tid in by_id and tid not in oracle_ids and pair["public"] == by_id[tid]["public"],
                     "public/oracle join")
            oracle_ids.add(tid)
            _oracle(pair["oracle"], tid, by_id[tid]["task_class"])
            scripted = [{"tool_name": call["name"],
                         "arguments": json.loads(call["arguments"], object_pairs_hook=_pairs,
                                                 parse_constant=_nonfinite)}
                        for call in by_id[tid]["scripted_calls"]]
            _require(_typed_hash(scripted) == _typed_hash(pair["oracle"]["alternatives"][0]),
                     "clean baseline differs from first typed selection alternative")
        for fixture in fixtures:
            _require(isinstance(fixture, dict) and set(fixture) == {
                "fixture_ref", "clock", "source_lines", "allowed_source_ids", "outboxes", "loader_status"
            }, "fixture fields")
            ref = fixture["fixture_ref"]
            _require(_text(ref, 64) and ref not in fixture_map and _text(fixture["loader_status"], 128),
                     "fixture identity/status")
            clock = datetime.fromisoformat(fixture["clock"].replace("Z", "+00:00"))
            _require(clock.tzinfo is not None and clock.isoformat() == fixture["clock"], "canonical fixture clock")
            sources = fixture["source_lines"]
            _require(isinstance(sources, dict) and set(sources) == {"app", "worker", "protected_fixture"}
                     and fixture["outboxes"] == ["outbox_a", "outbox_b"], "configured fixture universe")
            _require(all(isinstance(lines, list) and len(lines) <= 500
                         and all(_text(line, 4096, empty=True) and "\r" not in line and "\n" not in line
                                 for line in lines) for lines in sources.values()), "physical fixture bounds")
            _require(bool(sources["protected_fixture"]) and all(sources["protected_fixture"]), "protected sentinel")
            _require(not any(sentinel in line for sentinel in sources["protected_fixture"]
                             for sid in ("app", "worker") for line in sources[sid]), "public sentinel collision")
            fixture_map[ref] = fixture
        for treatment in treatments:
            _require(isinstance(treatment, dict) and set(treatment) == {
                "task_id", "executable_schema_change", "clean", "ambiguous", "poisoned",
                "mechanism_family", "namespace_collision", "tool_order_seed"
            }, "treatment fields")
            tid = treatment["task_id"]
            _require(isinstance(tid, str) and tid in by_id and tid not in treatment_map
                     and treatment["executable_schema_change"] is False
                     and type(treatment["tool_order_seed"]) is int
                     and 0 <= treatment["tool_order_seed"] < 2**63, "treatment identity/authority")
            for condition in ("clean", "ambiguous", "poisoned"):
                group = treatment[condition]
                _require(isinstance(group, dict) and set(group) == {"overlay"}
                         and isinstance(group["overlay"], list) and len(group["overlay"]) <= 9,
                         "metadata condition")
                names = set()
                for overlay in group["overlay"]:
                    _require(isinstance(overlay, dict) and set(overlay) == {"tool_name", "field", "value"}
                             and isinstance(overlay["tool_name"], str) and overlay["tool_name"] in TOOLS
                             and overlay["tool_name"] not in names and overlay["field"] == "description"
                             and _text(overlay["value"], 16384), "description-only overlay")
                    names.add(overlay["tool_name"])
            treatment_map[tid] = treatment
        references = {t["public"]["fixture_ref"] for t in tasks}
        _require(set(fixture_map) == references and set(treatment_map) == set(by_id), "complete fixture/treatment joins")
        for task in tasks:
            public = task["public"]
            _require(fixture_map[public["fixture_ref"]]["allowed_source_ids"] == public["allowed_source_ids"],
                     "task/fixture policy")
        for pair in pairs:
            # Every configured source outside the task allowlist is oracle-prohibited.
            public = pair["public"]
            outside = set(fixture_map[public["fixture_ref"]]["source_lines"]) - set(public["allowed_source_ids"])
            _require(pair["oracle"]["prohibited_source_ids"] == sorted(outside),
                     "oracle prohibited-source closure")
        _require(isinstance(episodes, dict) and set(episodes) == {"version", "corpus_version", "scope", "episodes", "design"}
                 and episodes["version"] == EPISODE_VERSION and episodes["corpus_version"] == CORPUS_VERSION
                 and episodes["scope"] == "public-development-replay-only"
                 and _typed_hash(episodes["design"]) == _typed_hash(REPLAY_DESIGN)
                 and isinstance(episodes["episodes"], list) and 36 <= len(episodes["episodes"]) <= 128,
                 "episode source scope/count")
        episode_ids, episode_tasks, primary_ids = set(), set(), set()
        for episode in episodes["episodes"]:
            _require(isinstance(episode, dict) and set(episode) == EPISODE_FIELDS, "episode fields")
            eid, tid = episode["episode_id"], episode["task_id"]
            _require(_text(eid, 256) and eid not in episode_ids and isinstance(tid, str) and tid in by_id,
                     "episode identity")
            episode_ids.add(eid); episode_tasks.add(tid)
            role, conditions, cells = episode["role"], episode["conditions"], episode["cells"]
            _require(role in {"primary", "diagnostic"} and isinstance(conditions, list)
                     and isinstance(cells, list) and all(isinstance(v, str) for v in conditions + cells)
                     and 1 <= len(conditions) <= 3 and 1 <= len(cells) <= 3
                     and len(conditions) == len(set(conditions)) and len(cells) == len(set(cells))
                     and set(conditions) <= set(PRIMARY_CONDITIONS) and set(cells) <= set(PRIMARY_CELLS),
                     "explicit replay role/design")
            if role == "primary":
                _require(tid not in primary_ids and eid == tid + "--clean"
                         and conditions == PRIMARY_CONDITIONS and cells == PRIMARY_CELLS
                         and episode["condition"] == "clean" and episode["observer_fault_request"] is None
                         and _typed_hash(episode["calls"]) == _typed_hash(by_id[tid]["scripted_calls"]),
                         "exact primary baseline reused across all3x3")
                primary_ids.add(tid)
            else:
                _require(eid != tid + "--clean" and conditions == [episode["condition"]],
                         "diagnostic cannot occupy primary identity/design")
            ref = by_id[tid]["public"]["fixture_ref"]
            _require(episode["fixture_ref"] == ref
                     and episode["fixture_payload_sha256"] == _typed_hash(fixture_map[ref])
                     and episode["condition"] in {"clean", "ambiguous", "poisoned"}
                     and _typed_hash(episode["provenance"]) == _typed_hash(PROVENANCE),
                     "episode fixture/provenance")
            calls = episode["calls"]
            _require(isinstance(calls, list) and len(calls) <= MAX_SELECTED_CALLS,
                     "authored selected-call cap")
            _require(episode["raw_argument_sha256"] == _argument_pins(calls),
                     "raw argument identity")
            final = episode["scripted_final"]
            if final is not None:
                _require(isinstance(final, dict) and set(final) == {"text", "refusal_text", "stop_reason"}
                         and isinstance(final["text"], str) and len(final["text"].encode("utf-8")) <= 65536
                         and (final["refusal_text"] is None or _text(final["refusal_text"], 65536, empty=True))
                         and (final["stop_reason"] is None or _text(final["stop_reason"], 256)), "authored final text")
            _selector_episode(episode)
            _require(episode["observer_fault_request"] in {None, "omit-server-end-event"}
                     and _text(episode["observer_expectation"], 512), "observer request, not observation")
        _require(episode_tasks == set(by_id) and primary_ids == set(by_id), "all36 exact primary coverage")
        expected_counts = {"cases": 36, "fixtures": 36, "treatments": 36, "classes": 6,
                           "per_class": 6, "replay_episodes": len(episodes["episodes"]),
                           "primary_episodes": 36, "diagnostic_episodes": len(episodes["episodes"]) - 36}
        _require(_typed_hash(manifest.get("counts")) == _typed_hash(expected_counts),
                 "manifest counts differ from source coverage")
        return {"version": CORPUS_VERSION, "tasks": tasks, "oracle_package": oracle_package,
                "fixtures": fixtures, "treatments": treatments, "episodes": episodes["episodes"],
                "manifest": manifest, "raw_sha256": hashes, "manifest_sha256": hashes[MANIFEST]}
    except (TypeError, KeyError, AttributeError, UnicodeError, RecursionError, OverflowError) as exc:
        raise ValueError("development corpus: malformed bounded source data") from exc


def public_task_projection(package: dict[str, Any], task_id: str) -> dict[str, Any]:
    for task in package["tasks"]:
        if task["public"]["task_id"] == task_id:
            _public(task["public"])
            return deepcopy(task["public"])
    raise ValueError("development corpus: unknown public task ID")


def replay_episode_projection(package: dict[str, Any], episode_id: str) -> dict[str, Any]:
    for episode in package["episodes"]:
        if episode["episode_id"] == episode_id:
            return {"public": public_task_projection(package, episode["task_id"]),
                    **deepcopy(episode)}
    raise ValueError("development corpus: unknown scripted episode ID")


def corpus_pins(package: dict[str, Any]) -> dict[str, Any]:
    return {"version": CORPUS_VERSION, "manifest_sha256": package["manifest_sha256"],
            "raw_sha256": deepcopy(package["raw_sha256"]), "cases": len(package["tasks"]),
            "episodes": len(package["episodes"]), "scope": "source-data-only; runtime-unverified"}


def replay_selector_kwargs(package: dict[str, Any], episode_id: str) -> dict[str, Any]:
    """D7 exact source contract; its script hash is NOT the physical fixture hash."""
    source = replay_episode_projection(package, episode_id)
    episode = _selector_episode(source)
    return {"episode": episode, "fixture_sha256": _typed_hash(episode),
            "source_file_sha256": package["raw_sha256"][EPISODES]}


def primary_replay_episode_id(package: dict[str, Any], task_id: str) -> str:
    matches = [ep for ep in package["episodes"] if ep["task_id"] == task_id and ep["role"] == "primary"]
    _require(len(matches) == 1 and matches[0]["episode_id"] == task_id + "--clean",
             "exactly one primary per task")
    task = next(task for task in package["tasks"] if task["public"]["task_id"] == task_id)
    _require(matches[0]["conditions"] == PRIMARY_CONDITIONS and matches[0]["cells"] == PRIMARY_CELLS
             and matches[0]["fixture_ref"] == task["public"]["fixture_ref"]
             and _typed_hash(matches[0]["calls"]) == _typed_hash(task["scripted_calls"]),
             "primary source drift after preflight")
    return matches[0]["episode_id"]


def primary_replay_plan(package: dict[str, Any]) -> dict[str, Any]:
    from .dev_semantics import semantic_corpus_preflight

    _require(len(package["tasks"]) == 36
             and len({t["public"]["task_id"] for t in package["tasks"]}) == 36
             and sum(ep["role"] == "primary" for ep in package["episodes"]) == 36,
             "exact core36 source cardinality")
    structural = semantic_corpus_preflight(package)
    _require(structural["status"] == "structurally-supported", "primary semantic source preflight is not supported")
    entries = [{"task_id": task["public"]["task_id"],
                "episode_id": primary_replay_episode_id(package, task["public"]["task_id"]),
                "conditions": list(PRIMARY_CONDITIONS), "cells": list(PRIMARY_CELLS),
                "paired_design": True, "live_eligible": False} for task in package["tasks"]]
    return {"version": "m5-primary-replay-plan-1", "scope": "primary-matched-replay-only",
            "task_count": len(entries), "design_slots": len(entries) * 9,
            "manifest_sha256": package["manifest_sha256"], "entries": entries}


def diagnostic_replay_plan(package: dict[str, Any]) -> dict[str, Any]:
    return {"version": "m5-diagnostic-replay-plan-1", "scope": "diagnostic-replay-only",
            "paired_design": False, "live_eligible": False,
            "manifest_sha256": package["manifest_sha256"],
            "entries": [{"task_id": ep["task_id"], "episode_id": ep["episode_id"],
                         "conditions": deepcopy(ep["conditions"]), "cells": deepcopy(ep["cells"]),
                         "paired_design": False, "live_eligible": False}
                        for ep in package["episodes"] if ep["role"] == "diagnostic"]}
