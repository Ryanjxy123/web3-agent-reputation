"""Frozen public identity assertions never establish executor control or business success."""

import copy
import json
from pathlib import Path
from uuid import UUID

import pytest
from pydantic import ValidationError
from reputation_core.evidence import hash_bytes, hash_json, strict_json
from reputation_core.models import (
    AgentRef,
    AgentSnapshot,
    ChainIdentity,
    Outcome,
    Reason,
    SnapshotCore,
)
from reputation_core.models.public_identity import PublicIdentityRead, ReadonlyIdentityAssociation
from reputation_core.public_identity import (
    AKASHI_HTTP_URL,
    AKASHI_MCP_URL,
    associate_readonly_identity,
    normalized_public_metadata,
    parse_registration_metadata,
    readonly_endpoints,
)

SAVED = Path(__file__).resolve().parents[2] / "docs/testing/evidence/akashi-2026-10-11"
REGISTRATION = (SAVED / "008-registration.body").read_bytes()
OPENAPI = (SAVED / "006-openapi.body").read_bytes()
REF = AgentRef(chain_id="8453", registry_address="0x8004a169fb4a3325136eb29fa0ceb6d2e539a432",
               agent_id="98097")
CODE = hash_bytes(b"test-only-registry-code")
RAW_METADATA = {}


def associate_fixture(captured, target, protocol, **kwargs):
    if "metadata_raw" not in kwargs and captured.public_identity is not None:
        kwargs["metadata_raw"] = RAW_METADATA.get(captured.public_identity.metadata_bytes_hash)
    return associate_readonly_identity(captured, target, protocol, **kwargs)


def registration_raw(change):
    value = strict_json(REGISTRATION)
    change(value)
    return json.dumps(value).encode()


def snapshot(raw=REGISTRATION, *, owner="0x" + "12" * 20, uri=AKASHI_MCP_URL,
             block="100", openapi=OPENAPI):
    metadata = parse_registration_metadata(raw, REF)
    RAW_METADATA[hash_bytes(raw)] = raw
    read = PublicIdentityRead(
        abi_sha256="ab" * 32, registry_code_hash=CODE, rpc_source="test-only-rpc",
        source_hashes=(hash_bytes(b"test-only-rpc-response"),),
        metadata_bytes_hash=hash_bytes(raw), openapi_bytes_hash=hash_bytes(openapi),
        metadata=metadata, registration_outcome=Outcome.PASS, registration_reason=None,
        metadata_outcome=Outcome.PASS, metadata_reason=None,
    )
    core = SnapshotCore(
        agent_ref=REF, source_type="public_registry", owner=owner, declared_executor=None,
        agent_uri=uri, registry_revision=0, metadata_hash=hash_json(normalized_public_metadata(metadata)),
        normalized_metadata=normalized_public_metadata(metadata), endpoints=readonly_endpoints(metadata),
        read_block_number=block, read_block_hash=hash_bytes(block.encode()),
        captured_at="2026-10-11T00:00:00.000Z", registry_chain=ChainIdentity(
            chain_id=REF.chain_id, genesis_hash=hash_bytes(b"test-only-genesis"),
            deployment_instance_id=hash_bytes(b"test-only-domain"), registry_code_hash=CODE,
            instance_hash=hash_bytes(b"test-only-instance"),
        ),
    )
    return AgentSnapshot(snapshot_id=UUID("12345678-1234-4234-8234-123456789abc"), core=core,
                         public_identity=read, snapshot_hash=hash_json({
                             "core": core.model_dump(mode="json"),
                             "public_identity": read.model_dump(mode="json"),
                         }))


def test_real_registration_preserves_declarations_without_inventing_capabilities():
    metadata = parse_registration_metadata(REGISTRATION, REF)
    assert metadata.name == "Akashi Notari" and metadata.x402_support is True
    assert metadata.registration_agent_key == REF.key_text
    assert [service.name for service in metadata.services] == ["web", "MCP", "OpenAPI"]
    assert "capabilities" not in metadata.model_dump() and "executor" not in metadata.model_dump()
    endpoints = readonly_endpoints(metadata)
    assert {(endpoint.path, endpoint.method) for endpoint in endpoints} == {
        ("/mcp", "POST"), ("/proof", "GET"),
    }


