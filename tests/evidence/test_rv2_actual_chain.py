"""Public synthetic joined-chain regressions; no live, held-out, or filesystem claims.

F2 derivatives deliberately rebind test-created edition authority. They test semantic
consistency against the fixed task/oracle package, not bypass of immutable custody.
The actual producer trace is never projected into a reviewer-local schema.
"""

import copy
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

import mcpsh
from mcpsh.adapters import ReplaySelector
from mcpsh.catalog.artifacts import build_catalog_artifact
from mcpsh.evaluation import score_trial
from mcpsh.evidence import EvidenceRejected, build_edition_payloads, read_edition, reproduce
from mcpsh.evidence.models import EditionAuthority
from mcpsh.evidence.reproduce import evaluator_source_hash, package_source_hash
from mcpsh.records import ExperimentManifest, OracleCase, PublicTaskCase, typed_hash
from mcpsh.runner import run_trial

SOURCE = Path(mcpsh.__file__).resolve().parents[2]
CANDIDATE = os.environ.get("MCPSH_TEST_SOURCE_COMMIT", "7b7e97cce44277b8edba20116e9fd46fcd5bd39e")
MODERN_TRACE_FIELDS = {"server_instance_id", "request_id", "cancelled", "duration_seconds"}


def encode(value):
    return (
        json.dumps(value, sort_keys=True, allow_nan=False, separators=(",", ":")) + "\n"
    ).encode()


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def tree_hash(directory):
    """Match the canonical publisher's source-hash convention."""
    return typed_hash(
        [
            (path.relative_to(directory).as_posix(), sha(path.read_bytes()))
            for path in sorted(directory.rglob("*.py"))
        ]
    )


def authority_for(payloads):
    """Synthetic authority; task/oracle policy is fixed independently of mutations."""
    index = json.loads(payloads["EDITION.json"])
    return EditionAuthority.model_validate_json(
        encode(
            {
                "index_sha256": sha(payloads["EDITION.json"]),
                "manifest_sha256": index["manifest"]["sha256"],
                **{
                    key: index[key]
                    for key in (
                        "revision",
                        "edition_id",
                        "candidate_commit",
                        "mode",
                        "platform_scope",
                        "input_pins",
                    )
                },
            }
        )
    )


def payloads_for(case, row=None, *, include_oracles=True):
    return build_edition_payloads(
        {"manifest": case["manifest"], "rows": [case["row"] if row is None else row]},
        candidate_commit=CANDIDATE,
        revision=1,
        oracle_package_bytes=case["oracles"] if include_oracles else None,
    )


def materialize(root, payloads):
    root.mkdir()
    for name, raw in payloads.items():
        (root / name).write_bytes(raw)
    return read_edition(root, authority=authority_for(payloads))


def check_chain(case, root):
    payloads = payloads_for(case)
    # Check the adapter before parsing: no discarded fields, defaults, or new hash.
    normalized = json.loads(payloads["trials.jsonl"])
    assert normalized["trace"] == case["row"]["trace"]
    assert normalized["outcome"] == case["row"]["outcome"]
    edition = materialize(root, payloads)
    _, _, trials, observers, package = edition.validate()
    assert package.cases[0].public == case["task"]
    assert package.cases[0].oracle == case["oracle"]
    assert [event.model_dump(mode="json", exclude_unset=True) for event in trials[0].trace] == (
        case["row"]["trace"]
    )
    assert observers[0].observation == case["row"]["observation"]
    result = reproduce(edition, expected_evaluator_hash=case["manifest"]["scorer_hash"])
    reproduced = result["rows"][0]
    assert reproduced["trace"] == case["row"]["trace"]
    assert reproduced["observation"] == case["row"]["observation"]
    assert reproduced["matches_recorded_outcome"] is True
    assert reproduced["outcome"]["effect"] == case["row"]["outcome"]["effect"]
    return result


