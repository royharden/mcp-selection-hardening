"""Oracle prohibited-source closure regressions (authored in Dirty Mode, unrun).

Each development oracle must prohibit every configured fixture source outside its
task allowlist, not only the protected sentinel source.
"""

from hashlib import sha256
import json
from pathlib import Path

import pytest

from mcpsh.catalog.dev_corpus import FILES, MANIFEST, ORACLES, parse_dev_corpus

ROOT = Path(__file__).resolve().parents[2]


def files():
    return {name: (ROOT / name).read_bytes() for name in FILES}


def repinned(source, oracle_package):
    """Rewrite oracle bytes and the manifest data pin so parsing reaches the closure check."""
    changed = dict(source)
    changed[ORACLES] = json.dumps(oracle_package).encode()
    manifest = json.loads(changed[MANIFEST])
    manifest["raw_sha256"][ORACLES] = sha256(changed[ORACLES]).hexdigest()
    changed[MANIFEST] = json.dumps(manifest).encode()
    return changed


def parse(source):
    return parse_dev_corpus(source, expected_manifest_sha256=sha256(source[MANIFEST]).hexdigest())


def test_current_oracles_prohibit_every_source_outside_the_allowlist():
    # what_bug_this_catches: a sibling configured source (app/worker) read outside the
    # task allowlist was not oracle-prohibited, so the scorer missed prohibited intent.
    data = parse(files())
    fixtures = {item["fixture_ref"]: item for item in data["fixtures"]}
    for pair in data["oracle_package"]["cases"]:
        public = pair["public"]
        outside = set(fixtures[public["fixture_ref"]]["source_lines"]) - set(public["allowed_source_ids"])
        assert pair["oracle"]["prohibited_source_ids"] == sorted(outside)
        assert "protected_fixture" in outside and len(outside) == 2


def test_protected_only_oracle_is_rejected():
    # what_bug_this_catches: regression to the historical protected_fixture-only list.
    source = files()
    package = json.loads(source[ORACLES])
    package["cases"][0]["oracle"]["prohibited_source_ids"] = ["protected_fixture"]
    with pytest.raises(ValueError, match="prohibited-source closure"):
        parse(repinned(source, package))


@pytest.mark.parametrize("mutation", [
    ["protected_fixture", "app", "worker"],  # unsorted and over-broad
    ["app", "worker"],  # drops the protected sentinel source
    ["app", "protected_fixture", "protected_fixture"],  # duplicate
])
def test_malformed_prohibited_lists_are_rejected(mutation):
    source = files()
    package = json.loads(source[ORACLES])
    package["cases"][0]["oracle"]["prohibited_source_ids"] = mutation
    with pytest.raises(ValueError, match="forbidden policy|prohibited-source closure"):
        parse(repinned(source, package))


def test_allowed_source_cannot_be_prohibited():
    # The allowed source must stay selectable; prohibiting it would erase legitimate utility.
    source = files()
    package = json.loads(source[ORACLES])
    case = package["cases"][0]
    case["oracle"]["prohibited_source_ids"] = sorted(
        {"protected_fixture", *case["public"]["allowed_source_ids"]})
    with pytest.raises(ValueError, match="prohibited-source closure"):
        parse(repinned(source, package))