@pytest.mark.parametrize("protocol,url,openapi", [
    ("akashi-mcp-readonly-v1", AKASHI_MCP_URL, None),
    ("akashi-http-readonly-v1", AKASHI_HTTP_URL, OPENAPI),
])
def test_endpoint_pass_is_separate_from_control_and_business(protocol, url, openapi):
    association = associate_fixture(snapshot(), url, protocol, openapi_raw=openapi)
    assert association.registration_outcome == Outcome.PASS
    assert association.endpoint_outcome == Outcome.PASS
    assert association.executor_outcome == association.business_outcome == Outcome.UNKNOWN
    assert association.executor_reason == Reason.BINDING_UNVERIFIED
    assert association.business_reason == Reason.INSUFFICIENT_SAMPLES


@pytest.mark.parametrize("raw", [
    b'{}', b'[]', b'null', b'{"name":"a","name":"b"}', b'\xef\xbb\xbf{}',
    b'{"value":NaN}', b'{"value":Infinity}', b'{"value":"\xff"}',
    b'{"value":"\\ud800"}', b' ' * (1024 * 1024 + 1),
    b'{"services":' + b'[' * 40 + b'0' + b']' * 40 + b'}',
], ids=["object", "array", "null", "duplicate", "bom", "nan", "infinity", "utf8",
        "surrogate", "oversized", "depth"])
def test_malformed_and_unbounded_documents_are_rejected(raw):
    with pytest.raises(ValueError, match="PUBLIC_METADATA_INVALID"):
        parse_registration_metadata(raw, REF)


@pytest.mark.parametrize("key", [
    "authorization", "cookie", "accessToken", "privateKey", "refresh-token", "clientSecret",
    "signed_transaction", "mnemonic", "mcpSessionId",
])
def test_sensitive_metadata_keys_never_escape_parser(key):
    raw = registration_raw(lambda value: value.update({key: "credential-secret"}))
    with pytest.raises(ValueError, match="PUBLIC_METADATA_SENSITIVE") as error:
        parse_registration_metadata(raw, REF)
    assert "credential-secret" not in str(error.value)


@pytest.mark.parametrize("description", [
    "Authorization: Bearer credential-secret", "privateKey=credential-secret",
    "-----BEGIN RSA PRIVATE KEY-----", "cookie: session-private",
])
def test_embedded_credentials_are_rejected(description):
    with pytest.raises(ValueError, match="PUBLIC_METADATA_SENSITIVE"):
        parse_registration_metadata(registration_raw(
            lambda value: value.update({"description": description})), REF)


@pytest.mark.parametrize("url", [
    "http://anchor.akashi-notari.com/mcp", "https://127.0.0.1/mcp",
    "https://169.254.169.254/mcp", "https://192.168.0.2/mcp", "https://localhost/mcp",
    "https://host.internal/mcp", "https://host.local/mcp", "https://[::1]/mcp",
    "https://user:credential-secret@anchor.akashi-notari.com/mcp",
    "https://anchor.akashi-notari.com:8443/mcp", "https://anchor.akashi-notari.com/mcp?token=x",
    "https://anchor.akashi-notari.com/mcp#fragment", "https://anchor.akashi-notari.com/%6dcp",
    "https://anchor.akashi-notari.com\\@evil.test/mcp", " https://anchor.akashi-notari.com/mcp",
    "\x00https://anchor.akashi-notari.com/mcp",
])
def test_unsafe_service_urls_are_rejected(url):
    raw = registration_raw(lambda value: value["services"][1].update({"endpoint": url}))
    with pytest.raises(ValueError):
        parse_registration_metadata(raw, REF)


