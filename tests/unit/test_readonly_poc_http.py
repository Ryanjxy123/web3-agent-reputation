"""Offline transport proves the PoC cannot pay, sign, write or leave its whitelist."""

import asyncio

import httpx
import pytest
from reputation_platform.infrastructure.network import safe_http
from reputation_platform.infrastructure.network.safe_http import (
    POC_IDENTITY_REGISTRY,
    POC_SOURCE_REF,
    NetworkPolicyError,
    SafeHttpClient,
)

AGENT = "https://anchor.akashi-notari.com"
RPC = "https://mainnet.base.org"
HASH = "0x" + "ab" * 32
ADDRESS = "0x" + "ab" * 20


def rpc(method, params):
    return {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}


@pytest.mark.parametrize("method,origin,path,payload", [
    ("GET", "https://raw.githubusercontent.com", "/self-reality/verifier/main/README.md", None),
    ("GET", "https://raw.githubusercontent.com",
     f"/self-reality/verifier/{POC_SOURCE_REF}/workers/anchor/src/abi.js", None),
    ("GET", "https://api.github.com", "/repos/self-reality/verifier/commits/main", None),
    ("GET", "https://api.github.com", "/repos/self-reality/verifier/git/trees/main?recursive=1", None),
    ("GET", AGENT, "/health", None),
    ("GET", AGENT, "/openapi.json", None),
    ("GET", AGENT, "/llms.txt", None),
    ("GET", AGENT, "/.well-known/agent-registration.json", None),
    ("GET", AGENT, "/proof?tx=" + HASH, None),
    ("GET", AGENT, "/proof?hash=" + HASH[2:], None),
    ("GET", AGENT, "/proof?hash=not-a-sha256", None),
    ("POST", AGENT, "/mcp", rpc("initialize", {
        "protocolVersion": "2025-03-26", "capabilities": {},
        "clientInfo": {"name": "readonly-poc", "version": "1.0"},
    })),
    ("POST", AGENT, "/mcp", {"jsonrpc": "2.0", "method": "notifications/initialized"}),
    ("POST", AGENT, "/mcp", rpc("tools/list", {})),
    ("POST", AGENT, "/mcp", rpc("tools/call", {"name": "find_proof", "arguments": {"tx": HASH}})),
    ("POST", RPC, "/", rpc("eth_chainId", [])),
    ("POST", RPC, "/", rpc("eth_blockNumber", [])),
    ("POST", RPC, "/", rpc("eth_getTransactionByHash", [HASH])),
    ("POST", RPC, "/", rpc("eth_getTransactionReceipt", [HASH])),
    ("POST", RPC, "/", rpc("eth_getBlockByHash", [HASH, False])),
    ("POST", RPC, "/", rpc("eth_getBlockByNumber", ["latest", False])),
    ("POST", RPC, "/", rpc("eth_getBlockByNumber", ["0x1", False])),
    ("POST", RPC, "/", rpc("eth_getCode", [POC_IDENTITY_REGISTRY, "latest"])),
    ("POST", RPC, "/", rpc("eth_getLogs", [{
        "address": ADDRESS, "fromBlock": "0x1", "toBlock": "0x7d0", "topics": [HASH, None],
    }])),
    ("POST", RPC, "/", rpc("eth_call", [{
        "to": POC_IDENTITY_REGISTRY, "data": "0x6352211e" + f"{98097:064x}",
    }, "latest"])),
    ("POST", RPC, "/", rpc("eth_call", [{
        "to": POC_IDENTITY_REGISTRY, "data": "0xc87b56dd" + f"{98097:064x}",
    }, "0x1"])),
])
async def test_exact_readonly_paths_reach_transport_once(method, origin, path, payload):
    requests = []
    def observe(request):
        requests.append(request)
        return httpx.Response(200, json={"ok": True})
    client = SafeHttpClient.readonly_poc(transport=httpx.MockTransport(observe))
    try:
        observation = await client.request(method, origin, path, json=payload)
        assert observation.status == 200 and len(requests) == 1
        assert str(requests[0].url) == origin + path
        assert client.client.trust_env is False and not client.client.follow_redirects
    finally:
        await client.close()


