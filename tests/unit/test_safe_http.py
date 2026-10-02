import gzip
import json

import httpx
import pytest
from reputation_platform.infrastructure.network.safe_http import NetworkPolicyError, SafeHttpClient

ORIGIN = "http://127.0.0.1:9101"


@pytest.mark.parametrize(
    "origin",
    [
        "http://169.254.169.254:9101",
        "http://127.0.0.1:5432",
        "http://localhost:9101",
        "http://[::1]:9101",
        "https://example.com",
        "http://user:password@127.0.0.1:9101",
        "http://fixture-a:9101/redirect",
        "http://127.0.0.1:9101?url=http://secret",
    ],
)
def test_configuration_has_no_global_private_ip_bypass(origin):
    with pytest.raises(NetworkPolicyError):
        SafeHttpClient(frozenset({origin}))


async def test_untrusted_url_path_method_and_redirect_are_never_followed():
    calls = []

    def responder(request):
        calls.append(str(request.url))
        return httpx.Response(302, headers={"location": "http://169.254.169.254"})

    client = SafeHttpClient(frozenset({ORIGIN}), transport=httpx.MockTransport(responder))
    try:
        for origin, path, method in [
            ("http://127.0.0.1:8000", "/health", "GET"),
            (ORIGIN, "/tasks/../../secrets", "GET"),
            (ORIGIN, "/health?url=http://secret", "GET"),
            (ORIGIN, "/health", "DELETE"),
        ]:
            with pytest.raises(NetworkPolicyError):
                await client.request(method, origin, path)
        assert calls == []
        with pytest.raises(NetworkPolicyError, match="REDIRECT"):
            await client.request("GET", ORIGIN, "/health")
        assert len(calls) == 1
    finally:
        await client.close()


@pytest.mark.parametrize(
    "body,error",
    [
        (b"x" * (1024 * 1024 + 1), "RESPONSE_TOO_LARGE"),
        (b'{"a":1,"a":2}', "INVALID_JSON"),
        (("[" * 34 + "0" + "]" * 34).encode(), "JSON_TOO_DEEP"),
    ],
    ids=["too-large", "duplicate-key", "too-deep"],
)
async def test_bounded_strict_json(body, error):
    client = SafeHttpClient(
        frozenset({ORIGIN}),
        transport=httpx.MockTransport(
            lambda _: httpx.Response(
                200, content=body, headers={"content-type": "application/json"}
            )
        ),
    )
    try:
        with pytest.raises(NetworkPolicyError, match=error):
            await client.request("GET", ORIGIN, "/health")
    finally:
        await client.close()


async def test_valid_controlled_response_and_no_host_proxy_inheritance(monkeypatch):
    monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:1")
    client = SafeHttpClient(
        frozenset({ORIGIN}),
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json={"status": "ok"})),
    )
    try:
        response = await client.request("GET", ORIGIN, "/health")
        assert response.status == 200 and json.loads(response.body) == {"status": "ok"}
        assert client.client.trust_env is False
    finally:
        await client.close()


async def test_compressed_response_is_rejected_before_body_consumption():
    client = SafeHttpClient(
        frozenset({ORIGIN}),
        transport=httpx.MockTransport(lambda _: httpx.Response(
            200, content=gzip.compress(b'{}'),
            headers={"content-encoding": "gzip", "content-type": "application/json"},
        )),
    )
    try:
        with pytest.raises(NetworkPolicyError, match="ENCODING_NOT_ALLOWED"):
            await client.request("GET", ORIGIN, "/health")
    finally:
        await client.close()
