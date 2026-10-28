"""Unrun consumer regressions; no evidence directories, hidden labels or probes."""

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from mcpsh.records import canonical_json, typed_hash
from mcpsh.runner.dossier import admit_dossier_metadata, assemble_offline_dossier


def metadata():
    pin = "a" * 64
    inputs = {field: pin for field in ("code_hash", "task_hash", "catalog_hash", "policy_hash",
                                      "scorer_hash", "observer_hash", "split_hash")}
    inputs.update(lock_hash=None, protocol_hash=None)
    return {"edition": {"index_sha256": pin, "manifest_sha256": pin, "candidate_commit": "b" * 40,
                         "revision": 1, "edition_id": "public-original", "mode": "replay",
                         "platform_scope": "synthetic-memory", "input_pins": inputs},
            "manifest_typed_sha256": pin}


def test_mismatched_typed_dossier_pin_rejects_before_any_edition_read():
    supplied = metadata()
    with pytest.raises(ValueError, match="external typed pin"):
        admit_dossier_metadata(canonical_json(supplied).encode(), b"{}",
                               expected_typed_authority_sha256="0" * 64)


@pytest.mark.parametrize("sources", [b'{"authentication":{"custody_confirmed":true}}', b'{"design":42}'])
def test_narrative_authentication_or_malformed_sources_are_not_accepted(sources):
    supplied = metadata()
    # Compute only this explicit public test fixture's typed record identity;
    # matching identity never authenticates any actor/custody/price/settlement.
    from mcpsh.evaluation.acceptance_evidence import DossierAuthority

    pin = typed_hash(DossierAuthority.model_validate_json(canonical_json(supplied)).model_dump(mode="json"))
    with pytest.raises(ValueError):
        admit_dossier_metadata(canonical_json(supplied).encode(), sources,
                               expected_typed_authority_sha256=pin)


def test_missing_saved_source_is_not_replaced_with_empty_edition():
    class RejectedEdition:
        def validate(self):
            raise ValueError("source test: missing original evidence")

    # The producer rejects this non-VerifiedEdition before any fabricated fallback.
    with pytest.raises(TypeError, match="VerifiedEdition"):
        assemble_offline_dossier(RejectedEdition(), authority=None, sources=None,
                                 expected_typed_authority_sha256="a" * 64,
                                 now=datetime(2026, 10, 23, tzinfo=timezone.utc))


def test_replay_and_missing_rows_stay_original_and_unauthenticated(monkeypatch):
    # Catches replay relabeling, missing-row denominator shrink and JSON-auth promotion.
    import mcpsh.evaluation.acceptance_evidence as producer

    outcome = SimpleNamespace(trial_id="public-existing", utility_basis="semantic-v2",
                              model_dump=lambda **kwargs: {"trial_id": "public-existing", "execution_mode": "replay"})
    trial = SimpleNamespace(outcome=outcome, repeat=1,
                            model_dump=lambda **kwargs: {"original_private": "PRIVATE-AUTHORED-DETAIL"})
    index = SimpleNamespace(platform_scope="synthetic-memory",
                             scheduled_trial_ids=("public-existing", "public-missing"))
    manifest = SimpleNamespace(model_dump=lambda **kwargs: {"mode": "replay"})
    edition = SimpleNamespace(validate=lambda: (index, manifest, (trial,), (), None))

    def assemble(_edition, **kwargs):
        assert not any(kwargs["authentication"].model_dump().values())
        return SimpleNamespace(version="verified-edition-acceptance-v1", source_index_sha256="a" * 64,
            authority_binding="pinned", authentication="unconfirmed", inspection_complete=False,
            recommendation="collect-required-evidence", outcomes=(outcome,),
            model_dump=lambda **options: {"private": "PRIVATE-AUTHORED-DETAIL"})

    monkeypatch.setattr(producer, "assemble_acceptance_dossier", assemble)
    view = assemble_offline_dossier(edition, authority=None, sources=None,
        expected_typed_authority_sha256="a" * 64, now=datetime(2026, 10, 23, tzinfo=timezone.utc))
    assert view.result["manifest"]["mode"] == "replay"
    assert len(view.result["rows"]) == view.result["scheduled_trials"] == 2
    assert view.result["rows"][1] == {"outcome": {"trial_id": "public-missing"}, "record_state": "unknown"}
    status = view.result["acceptance_dossier_status"]
    assert status["authentication"] == "unconfirmed" and status["missing_trials"] == 1
    assert status["runtime_authorized"] is False and "PRIVATE-AUTHORED-DETAIL" not in str(status)
