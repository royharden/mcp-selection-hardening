"""Closed project conformance evidence v1, not a product acceptance certificate."""

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal, TypedDict


class FrameReceipt(TypedDict):
    direction: Literal["request", "response"]
    sequence: int
    request_key: str
    sha256: str
    bytes: int
    response_expected: bool


class SessionBinding(TypedDict):
    server_instance_id: str
    trial_id: str
    child_pid: int | None
    fixture_id: str
    fixture_payload_sha256: str
    platform_scope: str


class ObservationBinding(TypedDict):
    observer_version: str
    trial_id: str
    epoch: str
    complete: bool
    reset_verified: bool
    sequence_complete: bool
    wire_complete: bool
    predicates: dict[str, Literal["none", "observed", "unknown"]]
    broker_event_count: int
    last_sequence: int
    events_sha256: str

PIN_NAMES = frozenset({"server", "broker", "observer", "stdio", "conformance"})
# Trusted-hook producer modules that must stay inside the pinned closure.
SERVER_CLOSURE_EXTRAS = ("policy/__init__.py", "catalog/schemas.py")
REQUIRED_CLOSURE_MEMBERS = {
    "server": frozenset({"__init__.py", "conformance.py", "admission.py", "validation.py",
                         *SERVER_CLOSURE_EXTRAS}),
    "broker": frozenset({"__init__.py", "bounds.py", "fixtures.py", "posix.py"}),
    "observer": frozenset({"__init__.py"}),
    "conformance": frozenset({"receipt_guard.py", "core_bridge.py", "host_control.py", "stdio_host.py"}),
}
PREDICATES = frozenset({"protected_read", "outbox_write", "wire_disclosure"})
SCOPES = frozenset({"actual-memory", "actual-posix", "actual-stdio",
                    "component-diagnostic", "mock-diagnostic"})
ROOT_FIELDS = frozenset({"schema_version", "probe_id", "track", "scope", "request_sha256",
                         "source_pins", "session", "frames", "observation", "checks", "record_sha256"})
SESSION_FIELDS = frozenset({"server_instance_id", "trial_id", "child_pid", "fixture_id",
                            "fixture_payload_sha256", "platform_scope"})
FRAME_FIELDS = frozenset({"direction", "sequence", "request_key", "sha256", "bytes", "response_expected"})
OBS_FIELDS = frozenset({"observer_version", "trial_id", "epoch", "complete", "reset_verified",
                        "sequence_complete", "wire_complete", "predicates", "broker_event_count",
                        "last_sequence", "events_sha256"})


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=True, allow_nan=False,
        sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def source_pins():
    """Fixed source-only file set, read only during explicitly admitted invocation."""
    root = Path(__file__).resolve().parents[1]

    def read(path):
        with path.open("rb") as handle:
            value = handle.read(1024 * 1024 + 1)
        if len(value) > 1024 * 1024:
            raise ValueError("source pin byte cap")
        return hashlib.sha256(value).hexdigest()

    pins = {"stdio": read(root / "server/stdio.py")}
    for name in ("server", "broker", "observer", "conformance"):
        paths = sorted((root / name).glob("*.py"))
        if not paths or len(paths) > 64:
            raise ValueError("source closure count cap")
        members = [(path.name, read(path)) for path in paths]
        if name == "server":
            # Producer receipts also depend on policy validators/caps and the
            # runtime tool schemas; the closed five-key pin shape is retained.
            members += [(relative, read(root / relative)) for relative in SERVER_CLOSURE_EXTRAS]
        present = {member for member, _ in members}
        if not REQUIRED_CLOSURE_MEMBERS.get(name, frozenset()) <= present:
            raise ValueError("producer source closure member missing: " + name)
        pins[name] = digest(members)
    return pins


@dataclass(frozen=True)
class EvidenceContext:
    request_sha256: str
    source_pins: dict[str, str]
    semantic_manifest: dict | None = None

    @classmethod
    def from_request(cls, request):
        request.require_activation()
        from .manifest import runtime_semantic_manifest

        return cls(digest(asdict(request)), source_pins(), runtime_semantic_manifest())


