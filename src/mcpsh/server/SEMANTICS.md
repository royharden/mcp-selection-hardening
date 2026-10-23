# Public matching and log parsing contract

These are source contracts, not measured conformance. Public regression source is
in tests/server/test_public_matching_parsing.py; it has not run during Dirty Mode.
No hidden example or retired custody content informed this contract.

## Search pattern v1

The authoritative source is matching.py, with PATTERN_GRAMMAR_VERSION and
PATTERN_DESCRIPTION available to catalog/probe consumers. Matching is case-sensitive.
There are up to sixteen nonempty literal alternatives separated by `|`. Each can
have one unescaped `^` at its start and `$` at its end. Dot is a literal dot.
Backslash can escape a reserved symbol as a literal: `\|^$.*+?()[]{}`. Other escape
forms are rejected. Empty alternatives and anchor-only patterns are rejected.
There is no wildcard, repetition, grouping, character class or backreference.
The UTF-8 pattern cap is 512 bytes. This finite literal matcher never dispatches
a user-controlled pattern to Python's regular-expression engine.

Examples: `timeout|^ERROR` selects a literal substring or leading ERROR;
`^x\|y$` matches exactly the literal text x|y; `a.b` requires a dot. Patterns
`.*`, `[ab]`, `a+`, `a||b` and `^$` return INVALID_PATTERN. Compilation occurs
before broker reads, including on an empty source. find_literal always performs
a literal substring search and does not interpret these pattern delimiters.

## Log fields v1

The authoritative source is parsing.py with LOG_PARSER_VERSION. Raw text remains
untrusted and is returned only through the usual source policy/bounds/redaction.
Recognized plain text has an optional timezone-aware ISO8601 first token, optionally
bracketed or prefixed timestamp=. A leading level token can be bare, [LEVEL] or
level=LEVEL. Levels are case-insensitive TRACE/DEBUG/INFO/WARN/ERROR/FATAL/CRITICAL;
WARNING normalizes to WARN. Severity is never inferred from an arbitrary word
inside a message. Untimestamped lines remain available to ordinary reads but are
excluded explicitly from time-window operations.

Plain explicit code labels are code=VALUE, code:VALUE, error_code=VALUE or
error_code:VALUE, with case-insensitive labels and bounded alphanumeric/underscore/
dot/hyphen values. Distinct conflicting codes produce an unclassified code, not
an arbitrary first match. A word such as decode= is not a code label.
Plain code values end at whitespace, end of line, comma, semicolon or a closing
bracket/brace; an unsupported slash-containing token is not shortened to a code.

A JSON object line can supply exact lowercase timestamp/time/ts, level,
code/error_code and message/msg fields. Timestamp aliases and code aliases must
agree; their invalid or conflicting values are explicitly unsupported. Timestamps
require a timezone. Codes must be bounded strings; booleans, numbers, objects and
arrays do not silently become code strings. Duplicate JSON keys and nonfinite
JSON values make the structured line unparsed. Additional log fields remain data
and cannot become executable settings. Unsupported message types retain raw text
for display while marking the parsing limitation.

error_counts groups only recognized ERROR/FATAL/CRITICAL lines within its bounded
scan. Missing/unsupported error codes use the visible UNKNOWN bin. Coverage has
parser version, format counts, unclassified levels, untimestamped lines, unsupported
field lines and unclassified error-code lines. semantic_complete is distinct from
physical scan completeness; no claim of complete interpretation follows merely
from reading all bytes. Time queries disclose excluded_untimestamped. Optional
future formats require a new declared parser version and public regressions.