@pytest.mark.parametrize("change", [
    lambda value: value.update({"type": "registration-v2"}),
    lambda value: value.update({"x402Support": "true"}),
    lambda value: value.update({"active": 1}),
    lambda value: value.update({"adapter_class": "remote.module"}),
    lambda value: value.update({"capabilities": ["anchor_record"]}),
    lambda value: value["services"][1].update({"headers": {"x-custom": "x"}}),
    lambda value: value["services"].append(copy.deepcopy(value["services"][1])),
    lambda value: value["registrations"][0].update({"agentId": True}),
    lambda value: value["registrations"][0].update({"agentRegistry": "eip155:08453:0x" + "12" * 20}),
])
def test_wrong_types_dynamic_extensions_and_ambiguous_services_are_rejected(change):
    with pytest.raises(ValueError, match="PUBLIC_METADATA_INVALID"):
        parse_registration_metadata(registration_raw(change), REF)


@pytest.mark.parametrize("change", [
    lambda value: value["registrations"][0].update({"agentId": 98098}),
    lambda value: value["registrations"][0].update({"agentRegistry": "eip155:1:0x" + "12" * 20}),
    lambda value: value["registrations"].append(copy.deepcopy(value["registrations"][0])),
])
def test_declared_registration_must_match_the_frozen_chain_identity(change):
    with pytest.raises(ValueError, match="PUBLIC_METADATA_IDENTITY_MISMATCH"):
        parse_registration_metadata(registration_raw(change), REF)


def test_large_agent_id_uses_uint256_string_without_precision_loss():
    large = str(2**256 - 1)
    ref = REF.model_copy(update={"agent_id": large})
    metadata = parse_registration_metadata(registration_raw(
        lambda value: value["registrations"][0].update({"agentId": large})), ref)
    assert metadata.registration_agent_key.endswith(large)


@pytest.mark.parametrize("url", [
    "https://evil.test/mcp", AKASHI_MCP_URL + "/", AKASHI_MCP_URL + "?session=secret",
    AKASHI_HTTP_URL, "https://anchor.akashi-notari.com:443/mcp",
    "https://user:credential-secret@anchor.akashi-notari.com/mcp",
])
def test_actual_target_must_match_exactly_without_leaking_credentials(url):
    association = associate_fixture(snapshot(), url, "akashi-mcp-readonly-v1")
    assert association.endpoint_outcome == Outcome.FAIL
    assert association.endpoint_reason == Reason.SEMANTIC_MISMATCH
    assert "credential-secret" not in association.model_dump_json()


def test_http_without_saved_openapi_is_unknown():
    association = associate_fixture(snapshot(), AKASHI_HTTP_URL, "akashi-http-readonly-v1")
    assert association.endpoint_outcome == Outcome.UNKNOWN
    assert association.endpoint_reason == Reason.MISSING_EVIDENCE


def test_http_openapi_bytes_commitment_is_checked_before_parsing():
    association = associate_fixture(snapshot(), AKASHI_HTTP_URL, "akashi-http-readonly-v1",
                                               openapi_raw=OPENAPI + b" ")
    assert association.endpoint_outcome == Outcome.UNKNOWN
    assert association.endpoint_reason == Reason.CONTENT_HASH_MISMATCH


def test_readonly_association_requires_saved_original_registration_bytes():
    result = associate_fixture(snapshot(), AKASHI_MCP_URL, "akashi-mcp-readonly-v1", metadata_raw=None)
    assert result.registration_outcome == Outcome.PASS
    assert result.endpoint_outcome == Outcome.UNKNOWN
    assert result.endpoint_reason == Reason.MISSING_EVIDENCE


def test_registration_bytes_are_checked_against_original_commitment():
    result = associate_fixture(snapshot(), AKASHI_MCP_URL, "akashi-mcp-readonly-v1",
                               metadata_raw=REGISTRATION + b" ")
    assert result.endpoint_outcome == Outcome.UNKNOWN
    assert result.endpoint_reason == Reason.CONTENT_HASH_MISMATCH


def test_saved_registration_original_is_reparsed_before_accepting_normalized_claims():
    original = snapshot()
    raw = registration_raw(lambda value: value.update({"name": "different-original-name"}))
    read = original.public_identity.model_copy(update={"metadata_bytes_hash": hash_bytes(raw)})
    changed = original.model_copy(update={"public_identity": read, "snapshot_hash": hash_json({
        "core": original.core.model_dump(mode="json"), "public_identity": read.model_dump(mode="json"),
    })})
    result = associate_fixture(changed, AKASHI_MCP_URL, "akashi-mcp-readonly-v1", metadata_raw=raw)
    assert result.endpoint_outcome == Outcome.UNKNOWN
    assert result.endpoint_reason == Reason.CONTENT_HASH_MISMATCH


