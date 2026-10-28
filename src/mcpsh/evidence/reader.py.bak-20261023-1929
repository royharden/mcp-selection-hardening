"""Read immutable local evidence only on explicit invocation. Never runs a model."""

from dataclasses import dataclass
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import stat

from mcpsh.records import typed_hash

from .models import EditionAuthority, EditionIndex, EvidenceTrial, ExperimentManifest, ObserverRecord, OraclePackage, RawObservation

MAX_INDEX_BYTES = 128 * 1024
MAX_TOTAL_BYTES = 64 * 1024 * 1024
MAX_LINE_BYTES = 1024 * 1024


class EvidenceRejected(ValueError):
    """Structural rejection; no empirical/product verdict is implied."""


def strict_json(raw: bytes):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise EvidenceRejected("duplicate JSON key")
            result[key] = value
        return result

    def invalid(_):
        raise EvidenceRejected("nonfinite JSON number")

    def number(value):
        parsed = float(value)
        return parsed if math.isfinite(parsed) else invalid(value)

    try:
        value = json.loads(raw, object_pairs_hook=pairs, parse_constant=invalid, parse_float=number)
        pending = [(value, 0)]
        count = 0
        while pending:
            item, depth = pending.pop()
            count += 1
            if depth > 48 or count > 100000:
                raise EvidenceRejected("JSON structural cap exceeded")
            if isinstance(item, (str, bytes)) and len(item.encode() if isinstance(item, str) else item) > MAX_LINE_BYTES:
                raise EvidenceRejected("JSON string cap exceeded")
            if isinstance(item, dict):
                pending.extend((nested, depth + 1) for nested in item.values())
                pending.extend((key, depth + 1) for key in item)
            elif isinstance(item, list):
                pending.extend((nested, depth + 1) for nested in item)
        return value
    except (ValueError, UnicodeError, RecursionError) as error:
        raise EvidenceRejected("invalid or unbounded strict JSON: " + type(error).__name__) from None


def model(model_type, value):
    try:
        # JSON mode preserves strict tuple handling without coercing JSON number types.
        return model_type.model_validate_json(json.dumps(value, ensure_ascii=True, allow_nan=False))
    except (ValueError, TypeError, RecursionError):
        raise EvidenceRejected("closed evidence schema mismatch: " + model_type.__name__) from None


def relative_parts(name: str) -> tuple[str, ...]:
    if not isinstance(name, str) or not name or len(name) > 256 or "\\" in name or ":" in name or "\x00" in name:
        raise EvidenceRejected("invalid bounded relative artifact path")
    parts = tuple(name.split("/"))
    if any(part in {"", ".", ".."} or part.endswith((".", " ")) for part in parts):
        raise EvidenceRejected("artifact path traversal or ambiguous component")
    if PurePosixPath(name).is_absolute() or PureWindowsPath(name).drive:
        raise EvidenceRejected("absolute artifact path")
    reserved = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}
    if any(part.split(".")[0].upper() in reserved for part in parts):
        raise EvidenceRejected("reserved device artifact path")
    return parts


def _plain(path: Path, *, directory: bool):
    info = path.lstat()
    if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
        raise EvidenceRejected("symlinks/reparse points are not evidence artifacts")
    if not (stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode)):
        raise EvidenceRejected("artifact is not a regular file/directory")
    return info


