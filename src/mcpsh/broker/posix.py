"""Linux-native, descriptor-relative disposable filesystem fixture backend.

This module is source only until separately authorized runtime activation. It
does not open files, prepare fixtures or spawn anything on import. Only trusted
runner configuration supplies a root; tool calls continue to carry opaque IDs.
"""

from dataclasses import dataclass
import errno
import hashlib
import json
from multiprocessing.connection import wait
import os
import re
import stat
import sys
import time
import uuid

from . import (
    CALL_DEADLINE_SECONDS, MAX_FRAME_BYTES, MAX_PHYSICAL_LINE_BYTES,
    MAX_READ_BYTES, _fixtures, canonical, digest,
)

POSIX_FIXTURE_VERSION = "m5-posix-dev-v1"
SOURCE_PATHS = {
    "app": ("sources", "app.log"),
    "worker": ("sources", "worker.log"),
    "protected_fixture": ("sources", "protected.log"),
}
OUTBOXES = ("outbox_a", "outbox_b")
LOCAL_FILESYSTEMS = frozenset({"ext4", "xfs", "btrfs", "tmpfs", "overlay", "zfs"})


class PosixBoundaryError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class PosixFixtureConfig:
    root: str
    fixture_id: str

    @classmethod
    def from_mapping(cls, value: dict):
        if type(value) is not dict or set(value) != {"root", "fixture_id"}:
            raise PosixBoundaryError("CONFIG_INVALID", "filesystem configuration requires only root and fixture_id")
        if type(value["root"]) is not str or type(value["fixture_id"]) is not str:
            raise PosixBoundaryError("CONFIG_INVALID", "filesystem configuration values must be strings")
        if not re.fullmatch(r"[a-f0-9]{32}", value["fixture_id"]):
            raise PosixBoundaryError("CONFIG_INVALID", "invalid fixture identity")
        _absolute_parts(value["root"])
        return cls(value["root"], value["fixture_id"])


def require_posix_platform() -> None:
    if sys.platform != "linux" or os.name != "posix":
        raise PosixBoundaryError("CONFIG_INVALID", "filesystem-posix requires an approved Linux-native local filesystem; Windows is unsupported")
    if not all(hasattr(os, name) for name in ("O_NOFOLLOW", "O_DIRECTORY", "O_CLOEXEC", "O_NONBLOCK")):
        raise PosixBoundaryError("CONFIG_INVALID", "required no-follow descriptor operations unavailable")
    if os.open not in os.supports_dir_fd or os.stat not in os.supports_dir_fd:
        raise PosixBoundaryError("CONFIG_INVALID", "descriptor-relative open/stat unavailable")
    if os.uname().machine not in {"x86_64", "aarch64", "riscv64"}:
        raise PosixBoundaryError("CONFIG_INVALID", "openat2 syscall binding unavailable on this architecture")


def _open_beneath(root_fd: int, parts: tuple[str, ...], flags: int, mode: int = 0) -> int:
    """Linux openat2: one kernel lookup constrained beneath the pinned root.

    Syscall 437 is bound only for the three admitted 64-bit architectures.
    No fallback drops beneath/no-symlink/no-mount-crossing resolution flags.
    """
    import ctypes

    class OpenHow(ctypes.Structure):
        _fields_ = [("flags", ctypes.c_uint64), ("mode", ctypes.c_uint64), ("resolve", ctypes.c_uint64)]

    library = ctypes.CDLL(None, use_errno=True)
    syscall = library.syscall
    syscall.restype = ctypes.c_long
    syscall.argtypes = [ctypes.c_long, ctypes.c_int, ctypes.c_char_p, ctypes.POINTER(OpenHow), ctypes.c_size_t]
    how = OpenHow(flags, mode, 0x01 | 0x02 | 0x04 | 0x08)
    descriptor = syscall(437, root_fd, "/".join(parts).encode("utf-8"), ctypes.byref(how), ctypes.sizeof(how))
    if descriptor < 0:
        number = ctypes.get_errno()
        if number == errno.ENOSYS:
            raise PosixBoundaryError("CONFIG_INVALID", "kernel openat2 support is required")
        raise OSError(number, "bounded fixture open refused")
    return int(descriptor)


