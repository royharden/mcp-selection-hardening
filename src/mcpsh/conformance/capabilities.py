"""Read-only source capability declaration, not a runtime detection claim."""


def capability_report():
    return {"schema_version": 1, "execution": "not-run", "tracks": {
        "synthetic-memory": {"backend": "bundled", "filesystem_proof": False},
        "filesystem-posix": {"requires": ["approved Linux-native disposable parent",
            "openat2", "no-follow descriptor semantics", "D2 deep boundary hooks"],
            "windows": "unsupported", "runtime_verified": False},
        "stdio": {"backend": "fixed bundled local child only", "remote_targets": False,
            "protocol_version": "2025-11-25", "sdk_lock": "pending",
            "control_transport": "owned inherited anonymous pipes with PID/nonce/sequence binding",
            "requires": ["compatible installed official SDK", "D2 same-reference conformance_session and serve_stdio injection"],
            "runtime_verified": False}},
        "concurrency_contract": {"active": 4, "queued": 16, "overflow": "BUSY",
            "proof": "requires independently witnessed occupancy and bounded release"},
        "cancellation_contract": {"method": "notifications/cancelled", "params": ["requestId", "reason"],
            "late_reply": "ignore after cancellation", "proof": "requires proven in-flight request and independent effects"}}