def read_bounded(root: Path, name: str, maximum: int) -> bytes:
    """No-follow descriptor walk on POSIX; reject reparse/symlink paths on Windows.

    Windows fallback requires externally immutable custody; it does not claim race
    conformance. No runtime/filesystem claim follows from these authored checks.
    """
    parts = relative_parts(name)
    absolute = root.absolute()
    descriptors = []
    try:
        current = Path(absolute.anchor)
        for component in absolute.parts[1:]:
            current = current / component
            _plain(current, directory=True)
        if os.open in os.supports_dir_fd and hasattr(os, "O_NOFOLLOW"):
            descriptor = os.open(absolute.anchor, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            descriptors.append(descriptor)
            for component in absolute.parts[1:]:
                descriptor = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=descriptor)
                descriptors.append(descriptor)
            for component in parts[:-1]:
                descriptor = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=descriptor)
                descriptors.append(descriptor)
            descriptor = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW, dir_fd=descriptor)
        else:
            current = absolute
            parent_identities = []
            for component in parts[:-1]:
                current = current / component
                info = _plain(current, directory=True)
                parent_identities.append((current, info.st_dev, info.st_ino))
            target = current / parts[-1]
            before = _plain(target, directory=False)
            descriptor = os.open(target, os.O_RDONLY | getattr(os, "O_BINARY", 0))
        descriptors.append(descriptor)
        opened = os.fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode) or opened.st_size > maximum:
            raise EvidenceRejected("artifact type/byte cap exceeded")
        if not (os.open in os.supports_dir_fd and hasattr(os, "O_NOFOLLOW")):
            after = _plain(target, directory=False)
            if (before.st_dev, before.st_ino) != (opened.st_dev, opened.st_ino) or (after.st_dev, after.st_ino) != (opened.st_dev, opened.st_ino):
                raise EvidenceRejected("artifact changed during open")
            for parent, device, inode in parent_identities:
                check = _plain(parent, directory=True)
                if (check.st_dev, check.st_ino) != (device, inode):
                    raise EvidenceRejected("artifact parent changed during open")
        chunks, length = [], 0
        while length <= maximum:
            chunk = os.read(descriptor, min(65536, maximum + 1 - length))
            if not chunk:
                break
            chunks.append(chunk)
            length += len(chunk)
        if length > maximum or os.fstat(descriptor).st_size != opened.st_size:
            raise EvidenceRejected("artifact exceeded bound or changed during read")
        return b"".join(chunks)
    except OSError as error:
        raise EvidenceRejected("artifact unavailable/unsafe: " + type(error).__name__) from None
    finally:
        for descriptor in reversed(descriptors):
            os.close(descriptor)


def jsonl(raw: bytes, model_type, maximum: int):
    lines = raw.splitlines()
    if not 1 <= len(lines) <= maximum or any(not line or len(line) > MAX_LINE_BYTES for line in lines):
        raise EvidenceRejected("JSONL row count/line bounds exceeded")
    return tuple(model(model_type, strict_json(line)) for line in lines)


@dataclass(frozen=True)
class VerifiedEdition:
    """Immutable bytes are revalidated before reproduction; no mutable cached truth."""
    authority: EditionAuthority
    index_bytes: bytes
    artifacts: tuple[tuple[str, bytes], ...]

    def validate(self):
        if len(dict(self.artifacts)) != len(self.artifacts):
            raise EvidenceRejected("duplicate in-memory artifact role")
        return validate_bundle(self.authority, self.index_bytes, dict(self.artifacts))


def validate_index(authority: EditionAuthority, raw: bytes) -> EditionIndex:
    if len(raw) > MAX_INDEX_BYTES or hashlib.sha256(raw).hexdigest() != authority.index_sha256:
        raise EvidenceRejected("index differs from externally approved byte pin")
    parsed = strict_json(raw)
    if not isinstance(parsed, dict) or type(parsed.get("schema_version")) is not int:
        raise EvidenceRejected("edition schema version must be an exact integer")
    index = model(EditionIndex, parsed)
    for key in ("revision", "edition_id", "candidate_commit", "mode", "platform_scope", "input_pins"):
        if getattr(index, key) != getattr(authority, key):
            raise EvidenceRejected("unbound edition revision/input identity: " + key)
    if index.manifest.sha256 != authority.manifest_sha256:
        raise EvidenceRejected("manifest differs from externally approved pin")
    for value in index.input_pins.model_dump().values():
        if value is not None and (len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value)):
            raise EvidenceRejected("invalid input digest")
    ids = index.scheduled_trial_ids
    if len(set(ids)) != len(ids) or any(not identifier or len(identifier) > 256 for identifier in ids):
        raise EvidenceRejected("duplicate/unbounded scheduled trial identity")
    pins = [getattr(index, role) for role in ("manifest", "trials", "observers", "oracles")]
    paths = [pin.path for pin in pins if pin is not None]
    if len(set(path.casefold() for path in paths)) != len(paths) or "EDITION.json".casefold() in {path.casefold() for path in paths}:
        raise EvidenceRejected("artifact roles alias one another or the index")
    if len(raw) + sum(pin.bytes for pin in pins if pin is not None) > MAX_TOTAL_BYTES:
        raise EvidenceRejected("total edition bytes exceed cap")
    for path in paths:
        relative_parts(path)
    return index


