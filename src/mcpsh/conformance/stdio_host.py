"""Fixed disposable conformance host, used only after parent runtime admission."""


def main():
    import argparse
    import asyncio
    import inspect
    import os
    import threading
    import uuid

    from mcpsh.server import ReferenceServer
    from mcpsh.server.stdio import serve_stdio
    from .backend import BackendUnavailable, development_fixture
    from .channel import open_child_streams
    from .core_bridge import open_core_control
    from .host_control import serve_control
    from .models import ConformanceRequest

    parser = argparse.ArgumentParser()
    parser.add_argument("--control-kind", choices=("windows-handle", "posix-fd"), required=True)
    parser.add_argument("--control-read", type=int, required=True)
    parser.add_argument("--control-write", type=int, required=True)
    parser.add_argument("--control-nonce", required=True)
    parser.add_argument("--runtime-authorized", action="store_true")
    parser.add_argument("--disposable-authorized", action="store_true")
    parser.add_argument("--approval-id", required=True)
    from .semantics import REQUIRED_CASE_IDS, semantic_fixture

    parser.add_argument("--semantic-case", choices=REQUIRED_CASE_IDS)
    args = parser.parse_args()
    request = ConformanceRequest(tracks=("stdio",), runtime_authorized=args.runtime_authorized,
        disposable_authorized=args.disposable_authorized, approval_id=args.approval_id)
    request.require_activation()
    if len(args.control_nonce) != 48 or any(character not in "0123456789abcdef" for character in args.control_nonce):
        parser.error("owned inherited control nonce required")
    reader, writer = open_child_streams(args.control_kind, args.control_read, args.control_write)
    fixture = semantic_fixture(args.semantic_case) if args.semantic_case else development_fixture()
    # Bounded, public escaping amplification stimulus; no evaluation fixture data.
    if not args.semantic_case:
        fixture["source_lines"]["app"] = ['"\\\t\u2028' * 100 for _ in range(100)]
    reference = ReferenceServer(mode="hardened", allowed_sources=("app",),
                                 trial_id="stdio-conformance-" + uuid.uuid4().hex,
                                 fixture_payload=fixture)
    control = None
    try:
        try:
            control = open_core_control(reference, request)
        except BackendUnavailable:
            pass
        parameters = inspect.signature(serve_stdio).parameters
        injected = "reference" in parameters and "conformance_session" in parameters
        identity = {"child_pid": os.getpid(), "server_instance_id": reference.instance_id,
                    "trial_id": reference.trial_id,
                    # Producer receipts attribute reference.fixture_id (instance),
                    # not the public fixture_ref; same-child guards compare both.
                    "fixture_id": reference.fixture_id,
                    "fixture_payload_sha256": reference.fixture_payload_sha256,
                    "platform_scope": reference.platform_scope,
                    "core_control_available": control is not None,
                    "stdio_reference_injected": injected}
        thread = threading.Thread(target=serve_control, args=(reader, writer),
            kwargs={"nonce": args.control_nonce, "identity": identity, "control": control}, daemon=True)
        thread.start()
        if not injected:
            # Let the parent receive truthful identity, then stop this unavailable host.
            thread.join(timeout=5)
            return
        asyncio.run(serve_stdio(reference=reference,
                                conformance_session=control.control if control is not None else None))
    finally:
        if control is not None:
            control.close()
        reference.close()


if __name__ == "__main__":
    main()
