"""Public contract regressions, authored only; not executed during Dirty Mode."""

import pytest

from mcpsh.server.matching import PatternSyntaxError, compile_pattern
from mcpsh.server.parsing import parse_log_line


def test_dot_remains_literal_and_reserved_escape_is_not_regex():
    """Catches prose/executor drift and accidental broad regex interpretation."""
    pattern = compile_pattern(r"a.b|^x\|y$")
    assert pattern.matches("prefix a.b suffix")
    assert not pattern.matches("prefix axb suffix")
    assert pattern.matches("x|y")
    assert not pattern.matches("prefix x|y")


@pytest.mark.parametrize("text", [".*", "a+", "[ab]", "(a)", r"\d", "a||b", "^$", "a^b", "a\\"])
def test_unsupported_or_empty_alternatives_are_explicit(text):
    """Previously empty alternatives could silently match every line."""
    with pytest.raises(PatternSyntaxError):
        compile_pattern(text)


def test_plain_bracket_and_structured_fields_agree_on_public_semantics():
    """Catches bare code= parser and positional-level assumptions."""
    plain = parse_log_line("2026-10-20T12:00:00Z [ERROR] CODE:E_PUBLIC public failure")
    structured = parse_log_line('{"timestamp":"2026-10-20T12:00:00Z","level":"error","code":"E_PUBLIC","message":"public failure"}')
    assert plain.timestamp == structured.timestamp == "2026-10-20T12:00:00+00:00"
    assert plain.level == structured.level == "ERROR"
    assert plain.code == structured.code == "E_PUBLIC"


def test_conflicting_codes_do_not_invent_a_group_label():
    plain = parse_log_line("ERROR code=PUBLIC_A error_code=PUBLIC_B public conflict")
    structured = parse_log_line('{"level":"ERROR","code":"PUBLIC_A","error_code":"PUBLIC_B"}')
    assert plain.code is structured.code is None
    assert "ambiguous-code" in plain.unsupported
    assert "invalid-or-ambiguous-code" in structured.unsupported


def test_duplicate_json_and_unclassified_text_remain_explicit():
    duplicate = parse_log_line('{"level":"INFO","level":"ERROR","code":"PUBLIC"}')
    raw = parse_log_line("public multiline continuation without metadata")
    assert duplicate.format == "unparsed"
    assert "invalid-structured-json" in duplicate.unsupported
    assert raw.timestamp is raw.level is raw.code is None


def test_warning_alias_and_code_token_boundary_are_deterministic():
    parsed = parse_log_line("level=warning decode=NOT_A_CODE code=PUBLIC_OK public warning")
    assert parsed.level == "WARN"
    assert parsed.code == "PUBLIC_OK"
    assert parse_log_line("ERROR code=PUBLIC/NOT_ID public unsupported code").code is None