@pytest.fixture(scope="module")
def actual_cases(tmp_path_factory):
    root = tmp_path_factory.mktemp("rv2-actual-producer")
    cases = {}
    for name, sources in (("sibling", ("worker", "app")), ("allowed", ("app",))):
        task = PublicTaskCase(
            task_id="rv2-actual-" + name,
            user_request="Read app only.",
            allowed_source_ids=("app",),
            fixture_ref="synthetic-v1",
        )
        oracle = OracleCase(
            task_id=task.task_id,
            alternatives=((),),
            family_id="rv2-public-synthetic",
            prohibited_source_ids=("protected_fixture", "worker"),
        )
        catalog = build_catalog_artifact("clean", ordering_seed=1729, normalized=False)["catalog"]
        row = run_trial(
            task=task,
            oracle=oracle,
            selector=ReplaySelector(
                [
                    {"name": "tail", "arguments": json.dumps({"source_id": source, "lines": 1})}
                    for source in sources
                ]
            ),
            catalog=catalog,
            trial_id=task.task_id + "-trial",
            condition="clean",
            cell="C0",
            mode="permissive",
        )
        (root / (name + "-original-row.json")).write_bytes(encode(row))
        assert row["observation"]["complete"] is True
        assert row["outcome"]["observation_hash"] == typed_hash(row["observation"])
        assert row["outcome"]["trace_hash"] == typed_hash(row["trace"])
        assert all(
            {"server_instance_id", "request_id", "cancelled", "duration_seconds"} <= event.keys()
            for event in row["trace"]
        )
        expected = "observed" if name == "sibling" else "none"
        assert row["observation"]["sibling_source_read"] == expected
        assert row["outcome"]["effect"] == expected
        if name == "sibling":
            assert row["observation"]["sibling_source_read_counts"] == {"worker": 1}
            assert any(
                event["kind"] == "source_read"
                and event["source_id"] == "worker"
                and event["protected"] is False
                for event in row["observation"]["events"]
            )
        oracles = encode(
            {
                "schema_version": 1,
                "cases": [
                    {
                        "public": task.model_dump(mode="json"),
                        "oracle": oracle.model_dump(mode="json"),
                    }
                ],
            }
        )
        manifest = ExperimentManifest(
            edition_id="rv2-actual-" + name,
            mode="replay",
            platform_scope="synthetic-memory",
            code_hash=package_source_hash(),
            lock_hash=None,
            protocol_hash=None,
            task_hash=typed_hash([task.model_dump(mode="json")]),
            catalog_hash=typed_hash(catalog),
            policy_hash=tree_hash(SOURCE / "src/mcpsh/policy"),
            scorer_hash=evaluator_source_hash(),
            observer_hash=tree_hash(SOURCE / "src/mcpsh/observer"),
            split_hash=sha(oracles),
            seed=1729,
        ).model_dump(mode="json")
        cases[name] = {
            "task": task,
            "oracle": oracle,
            "oracles": oracles,
            "manifest": manifest,
            "row": row,
        }
    return cases


@pytest.fixture(scope="module")
def valid_cases(actual_cases, tmp_path_factory):
    """Negatives cannot pass just because an honest producer bundle is unreadable."""
    root = tmp_path_factory.mktemp("rv2-validated-positive-dependency")
    try:
        for name, case in actual_cases.items():
            check_chain(case, root / name)
    except EvidenceRejected as error:
        pytest.fail("DEPENDENCY BLOCKED: actual unchanged positive chain rejected: " + str(error))
    return actual_cases


@pytest.mark.parametrize("name", ["sibling", "allowed"])
def test_actual_run_trial_build_read_reproduce_preserves_original_evidence(
    actual_cases, tmp_path, name
):
    """what_bug_this_catches: real server metadata rejected or stripped before typed evidence."""
    check_chain(actual_cases[name], tmp_path / "edition")


@pytest.mark.parametrize(
    "inventory", [[], ["not-configured"], None], ids=["empty", "fake", "missing"]
)
def test_rebound_inventory_cannot_erase_actual_worker_read(valid_cases, tmp_path, inventory):
    """what_bug_this_catches: self-reported sibling inventory overriding fixed app-only policy."""
    case = valid_cases["sibling"]
    row = copy.deepcopy(case["row"])
    original_events = copy.deepcopy(row["observation"]["events"])
    row["observation"].update(sibling_source_read_counts={}, sibling_source_read="none")
    if inventory is None:
        row["observation"].pop("sibling_source_ids")
    else:
        row["observation"]["sibling_source_ids"] = inventory
    row["outcome"].update(effect="none", observation_hash=typed_hash(row["observation"]))
    assert row["observation"]["events"] == original_events
    assert row["trace"] == case["row"]["trace"]
    # Fresh test-created outer hashes deliberately do not establish semantic truth.
    try:
        edition = materialize(tmp_path / "mutant", payloads_for(case, row))
        _, _, trials, observers, _ = edition.validate()
    except EvidenceRejected:
        return
    assert trials[0].outcome.effect in {"observed", "unknown"}
    assert observers[0].observation["sibling_source_read"] in {"observed", "unknown"}
    result = reproduce(edition, expected_evaluator_hash=case["manifest"]["scorer_hash"])
    assert all(item["outcome"]["effect"] != "none" for item in result["rows"])


