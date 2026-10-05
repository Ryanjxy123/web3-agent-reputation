import gzip
import json

import httpx
import pytest
from reputation_platform.configuration import controlled_fixture_ports
from reputation_platform.infrastructure.network.safe_http import NetworkPolicyError, SafeHttpClient

A_PORT, _ = controlled_fixture_ports()
ORIGIN = f"http://127.0.0.1:{A_PORT}"


@pytest.mark.parametrize(
    "name,value,error",
    [
        ("FIXTURE_PORT_A", "not-a-port", "must be an integer"),
        ("FIXTURE_PORT_A", "1023", "between 1024 and 65535"),
        ("FIXTURE_PORT_D", "65536", "between 1024 and 65535"),
    ],
)
def test_controlled_fixture_ports_reject_invalid_values(monkeypatch, name, value, error):
    monkeypatch.setenv(name, value)
    with pytest.raises(ValueError, match=error):
        controlled_fixture_ports()


def test_controlled_fixture_ports_must_be_distinct(monkeypatch):
    monkeypatch.setenv("FIXTURE_PORT_A", "19101")
    monkeypatch.setenv("FIXTURE_PORT_D", "19101")
    with pytest.raises(ValueError, match="must be distinct"):
        controlled_fixture_ports()


@pytest.mark.parametrize(
    "origin",
    [
        f"http://169.254.169.254:{A_PORT}",
        "http://127.0.0.1:5432",
        f"http://localhost:{A_PORT}",
        f"http://[::1]:{A_PORT}",
        "https://example.com",
        f"http://user:password@127.0.0.1:{A_PORT}",
        f"http://fixture-a:{A_PORT}/redirect",
        f"http://127.0.0.1:{A_PORT}?url=http://secret",
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
