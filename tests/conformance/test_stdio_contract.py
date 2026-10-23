"""Authored wire regressions; do not launch a child to test pure validators."""

import json

import pytest

from mcpsh.conformance.stdio import decode_frame, encode_frame, structured_tool_result


@pytest.mark.parametrize("raw", [b'hello\n', b'{"jsonrpc":"2.0","id":1,"id":2,"result":{}}\n',
    b'{"jsonrpc":"2.0","id":1,"result":NaN}\n', b'{"jsonrpc":"2.0","id":1,"result":{}}',
    b' ' * (32 * 1024) + b'\n'])
def test_invalid_stdout_is_not_a_protocol_pass(raw):
    # what_bug_this_catches: stdout noise/duplicates/nonfinite/truncation ignored.
    with pytest.raises(ValueError):
        decode_frame(raw)


def test_escaping_preserves_one_complete_frame():
    # what_bug_this_catches: embedded newline or escaped Unicode corrupts framing.
    value = {"jsonrpc": "2.0", "id": 7, "result": {"text": '\n"\\\u2028'}}
    raw = encode_frame(value)
    assert raw.count(b"\n") == 1
    assert decode_frame(raw) == value


def test_execution_error_is_distinct_from_protocol_error():
    # what_bug_this_catches: policy refusal gets counted as malformed JSON-RPC.
    structured = {"ok": False, "error": {"code": "POLICY_DENIED"}}
    frame = {"jsonrpc": "2.0", "id": 1, "result": {"isError": True,
        "structuredContent": structured, "content": [{"type": "text", "text": json.dumps(structured)}]}}
    result = structured_tool_result(frame)
    assert result["kind"] == "tool-result"
    assert result["error_code"] == "POLICY_DENIED"
    assert structured_tool_result({"error": {"code": -32601, "message": "unknown"}})["kind"] == "protocol-error"


def test_contradictory_structured_status_is_rejected():
    # what_bug_this_catches: structured success and isError can silently disagree.
    with pytest.raises(ValueError):
        structured_tool_result({"result": {"isError": False, "structuredContent": {"ok": False}, "content": []}})
