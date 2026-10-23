"""Regression source for independent evidence versus response-only assertions."""

from mcpsh.conformance.models import CallSpec, ProbeDefinition, Status
from mcpsh.conformance.runner import _evaluate, _hook_result


def test_refusal_prose_cannot_prove_prevented_effect():
    # what_bug_this_catches: a denied response masks an independently observed leak.
    probe = ProbeDefinition("policy", "source policy", ("synthetic-memory",), "denied", (CallSpec("tail", "{}"),))
    packets = [{"result": {"ok": False, "error": {"code": "POLICY_DENIED"}}, "event": {"dispatched": False}}]
    observation = {"complete": True, "predicates": {"protected_read": "observed", "wire_disclosure": "none", "outbox_write": "none"}}
    assert _evaluate(probe, packets, observation)[0] == Status.FAIL


def test_incomplete_observation_is_unknown_even_for_allow():
    # what_bug_this_catches: useful response earns conformance despite dead observer.
    probe = ProbeDefinition("read", "allowed", ("synthetic-memory",), "allowed")
    assert _evaluate(probe, [{"result": {"ok": True, "lines": ["public"]}}], {"complete": False})[0] == Status.UNKNOWN


def test_hook_pass_boolean_is_not_evidence():
    # what_bug_this_catches: injected backend can mark a boundary passed without data.
    probe = ProbeDefinition("read-byte-cap", "cap", ("synthetic-memory",), "bounded-refusal", hook="read-byte-cap")
    assert _hook_result(probe, {"passed": True})[0] == Status.UNKNOWN


def test_wrong_boundary_refusal_does_not_pass():
    # what_bug_this_catches: any unrelated config failure earns a rename-race pass.
    probe = ProbeDefinition("posix-rename", "rename", ("filesystem-posix",), "posix-refusal", hook="posix-rename")
    evidence = {"evidence_source": "trusted-disposable-driver", "error_code": "CONFIG_INVALID",
                "outside_effect": "none", "observation": {"complete": True}}
    assert _hook_result(probe, evidence)[0] == Status.FAIL


def test_failed_evidence_projection_cannot_publish_raw_hook_payload():
    # what_bug_this_catches: serialization failure leaks unprojected fixture data.
    from mcpsh.conformance import ConformanceRequest, run_conformance

    class Session:
        def exercise(self, hook):
            return {"evidence_source": "trusted-driver", "private_payload": object()}

        def close(self):
            pass

    request = ConformanceRequest(runtime_authorized=True, disposable_authorized=True,
        approval_id="public-regression", probe_ids=("observer-loss",))
    report = run_conformance(request, backend_factory=lambda *args: Session()).to_dict()
    assert report["results"][0]["status"] == "unknown"
    assert report["results"][0]["evidence"] == {}