@pytest.mark.parametrize("method,origin,path,payload", [
    ("GET", "https://example.com", "/health", None),
    ("GET", "http://anchor.akashi-notari.com", "/health", None),
    ("GET", AGENT + ":443", "/health", None),
    ("GET", AGENT, "//evil.example/health", None),
    ("GET", AGENT, "/health#fragment", None),
    ("GET", AGENT, "/proof?hash=" + HASH + "&hash=" + HASH, None),
    ("GET", AGENT, "/proof?tx=" + HASH + "&hash=" + HASH, None),
    ("GET", AGENT, "/proof?hash=" + HASH + "&url=https://evil.example", None),
    ("GET", AGENT, "/proof?tx=bad", None),
    ("GET", AGENT, "/proof?hash=bad", None),
    ("GET", AGENT, "/anchor", None),
    ("POST", AGENT, "/anchor", {"hash": HASH}),
    ("GET", AGENT, "/health", {"unexpected": "body"}),
    ("GET", "https://raw.githubusercontent.com", "/self-reality/verifier/main/.env", None),
    ("GET", "https://raw.githubusercontent.com", "/self-reality/verifier/other/README.md", None),
    ("GET", "https://raw.githubusercontent.com", "/self-reality/other/main/README.md", None),
    ("GET", "https://api.github.com", "/repos/self-reality/verifier/issues", None),
    ("POST", AGENT, "/mcp", rpc("tools/call", {"name": "anchor_hash", "arguments": {"hash": HASH}})),
    ("POST", AGENT, "/mcp", rpc("tools/call", {"name": "find_proof", "arguments": {"url": "https://evil.example"}})),
    ("POST", AGENT, "/mcp", rpc("tools/call", {"name": "find_proof", "arguments": {"hash": HASH, "pay": True}})),
    ("POST", AGENT, "/mcp", rpc("initialize", {"protocolVersion": "2025-03-26", "capabilities": {"sampling": {}}, "clientInfo": {}})),
    ("POST", AGENT, "/mcp", rpc("notifications/initialized", {})),
    ("POST", RPC, "/", rpc("eth_sendRawTransaction", ["0x01"])),
    ("POST", RPC, "/", rpc("eth_sendTransaction", [{"to": ADDRESS}])),
    ("POST", RPC, "/", rpc("eth_sign", [ADDRESS, HASH])),
    ("POST", RPC, "/", rpc("personal_sign", [HASH, ADDRESS])),
    ("POST", RPC, "/", rpc("eth_getBlockByNumber", ["latest", True])),
    ("POST", RPC, "/", rpc("eth_getTransactionReceipt", [True])),
    ("POST", RPC, "/", rpc("eth_getCode", [ADDRESS, "latest"])),
    ("POST", RPC, "/", rpc("eth_getLogs", [{"address": ADDRESS, "fromBlock": "0x1", "toBlock": "0x7d1"}])),
    ("POST", RPC, "/", rpc("eth_getLogs", [{"address": ADDRESS, "fromBlock": "0x2", "toBlock": "0x1"}])),
    ("POST", RPC, "/", rpc("eth_getLogs", [{"fromBlock": "0x1", "toBlock": "0x1"}])),
    ("POST", RPC, "/", rpc("eth_getLogs", [{"address": ADDRESS, "fromBlock": "0x1", "toBlock": "latest"}])),
    ("POST", RPC, "/", rpc("eth_call", [{"to": ADDRESS, "data": "0x6352211e" + f"{98097:064x}"}, "latest"])),
    ("POST", RPC, "/", rpc("eth_call", [{"to": POC_IDENTITY_REGISTRY, "data": "0x6352211e" + f"{98098:064x}"}, "latest"])),
    ("POST", RPC, "/", rpc("eth_call", [{"to": POC_IDENTITY_REGISTRY, "data": "0x095ea7b3" + "00" * 64}, "latest"])),
    ("POST", RPC, "/", rpc("eth_call", [{"to": POC_IDENTITY_REGISTRY, "data": "0x6352211e" + f"{98097:064x}", "value": "0x1"}, "latest"])),
    ("POST", RPC, "/", [{"jsonrpc": "2.0", "id": 1, "method": "eth_chainId", "params": []}]),
    ("POST", RPC, "/", {"jsonrpc": "2.0", "id": True, "method": "eth_chainId", "params": []}),
    ("POST", RPC, "/", {"jsonrpc": "2.0", "id": 1, "method": {}, "params": []}),
])
async def test_paid_write_or_unbounded_requests_never_reach_transport(method, origin, path, payload):
    requests = []
    client = SafeHttpClient.readonly_poc(transport=httpx.MockTransport(
        lambda request: requests.append(request) or httpx.Response(200, json={}),
    ))
    try:
        with pytest.raises(NetworkPolicyError):
            await client.request(method, origin, path, json=payload)
        assert requests == []
    finally:
        await client.close()


@pytest.mark.parametrize("headers", [
    {"Authorization": "Bearer forbidden"},
    {"X-PAYMENT": "forbidden"},
    {"Cookie": "forbidden"},
    {"MCP-Session-Id": "session\r\nX-PAYMENT: forbidden"},
])
async def test_no_credential_payment_or_injected_headers(headers):
    requests = []
    client = SafeHttpClient.readonly_poc(transport=httpx.MockTransport(
        lambda request: requests.append(request) or httpx.Response(200, json={}),
    ))
    try:
        with pytest.raises(NetworkPolicyError, match="HEADERS_NOT_ALLOWED"):
            await client.request("POST", AGENT, "/mcp", json=rpc("tools/list", {}), headers=headers)
        assert not requests
    finally:
        await client.close()


