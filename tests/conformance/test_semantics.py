"""Public regression source, authored under Dirty Mode and not executed."""

import json

import pytest

from mcpsh.conformance import ConformanceRequest, run_conformance
from mcpsh.conformance.host_control import dispatch
from mcpsh.conformance.semantics import public_case_source, semantic_cases


@pytest.mark.parametrize("case_id", ["literal-dot", "escaped-reserved", "unsupported-repetition"])
def test_real_memory_handler_semantic_controls(case_id):
    # what_bug_this_catches: pure matcher success masks wrong server dispatch,
    # wildcard behavior, escaped-literal rejection, or unsupported syntax after I/O.
    request = ConformanceRequest(runtime_authorized=True, disposable_authorized=True,
        approval_id="public-semantic-regression", probe_ids=("semantic-" + case_id,))
    row = run_conformance(request).to_dict()["results"][0]
    assert row["status"] == "pass"
    assert row["evidence"]["provenance"]["scope"] == "actual-memory"
    assert row["evidence"]["provenance"]["observation"]["complete"] is True


def test_public_case_omission_is_rejected():
    # what_bug_this_catches: packaging drops a difficult case while retaining a version.
    package = json.loads(public_case_source())
    package["cases"].pop()
    with pytest.raises(ValueError, match="count"):
        semantic_cases(json.dumps(package).encode("utf-8"))


def test_unknown_bins_are_not_full_semantic_coverage():
    # what_bug_this_catches: UNKNOWN is a useful bin but not a claim of parsed codes.
    request = ConformanceRequest(runtime_authorized=True, disposable_authorized=True,
        approval_id="public-unknown-regression", probe_ids=("semantic-unknown-code-bin",))
    payload = run_conformance(request).to_dict()
    assert payload["results"][0]["status"] == "pass"
    assert payload["results"][0]["evidence"]["provenance"]["semantic"]["coverage_kind"] == "unknown"
    assert payload["platforms"]["synthetic-memory"]["verdict"] == "pending"


def test_cancellation_id_type_is_forwarded_without_coercion():
    # what_bug_this_catches: string IDs lose correlation or bool masquerades as int.
    class Core:
        def wait_for_cancellation(self, *, request_id, timeout):
            return {"request_id": request_id, "timeout": timeout}

    for request_id in (7, "7"):
        result = dispatch(Core(), "wait_for_cancellation", {"request_id": request_id, "timeout": 1}, {})
        assert type(result["request_id"]) is type(request_id)
    with pytest.raises(ValueError):
        dispatch(Core(), "wait_for_cancellation", {"request_id": True, "timeout": 1}, {})
