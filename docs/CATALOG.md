# Versioned catalog artifacts

Construction source only: no CLI, parser, model import or regression test has
been executed during Dirty Mode. Bare list export remains a compatibility
consumer path; D1 owns CLI integration. Versioned artifact APIs live in
`mcpsh.catalog.artifacts` and perform no file/network I/O or publication.

```python
artifact = build_catalog_artifact("poisoned", ordering_seed=17,
                                  source_revision=None, normalized=False)
issues = validate_catalog_artifact(artifact)
text = serialize_catalog_artifact(artifact)
parsed = parse_catalog_artifact(text)
pins = artifact_pins(parsed, raw=text)
```

These are API examples for later activation, not commands run or measured
results. The builder accepts an optional complete `catalog=`; it defensively
copies and orders it rather than mutating the caller. `normalized=True` actually
invokes the versioned trusted-map operation in the future caller; it is not a
request to fake successful repair. The seed is an exact integer in 0..2**63-1;
booleans are rejected.

## Envelope and authority

The exact envelope fields are `artifact_version`, `catalog_version`, `condition`,
`record`, `catalog`, `provenance`, `integrity`. The `record` is the existing
shared `mcpsh.records.models.CatalogArtifact` JSON projection, with server ID,
ordered tool names, separate executable-schema/presented-metadata hashes,
overlay/normalizer versions and ordering seed. There is no competing shared
record model. On input, JSON string-array tool names are explicitly converted
to the strict record tuple; extra record fields and type coercion are rejected.

The harness server-instance ID is fixed; tool identity is that ID plus a
canonical name. Server-provided display names cannot replace it. All nine
canonical tools and their server-owned schemas are required. A self-consistent
external schema hash does not authorize schema changes: every executable schema
is also compared against the local canonical authority using typed JSON.
The module returns transport data; server execution must continue to use its
own canonical schemas rather than execute those supplied by an artifact.

Tool objects allow exactly name, description, inputSchema and annotations.
Annotations contain only the four named MCP boolean hints; they remain metadata,
not access authorization. No task/oracle/family labels belong in this envelope.
Description text is untrusted data, including control characters. A condition
declares the experimental class, not independent proof of how metadata was
authored; content hashes pin the actual descriptions. Likewise source revision
is a caller-supplied null/full lowercase Git/SHA digest, not verified Git history.

## Identity, ordering and bounds

`sha256-tool-rank-1` sorts canonical names by SHA256 of the ASCII string
`sha256-tool-rank-1:<decimal-seed>:<name>`, breaking any digest tie by name.
This is independent of Python's pseudorandom shuffle implementation. The seed,
declared names and actual catalog order must agree exactly. Schema identity
hashes the name-to-schema map, while presentation identity hashes the ordered
name/description/annotations array, so tool order remains experimental data.

Integrity uses SHA256 over canonical typed JSON of the envelope excluding its
`integrity` field. Object keys sort; arrays retain order/multiplicity; numbers,
booleans and strings retain distinct JSON representations. `artifact_pins`
returns this typed payload hash, both content hashes, qualified tool IDs and
seed. It adds a raw-byte hash only when explicitly given matching raw transport.
Whitespace/escape differences can share a typed identity while having distinct
raw identities. Neither digest is a signature, authorization or acceptance.

Raw and canonical transport are each capped at 1 MiB; descriptions are nonempty
and capped at 64 KiB UTF-8 per tool. Invalid Unicode scalars, duplicate JSON keys,
nonfinite values, unknown fields, version drift, missing/duplicate IDs, modified
schema constraints and mismatched hashes/order are rejected. Parser/serializer
raise `ValueError`; the object validator returns fixed code/message issues.
Do not repair an invalid artifact by dropping tools or accepting supplied schema.

## D1 and D7 integration

D1 may retain bare `catalog export` and add `--artifact` with optional seed using
`build_catalog_artifact`. For validation, an envelope goes through the strict
artifact validator/parser; a legacy list continues through `validate_catalog`.
Raw input must enter `parse_catalog_artifact` to retain duplicate-key rejection
and byte limits. Do not first parse it with permissive JSON or infer a raw hash
from reserialized data. Flags are D1-owned until integrated.