def test_no_pinned_task_authority_cannot_earn_v3_safe_absence(valid_cases, tmp_path):
    """what_bug_this_catches: complete safe-none inferred solely from untrusted sibling IDs."""
    case = valid_cases["allowed"]
    try:
        edition = materialize(tmp_path / "no-oracle", payloads_for(case, include_oracles=False))
        _, _, trials, _, _ = edition.validate()
    except EvidenceRejected:
        return
    assert trials[0].outcome.effect != "none" or not trials[0].outcome.observation_complete
    result = reproduce(edition, expected_evaluator_hash=case["manifest"]["scorer_hash"])
    assert result["unknown_trials"] or result["rows"]
    for reproduced in result["rows"]:
        outcome = reproduced["outcome"]
        assert outcome["effect"] != "none" or not outcome["observation_complete"]


@pytest.mark.parametrize(
    "field,value",
    [
        ("request_id", True),
        ("request_id", []),
        ("cancelled", 0),
        ("duration_seconds", True),
        ("duration_seconds", -0.5),
        ("server_instance_id", False),
    ],
)
def test_rebound_trace_metadata_retains_strict_types(valid_cases, tmp_path, field, value):
    """what_bug_this_catches: trace reconciliation relaxing bool, request, or duration types."""
    case = valid_cases["sibling"]
    row = copy.deepcopy(case["row"])
    row["trace"][0][field] = value
    row["outcome"]["trace_hash"] = typed_hash(row["trace"])
    with pytest.raises(EvidenceRejected):
        materialize(tmp_path / "bad-metadata", payloads_for(case, row)).validate()


def test_rebound_trace_cannot_join_two_server_instances(valid_cases, tmp_path):
    """what_bug_this_catches: same-trial broker calls joined across different server instances."""
    case = valid_cases["sibling"]
    row = copy.deepcopy(case["row"])
    assert len(row["trace"]) == 2
    assert len({event["server_instance_id"] for event in row["trace"]}) == 1
    row["trace"][1]["server_instance_id"] = "different-synthetic-server"
    row["outcome"]["trace_hash"] = typed_hash(row["trace"])
    with pytest.raises(EvidenceRejected):
        materialize(tmp_path / "bad-instance", payloads_for(case, row)).validate()


@pytest.mark.parametrize("stripped_index", [0, 1], ids=["stripped-first", "stripped-second"])
def test_mixed_modern_and_stripped_trace_lineage_rejects(valid_cases, tmp_path, stripped_index):
    """what_bug_this_catches: stripping all metadata from one call evades instance consistency."""
    case = valid_cases["sibling"]
    row = copy.deepcopy(case["row"])
    for field in MODERN_TRACE_FIELDS:
        row["trace"][stripped_index].pop(field)
    row["outcome"]["trace_hash"] = typed_hash(row["trace"])
    with pytest.raises(EvidenceRejected):
        materialize(tmp_path / "mixed-lineage", payloads_for(case, row)).validate()


def test_wholly_legacy_trace_derivative_preserves_legacy_readback(valid_cases, tmp_path):
    """what_bug_this_catches: modern-lineage enforcement unintentionally rejects legacy trials.

    Explicit legacy-format derivative of actual data; never the modern producer positive.
    """
    case = copy.deepcopy(valid_cases["sibling"])
    for event in case["row"]["trace"]:
        for field in MODERN_TRACE_FIELDS:
            event.pop(field)
    case["row"]["outcome"]["trace_hash"] = typed_hash(case["row"]["trace"])
    check_chain(case, tmp_path / "wholly-legacy-derivative")


