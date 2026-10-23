"""Authored under Dirty Mode; not executed. Regression intent is explicit."""

import pytest

from mcpsh.conformance import ConformanceRequest, Status, run_conformance
from mcpsh.conformance.models import ConformanceReport, ProbeResult


def test_no_activation_never_constructs_backend():
    # what_bug_this_catches: invoking server-check implicitly spawns a broker.
    def forbidden(*args):
        raise AssertionError("backend constructed before authorization")

    with pytest.raises(ValueError, match="authorization"):
        run_conformance(ConformanceRequest(), backend_factory=forbidden)


@pytest.mark.parametrize("status", [Status.UNKNOWN, Status.UNAVAILABLE, Status.UNSUPPORTED])
def test_unproven_required_check_remains_pending(status):
    # what_bug_this_catches: skipped or unsupported checks counted as platform passes.
    report = ConformanceReport((ProbeResult("boundary", "filesystem-posix", status, True, "pending"),),
                               ("filesystem-posix",), ("boundary",), True, "local-approval")
    platform = report.to_dict()["platforms"]["filesystem-posix"]
    assert platform["verdict"] == "pending"
    assert platform["filesystem_proof"] is False


def test_required_failure_blocks_platform_even_with_pass():
    # what_bug_this_catches: aggregate success hides a failed required boundary.
    rows = (ProbeResult("ok", "synthetic-memory", Status.PASS, True, "ok"),
            ProbeResult("escape", "synthetic-memory", Status.FAIL, True, "refusal missing"))
    report = ConformanceReport(rows, ("synthetic-memory",), ("ok", "escape"), True, "local-approval")
    assert report.to_dict()["platforms"]["synthetic-memory"]["verdict"] == "blocked"


def test_subset_cannot_claim_full_conformance():
    # what_bug_this_catches: --probe allowed-read silently earns platform acceptance.
    report = ConformanceReport((ProbeResult("one", "synthetic-memory", Status.PASS, True, "ok"),),
                               ("synthetic-memory",), ("one",), False, "local-approval")
    assert report.to_dict()["platforms"]["synthetic-memory"]["verdict"] == "pending"


def test_memory_never_proves_filesystem():
    # what_bug_this_catches: memory results mislabeled as POSIX conformance.
    report = ConformanceReport((ProbeResult("all", "synthetic-memory", Status.PASS, True, "ok"),),
                               ("synthetic-memory",), ("all",), True, "local-approval")
    assert report.to_dict()["platforms"]["synthetic-memory"]["filesystem_proof"] is False
