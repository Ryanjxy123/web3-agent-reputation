"""Formal identity reads reuse pinned egress and durable public evidence."""

import asyncio
import json
import ssl
from pathlib import Path

import httpcore
import httpx
import pytest
from reputation_core.evidence import strict_json
from reputation_platform.infrastructure.evidence_store import EvidenceStore
from reputation_platform.infrastructure.network import safe_http
from reputation_platform.infrastructure.network.audited_readonly import (
    EvidencePersistenceError,
    audited_readonly_request,
)
from reputation_platform.infrastructure.network.safe_http import NetworkPolicyError, SafeHttpClient

RPC = safe_http.PUBLIC_RPC_ORIGIN
AGENT = safe_http.PUBLIC_ORIGIN
REGISTRY = safe_http.POC_IDENTITY_REGISTRY
OWNER = "0x6352211e" + f"{98097:064x}"
URI = "0xc87b56dd" + f"{98097:064x}"


def rpc(method, params):
    return {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}


@pytest.fixture(autouse=True)
def no_rate_wait(monkeypatch):
    monkeypatch.setattr(safe_http, "PUBLIC_REQUEST_INTERVAL", 0)


@pytest.mark.parametrize("method,params", [
    ("eth_chainId", []),
    ("eth_getBlockByNumber", ["0x0", False]),
    ("eth_getBlockByNumber", ["latest", False]),
    ("eth_getBlockByNumber", ["0x1abc", False]),
    ("eth_getCode", [REGISTRY, "0x1abc"]),
    ("eth_call", [{"to": REGISTRY, "data": OWNER}, "0x1abc"]),
    ("eth_call", [{"to": REGISTRY, "data": URI}, "0x1abc"]),
])
async def test_only_exact_formal_identity_reads_are_allowed(method, params):
    requests, hosts = [], []
    client = SafeHttpClient.public_readonly(
        enabled=True, resolver=lambda host: hosts.append(host) or ["1.1.1.1"],
        transport=httpx.MockTransport(
            lambda request: requests.append(request) or httpx.Response(200, json={"result": "0x1"}),
        ),
    )
    try:
        result = await client.request("POST", RPC, "/", json=rpc(method, params))
        assert result.status == 200 and hosts == ["mainnet.base.org"]
        assert json.loads(requests[0].content) == rpc(method, params)
        assert requests[0].headers["host"] == "mainnet.base.org"
    finally:
        await client.close()


@pytest.mark.parametrize("method,params", [
    ("eth_blockNumber", []),
    ("eth_chainId", ["0x0"]),
    ("eth_getBlockByNumber", ["pending", False]),
    ("eth_getBlockByNumber", ["earliest", False]),
    ("eth_getBlockByNumber", ["safe", False]),
    ("eth_getBlockByNumber", ["finalized", False]),
    ("eth_getBlockByNumber", ["0x01", False]),
    ("eth_getBlockByNumber", ["0x1abc", True]),
    ("eth_getBlockByNumber", ["0x1abc"]),
    ("eth_getBlockByHash", ["0x" + "12" * 32, False]),
    ("eth_getTransactionByHash", ["0x" + "12" * 32]),
    ("eth_getTransactionReceipt", ["0x" + "12" * 32]),
    ("eth_getLogs", [{"address": REGISTRY, "fromBlock": "0x0", "toBlock": "0x1"}]),
    ("eth_getCode", [REGISTRY, "latest"]),
    ("eth_getCode", ["0xe0c6bb0914be3e49e13ffbc389cf659871a1bcd3", "0x1abc"]),
    ("eth_call", [{"to": REGISTRY, "data": OWNER}, "latest"]),
    ("eth_call", [{"to": REGISTRY, "data": URI}, "pending"]),
    ("eth_call", [{"to": REGISTRY, "data": "0x6352211e" + f"{98098:064x}"}, "0x1abc"]),
    ("eth_call", [{"to": REGISTRY, "data": "0x095ea7b3" + "00" * 64}, "0x1abc"]),
    ("eth_call", [{"to": REGISTRY, "data": OWNER, "value": "0x0"}, "0x1abc"]),
    ("eth_sendRawTransaction", ["0x1234"]),
    ("eth_sendTransaction", [{"to": REGISTRY}]),
    ("eth_sign", [REGISTRY, "0x1234"]),
    ("personal_sign", ["0x1234", REGISTRY]),
])
async def test_other_rpc_reads_writes_and_signatures_fail_before_dns(method, params):
    def forbidden(_):
        pytest.fail("Disallowed RPC must not reach DNS or transport")
    client = SafeHttpClient.public_readonly(
        enabled=True, resolver=forbidden, transport=httpx.MockTransport(forbidden),
    )
    try:
        with pytest.raises(NetworkPolicyError, match="METHOD_OR_PATH_NOT_ALLOWED"):
            await client.request("POST", RPC, "/", json=rpc(method, params))
    finally:
        await client.close()


