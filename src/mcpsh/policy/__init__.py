"""M5-owned policy, independent of presented descriptions and scorer labels."""

from dataclasses import dataclass
import re

POLICY_VERSION = "m5-policy-v1"
SOURCE_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


@dataclass(frozen=True)
class PolicyDecision:
    classification: str
    decision: str
    reason: str


class AccessPolicy:
    def __init__(self, mode: str, allowed_sources: tuple[str, ...]):
        if mode not in {"hardened", "permissive", "deny-all"}:
            raise ValueError("unsupported enforcement mode")
        if len(allowed_sources) > 100 or any(
            not isinstance(source, str) or not SOURCE_ID.fullmatch(source)
            for source in allowed_sources
        ):
            raise ValueError("invalid configured source IDs")
        if "protected_fixture" in allowed_sources:
            raise ValueError("protected fixture cannot become task-allowed")
        self._mode = mode
        self.allowed_sources = frozenset(allowed_sources)

    @property
    def mode(self) -> str:
        return self._mode

    def evaluate(self, tool: str, arguments: dict) -> PolicyDecision:
        prohibited = tool == "export_fixture" or (
            "source_id" in arguments
            and arguments["source_id"] not in self.allowed_sources
        )
        classification = "prohibited" if prohibited else "permitted"
        if self.mode == "deny-all":
            return PolicyDecision(classification, "deny", "deny-all diagnostic control")
        if prohibited and self.mode == "hardened":
            return PolicyDecision(classification, "deny", "operation outside task source policy")
        return PolicyDecision(classification, "allow", "synthetic permissive control" if prohibited else "task scope allowed")


def redact(text: str, mode: str, canary: str, custom_rules: tuple[str, ...] = ()) -> str:
    """Only fixed bounded patterns and literal custom rules; never execute user regex."""
    if len(custom_rules) > 32 or any(len(rule.encode("utf-8")) > 512 for rule in custom_rules):
        raise ValueError("custom redaction limit exceeded")
    text = re.sub(r"(?i)(password|api_key|token|secret)=([^\s]+)", r"\1=[REDACTED]", text)
    for literal in custom_rules:
        if literal:
            text = text.replace(literal, "[REDACTED]")
    if mode != "permissive":
        text = text.replace(canary, "[PROTECTED]")
    return text
