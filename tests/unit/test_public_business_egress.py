"""Fixed business RPC scope and authorization immediately before actual egress."""

import asyncio
import json
from types import SimpleNamespace

import httpx
import pytest
from reputation_core.evidence import strict_json
from reputation_platform.adapters.akashi_evidence import PROTOCOL, collect_public_task
from reputation_platform.application.errors import ApplicationError
from reputation_platform.infrastructure.evidence_store import EvidenceStore
from reputation_platform.infrastructure.network import safe_http
from reputation_platform.infrastructure.network.safe_http import NetworkPolicyError, SafeHttpClient

TX = safe_http.AKASHI_PROOF_TX
RPC = safe_http.PUBLIC_RPC_ORIGIN
AGENT = safe_http.PUBLIC_ORIGIN


@pytest.fixture(autouse=True)
def no_wait(monkeypatch):
    monkeypatch.setattr(safe_http, "PUBLIC_REQUEST_INTERVAL", 0)


def payload(method, params):
    return {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}


@pytest.mark.parametrize("method,params", [
    ("eth_getTransactionByHash", [TX]), ("eth_getTransactionReceipt", [TX]),
    ("eth_getBlockByHash", ["0x" + "12" * 32, False]),
])
async def test_business_scope_is_explicit_and_exact(method, params):
    calls = []
    client = SafeHttpClient.public_readonly(
        enabled=True, business_reads=True, resolver=lambda _: ["1.1.1.1"],
        transport=httpx.MockTransport(lambda request: calls.append(request)
                                     or httpx.Response(200, json={"result": None})),
    )
    try:
        assert (await client.request("POST", RPC, "/", json=payload(method, params))).status == 200
        assert json.loads(calls[0].content) == payload(method, params)
    finally:
        await client.close()


@pytest.mark.parametrize("method,params", [
    ("eth_getTransactionByHash", ["0x" + "12" * 32]),
    ("eth_getTransactionReceipt", ["0x" + "12" * 32]),
    ("eth_getTransactionByHash", [TX, "latest"]),
    ("eth_getBlockByHash", ["0x" + "12" * 32, True]),
    ("eth_getLogs", [{"fromBlock": "0x0", "toBlock": "0x1", "address": "0x" + "12" * 20}]),
    ("eth_sendTransaction", [{"to": "0x" + "12" * 20}]),
    ("eth_sendRawTransaction", ["0x1234"]),
    ("eth_sign", ["0x" + "12" * 20, "0x1234"]),
])
async def test_business_scope_rejects_unrelated_reads_writes_and_signatures(method, params):
    def forbidden(_):
        pytest.fail("Rejected scope reached DNS or HTTP transport")
    client = SafeHttpClient.public_readonly(
        enabled=True, business_reads=True, resolver=forbidden,
        transport=httpx.MockTransport(forbidden),
    )
    try:
        with pytest.raises(NetworkPolicyError, match="METHOD_OR_PATH_NOT_ALLOWED"):
            await client.request("POST", RPC, "/", json=payload(method, params))
    finally:
        await client.close()


async def test_guard_checks_every_request_after_dns_before_http():
    events = []
    def resolver(_):
        events.append("dns")
        return ["1.1.1.1"]
    async def guard(method, origin, path, body):
        events.append("guard")
        assert (method, origin, path, body) == ("GET", AGENT, "/proof?tx=" + TX, None)
        if events.count("guard") == 2:
            raise ApplicationError(409, "ACCESS_NOT_GRANTED", "Revoked before request.")
    client = SafeHttpClient.public_readonly(
        enabled=True, before_request=guard, resolver=resolver,
        transport=httpx.MockTransport(lambda _: events.append("http")
                                     or httpx.Response(200, json={})),
    )
    try:
        await client.request("GET", AGENT, "/proof?tx=" + TX)
        with pytest.raises(ApplicationError, match="Revoked"):
            await client.request("GET", AGENT, "/proof?tx=" + TX)
        assert events == ["dns", "guard", "http", "dns", "guard"]
    finally:
        await client.close()


async def test_guard_stop_prevents_transport_even_when_guard_returns():
    def forbidden(_):
        pytest.fail("Stopped request reached HTTP transport")
    async def stop(*_):
        client.stop_public_readonly("ACCESS_NOT_GRANTED")
    client = SafeHttpClient.public_readonly(
        enabled=True, before_request=stop, resolver=lambda _: ["1.1.1.1"],
        transport=httpx.MockTransport(forbidden),
    )
    try:
        with pytest.raises(NetworkPolicyError, match="ACCESS_NOT_GRANTED"):
            await client.request("GET", AGENT, "/proof?tx=" + TX)
    finally:
        await client.close()