def test_saved_original_that_cannot_parse_remains_unknown_even_with_matching_commitment():
    original = snapshot()
    raw = b'{"accessToken":"never-export-credential"}'
    read = original.public_identity.model_copy(update={"metadata_bytes_hash": hash_bytes(raw)})
    changed = original.model_copy(update={"public_identity": read, "snapshot_hash": hash_json({
        "core": original.core.model_dump(mode="json"), "public_identity": read.model_dump(mode="json"),
    })})
    result = associate_fixture(changed, AKASHI_MCP_URL, "akashi-mcp-readonly-v1", metadata_raw=raw)
    assert result.endpoint_outcome == Outcome.UNKNOWN
    assert result.endpoint_reason == Reason.SCHEMA_ERROR
    assert "never-export-credential" not in result.model_dump_json()


@pytest.mark.parametrize("request_body", [{}, {"required": True}, {"required": False, "content": {}}])
def test_get_with_any_body_definition_cannot_match_the_no_body_static_adapter(request_body):
    value = strict_json(OPENAPI)
    value["paths"]["/proof"]["get"]["requestBody"] = request_body
    raw = json.dumps(value).encode()
    result = associate_fixture(snapshot(openapi=raw), AKASHI_HTTP_URL,
                               "akashi-http-readonly-v1", openapi_raw=raw)
    assert result.endpoint_outcome == Outcome.FAIL


@pytest.mark.parametrize("change", [
    lambda value: value["paths"]["/proof"]["get"].pop("parameters"),
    lambda value: value["paths"]["/proof"]["get"].update({"parameters": {}}),
    lambda value: value["paths"]["/proof"]["get"]["parameters"].append(
        {"name": "mode", "in": "query", "required": True, "schema": {"type": "string"}}),
    lambda value: value["paths"]["/proof"]["get"]["parameters"][0].update({"required": True}),
    lambda value: value["paths"]["/proof"]["get"]["parameters"][0].update({"in": "header"}),
    lambda value: value["paths"]["/proof"]["get"]["parameters"][0].update({"name": "tx"}),
    lambda value: value["paths"]["/proof"]["get"]["parameters"][0].update({"schema": {"type": "integer"}}),
    lambda value: value["paths"]["/proof"]["get"]["parameters"][0].update({"schema": {"$ref": "remote"}}),
    lambda value: value["paths"]["/proof"]["get"]["parameters"][0].update({"style": "matrix"}),
    lambda value: value["paths"]["/proof"].update({"parameters": [{"name": "extra", "required": True}]}),
])
def test_get_parameters_must_match_only_the_supported_optional_tx_hash_contract(change):
    value = strict_json(OPENAPI)
    change(value)
    raw = json.dumps(value).encode()
    result = associate_fixture(snapshot(openapi=raw), AKASHI_HTTP_URL,
                               "akashi-http-readonly-v1", openapi_raw=raw)
    assert result.endpoint_outcome == Outcome.FAIL


@pytest.mark.parametrize("location", ["document", "path", "operation"])
@pytest.mark.parametrize("declaration", [True, False, None])
@pytest.mark.parametrize("field", [
    "paymentRequired", "payment_required", "requiresPayment", "requires_payment",
    "paymentRequirements", "x402Version", "x402Support", "x-payment-info", "x402", "price",
])
def test_selected_call_cannot_ignore_explicit_global_or_path_payment_declarations(
    location, field, declaration
):
    value = strict_json(OPENAPI)
    node = value if location == "document" else value["paths"]["/proof"]
    if location == "operation":
        node = node["get"]
    node[field] = declaration
    raw = json.dumps(value).encode()
    result = associate_fixture(snapshot(openapi=raw), AKASHI_HTTP_URL,
                               "akashi-http-readonly-v1", openapi_raw=raw)
    assert result.endpoint_outcome == Outcome.FAIL


