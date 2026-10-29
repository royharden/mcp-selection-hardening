"""Normative omission regressions, authored only; no helpers/tests ran here."""

import hashlib

from mcpsh.conformance.requirements import audit_requirements, decode_requirements, requirements_source


def fixture():
    raw = requirements_source()
    inventory = decode_requirements(raw)
    # A test-only observation simulating all implementations; not production scope.
    mapping = {}
    for requirement in inventory.requirements:
        for probe_id in requirement.probe_ids:
            mapping.setdefault(probe_id, set()).update(requirement.tracks)
    registry = [{"probe_id": name, "tracks": sorted(tracks), "required": True} for name, tracks in sorted(mapping.items())]
    return raw, hashlib.sha256(raw).hexdigest(), inventory, registry


def audit(raw, pin, registry, results=()):
    return audit_requirements(raw, expected_requirements_manifest_sha256=pin,
        registry=registry, results=results, tracks=("filesystem-posix",))


def test_registry_deletion_cannot_shrink_denominator():
    # what_bug_this_catches: required boundaries disappear when a probe is removed.
    raw, pin, inventory, registry = fixture()
    complete = audit(raw, pin, registry)
    removed = audit(raw, pin, [row for row in registry if row["probe_id"] != "posix-symlink"])
    expected = sum("filesystem-posix" in row.tracks for row in inventory.requirements)
    assert complete["platforms"]["filesystem-posix"]["required_requirements"] == expected
    assert removed["platforms"]["filesystem-posix"]["required_requirements"] == expected
    assert removed["platforms"]["filesystem-posix"]["verdict"] == "pending"
    boundary = next(row for row in removed["platforms"]["filesystem-posix"]["requirements"] if row["requirement_id"] == "posix-no-follow")
    assert "registry.missing:posix-symlink" in boundary["violations"]


def test_duplicate_registry_row_does_not_count_as_coverage():
    # what_bug_this_catches: two implementations with the same ID hide ambiguity.
    raw, pin, _, registry = fixture()
    duplicate = next(row for row in registry if row["probe_id"] == "posix-symlink")
    result = audit(raw, pin, registry + [duplicate])
    boundary = next(row for row in result["platforms"]["filesystem-posix"]["requirements"] if row["requirement_id"] == "posix-no-follow")
    assert "registry.duplicate:posix-symlink" in boundary["violations"]
    assert boundary["covered"] is False


def test_all_implemented_but_no_actual_results_stays_pending():
    # what_bug_this_catches: source availability is treated as executed conformance.
    raw, pin, _, registry = fixture()
    result = audit(raw, pin, registry)
    platform = result["platforms"]["filesystem-posix"]
    assert platform["verdict"] == "pending"
    assert platform["covered_requirements"] == 0
    assert platform["filesystem_proof"] is False


def test_skipped_required_outcome_is_not_a_pass():
    # what_bug_this_catches: skip/unsupported is silently converted into success.
    raw, pin, _, registry = fixture()
    rows = [{"probe_id": row["probe_id"], "track": "filesystem-posix", "required": True,
             "status": "skipped", "evidence": {}} for row in registry]
    result = audit(raw, pin, registry, rows)
    assert result["platforms"]["filesystem-posix"]["verdict"] == "pending"


def test_memory_registration_cannot_cover_posix_requirement():
    # what_bug_this_catches: same tool/probe name erases the platform boundary.
    raw, pin, _, registry = fixture()
    rows = [{**row, "tracks": ["synthetic-memory"]} if row["probe_id"] == "posix-symlink" else row for row in registry]
    result = audit(raw, pin, rows)
    boundary = next(row for row in result["platforms"]["filesystem-posix"]["requirements"] if row["requirement_id"] == "posix-no-follow")
    assert "registry.wrong-scope-or-optional:posix-symlink" in boundary["violations"]


def test_external_inventory_pin_is_not_generated_as_approval():
    # what_bug_this_catches: decoded inventory hash is silently treated as approval.
    raw, _, _, registry = fixture()
    result = audit(raw, None, registry)
    assert result["authority_valid"] is False
    assert "requirements.external-pin" in result["violations"]
    assert result["platforms"]["filesystem-posix"]["verdict"] == "pending"