@pytest.mark.parametrize("path", ["/openapi.json", "/.well-known/agent-registration.json"])
async def test_registration_discovery_is_fixed_to_akashi_origin(path):
    hosts = []
    client = SafeHttpClient.public_readonly(
        enabled=True, resolver=lambda host: hosts.append(host) or ["1.1.1.1"],
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json={})),
    )
    try:
        assert (await client.request("GET", AGENT, path)).status == 200
        assert hosts == ["anchor.akashi-notari.com"]
        for origin, unsafe_path in (
            ("http://anchor.akashi-notari.com", path),
            ("https://anchor.akashi-notari.com:443", path),
            ("https://elsewhere.example", path),
            (RPC, path),
            (AGENT, path + "?url=http://127.0.0.1"),
            (AGENT, path + "#fragment"),
            (AGENT, "/.well-known/../agent-registration.json"),
        ):
            with pytest.raises(NetworkPolicyError):
                await client.request("GET", origin, unsafe_path)
        assert hosts == ["anchor.akashi-notari.com"]
    finally:
        await client.close()


async def test_rpc_uses_checked_ip_with_base_host_tls_and_no_connection_reuse():
    calls, writes, names, hosts = [], [], [], []

    class Stream(httpcore.AsyncMockStream):
        async def start_tls(self, ssl_context, server_hostname=None, timeout=None):
            assert ssl_context.check_hostname and ssl_context.verify_mode == ssl.CERT_REQUIRED
            names.append(server_hostname)
            return self

        async def write(self, buffer, timeout=None):
            writes.append(buffer)

    class Backend(httpcore.AsyncNetworkBackend):
        async def connect_tcp(self, host, port, **kwargs):
            calls.append((host, port))
            return Stream([b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: 2\r\n\r\n{}"])

    client = SafeHttpClient.public_readonly(
        enabled=True, resolver=lambda host: hosts.append(host) or ["1.1.1.1", "2606:4700::1111"],
    )
    client._public_backend.backend = Backend()
    try:
        await client.request("POST", RPC, "/", json=rpc("eth_chainId", []))
        await client.request("GET", AGENT, "/openapi.json")
        assert calls == [("1.1.1.1", 443), ("1.1.1.1", 443)]
        assert names == hosts == ["mainnet.base.org", "anchor.akashi-notari.com"]
        requests = [part for part in writes if part.startswith((b"POST ", b"GET "))]
        assert b"Host: mainnet.base.org\r\n" in requests[0]
        assert b"Host: anchor.akashi-notari.com\r\n" in requests[1]
        with pytest.raises(NetworkPolicyError, match="TARGET_NOT_ALLOWED"):
            await client._public_backend.connect_tcp("mainnet.base.org", 443)
    finally:
        await client.close()


async def test_base_mixed_private_dns_answer_is_rejected():
    client = SafeHttpClient.public_readonly(
        enabled=True, resolver=lambda _: ["1.1.1.1", "127.0.0.1"],
        transport=httpx.MockTransport(lambda _: pytest.fail("Private DNS must not reach transport")),
    )
    try:
        with pytest.raises(NetworkPolicyError, match="PUBLIC_IP_REQUIRED"):
            await client.request("POST", RPC, "/", json=rpc("eth_chainId", []))
    finally:
        await client.close()


async def test_audited_rpc_saves_intent_before_network_and_original_response(tmp_path):
    records = []
    store = EvidenceStore(tmp_path)
    raw = b'{"jsonrpc":"2.0","id":1,"result":"0x2105"}'
    def response(_):
        assert len(records) == 1
        intent = strict_json(store.read(records[0]))
        assert intent["origin"] == RPC and intent["request_json"] == rpc("eth_chainId", [])
        return httpx.Response(200, content=raw, headers={"content-type": "application/json"})
    client = SafeHttpClient.public_readonly(
        enabled=True, resolver=lambda _: ["1.1.1.1"], transport=httpx.MockTransport(response),
    )
    try:
        response = await audited_readonly_request(
            client, store, protocol="erc8004-readonly-v1", capability_id="identity",
            method="POST", origin=RPC, path="/", payload=rpc("eth_chainId", []), records=records,
        )
        assert response.body == raw and len(records) == 2
        saved = strict_json(store.read(records[1]))
        assert saved["response"]["raw_body_utf8"].encode() == raw
        assert saved["response"]["audit"]["resolved_ips"] == ["1.1.1.1"]
    finally:
        await client.close()


@pytest.mark.parametrize("failure", ["intent", "response"])
async def test_audited_evidence_failure_stops_client_before_further_egress(tmp_path, monkeypatch, failure):
    store, records, calls = EvidenceStore(tmp_path), [], []
    prepare = store.prepare_json
    def save(value, source, observed_at, trust_group):
        if source == "public-readonly-" + failure:
            raise OSError("private-path-never-exposed")
        return prepare(value, source, observed_at, trust_group)
    monkeypatch.setattr(store, "prepare_json", save)
    client = SafeHttpClient.public_readonly(
        enabled=True, resolver=lambda _: ["1.1.1.1"],
        transport=httpx.MockTransport(lambda r: calls.append(r) or httpx.Response(200, json={})),
    )
    try:
        with pytest.raises(EvidencePersistenceError, match="PUBLIC_EVIDENCE_SAVE_FAILED"):
            await audited_readonly_request(
                client, store, protocol="erc8004-readonly-v1", capability_id="identity",
                method="POST", origin=RPC, path="/", payload=rpc("eth_chainId", []), records=records,
            )
        with pytest.raises(NetworkPolicyError, match="PUBLIC_EVIDENCE_SAVE_FAILED"):
            await client.request("POST", RPC, "/", json=rpc("eth_chainId", []))
        assert len(calls) == (0 if failure == "intent" else 1)
    finally:
        await client.close()


async def test_audited_rpc_redacts_sensitive_body_but_keeps_response_for_caller(tmp_path):
    store, records = EvidenceStore(tmp_path), []
    client = SafeHttpClient.public_readonly(
        enabled=True, resolver=lambda _: ["1.1.1.1"],
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json={
            "jsonrpc": "2.0", "id": 1, "result": "0x2105", "accessToken": "private-credential",
        })),
    )
    try:
        response = await audited_readonly_request(
            client, store, protocol="erc8004-readonly-v1", capability_id="identity",
            method="POST", origin=RPC, path="/", payload=rpc("eth_chainId", []), records=records,
        )
        assert b"private-credential" in response.body
        assert all(b"private-credential" not in store.read(record) for record in records)
        saved = strict_json(store.read(records[-1]))["response"]
        assert saved["raw_body_utf8"] is None and not saved["raw_body_retained"]
        assert saved["json"]["accessToken"] == "[REDACTED]"
    finally:
        await client.close()


