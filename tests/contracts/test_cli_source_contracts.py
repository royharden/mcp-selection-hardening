"""Meaningful CLI regression SOURCE, authored but not run during Dirty Mode."""

import json

import pytest

from mcpsh.cli import main


def test_default_catalog_export_stays_a_bare_nine_tool_list(capsys):
    """what_bug_this_catches: adding artifacts silently breaks existing list consumers."""
    assert main(["catalog", "export"]) == 0
    catalog = json.loads(capsys.readouterr().out)
    assert isinstance(catalog, list)
    assert len(catalog) == 9
    assert len({tool["name"] for tool in catalog}) == 9


def test_artifact_export_and_raw_validation_share_identity(tmp_path, capsys):
    """what_bug_this_catches: CLI strips artifact identity/order before validation."""
    assert main(["catalog", "export", "--artifact", "--ordering-seed", "17"]) == 0
    raw = capsys.readouterr().out
    artifact = json.loads(raw)
    assert artifact["record"]["ordering_seed"] == 17
    assert artifact["record"]["tool_names"] == [tool["name"] for tool in artifact["catalog"]]
    path = tmp_path / "public-catalog.json"
    path.write_text(raw, encoding="utf-8")
    assert main(["catalog", "validate", "--artifact", "--input", str(path)]) == 0
    assert json.loads(capsys.readouterr().out)["valid"] is True


def test_duplicate_artifact_json_key_is_not_repaired(tmp_path, capsys):
    """what_bug_this_catches: permissive pre-parsing hides duplicate transport fields."""
    assert main(["catalog", "export", "--artifact"]) == 0
    raw = capsys.readouterr().out
    artifact = json.loads(raw)
    duplicate = '{"artifact_version":' + json.dumps(artifact["artifact_version"]) + ',' + raw.lstrip()[1:]
    path = tmp_path / "duplicate-artifact.json"
    path.write_text(duplicate, encoding="utf-8")
    assert main(["catalog", "validate", "--artifact", "--input", str(path)]) == 2
    assert "rejected input" in capsys.readouterr().err


@pytest.mark.parametrize("request_data", [
    {"tracks": ["synthetic-memory"], "approval_id": "PUBLIC-ONLY"},
    {"tracks": ["synthetic-memory"], "runtime_authorized": True,
     "disposable_authorized": False, "approval_id": "PUBLIC-ONLY"},
])
def test_conformance_cli_cannot_start_without_both_explicit_grants(tmp_path, monkeypatch, request_data):
    """what_bug_this_catches: the earlier server-check path started a backend by default."""
    import mcpsh.conformance

    def forbidden(*args, **kwargs):
        raise AssertionError("backend entrypoint was reached without activation")

    monkeypatch.setattr(mcpsh.conformance, "run_conformance", forbidden)
    path = tmp_path / "public-probe-request.json"
    path.write_text(json.dumps(request_data), encoding="utf-8")
    assert main(["server-check", "--request", str(path)]) == 2


def test_external_authority_pin_is_checked_before_edition_read(tmp_path, monkeypatch):
    """what_bug_this_catches: a self-described edition becomes its own trust authority."""
    import mcpsh.evidence

    def forbidden(*args, **kwargs):
        raise AssertionError("untrusted authority reached the edition reader")

    monkeypatch.setattr(mcpsh.evidence, "read_edition", forbidden)
    path = tmp_path / "public-scope-authority.json"
    path.write_text("{}", encoding="utf-8")
    assert main(["evidence-check", "--root", str(tmp_path), "--authority", str(path),
                 "--authority-sha256", "0" * 64]) == 2


def test_conformance_external_pins_are_forwarded_unchanged(tmp_path, monkeypatch):
    """Catches treating a freshly calculated resource hash as external admission."""
    import mcpsh.conformance
    from types import SimpleNamespace

    supplied = {}

    def fake_run(probe_request, **pins):
        supplied.update(pins)
        return SimpleNamespace(to_dict=lambda: {"platforms": {"synthetic-memory": {"verdict": "pending"}}})

    monkeypatch.setattr(mcpsh.conformance, "run_conformance", fake_run)
    path = tmp_path / "public-probe-request.json"
    path.write_text(json.dumps({"tracks": ["synthetic-memory"], "runtime_authorized": True,
                                "disposable_authorized": True, "approval_id": "public-source-test"}),
                    encoding="utf-8")
    assert main(["server-check", "--request", str(path),
                 "--semantic-manifest-sha256", "a" * 64,
                 "--requirements-manifest-sha256", "b" * 64]) == 2
    assert supplied == {"expected_semantic_manifest_sha256": "a" * 64,
                        "expected_requirements_manifest_sha256": "b" * 64}


def test_lint_artifact_keeps_unicode_field_evidence(tmp_path, capsys):
    """what_bug_this_catches: artifact ingestion loses source text/span identity."""
    assert main(["catalog", "export", "--artifact", "--condition", "poisoned"]) == 0
    raw = capsys.readouterr().out
    path = tmp_path / "public-poisoned-artifact.json"
    path.write_text(raw, encoding="utf-8")
    assert main(["lint", "--input", str(path)]) == 1
    findings = json.loads(capsys.readouterr().out)["findings"]
    invisible = [finding for finding in findings if finding["rule_id"] == "L04"]
    assert invisible
    assert all(finding["field_sha256"] and finding["byte_span"] for finding in invisible)
