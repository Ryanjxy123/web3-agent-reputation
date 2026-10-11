"""Offline protocol/evidence boundaries; live access is an explicit separate command."""

import json
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from reputation_core.akashi import normalize_proof
from reputation_core.evidence import strict_json
from reputation_core.models import Reason
from reputation_platform.adapters.akashi import (
    PROTOCOLS,
    AkashiReadonlyAdapter,
    EvidencePersistenceError,
)
from reputation_platform.infrastructure.evidence_store import EvidenceStore
from reputation_platform.infrastructure.network.safe_http import NetworkPolicyError, SafeHttpClient

ROOT = Path(__file__).resolve().parents[2]
SAVED = ROOT / "docs/testing/evidence/akashi-2026-10-11"
TX = "0xd01d3e019906321b7d410538aebb696dec806df1099756ec85ac7b2da91df7fc"


@pytest.fixture
def adapter_factory(tmp_path, monkeypatch):
    from reputation_platform.infrastructure.network import safe_http
    monkeypatch.setattr(safe_http, "PUBLIC_REQUEST_INTERVAL", 0)
    clients = []
    def create(responder, protocol=PROTOCOLS[0]):
        client = SafeHttpClient.public_readonly(
            enabled=True, transport=httpx.MockTransport(responder), resolver=lambda host: ["1.1.1.1"]
        )
        clients.append(client)
        return AkashiReadonlyAdapter(protocol, client, EvidenceStore(tmp_path))
    yield create


async def test_http_retains_real_published_bytes_without_claiming_business_pass(adapter_factory):
    published = next(SAVED.glob("*-positive-http-1.body")).read_bytes()
    requests = []
    def reply(request):
        requests.append(request)
        return httpx.Response(200, content=published, headers={"content-type": "application/json"})
    adapter = adapter_factory(reply)
    try:
        result = await adapter.query({"tx": TX}, uuid4())
        assert result.normalized == normalize_proof(strict_json(published))
        assert result.observation.accepted and result.observation.candidate_tx_hash is None
        assert len(requests) == 1 and len(result.evidence) == 2
        saved = strict_json(adapter.evidence.read(result.evidence[-1]))
        assert saved["response"]["raw_body_utf8"].encode() == published
        assert result.observation.evidence_refs == tuple(r.evidence_id for r in result.evidence)
    finally:
        await adapter.client.close()


async def test_mcp_handshake_and_static_free_tool_only(adapter_factory):
    calls = []
    def reply(request):
        payload = json.loads(request.content)
        calls.append(payload)
        method = payload["method"]
        if method == "notifications/initialized":
            return httpx.Response(202)
        filename = {"initialize": "019-mcp-initialize.body", "tools/list": "020-mcp-tools.body",
                    "tools/call": "028-positive-mcp.body"}[method]
        value = strict_json((SAVED / filename).read_bytes())
        value["id"] = payload["id"]
        return httpx.Response(200, json=value, headers={"mcp-session-id": "session-private"})
    adapter = adapter_factory(reply, PROTOCOLS[1])
    try:
        result = await adapter.query({"tx": TX}, uuid4())
        assert result.observation.accepted
        assert [c["method"] for c in calls] == [
            "initialize", "notifications/initialized", "tools/list", "tools/call",
        ]
        assert calls[-1]["params"] == {"name": "find_proof", "arguments": {"tx": TX}}
        assert len(result.evidence) == 8
        for record in result.evidence:
            assert b"session-private" not in adapter.evidence.read(record)
        saved = strict_json(adapter.evidence.read(result.evidence[-1]))
        assert saved["response"]["raw_body_retained"]
    finally:
        await adapter.client.close()


@pytest.mark.parametrize("query", [{}, {"tx": "http://127.0.0.1"}, {"tx": TX, "hash": TX},
                                    {"anchor_hash": TX}, {"hash": "secret-value"}])
async def test_invalid_input_never_sends(adapter_factory, query):
    calls = []
    adapter = adapter_factory(lambda r: calls.append(r))
    try:
        with pytest.raises(NetworkPolicyError, match="INVALID_PROOF_QUERY"):
            await adapter.query(query, uuid4())
        assert not calls
    finally:
        await adapter.client.close()


@pytest.mark.parametrize("status,expected", [(503, Reason.AGENT_SERVICE_ERROR),
                                            (429, Reason.RATE_LIMIT_UNATTRIBUTED),
                                            (400, Reason.SCHEMA_ERROR)])
async def test_error_status_is_preserved_without_retry(adapter_factory, status, expected):
    calls = []
    def reply(request):
        calls.append(request)
        return httpx.Response(status, json={"error": "unavailable"})
    adapter = adapter_factory(reply)
    try:
        result = await adapter.query({"hash": "not-a-sha256"}, uuid4())
        assert result.observation.reason_code == expected and not result.observation.accepted
        assert result.observation.http_status == status and len(calls) == 1
    finally:
        await adapter.client.close()


@pytest.mark.parametrize("key", ["token", "accessToken", "privateKey", "refreshToken"])
async def test_sensitive_json_is_redacted_before_cas_and_raw_is_omitted(adapter_factory, key):
    adapter = adapter_factory(lambda r: httpx.Response(200, json={
        "anchored": False, "proofs": [], key: "credential-secret",
        "nested": {"Authorization": "Bearer private"},
    }))
    try:
        result = await adapter.query({"hash": "ab" * 32}, uuid4())
        raw = adapter.evidence.read(result.evidence[-1])
        assert b"credential-secret" not in raw and b"Bearer private" not in raw
        assert strict_json(raw)["response"]["raw_body_utf8"] is None
    finally:
        await adapter.client.close()


