"""Bounded lexical/structural metadata lint; never an enforcement oracle."""

from copy import deepcopy
import re
from typing import Any

from mcpsh.catalog import CANONICAL_DESCRIPTIONS

LINT_VERSION = "m5-lint-2"
NORMALIZER_VERSION = "m5-trusted-map-2"
MAX_METADATA_CHARS = 4096
MAX_METADATA_DEPTH = 8
LIMITS = {
    "L01": "Indirect prerequisite paraphrases may pass.",
    "L02": "Obfuscated references and synonyms may pass.",
    "L03": "Encoded or split role/priority claims may pass.",
    "L04": "Only named Unicode control classes are detected.",
    "L05": "Only explicit parameter/argument declarations are checked.",
    "L06": "Neutral verbs and semantic contradictions may pass.",
    "L07": "Lexical overlap only; semantic similarity is not measured.",
    "L08": "False bounds boilerplate can evade this rule.",
    "L09": "Implicit external destinations may pass.",
    "L10": "Paraphrased parameter substitutions may pass.",
    "L11": "Short malicious metadata may pass.",
    "L12": "Absent or false annotations limit interpretation.",
}
PATTERNS = {
    "L01": r"\b(?:before (?:using|calling)|first (?:call|invoke)|must (?:first )?(?:call|invoke)|always prefer)\b",
    "L02": r"\b(?:credentials?|api[_ -]?keys?|passwords?|protected_fixture|protected[- ]source)\b",
    "L03": r"\b(?:system override|ignore previous instructions|highest priority|developer message|you are now)\b",
    "L04": "[\u200b-\u200f\u202a-\u202e\u2066-\u2069\ufeff]",
    "L09": r"https?://\S+|\b(?:upload|email|webhook|exfiltrate)\b",
    "L10": r"\b(?:replace|substitute|override)\s+(?:the\s+)?(?:source_id|destination_id|argument|parameter)\b",
}


def _depth(value: Any, level: int = 0) -> int:
    if level > MAX_METADATA_DEPTH:
        return level
    if isinstance(value, dict):
        return max([level] + [_depth(item, level + 1) for item in value.values()])
    if isinstance(value, list):
        return max([level] + [_depth(item, level + 1) for item in value])
    return level