async def test_stopping_client_during_rate_wait_prevents_next_network_attempt(monkeypatch):
    calls = []
    sleeping, released = asyncio.Event(), asyncio.Event()
    async def wait(_):
        sleeping.set()
        await released.wait()
    monkeypatch.setattr(safe_http.asyncio, "sleep", wait)
    client = SafeHttpClient.public_readonly(
        enabled=True, resolver=lambda _: ["1.1.1.1"],
        transport=httpx.MockTransport(lambda r: calls.append(r) or httpx.Response(200, json={})),
    )
    try:
        await client.request("POST", RPC, "/", json=rpc("eth_chainId", []))
        client._next_request_at = asyncio.get_running_loop().time() + 10
        waiting = asyncio.create_task(client.request("POST", RPC, "/", json=rpc("eth_chainId", [])))
        await sleeping.wait()
        client.stop_public_readonly("PUBLIC_EVIDENCE_SAVE_FAILED")
        client._next_request_at = 0
        released.set()
        with pytest.raises(NetworkPolicyError, match="PUBLIC_EVIDENCE_SAVE_FAILED"):
            await waiting
        assert len(calls) == 1
    finally:
        await client.close()


async def test_openapi_paid_write_operations_do_not_stop_selected_free_proof():
    saved = Path(__file__).resolve().parents[2] / "docs/testing/evidence/akashi-2026-10-11/006-openapi.body"
    raw = saved.read_bytes()
    calls = []
    client = SafeHttpClient.public_readonly(
        enabled=True, resolver=lambda _: ["1.1.1.1"],
        transport=httpx.MockTransport(lambda r: calls.append(r) or httpx.Response(
            200, content=raw, headers={"content-type": "application/json"},
        )),
    )
    try:
        response = await client.request("GET", AGENT, "/openapi.json")
        assert response.body == raw and not response.audit["payment_required"]
        assert "validation_error" not in response.audit
        await client.request("GET", AGENT, "/.well-known/agent-registration.json")
        assert len(calls) == 2
    finally:
        await client.close()


