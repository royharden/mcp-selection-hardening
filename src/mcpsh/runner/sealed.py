"""Bounded sealed-data consumers. No private corpus is bundled or opened on import."""

import copy
import hashlib
from pathlib import Path

from mcpsh.records import strict_json_loads

CONDITIONS = ("clean", "ambiguous", "poisoned")


def load_pinned_json(path: Path, *, expected: str, maximum_bytes: int,
                     product_root: Path, private: bool):
    resolved = path.resolve()
    if private and (resolved == product_root or product_root in resolved.parents):
        raise ValueError("sealed custody must remain outside the product repository")
    if not isinstance(expected, str) or len(expected) != 64 or any(
        character not in "0123456789abcdef" for character in expected
    ):
        raise ValueError("explicit raw SHA256 package pin required")
    with resolved.open("rb") as handle:
        raw = handle.read(maximum_bytes + 1)
    if len(raw) > maximum_bytes:
        raise ValueError("sealed package byte cap exceeded")
    if hashlib.sha256(raw).hexdigest() != expected:
        raise ValueError("sealed package bytes differ from approved pin")
    return strict_json_loads(raw)


def load_sealed_inputs(*, fixtures_path: Path, treatments_path: Path, manifest,
                       approval: dict, cases, product_root: Path):
    from mcpsh.broker.fixtures import normalize_fixture_payload
    from mcpsh.catalog.schemas import TOOL_SCHEMAS

    private = manifest.settings.get("corpus_phase") == "heldout"
    maximum_cases = 24 if private else 36
    pins = {}
    for name in ("fixtures_sha256", "treatments_sha256"):
        pin = manifest.settings.get(name)
        if approval.get(name) != pin:
            raise ValueError("sealed input approval pin differs from manifest")
        pins[name] = pin
    fixtures = load_pinned_json(fixtures_path, expected=pins["fixtures_sha256"],
                                maximum_bytes=8 * 1024 * 1024,
                                product_root=product_root, private=private)
    treatments = load_pinned_json(treatments_path, expected=pins["treatments_sha256"],
                                  maximum_bytes=16 * 1024 * 1024,
                                  product_root=product_root, private=private)
    if not isinstance(fixtures, list) or not 1 <= len(fixtures) <= maximum_cases:
        raise ValueError("sealed fixture count/type outside bounds")
    fixture_map = {}
    for payload in fixtures:
        normalized = normalize_fixture_payload(payload)
        reference = normalized["fixture_ref"]
        if reference in fixture_map:
            raise ValueError("duplicate sealed fixture reference")
        fixture_map[reference] = normalized
    if not isinstance(treatments, list) or not 1 <= len(treatments) <= maximum_cases:
        raise ValueError("sealed treatment count/type outside bounds")
    treatment_map = {}
    expected_fields = {"task_id", "executable_schema_change", "clean", "ambiguous", "poisoned",
                       "mechanism_family", "namespace_collision", "tool_order_seed"}
    for entry in treatments:
        if not isinstance(entry, dict) or set(entry) != expected_fields:
            raise ValueError("sealed treatment fields differ from schema")
        task_id = entry["task_id"]
        if not isinstance(task_id, str) or not 1 <= len(task_id.encode("utf-8")) <= 256:
            raise ValueError("bounded treatment task ID required")
        if task_id in treatment_map or entry["executable_schema_change"] is not False:
            raise ValueError("duplicate treatment or prohibited executable-schema change")
        seed = entry["tool_order_seed"]
        if type(seed) is not int or not 0 <= seed <= 2**63 - 1:
            raise ValueError("bounded deterministic tool-order seed required")
        # Custodian-only lineage is structurally checked but never retained in selector input.
        for key in ("mechanism_family", "namespace_collision"):
            if not isinstance(entry[key], str) or len(entry[key].encode("utf-8")) > 4096:
                raise ValueError("invalid private treatment metadata")
        projected = {"tool_order_seed": seed}
        for condition in CONDITIONS:
            overlay_set = entry[condition]
            if not isinstance(overlay_set, dict) or set(overlay_set) != {"overlay"}:
                raise ValueError("condition must contain only a metadata overlay")
            overlays = overlay_set["overlay"]
            if not isinstance(overlays, list) or len(overlays) > 9:
                raise ValueError("at most nine metadata overlays per condition")
            seen = set()
            projected[condition] = []
            for overlay in overlays:
                if not isinstance(overlay, dict) or set(overlay) != {"tool_name", "field", "value"}:
                    raise ValueError("metadata overlay fields differ from schema")
                name = overlay["tool_name"]
                if not isinstance(name, str) or name not in TOOL_SCHEMAS or name in seen or overlay["field"] != "description":
                    raise ValueError("overlay must name one canonical description field")
                value = overlay["value"]
                if not isinstance(value, str) or len(value.encode("utf-8")) > 16 * 1024:
                    raise ValueError("metadata overlay text exceeds byte cap")
                seen.add(name)
                projected[condition].append({"tool_name": name, "field": "description", "value": value})
        treatment_map[task_id] = projected
    task_ids = {task.task_id for task, _ in cases}
    if len(task_ids) != len(cases) or set(treatment_map) != task_ids:
        raise ValueError("sealed treatment/public-task join is incomplete or duplicated")
    references = {task.fixture_ref for task, _ in cases}
    if set(fixture_map) != references:
        raise ValueError("sealed fixture/public-task join is incomplete")
    for task, _ in cases:
        if len(set(task.allowed_source_ids)) != len(task.allowed_source_ids):
            raise ValueError("duplicate public task policy source ID")
        if set(fixture_map[task.fixture_ref]["allowed_source_ids"]) != set(task.allowed_source_ids):
            raise ValueError("sealed fixture policy differs from public task policy")
    return fixture_map, treatment_map


def treatment_catalog(treatment: dict, condition: str):
    from mcpsh.catalog import build_catalog
    from mcpsh.catalog.artifacts import build_catalog_artifact
    from mcpsh.catalog.schemas import TOOL_SCHEMAS

    if condition not in CONDITIONS:
        raise ValueError("unsupported sealed catalog condition")
    catalog = copy.deepcopy(build_catalog("clean"))
    by_name = {tool["name"]: tool for tool in catalog}
    for overlay in treatment[condition]:
        by_name[overlay["tool_name"]]["description"] = overlay["value"]
    catalog = build_catalog_artifact(condition, ordering_seed=treatment["tool_order_seed"],
                                     catalog=catalog)["catalog"]
    if len(catalog) != 9 or set(by_name) != set(TOOL_SCHEMAS) or any(
        tool["inputSchema"] != TOOL_SCHEMAS[tool["name"]] for tool in catalog
    ):
        raise ValueError("sealed metadata treatment changed executable catalog authority")
    return catalog