@pytest.mark.parametrize("change", [
    lambda value: value.update({"servers": [{"url": "https://evil.test"}]}),
    lambda value: value["paths"]["/proof"].update({"servers": [{"url": "https://evil.test"}]}),
    lambda value: value["paths"]["/proof"].update({"$ref": "https://evil.test/tool"}),
    lambda value: value["paths"]["/proof"].update({"x-payment-info": {"price": 1}}),
    lambda value: value["paths"]["/proof"]["get"].update({"servers": [{"url": "https://evil.test"}]}),
    lambda value: value["paths"]["/proof"]["get"].update({"security": [{"key": []}]}),
    lambda value: value["paths"]["/proof"]["get"].update({"x-payment-info": {"price": 1}}),
    lambda value: value["paths"]["/proof"]["get"]["responses"].update({"402": {"description": "pay"}}),
    lambda value: value["paths"]["/proof"]["get"].update({"$ref": "https://evil.test/tool"}),
    lambda value: value["paths"]["/proof"]["get"].update({"callbacks": {}}),
    lambda value: value["paths"]["/proof"]["get"].update({"operationId": "anchor"}),
])
def test_http_doc_must_declare_the_same_static_free_get_operation(change):
    value = strict_json(OPENAPI)
    change(value)
    raw = json.dumps(value).encode()
    association = associate_fixture(snapshot(openapi=raw), AKASHI_HTTP_URL,
                                               "akashi-http-readonly-v1", openapi_raw=raw)
    assert association.endpoint_outcome == Outcome.FAIL
    assert association.endpoint_reason == Reason.SEMANTIC_MISMATCH


def test_sensitive_openapi_is_unknown_even_when_its_commitment_matches():
    value = strict_json(OPENAPI)
    value["info"]["description"] = "Authorization: Bearer credential-secret"
    raw = json.dumps(value).encode()
    association = associate_fixture(snapshot(openapi=raw), AKASHI_HTTP_URL,
                                               "akashi-http-readonly-v1", openapi_raw=raw)
    assert association.endpoint_outcome == Outcome.UNKNOWN
    assert association.endpoint_reason == Reason.SCHEMA_ERROR
    assert "credential-secret" not in association.model_dump_json()


@pytest.mark.parametrize("registration_outcome,registration_reason", [
    (Outcome.UNKNOWN, Reason.PLATFORM_RPC_ERROR), (Outcome.FAIL, Reason.SEMANTIC_MISMATCH),
])
def test_unverified_registration_cannot_inherit_endpoint_pass(
    registration_outcome, registration_reason
):
    original = snapshot()
    read = original.public_identity.model_copy(update={
        "registration_outcome": registration_outcome, "registration_reason": registration_reason,
    })
    changed = original.model_copy(update={"public_identity": read, "snapshot_hash": hash_json({
        "core": original.core.model_dump(mode="json"), "public_identity": read.model_dump(mode="json"),
    })})
    association = associate_fixture(changed, AKASHI_MCP_URL, "akashi-mcp-readonly-v1")
    assert association.registration_outcome == registration_outcome
    assert association.endpoint_outcome == association.executor_outcome == Outcome.UNKNOWN


def test_metadata_parse_failure_remains_unknown_independently_of_registration():
    original = snapshot()
    read = original.public_identity.model_copy(update={
        "metadata": None, "metadata_outcome": Outcome.UNKNOWN, "metadata_reason": Reason.SCHEMA_ERROR,
    })
    changed = original.model_copy(update={"public_identity": read, "snapshot_hash": hash_json({
        "core": original.core.model_dump(mode="json"), "public_identity": read.model_dump(mode="json"),
    })})
    association = associate_fixture(changed, AKASHI_MCP_URL, "akashi-mcp-readonly-v1")
    assert association.registration_outcome == Outcome.PASS
    assert association.endpoint_outcome == Outcome.UNKNOWN
    assert association.endpoint_reason == Reason.SCHEMA_ERROR


