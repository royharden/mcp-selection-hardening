"""Fixed control dispatcher; core counters/effects are always supplied by D2."""

import os

from .backend import BackendUnavailable
from .channel import COMMANDS, CONTROL_LIMIT, pack, unpack
from .probes import definitions


def dispatch(control, command, arguments, identity):
    if command == "identity":
        if arguments:
            raise ValueError("identity takes no arguments")
        return identity
    if control is None:
        raise BackendUnavailable("core session unavailable")
    if command in {"hold_execution", "release_execution", "observe", "close"}:
        if arguments:
            raise ValueError("unexpected control arguments")
        value = getattr(control, command)()
        return {} if value is None else value
    if command == "exercise":
        hooks = {probe.hook for probe in definitions() if probe.hook and not probe.hook.startswith("stdio-")}
        if "hook" not in arguments or set(arguments) - {"hook", "request_id", "payload"} or arguments["hook"] not in hooks:
            raise ValueError("unknown bounded core probe hook")
        request_id = arguments.get("request_id")
        if request_id is not None:
            _request_id(request_id)
        if arguments.get("payload") not in (None, {}):
            raise ValueError("unapproved core exercise payload")
        return control.exercise(arguments["hook"], request_id=request_id, payload=arguments.get("payload"))
    if command == "wait_for_occupancy":
        if set(arguments) != {"active", "queued", "timeout"}:
            raise ValueError("occupancy argument fields differ")
        if type(arguments["active"]) is not int or not 0 <= arguments["active"] <= 4 or type(arguments["queued"]) is not int or not 0 <= arguments["queued"] <= 16:
            raise ValueError("occupancy limits outside source contract")
        _timeout(arguments["timeout"])
        return control.wait_for_occupancy(**arguments)
    if command == "wait_for_cancellation":
        if set(arguments) != {"request_id", "timeout"}:
            raise ValueError("cancellation must address an issued bounded request ID")
        _request_id(arguments["request_id"])
        _timeout(arguments["timeout"])
        return control.wait_for_cancellation(request_id=arguments["request_id"], timeout=arguments["timeout"])
    raise ValueError("control command not supported")


def _timeout(value):
    if type(value) not in {int, float} or not 0 < value <= 5:
        raise ValueError("bounded positive control timeout required")


def _request_id(value):
    if type(value) not in {int, str} or (type(value) is str and not 1 <= len(value) <= 128):
        raise ValueError("exact JSON-RPC integer or bounded string ID required; bool forbidden")


def serve_control(reader, writer, *, nonce, identity, control):
    sequence = 0
    try:
        for _ in range(64):
            raw = reader.readline(CONTROL_LIMIT + 1)
            if not raw:
                return
            request = unpack(raw)
            if set(request) != {"schema_version", "nonce", "sequence", "command", "arguments"}:
                raise ValueError("control request fields differ")
            command = request["command"]
            if request["schema_version"] != 1 or request["nonce"] != nonce or type(request["sequence"]) is not int or request["sequence"] != sequence + 1 or command not in COMMANDS:
                raise ValueError("unbound, stale or unknown control request")
            sequence += 1
            payload, error = None, None
            try:
                if type(request["arguments"]) is not dict:
                    raise ValueError("control argument object required")
                payload = dispatch(control, command, request["arguments"], identity)
                if type(payload) is not dict:
                    raise ValueError("core control must return an evidence object")
            except BackendUnavailable:
                error = "unavailable"
            except Exception:
                error = "failed"
            wire = pack({"schema_version": 1, "nonce": nonce, "child_pid": os.getpid(),
                               "sequence": sequence, "command": command, "payload": payload,
                               "error": error})
            view = memoryview(wire)
            while view:
                count = writer.write(view)
                if not count:
                    raise OSError("short child control write")
                view = view[count:]
            writer.flush()
            if command == "close":
                return
    finally:
        reader.close()
        writer.close()
