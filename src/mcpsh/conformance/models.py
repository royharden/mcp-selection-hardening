"""Small immutable conformance API; importing it has no backend effects."""

from dataclasses import asdict, dataclass, field
from enum import Enum
import re
from typing import Any


class Status(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    UNKNOWN = "unknown"
    UNAVAILABLE = "unavailable"
    UNSUPPORTED = "unsupported"


@dataclass(frozen=True)
class ConformanceRequest:
    tracks: tuple[str, ...] = ("synthetic-memory",)
    runtime_authorized: bool = False
    disposable_authorized: bool = False
    approval_id: str = ""
    posix_fixture_parent: str | None = None
    probe_ids: tuple[str, ...] = ()
    timeout_seconds: float = 5.0

    def __post_init__(self):
        known = {"synthetic-memory", "filesystem-posix", "stdio"}
        if not self.tracks or len(set(self.tracks)) != len(self.tracks):
            raise ValueError("unique nonempty conformance tracks required")
        if set(self.tracks) - known:
            raise ValueError("unknown conformance track")
        if type(self.timeout_seconds) not in (float, int) or not 0 < self.timeout_seconds <= 5:
            raise ValueError("conformance timeout must be in (0, 5] seconds")
        if len(self.probe_ids) > 100 or len(set(self.probe_ids)) != len(self.probe_ids):
            raise ValueError("unique bounded probe selection required")
        if len(self.approval_id) > 256 or "\x00" in self.approval_id:
            raise ValueError("bounded approval ID required")
        if self.approval_id and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}", self.approval_id) is None:
            raise ValueError("approval ID must match the bounded core conformance authority format")

    def require_activation(self):
        if self.runtime_authorized is not True or self.disposable_authorized is not True:
            raise ValueError("explicit runtime and disposable-fixture authorization required")
        if not self.approval_id.strip():
            raise ValueError("explicit activation approval ID required")


@dataclass(frozen=True)
class CallSpec:
    tool: str
    raw_arguments: str


@dataclass(frozen=True)
class ProbeDefinition:
    probe_id: str
    description: str
    tracks: tuple[str, ...]
    expectation: str
    calls: tuple[CallSpec, ...] = ()
    mode: str = "hardened"
    required: bool = True
    hook: str | None = None
    semantic_case_id: str | None = None


@dataclass(frozen=True)
class ProbeResult:
    probe_id: str
    track: str
    status: Status
    required: bool
    reason: str
    evidence: dict[str, Any] = field(default_factory=dict)

    def to_dict(self):
        return {**asdict(self), "status": self.status.value}


@dataclass(frozen=True)
class ConformanceReport:
    results: tuple[ProbeResult, ...]
    tracks: tuple[str, ...]
    selected_probe_ids: tuple[str, ...]
    full_suite: bool
    approval_id: str
    semantic_manifest: dict | None = None

    def to_dict(self):
        from .probes import definitions

        platforms = {}
        for track in self.tracks:
            rows = [row for row in self.results if row.track == track]
            required = [row for row in rows if row.required]
            expected_ids = {probe.probe_id for probe in definitions() if probe.required and track in probe.tracks}
            actual_ids = [row.probe_id for row in required]
            counts = {status.value: sum(row.status == status for row in rows) for status in Status}
            if any(row.status == Status.FAIL for row in required):
                verdict = "blocked"
            elif not self.full_suite or not required or any(row.status != Status.PASS for row in required):
                verdict = "pending"
            elif len(actual_ids) != len(set(actual_ids)) or set(actual_ids) != expected_ids:
                verdict = "pending"
            elif any(row.evidence.get("verification", {}).get("creditable") is not True for row in required):
                verdict = "pending"
            elif self.semantic_manifest is not None and any(
                row.evidence.get("provenance", {}).get("semantic", {}).get("manifest_sha256") != self.semantic_manifest.get("manifest_sha256")
                for row in required):
                verdict = "pending"
            else:
                verdict = "passed"
            platforms[track] = {"verdict": verdict, "counts": counts,
                                "filesystem_proof": track == "filesystem-posix" and verdict == "passed"}
        payload = {"schema_version": 1, "kind": "conformance", "approval_id": self.approval_id,
                "full_suite": self.full_suite, "selected_probe_ids": list(self.selected_probe_ids),
                "platforms": platforms, "results": [row.to_dict() for row in self.results],
                "product_acceptance": "pending",
                "limitations": ["Track verdicts are separate; memory and stdio do not prove filesystem safety.",
                                "Source construction and authored probes are not measured conformance."]}
        if self.semantic_manifest is not None:
            payload["required_case_manifest"] = self.semantic_manifest
        return payload
