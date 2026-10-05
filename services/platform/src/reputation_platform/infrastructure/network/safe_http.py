"""M1 controlled-demo HTTP only. Public access remains disabled."""

import asyncio
from dataclasses import dataclass
from urllib.parse import urlsplit

import httpx
from reputation_core.evidence import strict_json

from reputation_platform.configuration import controlled_fixture_ports

MAX_BODY = 1024 * 1024


class NetworkPolicyError(ValueError):
    pass


@dataclass(frozen=True)
class HttpObservation:
    status: int
    body: bytes


class SafeHttpClient:
    def __init__(
        self, allowed_origins: frozenset[str], *, transport: httpx.AsyncBaseTransport | None = None
    ):
        if not allowed_origins:
            raise NetworkPolicyError("No controlled targets configured")
        controlled_ports = set(controlled_fixture_ports())
        for origin in allowed_origins:
            parsed = urlsplit(origin)
            if parsed.scheme != "http" or parsed.username or parsed.password or parsed.path:
                raise NetworkPolicyError("Invalid controlled target")
            if parsed.hostname not in {"127.0.0.1", "fixture-a", "fixture-d"}:
                raise NetworkPolicyError("Only exact controlled demo hosts are supported")
            if parsed.port not in controlled_ports or parsed.query or parsed.fragment:
                raise NetworkPolicyError("Invalid controlled port")
        self.origins = allowed_origins
        self.client = httpx.AsyncClient(
            follow_redirects=False,
            trust_env=False,
            timeout=httpx.Timeout(15, connect=5),
            transport=transport,
        )

    async def close(self) -> None:
        await self.client.aclose()

    async def request(
        self,
        method: str,
        origin: str,
        path: str,
        *,
        json: dict | None = None,
        request_id: str | None = None,
    ) -> HttpObservation:
        if origin not in self.origins:
            raise NetworkPolicyError("TARGET_NOT_ALLOWED")
        allowed = (method == "GET" and path in {"/health", "/capabilities"}) or (
            method == "POST" and path == "/tasks"
        )
        if method == "GET" and path.startswith("/tasks/"):
            identifier = path.removeprefix("/tasks/")
            allowed = (
                len(identifier) == 66
                and identifier.startswith("0x")
                and all(c in "0123456789abcdef" for c in identifier[2:])
            )
        if not allowed:
            raise NetworkPolicyError("METHOD_OR_PATH_NOT_ALLOWED")
        headers = {"Accept-Encoding": "identity"}
        if request_id:
            headers["Idempotency-Key"] = request_id
        async with asyncio.timeout(15):
            async with self.client.stream(
                method, origin + path, json=json, headers=headers
            ) as response:
                if response.is_redirect:
                    raise NetworkPolicyError("REDIRECT_NOT_ALLOWED")
                if response.headers.get("content-encoding", "identity") != "identity":
                    raise NetworkPolicyError("ENCODING_NOT_ALLOWED")
                chunks = bytearray()
                async for chunk in response.aiter_bytes():
                    chunks.extend(chunk)
                    if len(chunks) > MAX_BODY:
                        raise NetworkPolicyError("RESPONSE_TOO_LARGE")
                if (
                    response.headers.get("content-type", "").split(";")[0].strip()
                    != "application/json"
                ):
                    raise NetworkPolicyError("EXPECTED_JSON")
                raw = bytes(chunks)
                try:
                    value = strict_json(raw)
                except (ValueError, RecursionError) as exc:
                    raise NetworkPolicyError("INVALID_JSON") from exc
                stack = [(value, 0)]
                while stack:
                    item, depth = stack.pop()
                    if depth > 32:
                        raise NetworkPolicyError("JSON_TOO_DEEP")
                    if isinstance(item, dict):
                        stack.extend((child, depth + 1) for child in item.values())
                    elif isinstance(item, list):
                        stack.extend((child, depth + 1) for child in item)
                return HttpObservation(response.status_code, raw)
