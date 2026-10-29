"""Deterministic bounded literal-pattern grammar; never a backtracking regex."""

from dataclasses import dataclass

PATTERN_GRAMMAR_VERSION = "m5-literal-pattern-v1"
PATTERN_DESCRIPTION = (
    "Case-sensitive bounded literal pattern: up to 16 nonempty alternatives separated by |, "
    "with optional ^ start and $ end anchors. Dot is literal. Reserved symbols "
    "can be backslash-escaped as literals. Wildcards, repetition, groups, character "
    "classes, backreferences and other regular-expression syntax are unsupported."
)
_RESERVED = frozenset("\\|^$.*+?()[]{}")


class PatternSyntaxError(ValueError):
    pass


@dataclass(frozen=True)
class LiteralAlternative:
    literal: str
    anchored_start: bool
    anchored_end: bool

    def matches(self, text: str) -> bool:
        if self.anchored_start and self.anchored_end:
            return text == self.literal
        if self.anchored_start:
            return text.startswith(self.literal)
        if self.anchored_end:
            return text.endswith(self.literal)
        return self.literal in text


@dataclass(frozen=True)
class BoundedPattern:
    alternatives: tuple[LiteralAlternative, ...]

    def matches(self, text: str) -> bool:
        return any(alternative.matches(text) for alternative in self.alternatives)


def compile_pattern(pattern: str) -> BoundedPattern:
    if type(pattern) is not str or not pattern or len(pattern.encode("utf-8", "strict")) > 512:
        raise PatternSyntaxError("pattern must contain 1..512 UTF-8 bytes")
    groups: list[list[tuple[str, bool]]] = [[]]
    position = 0
    while position < len(pattern):
        character = pattern[position]
        if character == "\\":
            position += 1
            if position >= len(pattern) or pattern[position] not in _RESERVED:
                raise PatternSyntaxError("escape only a reserved literal symbol")
            groups[-1].append((pattern[position], True))
        elif character == "|":
            if len(groups) >= 16:
                raise PatternSyntaxError("at most sixteen literal alternatives are supported")
            groups.append([])
        elif character in "*+?()[]{}":
            raise PatternSyntaxError("wildcards, repetition, groups and character classes are unsupported")
        else:
            groups[-1].append((character, False))
        position += 1
    alternatives = []
    for tokens in groups:
        anchored_start = bool(tokens and tokens[0] == ("^", False))
        anchored_end = bool(tokens and tokens[-1] == ("$", False))
        body = tokens[1:] if anchored_start else tokens[:]
        body = body[:-1] if anchored_end else body
        if not body or any(character in "^$" and not escaped for character, escaped in body):
            raise PatternSyntaxError("nonempty literals required; anchors only at alternative boundaries")
        alternatives.append(LiteralAlternative("".join(character for character, _ in body), anchored_start, anchored_end))
    return BoundedPattern(tuple(alternatives))
