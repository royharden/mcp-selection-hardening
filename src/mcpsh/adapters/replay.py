"""Explicit authored replay episodes. No provider, oracle, usage, file or process API."""

from copy import deepcopy
import json
import re

from mcpsh.records import FinalAssistantResponse, typed_hash

MAX_EPISODE_BYTES = 4 * 1024 * 1024
MAX_SELECTED_CALLS = 65536
STOP_REASONS = frozenset({"stop", "end_turn", "stop_sequence", "refusal", "length", "max_tokens", "content_filter"})
EPISODE_FIELDS = frozenset({"schema_version", "episode_id", "provenance", "turns"})
TURN_FIELDS = frozenset({"calls", "final_text", "stop_reason"})


class ReplayFixtureError(ValueError):
    pass


class ReplayProtocolError(ValueError):
    pass


def _snapshot(value):
    try:
        raw = json.dumps(value, ensure_ascii=True, allow_nan=False, sort_keys=True,
                         separators=(",", ":")).encode("ascii")
        if len(raw) > MAX_EPISODE_BYTES:
            raise ReplayFixtureError("scripted episode byte cap exceeded")
        return json.loads(raw)
    except (ValueError, TypeError, RecursionError, OverflowError):
        raise ReplayFixtureError("bounded finite JSON fixture required") from None


def _pin(value):
    return type(value) is str and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _legacy_calls(calls):
    """Keep old valid dict-argument convenience; never repair malformed/extra calls."""
    normalized = []
    for call in calls:
        if type(call) is dict and set(call) in ({"name"}, {"name", "arguments"}) and type(call.get("name")) is str:
            arguments = call.get("arguments", "{}")
            if type(arguments) is not str:
                arguments = json.dumps(arguments, ensure_ascii=False, allow_nan=False,
                                       separators=(",", ":"))
            normalized.append({"name": call["name"], "arguments": arguments})
        else:
            normalized.append(deepcopy(call))
    return normalized


