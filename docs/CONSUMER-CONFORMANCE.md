# Portable M5 conformance contracts

Source authored under Dirty Mode. No bundle builder/export/example, import, test,
wheel build, backend, SDK, process or conformance probe has run. No empirical
result is included. A valid bundle attests source/schema integrity only.

## Producer and resource contract

`mcpsh.conformance.export.BundleInputs` takes the actual public case bytes,
required semantic manifest, canonical runtime schemas, three schema byte strings,
five public core source byte strings, and capability projection. Source keys are
grammar/parser/observer/policy/runtime_schema. Schemas use the canonical filenames
evidence-v1.schema.json, evidence-v2.schema.json and required-cases-v1.schema.json.
No competing tool, schema or required-case definitions are introduced.

`build_contract_bundle(inputs)` is pure and returns ContractBundle: deterministic
sorted `(relative_path, bytes)` entries plus bundle_sha256, manifest_sha256 and
runtime_schema_sha256. `.to_files()` returns the mapping. `packaged_bundle_inputs()`
is an explicit bounded metadata read, never backend activation.

D1 owns the exact wheel includes:

| Canonical source | Installed resource |
|---|---|
| fixtures/conformance/semantics-v1.json | mcpsh/conformance/data/semantics-v1.json |
| policy/conformance/evidence-v1.schema.json | mcpsh/conformance/data/schemas/evidence-v1.schema.json |
| policy/conformance/evidence-v2.schema.json | mcpsh/conformance/data/schemas/evidence-v2.schema.json |
| policy/conformance/required-cases-v1.schema.json | mcpsh/conformance/data/schemas/required-cases-v1.schema.json |

Checkout readers use canonical source paths; installed readers use only these
fixed package locations. Public core source pins bind installed matching.py,
parsing.py, observer/__init__.py, policy/__init__.py and catalog/schemas.py. Missing
resources are errors/unavailable, never an empty successful export. Do not copy
private/retired case data or substitute S1 operational acceptance.

## Format and pure validation

Format m5-conformance-bundle-v1 has exactly eight artifacts: bundle.json; the
public cases JSON; required-case, runtime-schema and capability JSON contracts;
and the three canonical closed JSON schemas. The index pins exact payload names,
byte counts and SHA256 values, required manifest, runtime schema identity,
grammar/parser/observer/policy/case versions and public source hashes.

`validate_contract_bundle(files, expected_bundle_sha256=...,
expected_manifest_sha256=..., expected_runtime_schema_sha256=...)` requires all
three externally supplied pins. bundle_sha256 identifies exact bundle.json bytes;
its closed file list pins every other byte. No self-generated digest is external
approval. Paths are canonical relative POSIX names from the exact fixed file set.
Unknown/duplicate/missing files, traversal/drive/UNC paths, changed bytes/IDs/versions,
remote schema references and unsupported claim promotion reject.

The result is valid plus verdict integrity-only or rejected, violations, runtime
acceptance pending, S1 operational acceptance false and per-platform pending or
component diagnostic-only. It never returns runtime/platform/product acceptance.
It is a compatibility/integrity check, not a general JSON Schema evaluator or
proof that observation narratives are truthful.

`write_contract_bundle(bundle, directory)` is an explicit future export into a new
directory, with no overwrite or deletion. Partial failures remain for disposition.
`read_contract_bundle(directory, expected_bundle_sha256=...)` reads only the fixed
eight public artifacts after pinning the index, refuses symlink resources and path
escapes, and enforces 256 KiB per file/2 MiB total. No archive extraction, listener,
provider, arbitrary executable/PID, background watcher or backend is involved.

## Claim and compatibility boundary

Origin is M5-owned synthetic fallback. Five request shapes retain S1 attribution;
this is not S1's operational filesystem acceptance or a takeover of its canonical
module. Pure/component diagnostics, actual memory, actual stdio and supported POSIX
evidence retain their own scopes. Memory/stdio cannot become filesystem proof.
Unknown/unavailable/unsupported results remain pending. A source bundle contains no
measured effect observations and cannot promote any track to passed.