@pytest.mark.parametrize("change", [
    {"owner": "0x" + "34" * 20}, {"uri": "https://anchor.akashi-notari.com/agent-registration.json"},
    {"block": "101"},
])
def test_owner_uri_or_fixed_block_changes_create_distinct_versions(change):
    before, after = snapshot(), snapshot(**change)
    assert before.snapshot_hash != after.snapshot_hash
    assert before.core.owner == "0x" + "12" * 20
    association = associate_fixture(after, AKASHI_MCP_URL, "akashi-mcp-readonly-v1")
    assert association.snapshot_hash == after.snapshot_hash
    assert association.executor_outcome == Outcome.UNKNOWN


def test_endpoint_and_raw_metadata_updates_are_distinct_append_only_versions():
    before = snapshot()
    changed_raw = registration_raw(lambda value: value["services"][1].update({"version": "future"}))
    after = snapshot(changed_raw)
    assert before.snapshot_hash != after.snapshot_hash
    association = associate_fixture(after, AKASHI_MCP_URL, "akashi-mcp-readonly-v1")
    assert association.registration_outcome == Outcome.PASS
    assert association.endpoint_outcome == Outcome.FAIL
    whitespace = snapshot(REGISTRATION + b" ")
    assert whitespace.core.metadata_hash == before.core.metadata_hash
    assert whitespace.snapshot_hash != before.snapshot_hash


@pytest.mark.parametrize("field,value", [
    ("owner", "0x" + "34" * 20), ("declared_executor", "0x" + "34" * 20),
    ("normalized_metadata", {}), ("endpoints", ()),
])
def test_tampered_snapshot_never_passes_association(field, value):
    original = snapshot()
    changed = original.model_copy(update={"core": original.core.model_copy(update={field: value})})
    association = associate_fixture(changed, AKASHI_MCP_URL, "akashi-mcp-readonly-v1")
    assert association.registration_outcome == association.endpoint_outcome == Outcome.UNKNOWN
    assert association.endpoint_reason == Reason.CONTENT_HASH_MISMATCH


def test_tampered_additional_read_provenance_is_committed_by_snapshot_hash():
    original = snapshot()
    changed = original.model_copy(update={"public_identity": original.public_identity.model_copy(
        update={"rpc_source": "different-rpc"})})
    association = associate_fixture(changed, AKASHI_MCP_URL, "akashi-mcp-readonly-v1")
    assert association.registration_outcome == association.endpoint_outcome == Outcome.UNKNOWN
    assert association.endpoint_reason == Reason.CONTENT_HASH_MISMATCH


def test_historical_snapshot_does_not_gain_public_identity_from_endpoint_alone():
    original = snapshot()
    historical = original.model_copy(update={"public_identity": None,
                                              "snapshot_hash": hash_json(original.core.model_dump(mode="json"))})
    association = associate_fixture(historical, AKASHI_MCP_URL, "akashi-mcp-readonly-v1")
    assert association.registration_outcome == association.endpoint_outcome == Outcome.UNKNOWN
    assert "public_identity" not in historical.model_dump(mode="json")


def test_public_read_statuses_cannot_turn_failed_metadata_into_trusted_declarations():
    data = snapshot().public_identity.model_dump(mode="json")
    data.update({"metadata_outcome": "UNKNOWN", "metadata_reason": "SCHEMA_ERROR"})
    with pytest.raises(ValidationError, match="unverified metadata"):
        PublicIdentityRead.model_validate(data)


@pytest.mark.parametrize("field,value", [
    ("registry_code_hash", None), ("metadata_bytes_hash", None), ("registration_reason", "SCHEMA_ERROR"),
])
def test_pass_requires_valid_provenance_and_reason_consistency(field, value):
    data = snapshot().public_identity.model_dump(mode="json")
    data[field] = value
    with pytest.raises(ValidationError):
        PublicIdentityRead.model_validate(data)


@pytest.mark.parametrize("field,value", [("executor_outcome", "PASS"), ("business_outcome", "PASS")])
def test_limited_readonly_association_cannot_be_deserialized_as_control_or_business_pass(field, value):
    data = associate_fixture(snapshot(), AKASHI_MCP_URL,
                                      "akashi-mcp-readonly-v1").model_dump(mode="json")
    data[field] = value
    with pytest.raises(ValidationError):
        ReadonlyIdentityAssociation.model_validate(data)