class ReplaySelector:
    provenance = "scripted-development-replay"

    def __init__(self, calls=None, *, episode=None, fixture_sha256=None, source_file_sha256=None):
        if calls is not None and episode is not None:
            raise ReplayFixtureError("choose legacy calls or an explicit authored episode")
        self._legacy = episode is None
        if self._legacy:
            calls = [] if calls is None else _snapshot(calls)
            if type(calls) is not list or len(calls) > MAX_SELECTED_CALLS:
                raise ReplayFixtureError("bounded legacy call list required")
            episode = {"schema_version": 1, "episode_id": "embedded-legacy-script",
                       "provenance": "authored-development-script",
                       "turns": [{"calls": _legacy_calls(calls), "final_text": None, "stop_reason": None}]}
        self._episode = _snapshot(episode)
        try:
            self._validate_episode()
            actual = typed_hash(self._episode)
        except UnicodeError:
            raise ReplayFixtureError("scripted fixture must contain valid bounded Unicode") from None
        if fixture_sha256 is not None and (not _pin(fixture_sha256) or fixture_sha256 != actual):
            raise ReplayFixtureError("scripted fixture pin differs from exact typed episode")
        if source_file_sha256 is not None and not _pin(source_file_sha256):
            raise ReplayFixtureError("raw public package pin must be an explicit SHA256")
        self._fixture_sha256 = actual
        self._source_file_sha256 = source_file_sha256
        self._turn = 0
        self._expected_history = 0
        self._pending_calls = []
        self._bound_task_id = None
        self._task_bound = False
        self._last_scripted_response = None
        self._scripted_final = FinalAssistantResponse(available=False)

    def _validate_episode(self):
        episode = self._episode
        if type(episode) is not dict or set(episode) != EPISODE_FIELDS:
            raise ReplayFixtureError("episode fields differ from authored replay v1")
        if type(episode["schema_version"]) is not int or episode["schema_version"] != 1 or episode["provenance"] != "authored-development-script":
            raise ReplayFixtureError("explicit authored-development v1 provenance required")
        identifier = episode["episode_id"]
        if type(identifier) is not str or not identifier or len(identifier.encode("utf-8")) > 256:
            raise ReplayFixtureError("bounded episode identity required")
        turns = episode["turns"]
        if type(turns) is not list or not 1 <= len(turns) <= 3:
            raise ReplayFixtureError("episode must contain one to three authored turns")
        selected = 0
        for index, turn in enumerate(turns):
            if type(turn) is not dict or set(turn) != TURN_FIELDS or type(turn["calls"]) is not list:
                raise ReplayFixtureError("turn must contain only calls, final_text and stop_reason")
            selected += len(turn["calls"])
            if selected > MAX_SELECTED_CALLS:
                raise ReplayFixtureError("scripted selected-call journal cap exceeded")
            if not turn["calls"] and index + 1 < len(turns):
                raise ReplayFixtureError("no-call terminal turn cannot hide unreachable later fixture turns")
            text, reason = turn["final_text"], turn["stop_reason"]
            if text is not None and (type(text) is not str or len(text.encode("utf-8")) > 65536):
                raise ReplayFixtureError("scripted text must be explicit bounded text or unavailable")
            if reason is not None and (type(reason) is not str or reason not in STOP_REASONS):
                raise ReplayFixtureError("unsupported scripted stop reason")

    @property
    def calls(self):
        return deepcopy(self._episode["turns"][0]["calls"])

    @property
    def scripted_fixture_sha256(self):
        return self._fixture_sha256

    @property
    def scripted_final_response(self):
        return self._scripted_final.model_copy(deep=True)

    @property
    def last_scripted_response(self):
        return deepcopy(self._last_scripted_response)

    def _capture(self, calls, text, reason, *, exhausted=False):
        available = type(text) is str
        complete = available and not calls and reason in {"stop", "end_turn", "stop_sequence", "refusal"}
        self._scripted_final = FinalAssistantResponse(
            available=available, text=text if available else None,
            refusal_text=text if available and reason == "refusal" else None,
            stop_reason=reason, model_attempt_id=None, raw_response_hash=None, complete=complete)
        value = {"provenance": self.provenance, "episode_id": self._episode["episode_id"],
                 "scripted_fixture_sha256": self._fixture_sha256,
                 "source_file_sha256": self._source_file_sha256,
                 "source_pin_basis": "caller-declared-public-package-pin" if self._source_file_sha256 else "embedded-script-only",
                 "turn_id": self._turn, "tool_calls": deepcopy(calls),
                 "final_response": self._scripted_final.model_dump(mode="json"),
                 "episode_exhausted": exhausted}
        value["scripted_response_sha256"] = typed_hash(value)
        self._last_scripted_response = value

    def select(self, task, catalog, history):
        del catalog
        self._last_scripted_response = None
        self._scripted_final = FinalAssistantResponse(available=False)
        if type(history) is not list:
            raise ReplayProtocolError("ordered captured tool history must be a list")
        task_id = task.get("task_id") if type(task) is dict else None
        if self._task_bound and task_id != self._bound_task_id:
            raise ReplayProtocolError("replay selector cannot be reused across task identities")
        self._bound_task_id, self._task_bound = task_id, True
        if self._legacy and history:
            self._capture([], None, None, exhausted=True)
            return []
        if not self._legacy:
            if len(history) != self._expected_history:
                raise ReplayProtocolError("every authored selection requires its ordered captured history before the next turn")
            if self._pending_calls:
                for captured, selected in zip(history[-len(self._pending_calls):], self._pending_calls, strict=True):
                    if type(captured) is not dict or captured.get("role") != "tool" or captured.get("call") != selected:
                        raise ReplayProtocolError("captured result does not match the prior authored call order")
        if self._turn >= len(self._episode["turns"]):
            self._pending_calls = []
            self._capture([], None, None, exhausted=True)
            return []
        turn = self._episode["turns"][self._turn]
        self._turn += 1
        calls = deepcopy(turn["calls"])
        self._expected_history += len(calls)
        self._pending_calls = deepcopy(calls)
        self._capture(calls, turn["final_text"], turn["stop_reason"])
        return calls
