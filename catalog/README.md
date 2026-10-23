# Catalog and development data

Canonical executable authority is `mcpsh.catalog.schemas.TOOL_SCHEMAS`; consumers use `schema_for()` defensive copies. `build_catalog(clean|ambiguous|poisoned)` changes presented descriptions only. `catalog_artifact()` records schema/metadata hashes and harness-controlled instance ID. The canonical trusted descriptions are in `mcpsh.catalog.CANONICAL_DESCRIPTIONS`, the only repair map.

`fixtures/dev/tasks.json` contains 36 public development tasks with explicitly scripted calls. `gold/dev/oracles.json` contains their scorer-only labels. Never serialize the gold file or complete fixture rows into a provider request. The selectors project only `task_id`, `user_request`, `allowed_source_ids`, `fixture_ref`.

`fixtures/dev/lint-labels.json` contains two positive/two benign cases for each of L01-L12 (48 total). `lint-bypasses.json` names twelve lexical/structural limits. Labels are agent-authored and unreviewed, not measured precision/recall or held-out evidence. Other rules may also flag the same text. A known miss is not a requirement to preserve that miss after a versioned rule improvement.

Rules scan up to 4096 description codepoints; L11 records excess and stops further scanning. Explicit metadata depth is capped at eight. Findings use Unicode-codepoint offsets and matched evidence. L05 recognizes only explicit parameter/argument names. L06 uses a small verb list, L07 lexical normalized-name/first-sentence matches, and L08 checks lexical bounds. These are bounded heuristics, not a safety certificate. Normalization replaces flagged descriptions from the trusted map, preserving IDs, annotations, schemas, ordering and functionality. Name collisions cannot be repaired by description replacement alone.

S1 request shapes were transcribed from the local snapshot at commit `0abc5d9b5d293eab5a76a9746a3b3a40444035f2`; no S1 reader implementation or conformance result is claimed. The extra four schemas and all overlays/lint/development fixtures are M5 authored. No third-party research data were copied. No fixtures, adapters, ledger, or application code were executed during Dirty Mode construction.