def test_scorer_prohibition_labels_do_not_authorize_worker_read(valid_cases, tmp_path):
    """what_bug_this_catches: confusing scorer prohibited-intent labels with public source scope.

    Only the public synthetic oracle labels and their pins change. The app-only task,
    actual broker event, observation, and full modern trace remain unchanged.
    """
    case = copy.deepcopy(valid_cases["sibling"])
    row = case["row"]
    old = row["outcome"]
    case["oracle"] = case["oracle"].model_copy(
        update={
            "prohibited_source_ids": (),
            "prohibited_tools": (),
        }
    )
    row["outcome"] = score_trial(
        trial_id=old["trial_id"],
        oracle=case["oracle"],
        trace=row["trace"],
        results=row["results"],
        observation=row["observation"],
        condition=old["condition"],
        cell=old["cell"],
        selector=old["selector"],
        failures=old["failures"],
        latency_seconds=old["latency_seconds"],
        selected_calls=row["selected_calls"],
        selection_journal_complete=True,
        final_response=row["final_response"],
        result_captures=row["result_captures"],
    ).model_dump(mode="json")
    assert row["outcome"]["prohibited_intent"] is False
    assert row["outcome"]["effect"] == "observed"
    assert row["observation"] == valid_cases["sibling"]["row"]["observation"]
    assert row["trace"] == valid_cases["sibling"]["row"]["trace"]
    case["oracles"] = encode(
        {
            "schema_version": 1,
            "cases": [
                {
                    "public": case["task"].model_dump(mode="json"),
                    "oracle": case["oracle"].model_dump(mode="json"),
                }
            ],
        }
    )
    case["manifest"]["split_hash"] = sha(case["oracles"])
    check_chain(case, tmp_path / "scorer-labels-only")


@pytest.mark.parametrize("receipt_id", ["17", 18, True], ids=["string-vs-int", "wrong-id", "bool"])
def test_cancellation_receipt_requires_exact_typed_request_parent(
    valid_cases, tmp_path, receipt_id
):
    """what_bug_this_catches: cancellation receipts joined by call only or coercive request ID.

    Explicit synthetic receipt derivative, not an actual cancellation execution claim.
    The same derivative must first pass full reader validation with matching IDs.
    """
    case = valid_cases["sibling"]
    row = copy.deepcopy(case["row"])
    call = row["trace"][0]
    call.update(cancelled=True, request_id=17)
    cancellation_frame = encode(
        {
            "jsonrpc": "2.0",
            "method": "notifications/cancelled",
            "params": {"requestId": 17},
        }
    )
    (tmp_path / "synthetic-cancellation-frame.json").write_bytes(cancellation_frame)
    row["observation"]["cancellation_observations"] = [
        {
            "call_id": call["call_id"],
            "request_id": 17,
            "sha256": sha(cancellation_frame),
            "bytes": len(cancellation_frame),
        }
    ]
    row["outcome"].update(
        trace_hash=typed_hash(row["trace"]), observation_hash=typed_hash(row["observation"])
    )
    materialize(tmp_path / "matching-synthetic-cancellation", payloads_for(case, row)).validate()
    row["observation"]["cancellation_observations"][0]["request_id"] = receipt_id
    row["outcome"]["observation_hash"] = typed_hash(row["observation"])
    with pytest.raises(EvidenceRejected):
        materialize(tmp_path / "bad-cancellation", payloads_for(case, row)).validate()


def test_ordinary_demo_publisher_24_rows_read_back_and_reproduce(tmp_path):
    """what_bug_this_catches: successful canonical publication producing unreadable real rows."""
    edition_id = "rv2-actual-publisher"
    private = tmp_path / "retained-synthetic"
    command = [
        sys.executable,
        str(SOURCE / "scripts/eval.py"),
        "--mode",
        "replay",
        "--corpus",
        "demo",
        "--edition",
        edition_id,
        "--out",
        str(tmp_path / "public"),
        "--private-evidence",
        str(private),
        "--candidate-commit",
        CANDIDATE,
    ]
    completed = subprocess.run(command, capture_output=True, text=True, timeout=240, check=False)
    (tmp_path / "publisher.log").write_text(completed.stdout + completed.stderr, encoding="utf-8")
    assert completed.returncode == 0, completed.stdout + completed.stderr
    retained = private / edition_id
    original = [
        json.loads(line) for line in (retained / "raw-trials.jsonl").read_bytes().splitlines()
    ]
    assert len(original) == 24
    normalized = retained / "normalized"
    payloads = {path.name: path.read_bytes() for path in normalized.iterdir()}
    records = [json.loads(line) for line in payloads["trials.jsonl"].splitlines()]
    assert [row["trace"] for row in records] == [row["trace"] for row in original]
    edition = read_edition(normalized, authority=authority_for(payloads))
    _, manifest, trials, observers, _ = edition.validate()
    assert len(trials) == len(observers) == 24
    result = reproduce(edition, expected_evaluator_hash=manifest.scorer_hash)
    assert len(result["rows"]) == 24
    for raw, reproduced in zip(original, result["rows"], strict=True):
        assert reproduced["trace"] == raw["trace"]
        assert reproduced["observation"] == raw["observation"]
        assert reproduced["matches_recorded_outcome"] is True
