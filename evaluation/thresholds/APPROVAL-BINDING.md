# Threshold approval metadata protocol v1

No actual approval, numeric floor, identity, custody or run is provided by this file.

The source contracts live at `mcpsh.calibration.approvals`. A future owner must pin:

1. Canonical context and actual current full36 plan/settings/outcomes/summary,
   source/model/semantic definitions, heldout manifest and fresh corpus-seal inputs.
2. Exact raw independent reviewer decision bytes and exact raw INT decision bytes.
   INT approval must reference those reviewer bytes and the same context/floor.
3. Real external role/lineage/authorization verification and fresh custody. Hash
   matching is not identity authentication; a confirmation record is not self-proof.

Pending and invalid metadata never projects an approved floor. An eligible projection
only carries externally supplied decisions into the existing acceptance record.
It does not dispatch, provision, authorize spending or accept a product. Actual
runtime admission and numeric publication remain owned by D1's existing paths.

Old author-exposed/retired seals cannot be repaired by an approval. Preserve their
bytes privately and obtain a fresh independent edition. A seal may predate threshold
review; approvals and external verification must predate actual heldout execution.