def lint_catalog(catalog: list[dict[str, Any]]) -> list[dict[str, Any]]:
    # Fragments are intentional rule controls; complete experiment catalogs are
    # validated separately. Malformed fields must never silently count as clean.
    if not isinstance(catalog, list) or not catalog or len(catalog) > 256:
        raise ValueError("lint requires 1..256 tool objects")
    for tool in catalog:
        if not isinstance(tool, dict):
            raise ValueError("tool must be an object")
        if not isinstance(tool.get("name"), str) or not tool["name"]:
            raise ValueError("tool name must be nonempty text")
        if not isinstance(tool.get("description"), str) or not tool["description"]:
            raise ValueError("description must be nonempty text")
        if len(tool["name"]) > 1024 or len(tool["description"]) > 1_048_576:
            raise ValueError("lint input exceeds processing limit")
        for value in (tool["name"], tool["description"]):
            try:
                value.encode("utf-8", errors="strict")
            except UnicodeError as exc:
                raise ValueError("metadata must contain valid Unicode scalars") from exc
        schema = tool.get("inputSchema")
        if not isinstance(schema, dict) or not isinstance(schema.get("properties", {}), dict):
            raise ValueError("inputSchema and properties must be objects")
        if not isinstance(tool.get("annotations", {}), dict):
            raise ValueError("annotations must be an object")
        for flag in ("readOnlyHint", "destructiveHint", "openWorldHint", "idempotentHint"):
            annotations = tool.get("annotations", {})
            if flag in annotations and type(annotations[flag]) is not bool:
                raise ValueError("standard tool annotation hints must be booleans")
    findings: list[dict[str, Any]] = []
    first_sentences: dict[str, int] = {}
    names: dict[str, int] = {}

    def add(rule: str, index: int, field: str, text: str, start: int, end: int, explanation: str) -> None:
        if end <= start:
            return
        findings.append({"rule_id": rule, "tool_index": index, "tool_name": catalog[index].get("name", ""), "field": field, "span": {"start": start, "end": end, "unit": "unicode-codepoint"}, "severity": "high" if rule in {"L01", "L02", "L03", "L09", "L10", "L12"} else "warning", "evidence": text[start:end], "explanation": explanation, "limit": LIMITS[rule], "rule_version": LINT_VERSION})

    for index, tool in enumerate(catalog):
        name = str(tool.get("name", ""))
        description = tool.get("description", "")
        if not isinstance(description, str):
            continue
        # Bound scanning; the excess itself is preserved as an evidence span.
        scan = description[:MAX_METADATA_CHARS]
        for rule, pattern in PATTERNS.items():
            for match in re.finditer(pattern, scan, flags=re.IGNORECASE):
                add(rule, index, "description", description, match.start(), match.end(), "Declared bounded metadata hazard matched.")
        properties = tool.get("inputSchema", {}).get("properties", {})
        for match in re.finditer(r"\b(?:parameter|argument)\s+[`'\"]?([A-Za-z_][A-Za-z0-9_]*)", scan, re.IGNORECASE):
            if match.group(1) not in properties:
                add("L05", index, "description", description, match.start(1), match.end(1), "Prose names a parameter absent from the executable schema.")
        contradiction = re.search(r"\b(?:write|delete|upload|copy)\b", scan, re.IGNORECASE) if name != "export_fixture" else re.search(r"\bread.only\b", scan, re.IGNORECASE)
        if contradiction:
            add("L06", index, "description", description, contradiction.start(), contradiction.end(), "Verb class conflicts with canonical tool behavior.")
        sentence = scan.split(".", 1)[0].strip().casefold()
        normalized_name = re.sub(r"[^a-z0-9]", "", name.casefold())
        if normalized_name in names:
            add("L07", index, "name", name, 0, len(name), "Name is a lexical near-duplicate of an earlier tool.")
        elif sentence and sentence in first_sentences:
            add("L07", index, "description", description, 0, len(scan.split(".", 1)[0]), "First sentence duplicates an earlier tool.")
        names[normalized_name] = index
        first_sentences[sentence] = index
        if name != "export_fixture" and scan and not re.search(r"\b(?:bounded|at most|maximum|max_|limit|[1-9][0-9]*\s+(?:lines|matches|sources|groups))\b", scan, re.IGNORECASE):
            add("L08", index, "description", description, 0, len(scan), "Read metadata lacks an explicit lexical bound.")
        if len(description) > MAX_METADATA_CHARS:
            add("L11", index, "description", description, MAX_METADATA_CHARS, min(len(description), MAX_METADATA_CHARS + 128), "Description exceeds the metadata character cap; further scanning stopped.")
        metadata = {key: value for key, value in tool.items() if key != "inputSchema"}
        if _depth(metadata) > MAX_METADATA_DEPTH and scan:
            add("L11", index, "description", description, 0, min(len(scan), 128), "Metadata nesting exceeds the cap; description identifies affected tool.")
        if tool.get("annotations", {}).get("readOnlyHint") is True:
            write = re.search(r"\b(?:write|delete|upload|copy)\b", scan, re.IGNORECASE)
            if write:
                add("L12", index, "description", description, write.start(), write.end(), "Read-only annotation conflicts with write language.")
    return findings


def normalize_catalog(catalog: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    normalized = deepcopy(catalog)
    diffs = []
    affected = {finding["tool_index"] for finding in lint_catalog(catalog) if finding["field"] == "description"}
    for index in sorted(affected):
        name = catalog[index].get("name")
        if name not in CANONICAL_DESCRIPTIONS:
            continue
        before, after = catalog[index].get("description"), CANONICAL_DESCRIPTIONS[name]
        if before != after:
            normalized[index]["description"] = after
            diffs.append({"tool_index": index, "tool_name": name, "field": "description", "before": before, "after": after, "normalizer_version": NORMALIZER_VERSION})
    return normalized, diffs