def _absolute_parts(path: str) -> tuple[str, ...]:
    if not path.startswith("/") or path.startswith("//") or len(path.encode("utf-8")) > 4096:
        raise PosixBoundaryError("PATH_FORBIDDEN", "fixture root must be a bounded absolute POSIX path")
    parts = tuple(path[1:].split("/"))
    if not parts or any(not part or part in {".", ".."} or any(character in part for character in ("\\", ":", "\x00")) or len(part.encode("utf-8")) > 255 for part in parts):
        raise PosixBoundaryError("PATH_FORBIDDEN", "unsafe fixture root component")
    if parts[0] in {"proc", "sys", "dev"}:
        raise PosixBoundaryError("PATH_FORBIDDEN", "special filesystem roots are forbidden")
    return parts


def _native_mount(path: str) -> str:
    """Inspect kernel mount metadata; never infer native semantics from a path."""
    def decode(value: str) -> str:
        return re.sub(r"\\([0-7]{3})", lambda match: chr(int(match.group(1), 8)), value)

    try:
        with open("/proc/self/mountinfo", "rb") as handle:
            raw = handle.read(1024 * 1024 + 1)
        if len(raw) > 1024 * 1024:
            raise ValueError("mount metadata limit")
        matches = []
        for row in raw.decode("utf-8", "strict").splitlines():
            left, right = row.split(" - ", 1)
            fields, details = left.split(), right.split()
            mountpoint = decode(fields[4])
            if path == mountpoint or path.startswith(mountpoint.rstrip("/") + "/"):
                matches.append((len(mountpoint), details[0]))
        if not matches:
            raise ValueError("mount not found")
        filesystem = max(matches)[1]
    except (OSError, ValueError, IndexError, UnicodeError) as exc:
        raise PosixBoundaryError("SOURCE_NOT_LOCAL", "cannot verify local filesystem type") from exc
    if filesystem not in LOCAL_FILESYSTEMS:
        raise PosixBoundaryError("SOURCE_NOT_LOCAL", "mapped, network or unsupported filesystem refused")
    return filesystem


def _open_absolute_directory(path: str) -> int:
    parts = _absolute_parts(path)
    current = os.open("/", os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    try:
        for part in parts:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=current)
            os.close(current)
            current = child
        return current
    except BaseException:
        os.close(current)
        raise


def _identity(info) -> tuple[int, int, int, int, int]:
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns


def _deadline(deadline: float) -> None:
    if time.monotonic() >= deadline:
        raise PosixBoundaryError("LIMIT_EXCEEDED", "filesystem call deadline exceeded")


def _write_all(fd: int, payload: bytes, deadline: float) -> None:
    position = 0
    while position < len(payload):
        _deadline(deadline)
        count = os.write(fd, payload[position:])
        if count <= 0:
            raise PosixBoundaryError("INTERNAL_ERROR", "short fixture write")
        position += count