@pytest.mark.parametrize("selected", [
    {"description": "Payment Required"},
    {"paymentRequired": True},
    {"x-payment-info": {"price": {"amount": "0.010000"}}},
    {"responses": {"402": {"description": "Payment Required"}}},
])
async def test_openapi_payment_on_selected_proof_operation_stops_future_requests(selected):
    calls = []
    client = SafeHttpClient.public_readonly(
        enabled=True, resolver=lambda _: ["1.1.1.1"],
        transport=httpx.MockTransport(lambda r: calls.append(r) or httpx.Response(
            200, json={"paths": {"/proof": {"get": selected}}},
        )),
    )
    try:
        response = await client.request("GET", AGENT, "/openapi.json")
        assert response.audit["payment_required"]
        with pytest.raises(NetworkPolicyError, match="PAYMENT_REQUIRED"):
            await client.request("GET", AGENT, "/.well-known/agent-registration.json")
        assert len(calls) == 1
    finally:
        await client.close()


@pytest.mark.parametrize("payload", [{}, {"paths": {}}, {"paths": {"/proof": {"post": {}}}}])
async def test_unknown_openapi_proof_operation_stops_future_requests(payload):
    client = SafeHttpClient.public_readonly(
        enabled=True, resolver=lambda _: ["1.1.1.1"],
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=payload)),
    )
    try:
        response = await client.request("GET", AGENT, "/openapi.json")
        assert response.audit["validation_error"] == "UNSUPPORTED_OPENAPI_PROOF"
        with pytest.raises(NetworkPolicyError, match="UNSUPPORTED_OPENAPI_PROOF"):
            await client.request("GET", AGENT, "/.well-known/agent-registration.json")
    finally:
        await client.close()