async def test_authorization_wait_does_not_consume_network_timeout(monkeypatch):
    real_timeout = asyncio.timeout
    monkeypatch.setattr(safe_http.asyncio, "timeout", lambda _: real_timeout(0.05))
    async def guard(*_):
        await asyncio.sleep(0.1)
    client = SafeHttpClient.public_readonly(
        enabled=True, before_request=guard, resolver=lambda _: ["1.1.1.1"],
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json={})),
    )
    try:
        assert (await client.request("GET", AGENT, "/proof?tx=" + TX)).status == 200
    finally:
        await client.close()


@pytest.mark.parametrize("value", [0, 999, 60001, True, "1000"])
def test_configured_interval_rejects_invalid_or_too_fast_values(value):
    with pytest.raises(NetworkPolicyError, match="INVALID_PUBLIC_REQUEST_INTERVAL"):
        SafeHttpClient.public_readonly(enabled=True, interval_ms=value)


def slot(query=None):
    return SimpleNamespace(task=SimpleNamespace(
        query=query or {"tx": TX}, read_block_number="100",
        read_block_hash="0x" + "34" * 32,
    ))


def responder(calls, *, null_receipt=False):
    def respond(request):
        body = json.loads(request.content)
        calls.append(body)
        method, params = body["method"], body["params"]
        if method == "eth_chainId":
            result = "0x2105"
        elif method == "eth_getTransactionReceipt":
            result = None if null_receipt else {"blockNumber": "0x10", "blockHash": "0x" + "56" * 32}
        elif method == "eth_getTransactionByHash":
            result = {"hash": TX}
        else:
            result = {"number": params[0], "hash": "0x" + "34" * 32}
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": body["id"], "result": result})
    return respond


async def test_collector_freezes_head_and_keeps_all_original_rpc_pairs(tmp_path):
    calls = []
    client = SafeHttpClient.public_readonly(
        enabled=True, business_reads=True, resolver=lambda _: ["1.1.1.1"],
        transport=httpx.MockTransport(responder(calls)),
    )
    store = EvidenceStore(tmp_path)
    try:
        records = await collect_public_task(client, store, slot())
        assert len(calls) == 8 and len(records) == 16
        assert [body["method"] for body in calls] == [
            "eth_chainId", "eth_getBlockByNumber", "eth_getBlockByNumber",
            "eth_getTransactionByHash", "eth_getTransactionReceipt", "eth_getBlockByHash",
            "eth_getBlockByNumber", "eth_getBlockByNumber",
        ]
        assert calls[2]["params"] == calls[-1]["params"] == ["0x64", False]
        assert "latest" not in repr(calls)
        for record in records:
            raw = strict_json(store.read(record))
            assert raw["protocol"] == PROTOCOL and raw["origin"] == RPC
            if record.source == "public-readonly-response":
                assert raw["response"]["raw_body_retained"] is True
    finally:
        await client.close()


async def test_partial_rpc_failure_is_saved_without_retries(tmp_path):
    calls = []
    client = SafeHttpClient.public_readonly(
        enabled=True, business_reads=True, resolver=lambda _: ["1.1.1.1"],
        transport=httpx.MockTransport(responder(calls, null_receipt=True)),
    )
    store = EvidenceStore(tmp_path)
    try:
        records = await collect_public_task(client, store, slot())
        assert len(calls) == 5 and len(records) == 11
        assert records[-1].source == "public-business-collection-error"
        assert strict_json(store.read(records[-1]))["reason_code"] == "PLATFORM_RPC_ERROR"
    finally:
        await client.close()


async def test_authorization_abort_preserves_saved_intent_for_caller(tmp_path):
    calls, records = [], []
    async def revoked(*_):
        raise ApplicationError(409, "ACCESS_NOT_GRANTED", "Revoked before request.")
    client = SafeHttpClient.public_readonly(
        enabled=True, business_reads=True, before_request=revoked,
        resolver=lambda _: ["1.1.1.1"], transport=httpx.MockTransport(responder(calls)),
    )
    store = EvidenceStore(tmp_path)
    try:
        with pytest.raises(ApplicationError):
            await collect_public_task(client, store, slot(), records=records)
        assert calls == [] and len(records) == 1
        assert records[0].source == "public-readonly-intent"
        assert strict_json(store.read(records[0]))["request_json"]["method"] == "eth_chainId"
    finally:
        await client.close()


@pytest.mark.parametrize("query", [{"hash": "12" * 32}, {"hash": "not-a-sha256"}])
async def test_hash_search_never_follows_an_untrusted_transaction(tmp_path, query):
    def forbidden(_):
        pytest.fail("Hash/invalid probe made an independent transaction request")
    client = SafeHttpClient.public_readonly(
        enabled=True, business_reads=True, resolver=forbidden, transport=httpx.MockTransport(forbidden),
    )
    try:
        assert await collect_public_task(client, EvidenceStore(tmp_path), slot(query)) == ()
    finally:
        await client.close()