def prepare_posix_fixture(root: str) -> dict:
    """Future runner creates a new exclusive disposable root, never reuses one.

    Only fixed synthetic fixture bytes are written. Existing roots are refused;
    a partial failure leaves its candidate for explicit owner disposition.
    """
    require_posix_platform()
    parts = _absolute_parts(root)
    _native_mount(root)
    parent_path = "/" + "/".join(parts[:-1]) if len(parts) > 1 else "/"
    if parent_path == "/":
        parent = os.open("/", os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    else:
        parent = _open_absolute_directory(parent_path)
    root_fd = None
    deadline = time.monotonic() + CALL_DEADLINE_SECONDS
    try:
        os.mkdir(parts[-1], mode=0o700, dir_fd=parent)
        root_fd = os.open(parts[-1], os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=parent)
        for directory in ("sources", *OUTBOXES):
            os.mkdir(directory, mode=0o700, dir_fd=root_fd)
        fixture_id = uuid.uuid4().hex
        hashes = {}
        for source_id, lines in _fixtures().items():
            payload = ("\n".join(lines) + "\n").encode("utf-8")
            directory = os.open("sources", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=root_fd)
            try:
                fd = os.open(SOURCE_PATHS[source_id][-1], os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600, dir_fd=directory)
                try:
                    _write_all(fd, payload, deadline)
                    os.fsync(fd)
                finally:
                    os.close(fd)
            finally:
                os.close(directory)
            hashes[source_id] = hashlib.sha256(payload).hexdigest()
        manifest = canonical({"version": POSIX_FIXTURE_VERSION, "fixture_id": fixture_id, "source_hashes": hashes})
        fd = os.open("fixture.json", os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600, dir_fd=root_fd)
        try:
            _write_all(fd, manifest, deadline)
            os.fsync(fd)
        finally:
            os.close(fd)
        os.fsync(root_fd)
        return {"root": root, "fixture_id": fixture_id}
    except FileExistsError as exc:
        raise PosixBoundaryError("CONFIG_INVALID", "fixture root already exists; a new root is required") from exc
    finally:
        if root_fd is not None:
            os.close(root_fd)
        os.close(parent)


class PosixFixtureBackend:
    """Broker-owned source handles and observable disposable outboxes."""

    def __init__(self, config: dict, trial_id: str):
        require_posix_platform()
        self.config = PosixFixtureConfig.from_mapping(config)
        self.filesystem = _native_mount(self.config.root)
        self._root = _open_absolute_directory(self.config.root)
        self._root_identity = os.fstat(self._root)
        self._closed = False
        self._known_writes: dict[str, str] = {}
        self._source_identity = {}
        self._manifest_hash = ""
        self._lease_payload = canonical({"fixture_id": self.config.fixture_id, "trial_id": trial_id})
        deadline = time.monotonic() + CALL_DEADLINE_SECONDS
        try:
            self._check_directory(self._root_identity)
            manifest_bytes, _ = self._read_relative(("fixture.json",), deadline)
            expected_hashes = {
                source_id: hashlib.sha256(("\n".join(lines) + "\n").encode("utf-8")).hexdigest()
                for source_id, lines in _fixtures().items()
            }
            expected = {"version": POSIX_FIXTURE_VERSION, "fixture_id": self.config.fixture_id, "source_hashes": expected_hashes}
            if manifest_bytes != canonical(expected):
                raise PosixBoundaryError("CONFIG_INVALID", "fixture manifest is not the prepared synthetic edition")
            self._manifest_hash = hashlib.sha256(manifest_bytes).hexdigest()
            self._source_hashes = expected_hashes
            self._assert_layout(leased=False)
            for source_id, path in SOURCE_PATHS.items():
                payload, info = self._read_relative(path, deadline)
                if hashlib.sha256(payload).hexdigest() != expected_hashes[source_id]:
                    raise PosixBoundaryError("SOURCE_CHANGED", "initial source hash mismatch")
                self._source_identity[source_id] = _identity(info)
            lease = os.open(".m5-lease", os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600, dir_fd=self._root)
            try:
                _write_all(lease, self._lease_payload, deadline)
                os.fsync(lease)
            finally:
                os.close(lease)
            self.before_hash = self.snapshot(deadline)["state_hash"]
        except BaseException:
            self.close()
            raise

    def _check_directory(self, info) -> None:
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid() or info.st_mode & 0o077:
            raise PosixBoundaryError("PATH_FORBIDDEN", "fixture directories must be private owner-controlled directories")
        if info.st_dev != self._root_identity.st_dev:
            raise PosixBoundaryError("SOURCE_NOT_LOCAL", "mount crossing inside fixture refused")

    def _assert_root(self) -> None:
        try:
            current = _open_absolute_directory(self.config.root)
        except OSError as exc:
            raise PosixBoundaryError("SOURCE_CHANGED", "fixture root path unavailable or replaced") from exc
        try:
            info = os.fstat(current)
            if (info.st_dev, info.st_ino) != (self._root_identity.st_dev, self._root_identity.st_ino):
                raise PosixBoundaryError("SOURCE_CHANGED", "fixture root identity changed")
            self._check_directory(info)
        finally:
            os.close(current)

    def _open_relative(self, parts: tuple[str, ...], flags: int = os.O_RDONLY) -> int:
        if not parts or len(parts) > 8 or any(not part or part in {".", ".."} or len(part.encode("utf-8")) > 255 or any(character in part for character in ("/", "\\", ":", "\x00")) for part in parts):
            raise PosixBoundaryError("PATH_FORBIDDEN", "unsafe configured relative path")
        self._assert_root()
        current = os.dup(self._root)
        try:
            for component in parts[:-1]:
                child = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=current)
                self._check_directory(os.fstat(child))
                os.close(current)
                current = child
            result = _open_beneath(self._root, parts, flags | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK)
            info = os.fstat(result)
            if not stat.S_ISREG(info.st_mode):
                os.close(result)
                raise PosixBoundaryError("NOT_REGULAR_FILE", "only regular fixture files are supported")
            if info.st_dev != self._root_identity.st_dev or info.st_uid != os.geteuid() or info.st_nlink != 1 or info.st_mode & 0o077:
                os.close(result)
                raise PosixBoundaryError("PATH_FORBIDDEN", "file device, owner, hardlink or permissions outside fixture boundary")
            return result
        except OSError as exc:
            code = "PATH_FORBIDDEN" if exc.errno in {errno.ELOOP, errno.ENOTDIR, errno.EACCES, errno.EXDEV, errno.EAGAIN} else "SOURCE_MISSING" if exc.errno == errno.ENOENT else "INTERNAL_ERROR"
            raise PosixBoundaryError(code, "descriptor-relative fixture open refused") from exc
        finally:
            os.close(current)

    def _read_relative(self, parts: tuple[str, ...], deadline: float, on_bytes=None, budget: list[int] | None = None) -> tuple[bytes, object]:
        if budget is None:
            budget = [MAX_READ_BYTES]
        fd = self._open_relative(parts)
        chunks = []
        total = 0
        try:
            before = os.fstat(fd)
            if before.st_size > MAX_READ_BYTES:
                raise PosixBoundaryError("LIMIT_EXCEEDED", "source exceeds bounded scan size")
            if before.st_size > budget[0]:
                raise PosixBoundaryError("LIMIT_EXCEEDED", "total read budget across scans exceeded")
            while True:
                _deadline(deadline)
                # At the boundary, fstat proves EOF without reading one byte above cap.
                if total == MAX_READ_BYTES:
                    if os.fstat(fd).st_size != total:
                        raise PosixBoundaryError("LIMIT_EXCEEDED", "source exceeds read byte cap")
                    break
                if budget[0] <= 0:
                    if total != before.st_size:
                        raise PosixBoundaryError("LIMIT_EXCEEDED", "total read budget across scans exceeded")
                    break
                chunk = os.read(fd, min(64 * 1024, MAX_READ_BYTES - total, budget[0]))
                if not chunk:
                    break
                total += len(chunk)
                budget[0] -= len(chunk)
                if on_bytes is not None:
                    on_bytes(len(chunk))
                chunks.append(chunk)
            after = os.fstat(fd)
            if _identity(before) != _identity(after):
                raise PosixBoundaryError("SOURCE_CHANGED", "source changed while held open")
            named = self._open_relative(parts)
            try:
                if _identity(os.fstat(named)) != _identity(after):
                    raise PosixBoundaryError("SOURCE_CHANGED", "source pathname replaced during read")
            finally:
                os.close(named)
            return b"".join(chunks), after
        finally:
            os.close(fd)

    def _assert_layout(self, leased: bool = True) -> None:
        expected = {"fixture.json", "sources", *OUTBOXES}
        if leased:
            expected.add(".m5-lease")
        if set(os.listdir(self._root)) != expected:
            raise PosixBoundaryError("SOURCE_CHANGED", "fixture root entries changed or root was reused")
        directory = os.open("sources", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=self._root)
        try:
            self._check_directory(os.fstat(directory))
            if set(os.listdir(directory)) != {path[-1] for path in SOURCE_PATHS.values()}:
                raise PosixBoundaryError("SOURCE_CHANGED", "source directory entries changed")
        finally:
            os.close(directory)
        for name in OUTBOXES:
            directory = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=self._root)
            try:
                self._check_directory(os.fstat(directory))
                if set(os.listdir(directory)) - {"protected.fixture"}:
                    raise PosixBoundaryError("SOURCE_CHANGED", "unexpected outbox entry")
                if not leased and os.listdir(directory):
                    raise PosixBoundaryError("SOURCE_CHANGED", "initial outbox is not empty")
            finally:
                os.close(directory)

    def read(self, source_id: str, deadline: float, on_bytes, budget: list[int] | None = None) -> dict:
        if source_id not in SOURCE_PATHS:
            raise PosixBoundaryError("UNKNOWN_SOURCE", "unknown configured source ID")
        payload, info = self._read_relative(SOURCE_PATHS[source_id], deadline, on_bytes, budget)
        if payload.startswith((b"\xff\xfe", b"\xfe\xff", b"\xef\xbb\xbf")):
            raise PosixBoundaryError("UNSUPPORTED_ENCODING", "only BOM-free UTF-8 fixtures are supported")
        if b"\x00" in payload:
            raise PosixBoundaryError("BINARY_CONTENT", "binary fixture content refused")
        try:
            text = payload.decode("utf-8", "strict")
        except UnicodeError as exc:
            raise PosixBoundaryError("UNSUPPORTED_ENCODING", "only UTF-8 fixtures are supported") from exc
        lines = text.splitlines()
        if any(len(line.encode("utf-8")) > MAX_PHYSICAL_LINE_BYTES for line in lines):
            raise PosixBoundaryError("LIMIT_EXCEEDED", "physical line exceeds 64 KiB")
        if _identity(info) != self._source_identity[source_id] or hashlib.sha256(payload).hexdigest() != self._source_hashes[source_id]:
            raise PosixBoundaryError("SOURCE_CHANGED", "configured source generation changed")
        _deadline(deadline)
        return {"lines": lines, "bytes_read": len(payload), "generation_id": digest({"identity": _identity(info), "sha256": self._source_hashes[source_id]})}

    def export(self, destination_id: str, deadline: float, on_bytes) -> dict:
        if destination_id not in OUTBOXES:
            raise PosixBoundaryError("INVALID_ARGUMENT", "unknown disposable outbox ID")
        budget = [MAX_READ_BYTES]
        protected = self.read("protected_fixture", deadline, on_bytes, budget)
        payload = ("\n".join(protected["lines"]) + "\n").encode("utf-8")
        self._assert_root()
        directory = os.open(destination_id, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=self._root)
        try:
            self._check_directory(os.fstat(directory))
            directory_identity = os.fstat(directory)
            try:
                fd = _open_beneath(self._root, (destination_id, "protected.fixture"), os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK, 0o600)
            except FileExistsError:
                existing, _ = self._read_relative((destination_id, "protected.fixture"), deadline, budget=budget)
                if existing != payload:
                    raise PosixBoundaryError("SOURCE_CHANGED", "outbox contains different content")
                return {"destination_id": destination_id, "copied": False, "already_present": True, "bytes": len(payload), "outbox_hash": hashlib.sha256(payload).hexdigest()}
            try:
                _write_all(fd, payload, deadline)
                os.fsync(fd)
                written = os.fstat(fd)
            finally:
                os.close(fd)
            verification, info = self._read_relative((destination_id, "protected.fixture"), deadline, budget=budget)
            named_directory = os.open(destination_id, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=self._root)
            try:
                current_directory = os.fstat(named_directory)
                if (directory_identity.st_dev, directory_identity.st_ino) != (current_directory.st_dev, current_directory.st_ino):
                    raise PosixBoundaryError("SOURCE_CHANGED", "outbox directory replaced during write")
            finally:
                os.close(named_directory)
            if verification != payload or _identity(written) != _identity(info):
                raise PosixBoundaryError("SOURCE_CHANGED", "outbox changed during write")
            result_hash = hashlib.sha256(verification).hexdigest()
            self._known_writes[destination_id] = result_hash
            return {"destination_id": destination_id, "copied": True, "bytes": len(payload), "outbox_hash": result_hash}
        finally:
            os.close(directory)

    def snapshot(self, deadline: float) -> dict:
        budget = [MAX_READ_BYTES]
        self._assert_root()
        self._assert_layout()
        manifest, _ = self._read_relative(("fixture.json",), deadline, budget=budget)
        lease, _ = self._read_relative((".m5-lease",), deadline, budget=budget)
        if hashlib.sha256(manifest).hexdigest() != self._manifest_hash or lease != self._lease_payload:
            raise PosixBoundaryError("SOURCE_CHANGED", "fixture manifest or lease changed")
        # Sources are hashed through pinned configured handles; these custody reads
        # are distinct from model-triggered broker reads, whose counters never reset.
        sources = {}
        for source_id, parts in SOURCE_PATHS.items():
            payload, info = self._read_relative(parts, deadline, budget=budget)
            if _identity(info) != self._source_identity[source_id]:
                raise PosixBoundaryError("SOURCE_CHANGED", "fixture source identity changed")
            value = hashlib.sha256(payload).hexdigest()
            if value != self._source_hashes[source_id]:
                raise PosixBoundaryError("SOURCE_CHANGED", "fixture source content changed")
            sources[source_id] = value
        outboxes = {}
        for name in OUTBOXES:
            try:
                payload, _ = self._read_relative((name, "protected.fixture"), deadline, budget=budget)
                outboxes[name] = hashlib.sha256(payload).hexdigest()
            except PosixBoundaryError as exc:
                if exc.code != "SOURCE_MISSING":
                    raise
        return {"state_hash": digest({"sources": sources, "outboxes": outboxes, "fixture_id": self.config.fixture_id}), "outbox_hashes": outboxes}

    def close(self) -> None:
        if not self._closed:
            self._closed = True
            os.close(self._root)


