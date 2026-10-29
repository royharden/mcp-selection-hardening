"""Public normalization contracts; authored only, not executed in Dirty Mode."""

from copy import deepcopy

from mcpsh.catalog import build_catalog, validate_catalog
from mcpsh.lint_evaluation import evaluate_normalization


def test_poison_repair_preserves_all_executable_authority_and_order():
    # what_bug_this_catches: removal/schema narrowing masquerading as metadata repair.
    original = build_catalog("poisoned")
    snapshot = deepcopy(original)
    result = evaluate_normalization(original)
    assert result["status"] == "verified-source-invariants"
    assert result["schema_before_sha256"] == result["schema_after_sha256"]
    assert result["immutable_before_sha256"] == result["immutable_after_sha256"]
    assert result["ids_before"] == result["ids_after"]
    assert result["no_suppression"] is True
    assert original == snapshot
    assert result["diffs"]
    for before, after in zip(original, result["catalog"], strict=True):
        assert {k: v for k, v in before.items() if k != "description"} == {
            k: v for k, v in after.items() if k != "description"}


def test_missing_or_duplicate_ids_are_ineligible_instead_of_dropped():
    # what_bug_this_catches: invalid duplicate/missing catalogs earning repair credit.
    missing = build_catalog()[:-1]
    duplicate = build_catalog()
    duplicate[-1] = deepcopy(duplicate[0])
    for catalog in (missing, duplicate):
        result = evaluate_normalization(catalog)
        assert result["status"] == "ineligible"
        assert "catalog" not in result


def test_numeric_schema_bounds_reject_boolean_substitution():
    # what_bug_this_catches: Python True==1 silently accepting executable schema drift.
    catalog = build_catalog()
    tail = next(tool for tool in catalog if tool["name"] == "tail")
    tail["inputSchema"]["properties"]["lines"]["minimum"] = True
    assert any(issue["code"] == "SCHEMA_DRIFT" for issue in validate_catalog(catalog))
    assert evaluate_normalization(catalog)["status"] == "ineligible"


def test_unrecognized_paraphrase_is_not_claimed_repaired():
    # what_bug_this_catches: claiming semantic sanitization for unflagged paraphrases.
    catalog = build_catalog()
    tail = next(tool for tool in catalog if tool["name"] == "tail")
    tail["description"] = (
        "A preliminary artifact transfer would make this bounded read more reliable."
    )
    result = evaluate_normalization(catalog)
    assert result["status"] == "verified-source-invariants"
    assert result["catalog"] == catalog
    assert result["diffs"] == []
    assert result["before_sha256"] == result["after_sha256"]


def test_clean_catalog_is_not_rewritten_without_findings():
    # what_bug_this_catches: unconditional replacement credited as lint-triggered repair.
    catalog = build_catalog()
    result = evaluate_normalization(catalog)
    assert result["diffs"] == []
    assert result["input_unmutated"] is True
    assert result["runtime_functionality"] == "unverified"


def test_invalid_unicode_and_empty_description_are_ineligible():
    # what_bug_this_catches: malformed metadata becoming an effect-free clean sample.
    for description in ("", "Read bounded \ud800 lines."):
        catalog = build_catalog()
        catalog[0]["description"] = description
        assert evaluate_normalization(catalog)["status"] == "ineligible"
