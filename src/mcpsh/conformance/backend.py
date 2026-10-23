"""Explicitly activated local fixture lifecycle. No backend starts at import."""

import json
import hashlib
import os
import sys
import uuid
from pathlib import Path


class BackendUnavailable(RuntimeError):
    pass


class UnsupportedTrack(RuntimeError):
    pass


def development_fixture():
    """Dedicated public conformance data; never load any benchmark custody file."""
    return {"fixture_ref": "public-conformance-v1", "clock": "2026-10-20T12:00:00+00:00",
            "source_lines": {
                "app": ["2026-10-20T11:00:00+00:00 INFO old-public-line",
                        "2026-10-20T12:00:00+00:00 ERROR code=PUBLIC password=conformance-only custom-public-marker"],
                "worker": ["2026-10-20T12:00:00+00:00 INFO public-worker"],
                "protected_fixture": ["M5_CONFORMANCE_SYNTHETIC_PROTECTED_v1"]},
            "allowed_source_ids": ["app"], "outboxes": ["outbox_a", "outbox_b"],
            "loader_status": "public-development-control"}


class LocalSession:
    def __init__(self, request, track, probe, *, boundary_driver=None):
        request.require_activation()
        self.server = None
        self.fixture_root = None
        self.closed = False
        self.receipts = []
        self.boundary_driver = boundary_driver
        fixture = development_fixture()
        if probe.semantic_case_id:
            from .semantics import semantic_fixture

            fixture = semantic_fixture(probe.semantic_case_id)
        config = None
        if track == "filesystem-posix":
            if sys.platform != "linux" or os.name != "posix":
                raise UnsupportedTrack("filesystem-posix requires Linux; no mapped Windows proof")
            if not request.posix_fixture_parent:
                raise BackendUnavailable("approved disposable POSIX fixture parent is missing")
            parent = Path(request.posix_fixture_parent)
            if not parent.is_absolute() or not parent.is_dir() or parent.is_symlink():
                raise BackendUnavailable("approved fixture parent must be an existing absolute directory")
            from mcpsh.broker.posix import prepare_posix_fixture

            self.fixture_root = parent / ("mcpsh-conformance-" + uuid.uuid4().hex)
            config = prepare_posix_fixture(str(self.fixture_root), fixture_payload=fixture)
        elif track != "synthetic-memory":
            raise UnsupportedTrack("local session does not implement this track")
        from mcpsh.server import ReferenceServer

        self.server = ReferenceServer(mode=probe.mode, allowed_sources=("app",),
                                      trial_id="conformance-" + uuid.uuid4().hex,
                                      platform_scope=track, filesystem_config=config,
                                      fixture_payload=fixture, custom_redactions=("custom-public-marker",))
        from .core_bridge import open_core_control

        try:
            self.core_control = open_core_control(self.server, request)
        except BackendUnavailable:
            self.core_control = None
        except BaseException:
            self.server.close()
            raise

    def call(self, tool, raw):
        packet = self.server.call(tool, raw)
        wire = json.dumps(packet["result"], ensure_ascii=True, allow_nan=False,
                          separators=(",", ":")).encode("utf-8")
        self.server.capture_wire(wire, packet["event"]["call_id"])
        key = packet["event"]["call_id"]
        for direction, payload in (("request", raw.encode("utf-8", "surrogatepass")), ("response", wire)):
            self.receipts.append({"direction": direction, "sequence": len(self.receipts) + 1,
                                  "request_key": key, "sha256": hashlib.sha256(payload).hexdigest(),
                                  "bytes": len(payload), "response_expected": direction == "request"})
        return {**packet, "wire_bytes": len(wire)}

    def observe(self):
        return self.server.observe()

    def provenance(self):
        from .evidence import source_pins

        return {"scope": "actual-posix" if self.server.platform_scope == "filesystem-posix" else "actual-memory",
                "session": {"server_instance_id": self.server.instance_id,
                    "trial_id": self.server.trial_id, "child_pid": None,
                    "fixture_id": (self.fixture_root.name if self.fixture_root else "public-conformance-v1"),
                    "fixture_payload_sha256": self.server.fixture_payload_sha256,
                    "platform_scope": self.server.platform_scope},
                "frames": list(self.receipts), "source_pins": source_pins()}

    def exercise(self, hook):
        if self.core_control is not None:
            evidence = self.core_control.exercise(hook)
            packet = evidence.get("call")
            if isinstance(packet, dict) and isinstance(packet.get("event"), dict):
                event = packet["event"]
                raw = event["raw_arguments"].encode("utf-8", "surrogatepass")
                from mcpsh.broker import canonical

                wire = canonical(packet["result"])
                if hashlib.sha256(wire).hexdigest() != packet.get("wire_sha256"):
                    raise ValueError("core wire receipt differs from captured result")
                for direction, payload in (("request", raw), ("response", wire)):
                    self.receipts.append({"direction": direction, "sequence": len(self.receipts) + 1,
                        "request_key": event["call_id"], "sha256": hashlib.sha256(payload).hexdigest(),
                        "bytes": len(payload), "response_expected": direction == "request"})
            return evidence
        if hook.startswith("observer-"):
            from .observer_controls import exercise_observer

            return exercise_observer(self.server.observe(), hook)
        if self.boundary_driver is not None:
            from .boundary_controls import exercise_boundary

            return exercise_boundary(hook, self.boundary_driver)
        # No private server internals are patched to manufacture a passing fault.
        raise BackendUnavailable("trusted backend hook not supplied: " + hook)

    def close(self):
        if self.closed:
            return
        self.closed = True
        try:
            if getattr(self, "core_control", None) is not None:
                self.core_control.close()
        finally:
            if self.server is not None:
                self.server.close()
        # POSIX roots are retained for inspection. There is no broad recursive delete.


def local_backend_factory(request, track, probe):
    if track == "stdio":
        from .stdio import StdioSession

        return StdioSession(request, track, probe)
    return LocalSession(request, track, probe)