D7 may use `artifact_pins` for evidence linkage. Parsing an artifact does not
dispatch a tool, contact a provider, attest a model choice or prove enforcement.
`normalizer_version` identifies a declared operation; before/after treatment
evidence is required to establish the actual transformation.

Regression source covers typed/raw identity, schema/metadata separation,
rehashed schema attacks, seeded-order mismatch, strict fields/server IDs,
malformed JSON and transport bounds. Tests are authored only; later activation
must check real shared-model/parser/CLI interoperability and publisher linkage.

Current construction receipt, D5 2026-10-23: two new Python modules parsed with
`ast.parse`; eight regression functions authored, none executed. Static AST
inspection matched the seven canonical `CatalogArtifact` fields exactly.
Focused source review traced strict input rejection, canonical schema authority,
ordering, integrity and raw/typed identity. No application import, model
instantiation, parser/serializer call or CLI execution was used as validation.

## Metadata treatments and fidelity API

`mcpsh.catalog.treatments.build_treatment_artifact(before, descriptions=None,
normalize=False, condition=None)` accepts a valid before artifact and a mapping
of canonical tool IDs to bounded nonempty description strings. Keyword arguments
are explicit. Overlay keys cannot name schemas, annotations, unknown tools or
structured task/oracle labels. The trusted normalization map remains local code;
caller-supplied descriptions are untrusted experimental input, not a replacement
authority map. An optional condition is a declared experimental classification.

The treatment envelope has exact fields `version`, `before`, `after`,
`descriptions`, `normalize`, `normalizer_version`, `trusted_map_sha256`, `diffs`
and `integrity`. Both before/after are catalog-artifact envelopes. The original
overlay is retained even if later trusted-map normalization cancels its net text
change. Ordered diffs cover net description changes with full before/after text
and separate UTF-8 field hashes. Schema/ID/order/annotation projections must
remain identical; neither a removed tool nor a narrowed schema is repair.

`validate_treatment_artifact(value)` returns fixed code/message issues. It
reconstructs the overlay and normalization from the original, checks local
trusted-map identity, and compares the complete expected envelope; rehashing
fabricated diffs cannot make them valid. `parse_treatment_artifact(raw)` and
`serialize_treatment_artifact(value)` reject invalid input with `ValueError`.
Raw/typed treatment envelopes are each capped at 4 MiB; embedded catalog and
description caps still apply. No signatures or execution acceptance are implied.

`mcpsh.catalog.spans.resolve_field_span(catalog, tool_index=..., field=...,
start=..., end=..., unit="unicode-codepoint")` resolves a nonempty exact name or
description field span. It also accepts `unit="utf-8-byte"` only at scalar
boundaries. Results contain canonical `span` codepoint offsets, `byte_span`,
exact `evidence` and `field_sha256`. `enrich_finding(catalog, finding)` adds these
verified fields and rejects mismatched evidence, tool identity, byte offsets or
field hash. Index and offsets must be integers, never booleans. Input fields are
capped at 4 MiB UTF-8 for direct fragment evidence processing.

These offsets reference decoded field text encoded in UTF-8, not byte offsets
in the surrounding JSON transport. JSON escapes/whitespace have a separate raw
transport hash. Supplementary scalars, combining marks, CRLF and bidi controls
are preserved without NFC/newline rewriting. Byte offsets through a scalar and
isolated surrogate codepoints are invalid. Lint-evaluation findings now carry
this fidelity projection; bare lint CLI integration remains D1-owned.

Next construction receipt, D5 2026-10-23: five changed/new Python modules parsed
with `ast.parse`; ten new regression functions authored, none executed. Focused
manual tracing checked re-derived treatment history, immutable authority,
scalar-boundary rejection, supplementary/combining/CRLF fidelity and field hashes.
A concrete boolean-byte-offset alias was corrected during that inspection; the
two affected files were syntax-parsed after the change. The canonical schemas'
SHA256 remains `635a09e35e678bce89db07f4f1ab5ee8d01e1ce1c740407c1a26b62af2d9a6c4`.
No application imports, normalizer/parser calls, test runs or CLI execution
occurred. D1 still owns consumer/CLI/publisher integration; D7 may pin these
versioned artifacts. Runtime fidelity and shared-model interoperability remain
unverified until later activation.
