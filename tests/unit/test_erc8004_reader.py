"""Fixed-block RPC replay and immutable evidence; no public traffic in automated tests."""

import json
from pathlib import Path

import httpx
import pytest
from eth_abi import encode
from reputation_core.evidence import hash_bytes, strict_json
from reputation_core.models import Outcome, Reason
from reputation_platform.adapters.registries.erc8004 import (
    AKASHI_REF,
    REGISTRATION_URI,
    Erc8004RegistryReader,
)
from reputation_platform.infrastructure.evidence_store import EvidenceStore
from reputation_platform.infrastructure.network.audited_readonly import EvidencePersistenceError
from reputation_platform.infrastructure.network.safe_http import NetworkPolicyError, SafeHttpClient

ROOT = Path(__file__).resolve().parents[2]
SAVED = ROOT / "docs/testing/evidence/akashi-2026-10-11"
REGISTRATION = (SAVED / "008-registration.body").read_bytes()
OPENAPI = (SAVED / "006-openapi.body").read_bytes()
OWNER = "0x" + "12" * 20


class RegistryResponder:
    def __init__(self):
        self.requests = []
        self.owner = OWNER
        self.uri = REGISTRATION_URI
        self.block = 100
        self.registration = REGISTRATION
        self.openapi = OPENAPI
        self.change = lambda payload, result: result
        self.reorg = False

    def __call__(self, request):
        self.requests.append(request)
        if request.method == "GET":
            return httpx.Response(200, content=self.registration if request.url.path.endswith(
                "agent-registration.json") else self.openapi, headers={"content-type": "application/json"})
        payload = json.loads(request.content)
        method, params = payload["method"], payload["params"]
        if method == "eth_chainId":
            result = "0x2105"
        elif method == "eth_getBlockByNumber":
            number = 0 if params[0] == "0x0" else self.block
            digest = "01" if number == 0 else "02" if params[0] == "latest" or not self.reorg else "03"
            result = {"number": hex(number), "hash": "0x" + digest * 32}
        elif method == "eth_getCode":
            result = "0x60016000"
        elif params[0]["data"].startswith("0x6352211e"):
            result = "0x" + encode(["address"], [self.owner]).hex()
        else:
            result = "0x" + encode(["string"], [self.uri]).hex()
        result = self.change(payload, result)
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": payload["id"], "result": result})


@pytest.fixture
def reader_factory(tmp_path, monkeypatch):
    from reputation_platform.infrastructure.network import safe_http
    monkeypatch.setattr(safe_http, "PUBLIC_REQUEST_INTERVAL", 0)
    def create(responder):
        client = SafeHttpClient.public_readonly(enabled=True, transport=httpx.MockTransport(responder),
                                               resolver=lambda host: ["1.1.1.1"])
        return Erc8004RegistryReader(ROOT, client, EvidenceStore(tmp_path))
    return create


async def test_fixed_block_abi_metadata_and_evidence(reader_factory):
    responder = RegistryResponder()
    reader = reader_factory(responder)
    try:
        result = await reader.read(AKASHI_REF)
        assert result.core is not None, result.identity
        assert result.core.owner == OWNER and result.core.declared_executor is None
        assert result.core.read_block_number == "100"
        assert result.core.read_block_hash == "0x" + "02" * 32
        assert result.identity.registration_outcome == result.identity.metadata_outcome == Outcome.PASS
        assert result.identity.metadata_bytes_hash == hash_bytes(REGISTRATION)
        assert len(responder.requests) == 10 and len(result.evidence) == 20
        for request in responder.requests:
            if request.method == "POST":
                value = json.loads(request.content)
                if value["method"] in {"eth_call", "eth_getCode"}:
                    assert value["params"][-1] == "0x64"
            assert "authorization" not in request.headers and "cookie" not in request.headers
        responses = [strict_json(reader.evidence.read(record)) for record in result.evidence[1::2]]
        assert responses[-3]["response"]["raw_body_utf8"].encode() == REGISTRATION
        assert responses[-2]["response"]["raw_body_utf8"].encode() == OPENAPI
    finally:
        await reader.client.close()


@pytest.mark.parametrize("method,value", [
    ("eth_chainId", "0x1"), ("eth_chainId", True),
    ("eth_getCode", "0x"), ("eth_getCode", "0x0"),
    ("eth_getBlockByNumber", None), ("eth_getBlockByNumber", {"number": "0x0", "hash": "0x" + "00" * 32}),
    ("eth_call", "0x"), ("eth_call", "0x" + "00" * 32),
    ("eth_call", "0x" + encode(["address"], [OWNER]).hex() + "00" * 32),
])
async def test_invalid_rpc_is_unknown_without_guessed_snapshot(reader_factory, method, value):
    responder = RegistryResponder()
    responder.change = lambda payload, result: value if payload["method"] == method else result
    reader = reader_factory(responder)
    try:
        result = await reader.read(AKASHI_REF)
        assert result.core is None and result.identity.registration_outcome == Outcome.UNKNOWN
        assert result.identity.registration_reason == Reason.PLATFORM_RPC_ERROR
        assert result.evidence
        assert all(request.method == "POST" for request in responder.requests)
    finally:
        await reader.client.close()


@pytest.mark.parametrize("uri", ["http://127.0.0.1/admin", "https://attacker.example/registration", REGISTRATION_URI + "?token=secret"])
async def test_uri_changes_never_authorize_network(reader_factory, uri):
    responder = RegistryResponder()
    responder.uri = uri
    reader = reader_factory(responder)
    try:
        result = await reader.read(AKASHI_REF)
        assert result.core is None
        assert result.identity.registration_outcome == Outcome.PASS
        assert result.identity.metadata_outcome == Outcome.UNKNOWN
        assert all(request.method == "POST" for request in responder.requests)
    finally:
        await reader.client.close()


