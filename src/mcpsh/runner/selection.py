"""Bounded ordered model selections, distinct from server admission/execution."""

import json

from mcpsh.records import SelectedCall, raw_hash

MAX_NORMALIZED_BATCH_BYTES = 4 * 1024 * 1024
MAX_SELECTED_CALLS = 65536


def journal_batch(calls, *, trial_id: str, turn_id: int, start_sequence: int,
                  model_attempt_id: str | None = None, provider_call_ids=None):
    """Retain every supported selected wrapper/argument before dispatch caps.

    The transport's actual response-body cap remains 1 MiB. This bounded expanded
    normalization budget is not permission to accept larger provider bodies or to
    dispatch more calls. Unsupported non-JSON/oversized journals are incomplete,
    never an empty successful selection. Original provider bytes stay private in
    the attempt journal; raw_call_json names its explicit normalized representation.
    """
    if not isinstance(calls, list):
        return [], False, "selected_batch_not_list"
    if len(calls) + start_sequence - 1 > MAX_SELECTED_CALLS:
        return [], False, "selected_journal_count_cap"
    try:
        encoded = json.dumps(calls, ensure_ascii=True, allow_nan=False,
                             separators=(",", ":"), sort_keys=True)
    except (ValueError, TypeError, RecursionError, OverflowError):
        return [], False, "selected_batch_not_json"
    if len(encoded.encode("ascii")) > MAX_NORMALIZED_BATCH_BYTES:
        return [], False, "selected_journal_byte_cap"
    from mcpsh.server.validation import parse_arguments

    entries = []
    ids = provider_call_ids if isinstance(provider_call_ids, list) else []
    for index, call in enumerate(calls):
        raw_call = json.dumps(call, ensure_ascii=True, allow_nan=False,
                              separators=(",", ":"), sort_keys=True)
        name = call.get("name") if isinstance(call, dict) else None
        arguments = call.get("arguments") if isinstance(call, dict) else None
        name = name if isinstance(name, str) else None
        arguments = arguments if isinstance(arguments, str) else None
        value, argument_hash, validation = None, None, "invalid"
        if isinstance(call, dict) and set(call) == {"name", "arguments"} and name is not None and arguments is not None:
            try:
                value, argument_hash = parse_arguments(name, arguments)
                validation = "valid"
            except (ValueError, TypeError, UnicodeError, RecursionError, OverflowError):
                pass
        sequence = start_sequence + index
        provider_id = ids[index] if index < len(ids) and isinstance(ids[index], str) else None
        entries.append(SelectedCall(
            trial_id=trial_id, turn_id=turn_id,
            selection_id=f"{trial_id}:selection:{sequence}", sequence=sequence,
            tool_name=name, raw_arguments=arguments,
            raw_arguments_hash=raw_hash(arguments.encode("utf-8", errors="surrogatepass"))
            if arguments is not None else None,
            raw_call_json=raw_call, raw_call_hash=raw_hash(raw_call),
            typed_arguments=value, typed_hash=argument_hash, validation=validation,
            disposition="selected", model_attempt_id=model_attempt_id,
            provider_call_id=provider_id,
        ))
    return entries, True, None


def reject_pending(entries, reason):
    return [entry.model_copy(update={"disposition": "rejected-before-dispatch",
                                     "rejection_reason": reason})
            if entry.disposition == "selected" else entry for entry in entries]