async def test_sse_and_mcp_session_headers_are_bounded_observations():
    requests = []
    def observe(request):
        requests.append(request)
        return httpx.Response(200, content=b'data: {"result": {"tools": []}}\n\n', headers={
            "content-type": "text/event-stream", "mcp-session-id": "opaque-session-1",
            "set-cookie": "must-not-be-exported", "authorization": "must-not-be-exported",
        })
    client = SafeHttpClient.readonly_poc(transport=httpx.MockTransport(observe))
    try:
        response = await client.request("POST", AGENT, "/mcp", json=rpc("tools/list", {}), headers={
            "MCP-Session-Id": "opaque-session-1", "MCP-Protocol-Version": "2025-03-26",
        })
        assert requests[0].headers["accept"] == "application/json, text/event-stream"
        assert requests[0].headers["mcp-session-id"] == "opaque-session-1"
        assert response.content_type == "text/event-stream"
        assert response.headers == {"content-type": "text/event-stream", "mcp-session-id": "opaque-session-1"}
        assert response.body.startswith(b"data:")
    finally:
        await client.close()


async def test_poc_does_not_replay_cookies_from_a_previous_response():
    requests = []
    def observe(request):
        requests.append(request)
        return httpx.Response(200, json={}, headers={"set-cookie": "poc_auth=unwanted; Path=/"})
    client = SafeHttpClient.readonly_poc(transport=httpx.MockTransport(observe))
    try:
        for _ in range(2):
            await client.request("GET", AGENT, "/health")
        assert len(requests) == 2 and all("cookie" not in request.headers for request in requests)
    finally:
        await client.close()


@pytest.mark.parametrize("body,content_type", [
    (b"official documentation", "text/plain"),
    (b'{invalid json', "application/json"),
    (b"", ""),
])
async def test_poc_preserves_bounded_raw_bytes_for_independent_parsing(body, content_type):
    client = SafeHttpClient.readonly_poc(transport=httpx.MockTransport(
        lambda _: httpx.Response(200, content=body, headers={"content-type": content_type}),
    ))
    try:
        observation = await client.request("GET", AGENT, "/health")
        assert observation.status == 200 and observation.body == body
    finally:
        await client.close()


class ForbiddenBody(httpx.AsyncByteStream):
    async def __aiter__(self):
        raise AssertionError("Payment body must not be consumed")
        yield b""  # pragma: no cover


@pytest.mark.parametrize("content_type", ["application/json", "unknown/type"])
async def test_402_stops_before_reading_any_body_and_blocks_all_later_requests(content_type):
    requests = []
    def payment(request):
        requests.append(request)
        return httpx.Response(402, stream=ForbiddenBody(), headers={
            "content-type": content_type, "content-encoding": "gzip",
        })
    client = SafeHttpClient.readonly_poc(transport=httpx.MockTransport(payment))
    try:
        response = await client.request("GET", AGENT, "/health")
        assert response.status == 402 and response.body == b""
        for method, origin, path, payload in (
            ("GET", AGENT, "/health", None),
            ("POST", RPC, "/", rpc("eth_chainId", [])),
        ):
            with pytest.raises(NetworkPolicyError, match="PAYMENT_REQUIRED"):
                await client.request(method, origin, path, json=payload)
        assert len(requests) == 1
    finally:
        await client.close()


@pytest.mark.parametrize("status,headers,body,error", [
    (302, {"location": "https://evil.example"}, b"", "REDIRECT_NOT_ALLOWED"),
    (200, {"content-encoding": "gzip"}, b"", "ENCODING_NOT_ALLOWED"),
    (200, {"content-type": "text/plain"}, b"x" * (1024 * 1024 + 1), "RESPONSE_TOO_LARGE"),
], ids=["redirect", "compression", "body-limit"])
async def test_remote_redirect_encoding_and_size_limits_have_no_retry(status, headers, body, error):
    requests = []
    def respond(request):
        requests.append(request)
        return httpx.Response(status, content=body, headers=headers)
    client = SafeHttpClient.readonly_poc(transport=httpx.MockTransport(respond))
    try:
        with pytest.raises(NetworkPolicyError, match=error):
            await client.request("GET", AGENT, "/health")
        assert len(requests) == 1
    finally:
        await client.close()


async def test_total_poc_timeout_cancels_a_stalled_request_without_retry(monkeypatch):
    timeout_values, requests = [], []
    original_timeout = asyncio.timeout
    def short_timeout(value):
        timeout_values.append(value)
        return original_timeout(0.01)
    async def stall(request):
        requests.append(request)
        await asyncio.sleep(1)
        raise AssertionError("Request should already have been cancelled")
    monkeypatch.setattr(safe_http.asyncio, "timeout", short_timeout)
    client = SafeHttpClient.readonly_poc(transport=httpx.MockTransport(stall))
    try:
        with pytest.raises(TimeoutError):
            await client.request("GET", AGENT, "/health")
        assert timeout_values == [20] and len(requests) == 1
    finally:
        await client.close()


def test_default_platform_constructor_still_rejects_every_public_origin():
    for origin in safe_http.POC_ORIGINS:
        with pytest.raises(NetworkPolicyError):
            SafeHttpClient(frozenset({origin}))