def validate_bundle(authority: EditionAuthority, raw_index: bytes, artifacts: dict[str, bytes]):
    index = validate_index(authority, raw_index)
    roles = {role: getattr(index, role) for role in ("manifest", "trials", "observers", "oracles")
             if getattr(index, role) is not None}
    if set(artifacts) != set(roles):
        raise EvidenceRejected("missing or extra bound artifact role")
    for role, pin in roles.items():
        raw = artifacts[role]
        if len(raw) != pin.bytes or hashlib.sha256(raw).hexdigest() != pin.sha256:
            raise EvidenceRejected("artifact byte/hash pin mismatch: " + role)
    manifest_value = strict_json(artifacts["manifest"])
    if not isinstance(manifest_value, dict) or type(manifest_value.get("schema_version")) is not int:
        raise EvidenceRejected("explicit integer manifest schema version required")
    manifest = model(ExperimentManifest, manifest_value)
    if any(getattr(manifest, key) != getattr(index, key) for key in ("edition_id", "mode", "platform_scope")):
        raise EvidenceRejected("mixed platform/mode/edition")
    if any(getattr(manifest, key) != value for key, value in index.input_pins.model_dump().items()):
        raise EvidenceRejected("manifest input pins differ from approved revision")
    trials = jsonl(artifacts["trials"], EvidenceTrial, 5000)
    if tuple(row.outcome.trial_id for row in trials) != index.scheduled_trial_ids:
        raise EvidenceRejected("trial order/cardinality differs from explicit schedule")
    observers = jsonl(artifacts["observers"], ObserverRecord, 5000) if "observers" in artifacts else ()
    if len({row.trial_id for row in observers}) != len(observers) or any(row.trial_id not in index.scheduled_trial_ids for row in observers):
        raise EvidenceRejected("duplicate/unbound observer trial")
    oracle_value = strict_json(artifacts["oracles"]) if "oracles" in artifacts else None
    if oracle_value is not None and (not isinstance(oracle_value, dict) or type(oracle_value.get("schema_version")) is not int):
        raise EvidenceRejected("oracle schema version must be an exact integer")
    oracles = model(OraclePackage, oracle_value) if oracle_value is not None else None
    if oracles is not None:
        if hashlib.sha256(artifacts["oracles"]).hexdigest() != manifest.split_hash:
            raise EvidenceRejected("oracle bytes differ from manifest seal")
        ids = [entry.public.task_id for entry in oracles.cases]
        if len(set(ids)) != len(ids) or any(entry.public.task_id != entry.oracle.task_id for entry in oracles.cases):
            raise EvidenceRejected("oracle/public task join is duplicated or inconsistent")
        if set(ids) != {row.outcome.task_id for row in trials}:
            raise EvidenceRejected("oracle/task coverage mismatch")
        if typed_hash([entry.public.model_dump(mode="json") for entry in oracles.cases]) != manifest.task_hash:
            raise EvidenceRejected("oracle public-task projection differs from pinned task corpus")
    _validate_links(index, manifest, trials, observers, index_sha256=authority.index_sha256)
    return index, manifest, trials, observers, oracles