def observation_projection(observation):
    events = observation.get("events", [])
    if type(events) is not list or len(events) > 1024:
        events = []
    epochs = {event.get("epoch") for event in events if isinstance(event, dict)}
    trial_ids = {event.get("trial_id") for event in events if isinstance(event, dict)}
    ordered = bool(events) and all(isinstance(event, dict) and type(event.get("sequence")) is int
                                  and event["sequence"] == index + 1 for index, event in enumerate(events))
    trial = observation.get("trial_id")
    attributable = isinstance(trial, str) and trial_ids == {trial} and len(epochs) == 1
    return {"observer_version": observation.get("observer_version", ""),
            "trial_id": trial or "", "epoch": next(iter(epochs)) if len(epochs) == 1 else "",
            "complete": observation.get("complete") is True and attributable and ordered,
            "reset_verified": observation.get("reset_verified") is True,
            "sequence_complete": observation.get("sequence_complete") is True and ordered,
            "wire_complete": observation.get("wire_complete") is True,
            "predicates": {key: observation.get("predicates", {}).get(key, "unknown") for key in PREDICATES},
            "broker_event_count": len(events), "last_sequence": len(events) if ordered else 0,
            "events_sha256": digest(events)}


def build_evidence(*, context, probe, track, session_binding, frames, observation,
                   scope, checks=None):
    session = {key: session_binding.get(key) for key in SESSION_FIELDS}
    document = {"schema_version": 1, "probe_id": probe.probe_id, "track": track,
        "scope": scope, "request_sha256": context.request_sha256,
        "source_pins": dict(context.source_pins), "session": session,
        "frames": list(frames), "observation": observation_projection(observation),
        "checks": dict(checks or {})}
    document["record_sha256"] = digest(document)
    return document


def _hex(value):
    return type(value) is str and re.fullmatch(r"[a-f0-9]{64}", value) is not None


def _text(value, maximum=256):
    return type(value) is str and 0 < len(value.encode("utf-8")) <= maximum and "\x00" not in value


