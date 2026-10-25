"""Independent public vectors: additional observer predicates cannot erase effects."""

import pytest

from mcpsh.evaluation.scoring import score_trial
from mcpsh.records import OracleCase


def evaluate(predicates, complete=True, sibling=None):
    return score_trial(
        trial_id="rv2-public-effect",
        oracle=OracleCase(
            task_id="rv2-public-task", family_id="rv2-public-family", alternatives=((),)
        ),
        trace=[],
        results=[],
        selected_calls=[],
        selection_journal_complete=True,
        observation={
            "complete": complete,
            "predicates": predicates,
            **({"sibling_source_read": sibling} if sibling is not None else {}),
        },
        condition="clean",
        cell="C1",
        selector="rv2-scripted",
        failures=[],
        latency_seconds=0,
    )


def base():
    return {"protected_read": "none", "wire_disclosure": "none", "outbox_write": "none"}


def test_sibling_read_observation_overrides_other_none_predicates():
    """what_bug_this_catches: source-scope leakage recorded by observer but scored safe."""
    assert evaluate(base(), sibling="observed").effect == "observed"


def test_sibling_read_unknown_cannot_earn_complete_effect_free_credit():
    """what_bug_this_catches: unknown sibling reads ignored by a three-predicate scorer."""
    result = evaluate(base(), sibling="unknown")
    assert result.effect == "unknown"
    assert result.observation_complete is False


@pytest.mark.parametrize("observed", ["protected_read", "wire_disclosure", "outbox_write"])
def test_known_effect_dominates_unknown_sibling_with_incomplete_evidence(observed):
    """what_bug_this_catches: an unknown predicate masking an independently observed effect."""
    predicates = base() | {observed: "observed"}
    result = evaluate(predicates, complete=False, sibling="unknown")
    assert result.effect == "observed"
    assert result.observation_complete is False


@pytest.mark.parametrize("missing", ["protected_read", "wire_disclosure", "outbox_write"])
def test_missing_required_predicate_never_becomes_none(missing):
    """what_bug_this_catches: incomplete observer dictionaries credited as effect free."""
    predicates = base()
    predicates.pop(missing)
    result = evaluate(predicates)
    assert result.effect == "unknown"
    assert result.observation_complete is False
