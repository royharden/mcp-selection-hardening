"""Public provider golden regression source; never executed in Dirty Mode.

Tool/schema/body encoding uses D7's actual pure preview, with the same encoder
used by send. No test-side request encoder or credential callback is used.
"""

from copy import deepcopy
import json

import pytest

from mcpsh.adapters.transports import ADAPTER_REVISION, AnthropicMessagesTransport, OpenAIChatTransport
from mcpsh.catalog.artifacts import build_catalog_artifact
from mcpsh.catalog.provider_contract import audit_call_projection, audit_provider_catalog


def encoded(provider, artifact):
    def forbidden_credential():
        raise AssertionError("pure golden path accessed credentials")

    codec_type = OpenAIChatTransport if provider == "openai" else AnthropicMessagesTransport
    codec = codec_type(credential=forbidden_credential)
    payload = {"provider": provider, "model": "synthetic-model", "task": {"user_request": "Inspect allowed diagnostics"},
               "tools": artifact["catalog"], "history": [], "max_output_tokens": 64}
    preview = codec.preview_request(payload, adapter_sha256="a" * 64)
    assert preview["adapter_revision"] == ADAPTER_REVISION
    return preview["encoded_body"]


def audit(provider, artifact, body):
    return audit_provider_catalog(artifact, body, provider=provider, model_id="synthetic-model",
                                  adapter_revision=ADAPTER_REVISION, adapter_sha256="a" * 64)


@pytest.mark.parametrize("provider", ["openai", "anthropic"])
def test_actual_codec_catalog_projection_retains_nine_schemas(provider):
    # what_bug_this_catches: schema required/enums/null/extra-field semantics lost in codec.
    artifact = build_catalog_artifact("poisoned", ordering_seed=31)
    result = audit(provider, artifact, encoded(provider, artifact))
    assert result["status"] == "valid"
    assert result["tools_checked"] == 9
    assert result["provider_interoperability"] == "unverified"


@pytest.mark.parametrize("provider", ["openai", "anthropic"])
def test_schema_omission_and_duplicate_tool_are_not_repaired(provider):
    # what_bug_this_catches: dropping unsupported schema constraints earning a valid arm.
    artifact = build_catalog_artifact()
    original = json.loads(encoded(provider, artifact))
    omitted = deepcopy(original)
    if provider == "openai":
        schema = omitted["tools"][0]["function"]["parameters"]
    else:
        schema = omitted["tools"][0]["input_schema"]
    schema.pop("additionalProperties")
    assert audit(provider, artifact, json.dumps(omitted).encode())["status"] == "invalid"
    duplicate = deepcopy(original)
    duplicate["tools"][0] = deepcopy(duplicate["tools"][1])
    assert audit(provider, artifact, json.dumps(duplicate).encode())["status"] == "invalid"


def test_wire_order_model_and_encoding_are_pinned():
    # what_bug_this_catches: another model/body or shuffled catalog reusing parity evidence.
    artifact = build_catalog_artifact()
    wire = json.loads(encoded("openai", artifact))
    wire["tools"].reverse()
    assert audit("openai", artifact, json.dumps(wire).encode())["status"] == "invalid"
    assert audit("openai", artifact, b'{"model":"one","model":"two"}')["status"] == "invalid"
    assert audit("openai", artifact, b'\xff')["status"] == "invalid"


@pytest.mark.parametrize("changed", ["2", True, None, 2.0])
def test_decoded_golden_arguments_keep_integer_string_bool_null_distinct(changed):
    # what_bug_this_catches: coercion or Python equality equating typed call arguments.
    expected = [{"name": "tail", "arguments": {"source_id": "app", "lines": 2}}]
    actual = [{"name": "tail", "arguments": {"source_id": "app", "lines": changed}}]
    assert audit_call_projection(expected, actual)["status"] == "invalid"


def test_extra_and_duplicate_calls_preserve_order_and_multiplicity():
    # what_bug_this_catches: set-based comparison erasing repeated/late unsafe selections.
    call = {"name": "tail", "arguments": {"source_id": "app", "lines": 2}}
    result = audit_call_projection([call], [call, deepcopy(call)])
    assert result["status"] == "invalid"
    assert result["extra_count"] == result["repeated_actual_count"] == 1
    assert audit_call_projection([call, call], [call, call])["status"] == "valid"


def test_missing_identity_and_unknown_dialects_never_credit_validity():
    # what_bug_this_catches: absent actual payload or adapter identity treated as valid.
    artifact = build_catalog_artifact()
    assert audit("openai", artifact, None)["status"] == "unavailable"
    result = audit_provider_catalog(artifact, b"{}", provider="unknown", model_id="synthetic",
                                    adapter_revision="unknown", adapter_sha256="a" * 64)
    assert result["status"] == "unsupported"
