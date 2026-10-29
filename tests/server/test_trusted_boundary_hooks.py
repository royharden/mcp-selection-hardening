"""Authored actual-session regressions; future runtime authorization is required.

These tests would start only their own disposable reference and broker. They have
NOT been imported or executed during Dirty Mode. They are not mock effect proof.
"""

import sys

import pytest

from mcpsh.broker.posix import prepare_posix_fixture
from mcpsh.server import ReferenceServer
from mcpsh.server.conformance import create_conformance_session


def test_memory_missing_source_and_aggregate_scan_use_same_owned_reference():
    reference = ReferenceServer(trial_id="public-hook-regression")
    control = None
    try:
        control = create_conformance_session(reference, runtime_authorized=True,
            disposable_authorized=True, approval_id="public-regression-runtime-only")
        missing = control.exercise("missing-source")
        assert missing["server_instance_id"] == reference.instance_id
        assert missing["error_code"] == "SOURCE_MISSING"
        assert missing["observation"]["complete"] is True
        aggregate = control.exercise("read-amplification")
        assert aggregate["error_code"] == "LIMIT_EXCEEDED"
        assert aggregate["metrics"]["completed_scans"] == 2
        assert aggregate["metrics"]["aggregate_read_bytes"] == 6 * 1024 * 1024
        assert aggregate["metrics"]["aggregate_read_bytes"] <= aggregate["metrics"]["read_limit_bytes"]
        broker_pid = reference._broker._process.pid
        for hook in ("source-count-cap", "custom-rule-count-cap"):
            configuration = control.exercise(hook)
            assert configuration["evidence_scope"] == "component-diagnostic"
            assert configuration["call"] is None
            assert configuration["control_receipt"]["error_code_source"] == "component-validation-mapping-v1"
            assert configuration["observed_state_unchanged"] is True
            assert configuration["broker_pid"] == broker_pid
            assert configuration["server_instance_id"] == reference.instance_id
    finally:
        if control is not None:
            control.close()
        reference.close()


@pytest.mark.skipif(sys.platform != "linux", reason="POSIX proof cannot run on Windows")
@pytest.mark.parametrize("hook,code", [("missing-source", "SOURCE_MISSING"),
    ("binary-content", "BINARY_CONTENT"), ("unsupported-encoding", "UNSUPPORTED_ENCODING")])
def test_posix_owned_file_fault_refusals_and_actual_restoration(tmp_path, hook, code):
    # Unsupported kernel/filesystem requirements fail visibly; no catch-and-pass.
    config = prepare_posix_fixture(str(tmp_path / "owned-public-fixture"))
    reference = ReferenceServer(trial_id="public-posix-hook", platform_scope="filesystem-posix", filesystem_config=config)
    control = None
    try:
        control = create_conformance_session(reference, runtime_authorized=True,
            disposable_authorized=True, approval_id="public-regression-runtime-only")
        observed = control.exercise(hook)
        assert observed["error_code"] == code
        assert observed["restoration_receipt"]["applied"] is True
        assert observed["observation"]["complete"] is True
        assert observed["outside_effect"] == "none"
    finally:
        if control is not None:
            control.close()
        reference.close()
