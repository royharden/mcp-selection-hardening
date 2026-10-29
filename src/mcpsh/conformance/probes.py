"""Public development controls only. No oracle or independently sealed data."""

import json

from .models import CallSpec, ProbeDefinition

LOCAL = ("synthetic-memory", "filesystem-posix")


def call(tool, arguments):
    return CallSpec(tool, json.dumps(arguments, ensure_ascii=True, allow_nan=False))


def definitions():
    """Bounded fixed suite, with explicit hooks for intrusive boundary controls."""
    probes = [
        ProbeDefinition("allowed-read", "Allowed source read is observable and useful", LOCAL,
                        "allowed", (call("tail", {"source_id": "app", "lines": 2}),)),
        ProbeDefinition("source-policy", "Configured worker exists but is not task-allowed", LOCAL,
                        "denied", (call("tail", {"source_id": "worker"}),)),
        ProbeDefinition("source-list", "List exposes only task-allowed IDs", LOCAL,
                        "sources", (call("list_sources", {}),)),
        ProbeDefinition("duplicate-json", "Duplicate JSON keys rejected before broker I/O", LOCAL,
                        "invalid", (CallSpec("tail", '{"source_id":"app","source_id":"protected_fixture"}'),)),
        ProbeDefinition("nonfinite-json", "Nonfinite JSON rejected before broker I/O", LOCAL,
                        "invalid", (CallSpec("tail", '{"source_id":"app","lines":NaN}'),)),
        ProbeDefinition("strict-integer", "Boolean is not an integer line limit", LOCAL,
                        "invalid", (call("tail", {"source_id": "app", "lines": True}),)),
        ProbeDefinition("extra-field", "Extra fields cannot become executable arguments", LOCAL,
                        "invalid", (call("tail", {"source_id": "app", "path": "/etc/passwd"}),)),
        ProbeDefinition("unknown-source", "Unknown configured source cannot trigger I/O", LOCAL,
                        "unknown-source", (call("tail", {"source_id": "not_configured"}),), mode="permissive"),
        ProbeDefinition("protected-read", "Permissive synthetic protected-read positive control", LOCAL,
                        "read-positive", (call("error_counts", {"source_id": "protected_fixture", "group_by": "level", "max_groups": 2}),), mode="permissive"),
        ProbeDefinition("wire-disclosure", "Permissive protected wire positive control", LOCAL,
                        "wire-positive", (call("tail", {"source_id": "protected_fixture", "lines": 1}),), mode="permissive"),
        ProbeDefinition("synthetic-export", "Permissive outbox-write positive control", LOCAL,
                        "export-positive", (call("export_fixture", {"destination_id": "outbox_a"}),), mode="permissive"),
        ProbeDefinition("export-denial", "Hardened export denied without side effects", LOCAL,
                        "denied", (call("export_fixture", {"destination_id": "outbox_a"}),)),
        ProbeDefinition("custom-redaction", "Public development credential marker is redacted", LOCAL,
                        "redacted", (call("tail", {"source_id": "app", "lines": 2}),)),
        ProbeDefinition("clock-window", "Relative window uses trusted fixture clock", LOCAL,
                        "clock", (call("recent_lines", {"source_id": "app", "since_seconds": 60, "max_lines": 10}),)),
        ProbeDefinition("cursor-corruption", "Forged cursor refused", LOCAL,
                        "cursor", (call("errors", {"source_id": "app", "cursor": "forged"}),)),
        ProbeDefinition("line-count-cap", "Returned-line request cap is enforced", LOCAL,
                        "invalid", (call("tail", {"source_id": "app", "lines": 501}),)),
        ProbeDefinition("range-cap", "Range amplification rejected before I/O", LOCAL,
                        "invalid", (call("read_range", {"source_id": "app", "start_line": 1, "end_line": 501}),)),
        ProbeDefinition("input-frame-cap", "Oversized raw arguments rejected before I/O", LOCAL,
                        "invalid", (CallSpec("tail", " " * (32 * 1024 + 1)),)),
    ]
    probes.extend((
        ProbeDefinition("device-path", "Device spelling rejected as an opaque source ID (namespace only)", LOCAL,
                        "invalid", (call("tail", {"source_id": "\\\\.\\NUL"}),)),
        ProbeDefinition("cursor-length-cap", "4097-character cursor refused by the actual handler", LOCAL,
                        "invalid", (call("errors", {"source_id": "app", "cursor": "x" * 4097}),)),
        ProbeDefinition("cursor-binding", "Actual issued cursor cannot change query binding", LOCAL,
                        "ordinary-control", hook="cursor-binding"),
        ProbeDefinition("concurrency-cap", "Actual same-reference four active/sixteen queued and BUSY", LOCAL,
                        "ordinary-control", hook="concurrency-cap"),
        ProbeDefinition("broker-death", "Owned broker loss cannot produce complete observation", LOCAL,
                        "observation-unknown", hook="broker-death"),
    ))
    for hook in ("missing-source", "binary-content", "unsupported-encoding", "read-amplification",
                 "source-count-cap", "custom-rule-count-cap"):
        tracks = ("filesystem-posix",) if hook in {"missing-source", "binary-content", "unsupported-encoding"} else LOCAL
        probes.append(ProbeDefinition(hook, "Trusted production boundary with raw receipts", tracks,
                                      "trusted-refusal", hook=hook))
        probes.append(ProbeDefinition("control-stdio-" + hook,
            "Same-owned-child control diagnostic; does not claim MCP transport proof", ("stdio",),
            "trusted-refusal", required=False, hook="control-stdio:" + hook))
    for index, source in enumerate(("../outside", "/etc/passwd", "C:\\outside", "\\\\host\\share", "app:stream", "x" * 65)):
        probes.append(ProbeDefinition(f"opaque-source-{index}", "Tool arguments never select host paths", LOCAL,
                                      "invalid", (call("tail", {"source_id": source}),)))
    for fault in ("observer-loss", "observer-truncated", "observer-reset-corrupt", "observer-fixture-mismatch"):
        probes.append(ProbeDefinition(fault, "Observation failure remains unknown", LOCAL,
                                      "observation-unknown", hook=fault))
    for hook in ("read-byte-cap", "physical-line-cap", "deadline", "frame-amplification"):
        probes.append(ProbeDefinition(hook, "Bounded backend refuses amplification", LOCAL,
                                      "bounded-refusal", hook=hook))
    for hook in ("posix-symlink", "posix-rename", "posix-nonlocal", "posix-source-change"):
        probes.append(ProbeDefinition(hook, "Disposable POSIX boundary refusal", ("filesystem-posix",),
                                      "posix-refusal", hook=hook))
    for hook in ("stdio-catalog", "stdio-success", "stdio-policy-error", "stdio-unknown-method",
                 "stdio-escaping", "stdio-duplicate", "stdio-nonfinite", "stdio-input-frame",
                 "stdio-output-amplification", "stdio-cancellation", "stdio-concurrency"):
        probes.append(ProbeDefinition(hook, "Actual bounded MCP stdio protocol control", ("stdio",),
                                      "stdio-protocol", hook=hook))
    from .semantics import REQUIRED_CASE_IDS

    for case_id in REQUIRED_CASE_IDS:
        probes.append(ProbeDefinition("semantic-" + case_id, "Public server matching/log semantic contract",
            LOCAL, "semantic:" + case_id, semantic_case_id=case_id))
        probes.append(ProbeDefinition("semantic-stdio-" + case_id, "Same-child public stdio semantic contract",
            ("stdio",), "semantic-stdio", hook="semantic-stdio:" + case_id, semantic_case_id=case_id))
    return tuple(probes)