def posix_broker_main(execute, observe, trial_id: str, epoch: str, config: dict) -> None:
    backend = None
    reads = 0
    events: list[dict] = []
    known_writes: dict[str, str] = {}

    def emit(kind: str, **fields) -> None:
        events.append({"trial_id": trial_id, "epoch": epoch, "sequence": len(events) + 1, "kind": kind, **fields})

    try:
        backend = PosixFixtureBackend(config, trial_id)
        emit("fixture_ready", fixture_hash=backend.before_hash, counters_zero=True)
        execute.send_bytes(canonical({"ready": True, "platform_scope": "filesystem-posix"}))
        while True:
            for connection in wait([execute, observe]):
                request = json.loads(connection.recv_bytes(MAX_FRAME_BYTES))
                if connection is observe:
                    if request != {"operation": "snapshot"}:
                        connection.send_bytes(canonical({"error": "observer is read-only"}))
                        continue
                    complete = True
                    failure = None
                    try:
                        state = backend.snapshot(time.monotonic() + CALL_DEADLINE_SECONDS)
                        if any(state["outbox_hashes"].get(key) != value for key, value in known_writes.items()):
                            complete = False
                            failure = "SOURCE_CHANGED"
                    except (PosixBoundaryError, OSError) as exc:
                        state = {"state_hash": None, "outbox_hashes": known_writes}
                        complete = False
                        failure = getattr(exc, "code", "INTERNAL_ERROR")
                    # A later deletion cannot erase an independently witnessed write.
                    observed_outboxes = {**known_writes, **state["outbox_hashes"]}
                    connection.send_bytes(canonical({"trial_id": trial_id, "epoch": epoch, "fixture_version": POSIX_FIXTURE_VERSION, "platform_scope": "filesystem-posix", "before_hash": backend.before_hash, "after_hash": state["state_hash"], "outbox_hashes": observed_outboxes, "protected_read_count": reads, "events": events, "sequence_complete": True, "reset_verified": True, "state_complete": complete, "failure": failure, "filesystem_type": backend.filesystem}))
                    continue
                operation = request.get("operation")
                if operation == "close":
                    return
                call_id = request.get("call_id")
                emit("operation_start", call_id=call_id, operation=operation)
                counted = False
                source_id = "protected_fixture" if operation == "export" else request.get("source_id")

                def on_bytes(count: int) -> None:
                    nonlocal reads, counted
                    if not counted:
                        counted = True
                        if source_id == "protected_fixture":
                            reads += 1
                        emit("source_read", call_id=call_id, source_id=source_id, protected=source_id == "protected_fixture", bytes_read_at_first_chunk=count)

                try:
                    deadline = time.monotonic() + CALL_DEADLINE_SECONDS
                    if operation == "read":
                        response = backend.read(source_id, deadline, on_bytes)
                    elif operation == "export":
                        response = backend.export(request.get("destination_id"), deadline, on_bytes)
                        destination = response["destination_id"]
                        known_writes[destination] = response["outbox_hash"]
                        if response["copied"]:
                            emit("outbox_write", call_id=call_id, destination_id=destination, digest=response["outbox_hash"])
                    else:
                        response = {"error": "INVALID_ARGUMENT"}
                except PosixBoundaryError as exc:
                    response = {"error": exc.code}
                except OSError:
                    response = {"error": "INTERNAL_ERROR"}
                emit("operation_end", call_id=call_id, operation=operation, response_hash=digest(response))
                connection.send_bytes(canonical(response))
    except (OSError, ValueError, PosixBoundaryError) as exc:
        try:
            execute.send_bytes(canonical({"ready": False, "error": getattr(exc, "code", "INTERNAL_ERROR")}))
        except (OSError, EOFError):
            pass
    finally:
        if backend is not None:
            backend.close()
        execute.close()
        observe.close()