@pytest.mark.parametrize("status", [200, 400])
async def test_caller_response_redactor_omits_encoded_secret_without_mutating_result(tmp_path, status):
    store, records = EvidenceStore(tmp_path), []
    secret_uri = "https://user:credential-secret@elsewhere.example/token"
    encoded = "0x" + secret_uri.encode().hex()
    payload = {"jsonrpc": "2.0", "id": 1, "result": encoded}
    def redact_result(value):
        # The helper must detect even a callback that edits its provided object in place.
        value["result"] = "[UNSUPPORTED URI OMITTED]"
        return value
    client = SafeHttpClient.public_readonly(
        enabled=True, resolver=lambda _: ["1.1.1.1"],
        transport=httpx.MockTransport(lambda _: httpx.Response(status, json=payload)),
    )
    try:
        response = await audited_readonly_request(
            client, store, protocol="erc8004-readonly-v1", capability_id="identity",
            method="POST", origin=RPC, path="/", payload=rpc("eth_chainId", []), records=records,
            response_redactor=redact_result,
        )
        assert response.status == status and strict_json(response.body) == payload
        assert all(encoded.encode() not in store.read(record) for record in records)
        saved = strict_json(store.read(records[-1]))["response"]
        assert saved["json"]["result"] == "[UNSUPPORTED URI OMITTED]"
        assert saved["raw_body_utf8"] is None and not saved["raw_body_retained"]
    finally:
        await client.close()


async def test_response_redactor_preserves_safe_raw_and_payment_stop(tmp_path):
    store, records = EvidenceStore(tmp_path), []
    client = SafeHttpClient.public_readonly(
        enabled=True, resolver=lambda _: ["1.1.1.1"],
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json={"paymentRequired": True})),
    )
    try:
        response = await audited_readonly_request(
            client, store, protocol="erc8004-readonly-v1", capability_id="identity",
            method="POST", origin=RPC, path="/", payload=rpc("eth_chainId", []), records=records,
            response_redactor=lambda value: value,
        )
        saved = strict_json(store.read(records[-1]))["response"]
        assert response.audit["payment_required"] and saved["raw_body_utf8"].encode() == response.body
        with pytest.raises(NetworkPolicyError, match="PAYMENT_REQUIRED"):
            await client.request("POST", RPC, "/", json=rpc("eth_chainId", []))
    finally:
        await client.close()


@pytest.mark.parametrize("scope", ["document", "path"])
@pytest.mark.parametrize("payment", [
    {"paymentRequired": True},
    {"paymentRequirements": [{"amount": "1"}]},
    {"x-payment-info": {"price": {"amount": "0.010000"}}},
    {"x-payment-info": False},
    {"x402": False},
    {"x402Support": False},
    {"price": 0},
])
async def test_global_and_path_openapi_payment_limits_stop_free_operation(scope, payment):
    document = {"paths": {"/proof": {"get": {"operationId": "proof"}}}}
    node = document if scope == "document" else document["paths"]["/proof"]
    node.update(payment)
    calls = []
    client = SafeHttpClient.public_readonly(
        enabled=True, resolver=lambda _: ["1.1.1.1"],
        transport=httpx.MockTransport(lambda r: calls.append(r) or httpx.Response(200, json=document)),
    )
    try:
        response = await client.request("GET", AGENT, "/openapi.json")
        assert response.audit["payment_required"]
        with pytest.raises(NetworkPolicyError, match="PAYMENT_REQUIRED"):
            await client.request("GET", AGENT, "/.well-known/agent-registration.json")
        assert len(calls) == 1
    finally:
        await client.close()


async def test_unselected_openapi_write_on_same_path_is_ignored():
    document = {"paths": {"/proof": {
        "get": {"operationId": "proof"},
        "post": {"paymentRequired": True, "x-payment-info": {"price": 1}},
    }}}
    client = SafeHttpClient.public_readonly(
        enabled=True, resolver=lambda _: ["1.1.1.1"],
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=document)),
    )
    try:
        for _ in range(2):
            response = await client.request("GET", AGENT, "/openapi.json")
            assert not response.audit["payment_required"]
    finally:
        await client.close()
