"""Character/byte evidence regressions; authored source, no test execution."""

import pytest

from mcpsh.catalog.spans import enrich_finding, resolve_field_span


def source(text):
    return [{"name": "tail", "description": text}]


def test_supplementary_unicode_has_distinct_codepoint_and_utf8_offsets():
    # what_bug_this_catches: UTF-16/byte offsets reused as Python character positions.
    catalog = source("\U0001f680 warning")
    resolved = resolve_field_span(catalog, tool_index=0, field="description", start=2, end=9)
    assert resolved["evidence"] == "warning"
    assert resolved["byte_span"] == {"start": 5, "end": 12, "unit": "utf-8-byte"}
    from_bytes = resolve_field_span(catalog, tool_index=0, field="description",
                                    start=5, end=12, unit="utf-8-byte")
    assert from_bytes == resolved


def test_byte_offsets_inside_multibyte_scalar_are_rejected():
    # what_bug_this_catches: replacement decoding making evidence appear valid.
    with pytest.raises(ValueError):
        resolve_field_span(source("\U0001f680 x"), tool_index=0, field="description",
                           start=1, end=4, unit="utf-8-byte")


def test_combining_marks_crlf_and_bidi_are_not_normalized():
    # what_bug_this_catches: newline or NFC folding losing original field identity.
    text = "e\u0301\r\n\u202eX\u202c"
    result = resolve_field_span(source(text), tool_index=0, field="description",
                                start=0, end=len(text))
    assert result["evidence"] == text
    assert result["byte_span"]["end"] == len(text.encode("utf-8"))
    composed = resolve_field_span(source("\u00e9\r\n\u202eX\u202c"), tool_index=0,
                                  field="description", start=0, end=6)
    assert result["field_sha256"] != composed["field_sha256"]


def test_inexact_existing_evidence_identity_and_empty_span_are_rejected():
    # what_bug_this_catches: caller supplied prose accepted as source evidence.
    catalog = source("Read bounded lines.")
    finding = {"tool_index": 0, "tool_name": "tail", "field": "description",
               "span": {"start": 0, "end": 4, "unit": "unicode-codepoint"},
               "evidence": "Write"}
    with pytest.raises(ValueError):
        enrich_finding(catalog, finding)
    finding["evidence"] = "Read"
    enriched = enrich_finding(catalog, finding)
    assert enriched["byte_span"]["end"] == 4
    finding["byte_span"] = {"start": False, "end": 4, "unit": "utf-8-byte"}
    with pytest.raises(ValueError):
        enrich_finding(catalog, finding)
    finding.pop("byte_span")
    finding["tool_name"] = "other"
    with pytest.raises(ValueError):
        enrich_finding(catalog, finding)
    with pytest.raises(ValueError):
        resolve_field_span(catalog, tool_index=0, field="description", start=0, end=0)
