"""Private inherited-pipe control RPC bound to one owned child, never a listener."""

import json
import os
import queue
import secrets
import subprocess
import threading

CONTROL_LIMIT = 256 * 1024
CONTROL_STARTUP_SECONDS = 120.0
COMMANDS = frozenset({"identity", "hold_execution", "release_execution", "wait_for_occupancy",
                      "wait_for_cancellation", "observe", "exercise", "close"})


def pack(value):
    raw = json.dumps(value, ensure_ascii=True, allow_nan=False,
                     separators=(",", ":")).encode("utf-8") + b"\n"
    if len(raw) > CONTROL_LIMIT:
        raise ValueError("control frame limit")
    return raw


def unpack(raw):
    from mcpsh.records import strict_json_loads

    if not raw.endswith(b"\n") or len(raw) > CONTROL_LIMIT:
        raise ValueError("incomplete/oversized control frame")
    value = strict_json_loads(raw)
    if type(value) is not dict:
        raise ValueError("control object required")
    return value


def verify_reply(reply, *, nonce, child_pid, sequence, command):
    if set(reply) != {"schema_version", "nonce", "child_pid", "sequence", "command", "payload", "error"}:
        raise ValueError("control reply fields differ")
    if reply["schema_version"] != 1 or reply["nonce"] != nonce or type(reply["child_pid"]) is not int or reply["child_pid"] != child_pid:
        raise ValueError("control reply belongs to a different child/session")
    if type(reply["sequence"]) is not int or reply["sequence"] != sequence or reply["command"] != command:
        raise ValueError("stale or misattributed control reply")
    if reply["error"] is not None:
        from .backend import BackendUnavailable

        if reply["error"] == "unavailable":
            raise BackendUnavailable("genuine core control unavailable")
        raise ValueError("core control did not complete")
    if not isinstance(reply["payload"], dict):
        raise ValueError("control payload object required")
    return reply["payload"]


class InheritedControl:
    def __init__(self, request):
        request.require_activation()
        self.nonce = secrets.token_hex(24)
        self.timeout = request.timeout_seconds
        self.reader_file = None
        self.to_child_read = self.to_child_write = None
        self.from_child_read = self.from_child_write = None
        try:
            self.to_child_read, self.to_child_write = os.pipe()
            self.from_child_read, self.from_child_write = os.pipe()
        except BaseException:
            self.close()
            raise
        self.sequence = 0
        self.child_pid = None
        self.failed = False
        self.lock = threading.Lock()
        self.inbox = queue.Queue(maxsize=64)

    def child_arguments(self):
        reads, writes = self.to_child_read, self.from_child_write
        os.set_inheritable(reads, True)
        os.set_inheritable(writes, True)
        if os.name == "nt":
            import msvcrt

            read_handle, write_handle = msvcrt.get_osfhandle(reads), msvcrt.get_osfhandle(writes)
            startup = subprocess.STARTUPINFO()
            startup.lpAttributeList = {"handle_list": [read_handle, write_handle]}
            options = {"startupinfo": startup, "close_fds": True}
            kind = "windows-handle"
        else:
            read_handle, write_handle = reads, writes
            options = {"pass_fds": (reads, writes), "close_fds": True}
            kind = "posix-fd"
        return ["--control-kind", kind, "--control-read", str(read_handle),
                "--control-write", str(write_handle), "--control-nonce", self.nonce], options

    def bind(self, process):
        self.child_pid = process.pid
        self._close_fd("to_child_read")
        self._close_fd("from_child_write")
        self.reader_file = os.fdopen(self.from_child_read, "rb", buffering=0)
        self.from_child_read = None
        threading.Thread(target=self._read, daemon=True).start()
        # The child imports its SDK and prepares its broker before serving the
        # identity request. Give bootstrap its own bounded allowance; subsequent
        # controls and tool execution retain the admitted request deadline.
        call_timeout = self.timeout
        try:
            self.timeout = CONTROL_STARTUP_SECONDS
            identity = self.request("identity")
        finally:
            self.timeout = call_timeout
        if identity.get("child_pid") != process.pid or not identity.get("server_instance_id"):
            raise ValueError("host identity does not bind to owned child/server")
        self.identity = identity

    def _read(self):
        try:
            for _ in range(64):
                raw = self.reader_file.readline(CONTROL_LIMIT + 1)
                if not raw:
                    raise EOFError("control child exited")
                self.inbox.put_nowait(unpack(raw))
        except (OSError, EOFError, ValueError, queue.Full) as exc:
            try:
                self.inbox.put_nowait(exc)
            except queue.Full:
                pass

    def request(self, command, **arguments):
        if command not in COMMANDS or self.failed or self.child_pid is None:
            raise ValueError("invalid or unavailable bound control channel")
        with self.lock:
            self.sequence += 1
            frame = pack({"schema_version": 1, "nonce": self.nonce, "sequence": self.sequence,
                          "command": command, "arguments": arguments})
            if len(frame) > 4096:
                raise ValueError("control request argument cap")
            completed = threading.Event()
            errors = []

            def write():
                try:
                    view = memoryview(frame)
                    while view:
                        count = os.write(self.to_child_write, view)
                        if count <= 0:
                            raise OSError("short control write")
                        view = view[count:]
                except (OSError, ValueError) as exc:
                    errors.append(exc)
                finally:
                    completed.set()

            threading.Thread(target=write, daemon=True).start()
            try:
                if not completed.wait(self.timeout):
                    raise TimeoutError("control write deadline")
                if errors:
                    raise errors[0]
                reply = self.inbox.get(timeout=self.timeout)
                if isinstance(reply, BaseException):
                    raise reply
                return verify_reply(reply, nonce=self.nonce, child_pid=self.child_pid,
                                    sequence=self.sequence, command=command)
            except BaseException:
                self.failed = True
                raise

    def hold_execution(self):
        return self.request("hold_execution")

    def release_execution(self):
        return self.request("release_execution")

    def wait_for_occupancy(self, *, active, queued, timeout):
        return self.request("wait_for_occupancy", active=active, queued=queued, timeout=timeout)

    def wait_for_cancellation(self, request_id, *, timeout):
        return self.request("wait_for_cancellation", request_id=request_id, timeout=timeout)

    def observe(self):
        return self.request("observe")

    def exercise(self, hook, request_id=None, payload=None):
        return self.request("exercise", hook=hook, request_id=request_id, payload=payload)

    def _close_fd(self, name):
        descriptor = getattr(self, name, None)
        if descriptor is not None:
            setattr(self, name, None)
            os.close(descriptor)

    def close(self):
        errors = []
        for name in ("to_child_read", "to_child_write", "from_child_read", "from_child_write"):
            try:
                self._close_fd(name)
            except OSError as exc:
                errors.append(exc)
        if self.reader_file is not None:
            reader = self.reader_file
            self.reader_file = None
            try:
                reader.close()
            except OSError as exc:
                errors.append(exc)
        if errors:
            raise OSError("owned control teardown incomplete") from errors[0]


def open_child_streams(kind, read_handle, write_handle):
    if kind == "windows-handle" and os.name == "nt":
        import msvcrt

        read_handle = msvcrt.open_osfhandle(read_handle, os.O_RDONLY | os.O_BINARY)
        write_handle = msvcrt.open_osfhandle(write_handle, os.O_WRONLY | os.O_BINARY)
    elif kind != "posix-fd" or os.name == "nt":
        raise ValueError("inherited control handle kind differs from platform")
    return os.fdopen(read_handle, "rb", buffering=0), os.fdopen(write_handle, "wb", buffering=0)