def verify_evidence(document, *, expected_probe_id, expected_track, expected_request_sha256,
                    expected_source_pins, expected_server_instance_id,
                    expected_fixture_payload_sha256=None):
    """D7 API: externally supplied selection/pins, strict keys, no file/OS access.

    A structurally valid diagnostic or incomplete observation remains uncreditable.
    The checker cannot prove an observation narrative truthful or grant acceptance.
    """
    issues = []
    if type(document) is not dict or set(document) != ROOT_FIELDS:
        return {"valid": False, "creditable": False, "violations": ["evidence.fields"], "scope": "unknown", "predicates": {}}
    try:
        if type(document["schema_version"]) is not int or document["schema_version"] != 1:
            issues.append("evidence.version")
        if document["probe_id"] != expected_probe_id or document["track"] != expected_track:
            issues.append("evidence.selection")
        if not _hex(expected_request_sha256) or document["request_sha256"] != expected_request_sha256:
            issues.append("evidence.request-pin")
        pins = document["source_pins"]
        if type(pins) is not dict or set(pins) != PIN_NAMES or set(expected_source_pins) != PIN_NAMES or pins != expected_source_pins or not all(_hex(value) for value in pins.values()):
            issues.append("evidence.source-pins")
        if type(document["scope"]) is not str or document["scope"] not in SCOPES:
            issues.append("evidence.scope")
        session = document["session"]
        if type(session) is not dict or set(session) != SESSION_FIELDS:
            issues.append("session.fields")
            session = {}
        if not _text(session.get("server_instance_id")) or session.get("server_instance_id") != expected_server_instance_id:
            issues.append("session.instance")
        if not _text(session.get("fixture_id")) or not _hex(session.get("fixture_payload_sha256")):
            issues.append("session.fixture")
        if not _hex(expected_fixture_payload_sha256) or session.get("fixture_payload_sha256") != expected_fixture_payload_sha256:
            issues.append("session.fixture-pin")
        pid = session.get("child_pid")
        if pid is not None and (type(pid) is not int or pid <= 0):
            issues.append("session.child")
        expected_scope = {"synthetic-memory": "actual-memory", "filesystem-posix": "actual-posix", "stdio": "actual-stdio"}.get(expected_track)
        if isinstance(document["scope"], str) and document["scope"].startswith("actual-") and document["scope"] != expected_scope:
            issues.append("session.track-scope")
        if session.get("platform_scope") not in {"synthetic-memory", "filesystem-posix"} or (expected_track != "stdio" and session.get("platform_scope") != expected_track):
            issues.append("session.platform")
        if expected_track == "stdio" and (type(pid) is not int or pid <= 0):
            issues.append("session.child")
        frames = document["frames"]
        if type(frames) is not list or not 1 <= len(frames) <= 128:
            issues.append("frames.missing-or-cap")
            frames = []
        for index, frame in enumerate(frames):
            if type(frame) is not dict or set(frame) != FRAME_FIELDS:
                issues.append("frames.fields")
                continue
            if frame["direction"] not in {"request", "response"} or type(frame["response_expected"]) is not bool or type(frame["sequence"]) is not int or frame["sequence"] != index + 1 or not _text(frame["request_key"]) or not _hex(frame["sha256"]) or type(frame["bytes"]) is not int or not 0 < frame["bytes"] <= (32 * 1024 + 1024 if frame["direction"] == "request" else 32 * 1024):
                issues.append("frames.binding-or-cap")
        requests = {frame.get("request_key") for frame in frames if isinstance(frame, dict) and frame.get("direction") == "request"}
        responses = [frame.get("request_key") for frame in frames if isinstance(frame, dict) and frame.get("direction") == "response"]
        required_replies = {frame.get("request_key") for frame in frames if isinstance(frame, dict) and frame.get("direction") == "request" and frame.get("response_expected") is True}
        if not responses or not set(responses).issubset(requests) or len(responses) != len(set(responses)):
            issues.append("frames.response-attribution")
        if not required_replies.issubset(responses):
            issues.append("frames.omitted-response")
        request_order = {frame.get("request_key"): frame.get("sequence") for frame in frames if isinstance(frame, dict) and frame.get("direction") == "request" and frame.get("request_key") != "null"}
        if any(request_order.get(frame.get("request_key"), 0) >= frame.get("sequence", 0) for frame in frames if isinstance(frame, dict) and frame.get("direction") == "response"):
            issues.append("frames.order")
        observation = document["observation"]
        if type(observation) is not dict or set(observation) != OBS_FIELDS:
            issues.append("observation.fields")
            observation = {}
        for key in ("complete", "reset_verified", "sequence_complete", "wire_complete"):
            if type(observation.get(key)) is not bool:
                issues.append("observation.flags")
        if not _text(session.get("trial_id")) or observation.get("trial_id") != session.get("trial_id") or not _text(observation.get("epoch")) or not _text(observation.get("observer_version")):
            issues.append("observation.attribution")
        count = observation.get("broker_event_count")
        if type(count) is not int or not 1 <= count <= 1024 or type(observation.get("last_sequence")) is not int or not _hex(observation.get("events_sha256")):
            issues.append("observation.sequence")
        if observation.get("sequence_complete") is True and observation.get("last_sequence") != count:
            issues.append("observation.sequence")
        predicates = observation.get("predicates", {})
        if type(predicates) is not dict or set(predicates) != PREDICATES or any(value not in {"none", "observed", "unknown"} for value in predicates.values()):
            issues.append("observation.predicates")
            predicates = {}
        checks = document["checks"]
        if type(checks) is not dict or len(checks) > 32 or any(not _text(key, 96) or type(value) is not bool for key, value in checks.items()):
            issues.append("evidence.checks")
        unsigned = {key: value for key, value in document.items() if key != "record_sha256"}
        if not _hex(document["record_sha256"]) or digest(unsigned) != document["record_sha256"]:
            issues.append("evidence.digest")
        complete = all(observation.get(key) is True for key in ("complete", "reset_verified", "sequence_complete", "wire_complete")) and "unknown" not in predicates.values()
        creditable = not issues and document["scope"] == expected_scope and complete
        return {"valid": not issues, "creditable": creditable, "violations": sorted(set(issues)),
                "scope": document["scope"], "predicates": dict(predicates)}
    except (ValueError, TypeError, KeyError, UnicodeError, OverflowError, RecursionError):
        return {"valid": False, "creditable": False, "violations": ["evidence.ill-shaped"],
                "scope": "unknown", "predicates": {}}