async def test_sensitive_business_field_never_escapes_in_normalized_result(adapter_factory):
    proof = strict_json(next(SAVED.glob("*-positive-http-1.body")).read_bytes())
    proof["proofs"][0]["filename"] = "Authorization: Bearer business-secret"
    adapter = adapter_factory(lambda r: httpx.Response(200, json=proof))
    try:
        result = await adapter.query({"tx": TX}, uuid4())
        assert result.normalized is None and not result.observation.accepted
        assert result.observation.reason_code == Reason.SCHEMA_ERROR
        assert all(b"business-secret" not in adapter.evidence.read(r) for r in result.evidence)
    finally:
        await adapter.client.close()


@pytest.mark.parametrize("status,body", [(402, {"secret": "payment-secret"}),
                                       (200, {"code": "PAYMENT_REQUIRED"})])
async def test_payment_stops_calls_and_saves_status(adapter_factory, status, body):
    calls = []
    def reply(request):
        calls.append(request)
        return httpx.Response(status, json=body)
    adapter = adapter_factory(reply)
    try:
        result = await adapter.query({"tx": TX}, uuid4())
        assert not result.observation.accepted and result.observation.http_status == status
        with pytest.raises(NetworkPolicyError, match="STOPPED"):
            await adapter.query({"tx": TX}, uuid4())
        assert len(calls) == 1
        assert b"payment-secret" not in adapter.evidence.read(result.evidence[-1])
    finally:
        await adapter.client.close()


async def test_evidence_failure_prevents_first_send_and_stops_adapter(adapter_factory, monkeypatch):
    calls = []
    adapter = adapter_factory(lambda r: calls.append(r))
    def failed(*args):
        raise OSError("local-secret-path")
    monkeypatch.setattr(adapter.evidence, "prepare_json", failed)
    try:
        with pytest.raises(EvidencePersistenceError, match="SAVE_FAILED"):
            await adapter.query({"tx": TX}, uuid4())
        with pytest.raises(NetworkPolicyError, match="STOPPED"):
            await adapter.query({"tx": TX}, uuid4())
        assert not calls
    finally:
        await adapter.client.close()


async def test_mcp_wrong_id_stops_before_business_tool(adapter_factory):
    calls = []
    def reply(request):
        calls.append(request)
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": 99,
                                        "result": {"protocolVersion": "2025-11-25"}})
    adapter = adapter_factory(reply, PROTOCOLS[1])
    try:
        result = await adapter.query({"tx": TX}, uuid4())
        assert result.observation.reason_code == Reason.UNSUPPORTED_PROTOCOL
        with pytest.raises(NetworkPolicyError, match="STOPPED"):
            await adapter.query({"tx": TX}, uuid4())
        assert len(calls) == 1
    finally:
        await adapter.client.close()


@pytest.mark.parametrize("failed_method", ["notifications/initialized", "tools/list"])
async def test_partial_mcp_handshake_timeout_cannot_skip_tool_gate(adapter_factory, failed_method):
    calls = []
    def reply(request):
        payload = json.loads(request.content)
        calls.append(payload["method"])
        if payload["method"] == failed_method:
            raise httpx.ReadTimeout("upstream-sensitive-diagnostic")
        if payload["method"] == "notifications/initialized":
            return httpx.Response(202)
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": payload["id"],
                                        "result": {"protocolVersion": "2025-11-25"}})
    adapter = adapter_factory(reply, PROTOCOLS[1])
    try:
        result = await adapter.query({"tx": TX}, uuid4())
        assert result.observation.reason_code == Reason.SERVICE_TIMEOUT
        with pytest.raises(NetworkPolicyError, match="STOPPED"):
            await adapter.query({"tx": TX}, uuid4())
        assert "tools/call" not in calls
        assert all(b"upstream-sensitive" not in adapter.evidence.read(r) for r in result.evidence)
    finally:
        await adapter.client.close()


async def test_selected_readonly_tool_demanding_payment_never_runs(adapter_factory):
    calls = []
    def reply(request):
        payload = json.loads(request.content)
        calls.append(payload["method"])
        if payload["method"] == "notifications/initialized":
            return httpx.Response(202)
        result = {"protocolVersion": "2025-11-25"} if payload["method"] == "initialize" else {
            "tools": [{"name": "find_proof", "paymentRequired": True,
                       "description": "Payment required before each find_proof call",
                       "annotations": {"readOnlyHint": True}}],
        }
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": payload["id"], "result": result})
    adapter = adapter_factory(reply, PROTOCOLS[1])
    try:
        result = await adapter.query({"tx": TX}, uuid4())
        assert not result.observation.accepted and "tools/call" not in calls
        with pytest.raises(NetworkPolicyError, match="STOPPED"):
            await adapter.query({"tx": TX}, uuid4())
        last = strict_json(adapter.evidence.read(result.evidence[-1]))
        assert last["response"]["audit"]["payment_required"]
    finally:
        await adapter.client.close()