async def test_reorg_cannot_emit_snapshot(reader_factory):
    responder = RegistryResponder()
    responder.reorg = True
    reader = reader_factory(responder)
    try:
        result = await reader.read(AKASHI_REF)
        assert result.core is None and result.identity.registration_outcome == Outcome.UNKNOWN
        assert all(request.method == "POST" for request in responder.requests)
    finally:
        await reader.client.close()


async def test_sensitive_registration_is_not_saved_or_trusted(reader_factory):
    responder = RegistryResponder()
    responder.registration = b'{"accessToken":"secret-never-export"}'
    reader = reader_factory(responder)
    try:
        result = await reader.read(AKASHI_REF)
        assert result.core is None and result.identity.metadata_outcome == Outcome.UNKNOWN
        assert all(b"secret-never-export" not in reader.evidence.read(record) for record in result.evidence)
        with pytest.raises(NetworkPolicyError, match="SENSITIVE_METADATA"):
            await reader.client.request("GET", "https://anchor.akashi-notari.com", "/openapi.json")
    finally:
        await reader.client.close()


@pytest.mark.parametrize("field", ["endpoint", "description", "key"])
@pytest.mark.parametrize("control", ["", "\t", "\n", "\r"])
@pytest.mark.parametrize("authority", ["//", "\\\\", "/\\", "\\/"])
async def test_url_credentials_are_redacted_before_evidence_or_snapshot(
    reader_factory, field, control, authority,
):
    responder = RegistryResponder()
    metadata = json.loads(responder.registration)
    secret = "AUDIT_FAKE_CREDENTIAL_ONLY"
    url = f"https:{authority}audit-user:{secret}{control}@anchor.akashi-notari.com/mcp"
    if field == "endpoint":
        metadata["services"][1]["endpoint"] = url
    elif field == "description":
        metadata["description"] = "Connection example " + url
    else:
        metadata[url] = "public value"
    responder.registration = json.dumps(metadata).encode()
    reader = reader_factory(responder)
    try:
        result = await reader.read(AKASHI_REF)
        assert result.core is None and result.identity.metadata_outcome == Outcome.UNKNOWN
        assert all(secret.encode() not in reader.evidence.read(record) for record in result.evidence)
        metadata_response = next(
            value for record in result.evidence
            if (value := strict_json(reader.evidence.read(record))).get("path")
            == "/.well-known/agent-registration.json" and "response" in value
        )
        assert metadata_response["response"]["raw_body_utf8"] is None
        assert not metadata_response["response"]["raw_body_retained"]
        assert result.metadata_raw is None and result.identity.metadata is None
    finally:
        await reader.client.close()


async def test_evidence_failure_stops_before_network(reader_factory, monkeypatch):
    responder = RegistryResponder()
    reader = reader_factory(responder)
    monkeypatch.setattr(reader.evidence, "prepare_json", lambda *args: (_ for _ in ()).throw(OSError()))
    try:
        with pytest.raises(EvidencePersistenceError):
            await reader.read(AKASHI_REF)
        assert not responder.requests
        with pytest.raises(NetworkPolicyError, match="PUBLIC_EVIDENCE_SAVE_FAILED"):
            await reader.client.request("GET", "https://anchor.akashi-notari.com", "/openapi.json")
    finally:
        await reader.client.close()


async def test_token_uri_abi_cannot_smuggle_credentials_into_evidence(reader_factory):
    responder = RegistryResponder()
    responder.uri = REGISTRATION_URI + "?token=credential-never-export"
    reader = reader_factory(responder)
    try:
        result = await reader.read(AKASHI_REF)
        assert result.core is None and result.identity.metadata_outcome == Outcome.UNKNOWN
        secret_hex = b"credential-never-export".hex().encode()
        for record in result.evidence:
            raw = reader.evidence.read(record)
            assert secret_hex not in raw and b"credential-never-export" not in raw
        response = strict_json(reader.evidence.read(result.evidence[11]))["response"]
        assert response["raw_body_retained"] is False
    finally:
        await reader.client.close()


async def test_metadata_transport_failure_is_network_unknown(reader_factory):
    responder = RegistryResponder()
    def fail_metadata(request):
        if request.method == "GET":
            raise httpx.ConnectError("unavailable")
        return responder(request)
    reader = reader_factory(fail_metadata)
    try:
        result = await reader.read(AKASHI_REF)
        assert result.core is None and result.identity.registration_outcome == Outcome.PASS
        assert result.identity.metadata_reason == Reason.PLATFORM_NETWORK_ERROR
    finally:
        await reader.client.close()


@pytest.mark.parametrize("extra", ["error", "extra"])
async def test_invalid_rpc_envelope_opaque_hex_is_not_exported(reader_factory, extra):
    responder = RegistryResponder()
    secret_hex = b"opaque-credential-never-export".hex()
    def bad_envelope(request):
        response = responder(request)
        value = json.loads(response.content)
        value[extra] = {"data": secret_hex}
        return httpx.Response(200, json=value)
    reader = reader_factory(bad_envelope)
    try:
        result = await reader.read(AKASHI_REF)
        assert result.core is None and result.identity.registration_outcome == Outcome.UNKNOWN
        for record in result.evidence:
            raw = reader.evidence.read(record)
            assert secret_hex.encode() not in raw and b"opaque-credential-never-export" not in raw
        assert strict_json(reader.evidence.read(result.evidence[-1]))["response"]["raw_body_retained"] is False
    finally:
        await reader.client.close()