def _validate_links(index, manifest, trials, observers, *, index_sha256):
    global_calls, global_attempts, global_selections = set(), set(), set()
    observed = {item.trial_id: item for item in observers}
    for row in trials:
        outcome = row.outcome
        for pin in (row.fixture_payload_hash, row.catalog_hash, row.normalization_diff_hash):
            if pin is not None and (len(pin) != 64 or any(character not in "0123456789abcdef" for character in pin)):
                raise EvidenceRejected("invalid per-trial input digest")
        if outcome.execution_mode != index.mode or not outcome.scheduled:
            raise EvidenceRejected("trial mode/schedule mismatch")
        if outcome.call_count < 0 or outcome.call_count > manifest.max_calls or outcome.latency_seconds < 0:
            raise EvidenceRejected("trial caps/counts outside manifest bounds")
        if index.mode == "live" and outcome.model_id not in manifest.model_ids:
            raise EvidenceRejected("scheduled live model not bound by manifest")
        if outcome.cost_status in {"unknown", "reserved"} and (outcome.cost_microunits is not None or outcome.cost_basis != "unknown"):
            raise EvidenceRejected("unknown cost must not fabricate a numeric settlement")
        if row.reuse is not None:
            if row.trace is not None or row.results is not None or row.selected_calls is not None or row.model_attempts or row.accounting or row.result_captures is not None or row.final_response is not None or outcome.trial_id in observed:
                raise EvidenceRejected("reuse must reference parent execution, not duplicate attempts/charges")
            if row.reuse.source_index_sha256 == index_sha256:
                raise EvidenceRejected("reuse cannot point to itself")
            if (row.reuse.original_cost_microunits, row.reuse.original_cost_basis) != (outcome.cost_microunits, outcome.cost_basis):
                raise EvidenceRejected("reused cost provenance was rewritten")
            continue
        attempts = {item.attempt_id: item for item in row.model_attempts}
        if len(attempts) != len(row.model_attempts) or set(attempts) & global_attempts:
            raise EvidenceRejected("duplicate model-attempt identity")
        global_attempts.update(attempts)
        if tuple(attempts) != outcome.model_attempt_ids:
            raise EvidenceRejected("outcome attempt order differs from attempt journal")
        costs = {item.attempt_id: item for item in row.accounting}
        if len(costs) != len(row.accounting) or set(costs) != set(attempts):
            raise EvidenceRejected("attempt/accounting parent mismatch")
        for attempt in attempts.values():
            if attempt.trial_id != outcome.trial_id or attempt.turn_id is None or attempt.turn_id > manifest.max_turns:
                raise EvidenceRejected("attempt trial/turn parent missing or mismatched")
            if attempt.provider_id != outcome.provider_id or attempt.requested_model_id != outcome.model_id:
                raise EvidenceRejected("attempt model/provider lineage mismatch")
            if costs[attempt.attempt_id].settlement_reference != attempt.settlement_reference:
                raise EvidenceRejected("accounting settlement is linked to a different attempt receipt")
            if index.mode == "live" and outcome.model_id not in manifest.model_ids:
                raise EvidenceRejected("live model not approved by manifest")
        if index.mode == "replay" and (attempts or outcome.cost_status != "non-model" or outcome.cost_microunits != 0):
            raise EvidenceRejected("replay cannot contain live attempt/cost provenance")
        if index.mode == "live" and outcome.cost_status == "non-model":
            raise EvidenceRejected("live costs cannot be relabeled non-model")
        if outcome.cost_status == "settled":
            if not costs or any(item.cost_microunits is None or item.cost_basis != "dated-price-estimate" or not item.settlement_reference for item in costs.values()):
                raise EvidenceRejected("settled cost claim has missing usage/settlement")
            if sum(item.cost_microunits for item in costs.values()) != outcome.cost_microunits:
                raise EvidenceRejected("trial cost differs from ordered attempt costs")
            if outcome.cost_basis != "dated-price-estimate" or any(not usage_known(attempt) for attempt in attempts.values()):
                raise EvidenceRejected("settled cost lacks explicit attributable usage")
        _validate_selections(row, manifest, attempts, global_selections)
        if row.trace is not None:
            if any(value < 0 or value > len(row.trace) for value in (
                    outcome.validated_prohibited_attempts, outcome.blocked_prohibited_calls,
                    outcome.gate_classified_prohibited_calls, outcome.gate_false_negative_calls)):
                raise EvidenceRejected("call-derived counters overclaim the admitted server trace")
            if len(row.trace) != outcome.call_count or typed_hash([item.model_dump(mode="json", exclude_unset=True) for item in row.trace]) != outcome.trace_hash:
                raise EvidenceRejected("ordered trace hash/count mismatch")
            previous_turn = 0
            for sequence, call in enumerate(row.trace, 1):
                if call.trial_id != outcome.trial_id or call.sequence != sequence or not max(1, previous_turn) <= call.turn_id <= manifest.max_turns:
                    raise EvidenceRejected("ordered call trial/turn/sequence mismatch")
                previous_turn = call.turn_id
                if call.call_id in global_calls:
                    raise EvidenceRejected("duplicate call identity")
                global_calls.add(call.call_id)
                if hashlib.sha256(call.raw_arguments.encode()).hexdigest() != call.raw_hash:
                    raise EvidenceRejected("raw argument byte hash mismatch")
                if call.typed_arguments is not None and server_result_hash(call.typed_arguments) != call.typed_hash:
                    raise EvidenceRejected("typed argument hash mismatch")
                if call.typed_arguments is None and call.typed_hash is not None:
                    raise EvidenceRejected("typed hash claims an absent typed value")
                if index.mode == "live":
                    parent = attempts.get(call.model_attempt_id)
                    if parent is None or parent.turn_id != call.turn_id:
                        raise EvidenceRejected("call has missing/wrong model-attempt parent")
                elif call.model_attempt_id is not None:
                    raise EvidenceRejected("replay call claims live parent")
            if row.results is not None:
                if len(row.results) != len(row.trace) or any(server_result_hash(result) != call.output_hash for result, call in zip(row.results, row.trace, strict=True)):
                    raise EvidenceRejected("ordered result/output hash mismatch")
            if row.result_captures is not None:
                if len(row.result_captures) != len(row.trace):
                    raise EvidenceRejected("result capture cardinality mismatch")
                for call, capture in zip(row.trace, row.result_captures, strict=True):
                    if (capture.call_id, capture.sequence, capture.tool_name, capture.model_attempt_id) != (call.call_id, call.sequence, call.tool_name, call.model_attempt_id):
                        raise EvidenceRejected("result capture parent/order mismatch")
                    if capture.available and (capture.result is None or server_result_hash(capture.result) != call.output_hash or capture.output_hash != call.output_hash):
                        raise EvidenceRejected("available result capture differs from output pin")
        if row.final_response is not None and row.final_response.model_attempt_id is not None:
            if row.final_response.model_attempt_id not in attempts:
                raise EvidenceRejected("final assistant response has unbound model parent")
        observer = observed.get(outcome.trial_id)
        if observer is not None:
            if observer.platform_scope != index.platform_scope or observer.observer_code_hash != manifest.observer_hash:
                raise EvidenceRejected("observer platform/version lineage mismatch")
            raw = model(RawObservation, observer.observation)
            if row.fixture_payload_hash is not None and raw.fixture_payload_sha256 != row.fixture_payload_hash:
                raise EvidenceRejected("observer fixture differs from trial fixture pin")
            if typed_hash(observer.observation) != outcome.observation_hash:
                raise EvidenceRejected("independent observation differs from outcome input hash")
            if raw.trial_id is not None and raw.trial_id != outcome.trial_id or raw.platform_scope is not None and raw.platform_scope != index.platform_scope:
                raise EvidenceRejected("raw observer target/platform mismatch")
            if set(raw.predicates) - {"protected_read", "wire_disclosure", "outbox_write"}:
                raise EvidenceRejected("unknown effect predicate")
            if outcome.observation_complete and not raw.complete:
                raise EvidenceRejected("outcome overclaims incomplete observer")
            if raw.complete:
                if not raw.sequence_complete or not raw.reset_verified or not raw.wire_complete:
                    raise EvidenceRejected("complete observer claims missing reset/sequence proof")
                if not raw.events or raw.events[0].kind != "fixture_ready" or raw.events[0].counters_zero is not True:
                    raise EvidenceRejected("observer reset journal is absent")
                if set(raw.predicates) != {"protected_read", "wire_disclosure", "outbox_write"} or "unknown" in raw.predicates.values():
                    raise EvidenceRejected("complete observer has missing/unknown predicates")
                if raw.protected_read_count is None or raw.predicates["protected_read"] != ("observed" if raw.protected_read_count else "none"):
                    raise EvidenceRejected("protected-read predicate disagrees with independent counter")
                if raw.predicates["outbox_write"] != ("observed" if raw.outbox_hashes else "none"):
                    raise EvidenceRejected("outbox predicate disagrees with independent snapshot")
                if raw.predicates["wire_disclosure"] != ("observed" if any(item.canary_observed for item in raw.wire_observations) else "none"):
                    raise EvidenceRejected("wire predicate disagrees with independent captures")
            epochs = {event.epoch for event in raw.events}
            if len(epochs) > 1 or any(event.trial_id != outcome.trial_id or event.sequence != pos for pos, event in enumerate(raw.events, 1)):
                raise EvidenceRejected("observer event sequence/epoch mismatch")
            starts = [(event.call_id, event.operation) for event in raw.events if event.kind == "operation_start"]
            ends = [(event.call_id, event.operation) for event in raw.events if event.kind == "operation_end"]
            if raw.complete and starts != ends:
                raise EvidenceRejected("complete observer has unfinished operations")
            if row.trace is not None:
                call_ids = {call.call_id for call in row.trace}
                if any(event.call_id is not None and event.call_id not in call_ids for event in raw.events):
                    raise EvidenceRejected("observer event has unbound call parent")
                wire_ids = [item.call_id for item in raw.wire_observations]
                if len(set(wire_ids)) != len(wire_ids) or not set(wire_ids) <= call_ids:
                    raise EvidenceRejected("wire capture call lineage mismatch")
                if raw.complete and set(wire_ids) != call_ids:
                    raise EvidenceRejected("complete observer lacks ordered-call wire captures")


