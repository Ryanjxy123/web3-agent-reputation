"""Public egress policy, actual socket pinning and bounded MCP decoding."""

import asyncio
import json
import ssl

import httpcore
import httpx
import pytest
from reputation_platform.infrastructure.network import safe_http
from reputation_platform.infrastructure.network.safe_http import (
    HttpObservation,
    NetworkPolicyError,
    SafeHttpClient,
    decode_public_json,
)

AGENT = safe_http.PUBLIC_ORIGIN
HASH = "0x" + "ab" * 32
PATH = "/proof?tx=" + HASH


def rpc(method, params=None):
    return {"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}}


def client_for(handler, resolver=None):
    return SafeHttpClient.public_readonly(
        enabled=True, transport=httpx.MockTransport(handler),
        resolver=resolver or (lambda _: ["1.1.1.1"]),
    )


@pytest.fixture(autouse=True)
def no_rate_wait(monkeypatch):
    monkeypatch.setattr(safe_http, "PUBLIC_REQUEST_INTERVAL", 0)


def test_public_client_requires_explicit_opt_in():
    for enabled in (False, None, 1, "true"):
        with pytest.raises(NetworkPolicyError, match="PUBLIC_READONLY_DISABLED"):
            SafeHttpClient.public_readonly(enabled=enabled)


@pytest.mark.parametrize("address", [
    "127.0.0.1", "10.1.2.3", "172.16.0.1", "192.168.1.1", "169.254.169.254",
    "0.0.0.0", "100.64.0.1", "224.0.0.1", "255.255.255.255", "192.0.2.1",
    "::", "::1", "fe80::1", "fc00::1", "ff02::1", "2001:db8::1", "::ffff:127.0.0.1",
    "::ffff:1.1.1.1", "64:ff9b::7f00:1", "2002:7f00:1::", "2001::1", "fe80::1%eth0",
    "localhost", "2130706433", "0177.0.0.1", "0x7f000001",
])
async def test_non_public_or_translated_dns_answers_never_reach_transport(address):
    requests = []
    client = client_for(
        lambda request: requests.append(request) or httpx.Response(200, json={}),
        lambda _: ["1.1.1.1", address],
    )
    try:
        with pytest.raises(NetworkPolicyError, match="PUBLIC_IP_REQUIRED"):
            await client.request("GET", AGENT, PATH)
        assert requests == []
    finally:
        await client.close()


async def test_empty_dns_answers_fail_closed():
    client = client_for(lambda _: pytest.fail("Network must not run"), lambda _: [])
    try:
        with pytest.raises(NetworkPolicyError, match="PUBLIC_IP_REQUIRED"):
            await client.request("GET", AGENT, PATH)
    finally:
        await client.close()


async def test_dns_failure_is_a_sanitized_network_error():
    def unavailable(_):
        raise OSError("must-not-export-private-dns-diagnostics")
    client = client_for(lambda _: pytest.fail("Network must not run"), unavailable)
    try:
        with pytest.raises(httpx.ConnectError, match="^Public DNS resolution failed$"):
            await client.request("GET", AGENT, PATH)
    finally:
        await client.close()


@pytest.mark.parametrize("method,origin,path,payload", [
    ("GET", "https://user:password@anchor.akashi-notari.com", PATH, None),
    ("GET", "https://anchor.akashi-notari.com:443", PATH, None),
    ("GET", "http://anchor.akashi-notari.com", PATH, None),
    ("GET", "https://1.1.1.1", PATH, None),
    ("GET", "https://api.github.com", "/repos/self-reality/verifier", None),
    ("GET", AGENT, "/health", None),
    ("GET", AGENT, "//evil.example" + PATH, None),
    ("GET", AGENT, PATH + "#fragment", None),
    ("GET", AGENT, PATH + "&url=https://evil.example", None),
    ("POST", AGENT, "/anchor", {"hash": HASH}),
    ("POST", AGENT, "/mcp", rpc("tools/call", {"name": "anchor_hash", "arguments": {"hash": HASH}})),
    ("POST", AGENT, "/mcp", rpc("tools/call", {"name": "find_proof", "arguments": {"url": "https://evil.example"}})),
    ("POST", AGENT, "/mcp", rpc("tools/call", {"name": "find_proof", "arguments": {"hash": HASH, "pay": True}})),
    ("POST", AGENT, "/mcp", rpc("sampling/createMessage")),
])
async def test_url_and_tool_policy_is_checked_before_dns(method, origin, path, payload):
    def forbidden(_):
        pytest.fail("Disallowed input must not reach DNS or transport")
    client = client_for(forbidden, forbidden)
    try:
        with pytest.raises(NetworkPolicyError):
            await client.request(method, origin, path, json=payload)
    finally:
        await client.close()


async def test_real_httpcore_connects_to_validated_address_but_keeps_tls_name_and_host():
    calls, writes, tls_names = [], [], []

    class Stream(httpcore.AsyncMockStream):
        async def start_tls(self, ssl_context, server_hostname=None, timeout=None):
            assert ssl_context.check_hostname and ssl_context.verify_mode == ssl.CERT_REQUIRED
            tls_names.append(server_hostname)
            return self

        async def write(self, buffer, timeout=None):
            writes.append(buffer)

    class Backend(httpcore.AsyncNetworkBackend):
        async def connect_tcp(self, host, port, **kwargs):
            calls.append((host, port))
            return Stream([b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: 2\r\n\r\n{}"])

    answers = iter([["2606:4700::1111", "1.1.1.1"], ["8.8.8.8"]])
    client = SafeHttpClient.public_readonly(enabled=True, resolver=lambda _: next(answers))
    client._public_backend.backend = Backend()
    try:
        first = await client.request("GET", AGENT, PATH)
        second = await client.request("GET", AGENT, PATH)
        assert calls == [("1.1.1.1", 443), ("8.8.8.8", 443)]
        assert tls_names == ["anchor.akashi-notari.com", "anchor.akashi-notari.com"]
        requests = [part for part in writes if part.startswith(b"GET ")]
        assert len(requests) == 2
        assert all(b"Host: anchor.akashi-notari.com\r\n" in request for request in requests)
        assert first.audit["resolved_ips"] == ["1.1.1.1", "2606:4700::1111"]
        assert second.audit["resolved_ips"] == ["8.8.8.8"]
        assert client.client.trust_env is False and not client.client.follow_redirects
    finally:
        await client.close()


async def test_rebinding_to_private_answer_stops_next_request():
    answers = iter([["1.1.1.1"], ["127.0.0.1"]])
    requests = []
    client = client_for(
        lambda request: requests.append(request) or httpx.Response(200, json={}),
        lambda _: next(answers),
    )
    try:
        await client.request("GET", AGENT, PATH)
        with pytest.raises(NetworkPolicyError, match="PUBLIC_IP_REQUIRED"):
            await client.request("GET", AGENT, PATH)
        assert len(requests) == 1
    finally:
        await client.close()


async def test_attempt_quota_includes_transport_failures_and_does_not_retry(monkeypatch):
    monkeypatch.setattr(safe_http, "PUBLIC_REQUEST_QUOTA", 2)
    calls = []
    def fail(request):
        calls.append(request)
        raise httpx.ConnectError("offline")
    client = client_for(fail)
    try:
        for _ in range(2):
            with pytest.raises(httpx.ConnectError):
                await client.request("GET", AGENT, PATH)
        with pytest.raises(NetworkPolicyError, match="REQUEST_QUOTA_EXCEEDED"):
            await client.request("GET", AGENT, PATH)
        assert client.public_stop_reason == "REQUEST_QUOTA_EXCEEDED"
        assert len(calls) == 2
    finally:
        await client.close()


async def test_concurrent_calls_are_serial_and_rate_limited(monkeypatch):
    monkeypatch.setattr(safe_http, "PUBLIC_REQUEST_INTERVAL", 0.03)
    starts, active = [], 0
    async def respond(_):
        nonlocal active
        active += 1
        assert active == 1
        starts.append(asyncio.get_running_loop().time())
        await asyncio.sleep(0.005)
        active -= 1
        return httpx.Response(200, json={})
    client = client_for(respond)
    try:
        responses = await asyncio.gather(*(client.request("GET", AGENT, PATH) for _ in range(3)))
        assert [item.audit["sequence"] for item in responses] == [1, 2, 3]
        assert all(end - start >= 0.029 for start, end in zip(starts, starts[1:], strict=False))
    finally:
        await client.close()


async def test_pacing_starts_after_slow_dns_and_rechecks_early_timer(monkeypatch):
    monkeypatch.setattr(safe_http, "PUBLIC_REQUEST_INTERVAL", 0.03)
    loop = asyncio.get_running_loop()
    now = [loop.time()]
    monkeypatch.setattr(loop, "time", lambda: now[0])
    starts, wakeups = [], []
    async def early_sleep(delay):
        wakeups.append(delay)
        now[0] += min(delay, 0.005)
    monkeypatch.setattr(safe_http.asyncio, "sleep", early_sleep)
    async def slow_resolve(_):
        now[0] += 0.04
        return ["1.1.1.1"]
    def respond(_):
        starts.append(asyncio.get_running_loop().time())
        return httpx.Response(200, json={})
    client = client_for(respond, resolver=slow_resolve)
    try:
        await client.request("GET", AGENT, PATH)
        await client.request("GET", AGENT, PATH)
        assert starts[1] - starts[0] >= 0.069
        assert len(wakeups) > 1
    finally:
        await client.close()


async def test_dns_resolution_is_in_total_timeout_without_retry(monkeypatch):
    original = asyncio.timeout
    timeouts, calls = [], []
    def short_timeout(seconds):
        timeouts.append(seconds)
        return original(0.01)
    async def stall(host):
        calls.append(host)
        await asyncio.sleep(1)
        return ["1.1.1.1"]
    monkeypatch.setattr(safe_http.asyncio, "timeout", short_timeout)
    client = client_for(lambda _: pytest.fail("Must cancel during DNS"), stall)
    try:
        with pytest.raises(TimeoutError):
            await client.request("GET", AGENT, PATH)
        assert timeouts == [20] and calls == ["anchor.akashi-notari.com"]
    finally:
        await client.close()


@pytest.mark.parametrize("status,headers,body,error", [
    (302, {"location": "http://127.0.0.1"}, b"", "REDIRECT_NOT_ALLOWED"),
    (200, {"content-encoding": "gzip"}, b"", "ENCODING_NOT_ALLOWED"),
    (200, {"content-type": "application/json"}, b"x" * (1024 * 1024 + 1), "RESPONSE_TOO_LARGE"),
], ids=["redirect", "encoding", "size"])
async def test_redirect_encoding_and_response_size_have_no_retry(status, headers, body, error):
    calls = []
    client = client_for(lambda request: calls.append(request) or httpx.Response(status, content=body, headers=headers))
    try:
        with pytest.raises(NetworkPolicyError, match=error):
            await client.request("GET", AGENT, PATH)
        assert len(calls) == 1
    finally:
        await client.close()


class UnreadableBody(httpx.AsyncByteStream):
    async def __aiter__(self):
        raise AssertionError("Payment body must not be read")
        yield b""  # pragma: no cover


@pytest.mark.parametrize("status,headers", [(402, {}), (200, {"payment-required": "opaque"})])
async def test_payment_status_or_header_sticky_stops_without_consuming_body(status, headers):
    calls = []
    client = client_for(lambda request: calls.append(request) or httpx.Response(
        status, stream=UnreadableBody(), headers=headers,
    ))
    try:
        result = await client.request("GET", AGENT, PATH)
        assert result.status == status and result.body == b""
        assert result.audit["payment_required"] and result.audit["body_not_read"]
        with pytest.raises(NetworkPolicyError, match="PAYMENT_REQUIRED"):
            await client.request("GET", AGENT, PATH)
        assert len(calls) == 1
    finally:
        await client.close()


@pytest.mark.parametrize("payload", [
    {"error": {"code": "PAYMENT_REQUIRED"}},
    {"paymentRequirements": [{"amount": "1"}]},
    {"result": {"content": [{"type": "text", "text": '{"requiresPayment":true}'}]}},
])
async def test_payment_body_is_preserved_and_stops_followups(payload):
    client = client_for(lambda _: httpx.Response(200, json=payload))
    try:
        result = await client.request("GET", AGENT, PATH)
        assert json.loads(result.body) == payload
        assert result.audit["payment_required"] and not result.audit["body_not_read"]
        with pytest.raises(NetworkPolicyError, match="PAYMENT_REQUIRED"):
            await client.request("GET", AGENT, PATH)
    finally:
        await client.close()


def test_sse_supports_comments_and_multiline_json_but_rejects_multiple_responses():
    observation = HttpObservation(200, b': keepalive\n\nevent: message\ndata: {"result":\ndata: {"content":[]}}\n\n', "text/event-stream")
    assert decode_public_json(observation) == {"result": {"content": []}}
    with pytest.raises(NetworkPolicyError, match="INVALID_SSE"):
        decode_public_json(HttpObservation(200, b'data: {}\n\ndata: {}\n\n', "text/event-stream"))


@pytest.mark.parametrize("body,content_type,error", [
    (b'{"id":1,"id":2}', "application/json", "INVALID_JSON"),
    (b'{"value":NaN}', "application/json", "INVALID_JSON"),
    (b'{invalid', "application/json", "INVALID_JSON"),
    (b'{"value":"\xff"}', "application/json", "INVALID_JSON"),
    (b"[]", "application/json", "EXPECTED_JSON_OBJECT"),
    (b"anything", "text/plain", "EXPECTED_JSON"),
    (b'data: {invalid}\n\n', "text/event-stream", "INVALID_JSON"),
    (b'data: {}\nunknown: bad\n\n', "text/event-stream", "INVALID_SSE"),
    (b'{"result":{"content":[{"type":"text","text":"{invalid}"}]}}', "application/json", "INVALID_JSON"),
    (b'{"result":{"content":[{"type":"text","text":1}]}}', "application/json", "INVALID_MCP_TEXT"),
])
async def test_malformed_response_preserves_evidence_and_marks_validation_error(body, content_type, error):
    client = client_for(lambda _: httpx.Response(200, content=body, headers={"content-type": content_type}))
    try:
        result = await client.request("GET", AGENT, PATH)
        assert result.body == body and result.audit["validation_error"] == error
        with pytest.raises(NetworkPolicyError, match=error):
            decode_public_json(result)
    finally:
        await client.close()


@pytest.mark.parametrize("embedded", [False, True])
async def test_json_depth_applies_to_outer_envelope_and_mcp_text(embedded):
    payload = b'[' * 34 + b'0' + b']' * 34
    raw = json.dumps({"result": {"content": [{"type": "text", "text": payload.decode()}]}}).encode() if embedded else b'{"deep":' + payload + b'}'
    client = client_for(lambda _: httpx.Response(200, content=raw, headers={"content-type": "application/json"}))
    try:
        result = await client.request("GET", AGENT, PATH)
        assert result.audit["validation_error"] == "JSON_TOO_DEEP"
        with pytest.raises(NetworkPolicyError, match="JSON_TOO_DEEP"):
            decode_public_json(result)
    finally:
        await client.close()


@pytest.mark.parametrize("headers", [
    {"Authorization": "Bearer secret"}, {"Cookie": "private=secret"},
    {"X-Payment": "secret"}, {"Host": "127.0.0.1"},
    {"MCP-Session-ID": "session\r\nX-Payment: secret"},
])
async def test_credentials_and_unknown_headers_never_leave_client(headers):
    client = client_for(lambda _: pytest.fail("Headers must fail before network"))
    try:
        with pytest.raises(NetworkPolicyError, match="HEADERS_NOT_ALLOWED"):
            await client.request("POST", AGENT, "/mcp", json=rpc("tools/list"), headers=headers)
    finally:
        await client.close()


async def test_cookies_and_response_credentials_are_isolated():
    calls = []
    client = client_for(lambda request: calls.append(request) or httpx.Response(200, json={}, headers={
        "Set-Cookie": "private=secret; Path=/", "Authorization": "secret",
        "X-Payment-Response": "secret", "mcp-session-id": "opaque-session",
    }))
    client.client.cookies.set("ambient", "secret")
    try:
        for _ in range(2):
            result = await client.request("GET", AGENT, PATH)
            assert set(result.headers) == {"content-type", "mcp-session-id"}
            assert "secret" not in str(result.audit)
        assert all("cookie" not in call.headers and "authorization" not in call.headers for call in calls)
    finally:
        await client.close()


@pytest.mark.parametrize("session", ["secret\r\nX-Payment: secret", "x" * 257, "Bearer secret"])
async def test_invalid_response_session_is_not_exposed_or_replayed(session):
    client = client_for(lambda _: httpx.Response(200, json={}, headers={"mcp-session-id": session}))
    try:
        result = await client.request("POST", AGENT, "/mcp", json=rpc("tools/list"))
        assert "mcp-session-id" not in result.headers
        assert result.audit["validation_error"] == "INVALID_MCP_SESSION"
        with pytest.raises(NetworkPolicyError, match="INVALID_MCP_SESSION"):
            decode_public_json(result)
    finally:
        await client.close()
