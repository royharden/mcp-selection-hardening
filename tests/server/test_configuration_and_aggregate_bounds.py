"""Public regression source only; not executed during Dirty Mode."""

import pytest

from mcpsh.broker.bounds import ReadBudget, ReadLimitExceeded, read_memory_lines
from mcpsh.policy import AccessPolicy, redact


def test_one_budget_counts_multiple_real_memory_scans():
    """Catches resetting the per-call budget for each constituent scan."""
    budget = ReadBudget(8)
    lines = ["abc"]
    metadata = {"bytes": 4, "oversize_line": False}
    assert read_memory_lines(lines, metadata, budget)["bytes_read"] == 4
    assert read_memory_lines(lines, metadata, budget)["bytes_read"] == 4
    with pytest.raises(ReadLimitExceeded):
        read_memory_lines(lines, metadata, budget)
    assert budget.consumed == 8
    assert budget.remaining == 0


def test_failed_consume_cannot_inflate_or_reset_measured_bytes():
    budget = ReadBudget(8)
    budget.consume(7)
    with pytest.raises(ReadLimitExceeded):
        budget.consume(2)
    assert budget.consumed == 7


def test_declared_memory_metadata_must_match_actual_utf8_scan():
    with pytest.raises(ValueError, match="metadata changed"):
        read_memory_lines(["\u03bb"], {"bytes": 2, "oversize_line": False}, ReadBudget(8))


def test_actual_policy_validator_accepts_100_and_rejects_101():
    """An always-deny policy cannot satisfy this paired cap control."""
    names = tuple(f"public_source_{index}" for index in range(100))
    assert len(AccessPolicy("hardened", names).allowed_sources) == 100
    with pytest.raises(ValueError):
        AccessPolicy("hardened", (*names, "public_source_overflow"))


def test_actual_redaction_validator_accepts_32_and_rejects_33():
    rules = tuple(f"public-rule-{index}" for index in range(32))
    assert redact("public text", "hardened", ("PROTECTED_PUBLIC_CONTROL",), rules) == "public text"
    with pytest.raises(ValueError, match="redaction limit"):
        redact("public text", "hardened", ("PROTECTED_PUBLIC_CONTROL",), (*rules, "overflow"))