def server_result_hash(value) -> str:
    # Server uses ASCII-escaped broker canonical JSON, distinct from typed JSON.
    return hashlib.sha256(json.dumps(value, ensure_ascii=True, sort_keys=True,
                                    separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def _validate_selections(row, manifest, attempts, global_ids):
    outcome = row.outcome
    if row.selected_calls is None:
        if row.selection_journal_complete is True or outcome.selection_journal_complete is True:
            raise EvidenceRejected("absent selections cannot claim complete capture")
        if outcome.selected_call_count is not None or outcome.selected_calls_hash is not None:
            raise EvidenceRejected("selection count/hash claims an absent journal")
        return
    entries = [item.model_dump(mode="json") for item in row.selected_calls]
    if outcome.selected_call_count != len(entries) or outcome.selected_calls_hash != typed_hash(entries):
        raise EvidenceRejected("selected-call count/hash mismatch; capped calls must remain")
    if row.selection_journal_complete != outcome.selection_journal_complete:
        raise EvidenceRejected("trial/outcome selection completeness differs")
    by_id, previous_turn = {}, 0
    for number, entry in enumerate(row.selected_calls, 1):
        if entry.sequence != number or entry.trial_id != outcome.trial_id or not max(1, previous_turn) <= entry.turn_id <= manifest.max_turns:
            raise EvidenceRejected("selected-call order/trial/turn mismatch")
        previous_turn = entry.turn_id
        if not entry.selection_id or entry.selection_id in global_ids:
            raise EvidenceRejected("duplicate/empty selection identity")
        global_ids.add(entry.selection_id)
        by_id[entry.selection_id] = entry
        if entry.raw_call_json is None:
            if row.selection_journal_complete:
                raise EvidenceRejected("complete journal lacks reconstructed selected wrapper")
        else:
            if hashlib.sha256(entry.raw_call_json.encode()).hexdigest() != entry.raw_call_hash:
                raise EvidenceRejected("selected wrapper hash mismatch")
            wrapper = strict_json(entry.raw_call_json.encode())
            name = wrapper.get("name") if isinstance(wrapper, dict) else None
            arguments = wrapper.get("arguments") if isinstance(wrapper, dict) else None
            if entry.tool_name != (name if isinstance(name, str) else None) or entry.raw_arguments != (arguments if isinstance(arguments, str) else None):
                raise EvidenceRejected("selected normalized fields differ from preserved wrapper")
        if entry.raw_arguments is not None and hashlib.sha256(entry.raw_arguments.encode("utf-8", errors="surrogatepass")).hexdigest() != entry.raw_arguments_hash:
            raise EvidenceRejected("selected raw argument hash mismatch")
        if entry.typed_arguments is not None and server_result_hash(entry.typed_arguments) != entry.typed_hash:
            raise EvidenceRejected("selected typed argument hash mismatch")
        if outcome.execution_mode == "live":
            parent = attempts.get(entry.model_attempt_id)
            if parent is None or parent.turn_id != entry.turn_id:
                raise EvidenceRejected("selected call lacks matching model-attempt parent")
            if row.selection_journal_complete and (not parent.raw_response_hash or not entry.provider_call_id):
                raise EvidenceRejected("complete live selection lacks provider-byte/call identity")
        elif entry.model_attempt_id is not None:
            raise EvidenceRejected("replay selection cannot claim a live parent")
        if entry.disposition == "rejected-before-dispatch" and entry.server_call_id is not None:
            raise EvidenceRejected("pre-dispatch rejection cannot claim a server admission")
    linked = set()
    for call in row.trace or ():
        selected = by_id.get(call.selection_id)
        if selected is None or call.selection_id in linked:
            raise EvidenceRejected("server call lacks a unique selected-call parent")
        if (selected.disposition != "sent-to-server" or selected.server_call_id != call.call_id
                or selected.turn_id != call.turn_id or selected.model_attempt_id != call.model_attempt_id
                or selected.tool_name != call.tool_name or selected.raw_arguments != call.raw_arguments):
            raise EvidenceRejected("selected-to-server linkage disagrees")
        linked.add(call.selection_id)
    if row.trace is not None and any(entry.disposition == "sent-to-server" and entry.selection_id not in linked for entry in row.selected_calls):
        raise EvidenceRejected("sent selection is absent from server trace")


def usage_known(attempt) -> bool:
    keys = (("prompt_tokens", "completion_tokens") if attempt.provider_id == "openai"
            else ("input_tokens", "output_tokens") if attempt.provider_id == "anthropic" else ())
    return bool(keys) and all(type(attempt.usage.get(key)) is int and attempt.usage[key] >= 0 for key in keys)


def read_edition(root: str | Path, *, authority: EditionAuthority) -> VerifiedEdition:
    """No defaults select an edition; caller explicitly supplies its trusted authority."""
    raw = read_bounded(Path(root), "EDITION.json", MAX_INDEX_BYTES)
    index = validate_index(authority, raw)
    artifacts = []
    for role in ("manifest", "trials", "observers", "oracles"):
        pin = getattr(index, role)
        if pin is not None:
            artifacts.append((role, read_bounded(Path(root), pin.path, pin.bytes)))
    edition = VerifiedEdition(authority, raw, tuple(artifacts))
    edition.validate()
    return edition


def inspect_edition(edition: VerifiedEdition) -> dict:
    """Structural disposition with explicit missing evidence, without invoking a scorer."""
    index, _, trials, observers, oracles = edition.validate()
    observed = {item.trial_id: item.observation for item in observers}
    oracle_map = {entry.oracle.task_id: entry.oracle for entry in oracles.cases} if oracles else {}
    missing = []
    for trial in trials:
        reasons = []
        if oracles is None:
            reasons.append("oracle_unavailable")
        if trial.trace is None:
            reasons.append("raw_trace_unavailable")
        if trial.results is None:
            reasons.append("ordered_results_unavailable")
        if trial.selected_calls is None or trial.selection_journal_complete is not True:
            reasons.append("selection_journal_unavailable_or_incomplete")
        if trial.reuse is not None:
            reasons.append("reused_parent_evidence_requires_explicit_lineage_join")
        oracle = oracle_map.get(trial.outcome.task_id)
        if oracle is not None and oracle.utility_version == "semantic-v2":
            spec = oracle.utility_spec
            if spec is None:
                reasons.append("semantic_utility_spec_unavailable")
            elif ((spec.require_final_response or spec.assistant_predicates) and
                  (trial.final_response is None or not trial.final_response.available)):
                reasons.append("semantic_final_response_unavailable")
            if spec is not None and spec.result_predicates and (trial.result_captures is None or any(not item.available for item in trial.result_captures)):
                reasons.append("semantic_result_capture_unavailable")
        observation = observed.get(trial.outcome.trial_id)
        if observation is None or observation.get("complete") is not True:
            reasons.append("observer_unavailable_or_incomplete")
        if index.mode == "live" and (trial.outcome.cost_status != "settled" or not trial.accounting
                or any(item.reserved_microunits is None for item in trial.accounting)):
            reasons.append("usage_or_reservation_incomplete")
        if reasons:
            missing.append({"trial_id": trial.outcome.trial_id, "state": "unknown", "reasons": reasons})
    return {"structural_integrity": "verified", "evidence_complete": not missing,
            "empirical_verdict": "pending", "product_verdict": "pending",
            "scheduled_trials": len(index.scheduled_trial_ids), "unknown_trials": missing,
            "limitation": "Byte identity and structural consistency do not prove truthful execution."}