Existing ConformanceRequest, run_conformance and report contracts remain unchanged.
The portable bundle reuses the existing semantic manifest and evidence-v1/v2 schemas;
older evidence-v1 remains structurally supported without inventing semantic-v2 proof.
Later actual conformance activation is a separate explicitly approved disposable
session. The detached consumer defaults to integrity-only.

## Detached consumer source

`examples/conformance_consumer.py` is intended for later use outside the checkout
with the installed M5 package. It does not add the checkout to sys.path, install
dependencies, read keys or activate any backend. Its explicit arguments are the
public bundle directory and required --bundle-sha256, --manifest-sha256 and
--runtime-schema-sha256 pins. Missing package/dependency/resource returns unavailable
with exit 2; rejected bytes/schema/claims returns exit 1; successful integrity-only
inspection returns exit 0. None of these means conformance passed.

Optional --evidence and --selection must be provided together. They read only those
explicit public files, bounded to 256 KiB each. Selection is a closed JSON object:
expected_evidence_sha256, expected_probe_id, expected_track, expected_request_sha256,
expected_source_pins, expected_server_instance_id, expected_fixture_payload_sha256.
The caller supplies this authority independently; evidence does not approve itself.

Pure `consumer.inspect_bundle(files, expected_bundle_sha256=...,
expected_manifest_sha256=..., expected_runtime_schema_sha256=..., evidence_raw=None,
evidence_selection=None)` reuses the portable bundle validator. Optional evidence
uses `inspect_consumer_evidence`: evidence v1 is legacy-v1-integrity-only and never
earns v2 semantic credit; evidence v2 uses its existing strict externally pinned
verifier. Unsupported versions reject without guessing. Component diagnostics stay
component diagnostics. Mixed observed/unknown effects retain their known effect
while remaining uncreditable. A single structurally creditable probe does not
finish a platform, so consumer conformance/runtime acceptance always stays pending.

The example has no optional activation path. Actual conformance remains a separate
explicit runtime/disposable approval through the existing session API. Conformance
request/report signatures are unchanged by this portable consumer package.

All compatibility regressions are authored source only. No example, export,
resource helper, import, test or bundle build was invoked during construction.

## Normative portable format v2

V1 above remains an explicit legacy integrity-only format. The new
`mcpsh.conformance.export_v2` adapter reuses its producer, loader and validator;
it does not redefine schemas or required cases. `packaged_normative_inputs()`
returns base BundleInputs, fixed normative bytes, and two extra canonical schemas.
`build_normative_bundle(base_inputs, requirements_raw=..., schemas=...)` returns
deterministic bytes with an additional requirements_manifest_sha256 receipt.
No construction helper is invoked merely by importing a module.

Bundle v2 has eleven fixed artifacts: the original eight, contracts/requirements-v1.json,
schemas/requirements-v1.schema.json and schemas/evidence-v3.schema.json. Its closed
v2 index pins normative identity/version and every added byte before checking the
closed legacy subset. Original bundle/semantic/runtime-schema pin checks remain.
Source-integrity validation cannot promote unsupported platform or S1 claims.

`validate_normative_bundle` adds optional expected_requirements_manifest_sha256.
Without it, integrity-only may be valid while requirements_authority_valid is false;
full conformance always remains pending. A supplied mismatching inventory pin
rejects. The semantic-case and normative-boundary pins are distinct authorities.
`read_portable_bundle` dispatches explicit v1/v2 resource sets and never downgrades
missing v2 data. `write_normative_bundle` uses the existing new-directory writer;
no exports were run here.

D1 additional resources are requirements-v1.json under mcpsh/conformance/data and
requirements-v1.schema.json/evidence-v3.schema.json under its data/schemas directory.
The detached example now reads either portable version and accepts optional
--requirements-sha256. Consumer inspect_bundle accepts the same optional keyword;
v3 per-probe inspection verifies the outer inventory pin plus all unchanged v2
external selections. Missing normative data/pins cannot grant normative credit.
Legacy v1/v2 evidence retains its earlier compatibility without full normative
credit. Component/memory cannot become POSIX proof; mixed known effects remain visible.
