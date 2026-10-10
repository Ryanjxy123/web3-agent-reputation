"""Controlled-demo HTTP; a separately selected fixed, read-only third-party PoC."""

import asyncio
import re
from dataclasses import dataclass, field
from urllib.parse import parse_qsl, urlsplit

import httpx
from reputation_core.evidence import strict_json

from reputation_platform.configuration import controlled_fixture_ports

MAX_BODY = 1024 * 1024
POC_ORIGINS = frozenset({
    "https://raw.githubusercontent.com", "https://api.github.com",
    "https://anchor.akashi-notari.com", "https://mainnet.base.org",
})
POC_SOURCE_REF = "21a1ebd5e6af277c5e94407d576a8ca5219591f5"
POC_IDENTITY_REGISTRY = "0x8004a169fb4a3325136eb29fa0ceb6d2e539a432"
POC_CONTRACTS = frozenset({
    POC_IDENTITY_REGISTRY, "0xe0c6bb0914be3e49e13ffbc389cf659871a1bcd3",
    "0xeed9d0f7265892e84e43d05da464c75add199260",
})
POC_RAW_FILES = frozenset({
    "README.md", "workers/anchor/README.md", "contracts/registry/constants-usdc.json",
    "contracts/registry/constants.json", "contracts/registry/contracts/VerifierRegistry.sol",
    "contracts/registry/contracts/VerifierRegistryUSDC.sol", "workers/anchor/src/abi.js",
    "workers/anchor/src/index.js", "workers/anchor/wrangler.toml",
    "contracts/registry/scripts/register-agent.js",
})


def _hash32(value) -> bool:
    return isinstance(value, str) and re.fullmatch(r"0x[0-9a-fA-F]{64}", value) is not None


def _quantity(value) -> bool:
    return isinstance(value, str) and re.fullmatch(r"0x(?:0|[1-9a-fA-F][0-9a-fA-F]{0,15})", value) is not None


def _readonly_request_allowed(method: str, origin: str, path: str, body: dict | None) -> bool:
    parsed = urlsplit(path)
    if parsed.scheme or parsed.netloc or parsed.fragment:
        return False
    if method == "GET" and body is None:
        if origin == "https://raw.githubusercontent.com":
            return path in {
                f"/self-reality/verifier/{ref}/{name}"
                for ref in ("main", POC_SOURCE_REF) for name in POC_RAW_FILES
            }
        if origin == "https://api.github.com":
            return path in {
                "/repos/self-reality/verifier", "/repos/self-reality/verifier/commits/main",
                "/repos/self-reality/verifier/git/trees/main?recursive=1",
            }
        if origin == "https://anchor.akashi-notari.com":
            if path in {"/health", "/openapi.json", "/llms.txt", "/.well-known/agent-registration.json"}:
                return True
            if parsed.path != "/proof":
                return False
            parameters = parse_qsl(parsed.query, keep_blank_values=True)
            if len(parameters) != 1:
                return False
            name, value = parameters[0]
            return (
                name == "tx" and _hash32(value)
                or name == "hash" and (
                    re.fullmatch(r"(?:0x)?[0-9a-fA-F]{64}", value) is not None
                    or value == "not-a-sha256"
                )
            )
        return False
    if method != "POST" or not isinstance(body, dict) or body.get("jsonrpc") != "2.0":
        return False
    if set(body) - {"jsonrpc", "id", "method", "params"}:
        return False
    operation, parameters = body.get("method"), body.get("params", {})
    if not isinstance(operation, str):
        return False
    identifier = body.get("id")
    if operation == "notifications/initialized":
        if "id" in body:
            return False
    elif not (
        type(identifier) is int and 0 <= identifier <= 2**31 - 1
        or isinstance(identifier, str) and 0 < len(identifier) <= 128
    ):
        return False
    if origin == "https://anchor.akashi-notari.com" and path == "/mcp":
        if operation == "initialize":
            return (
                isinstance(parameters, dict)
                and set(parameters) == {"protocolVersion", "capabilities", "clientInfo"}
                and isinstance(parameters["protocolVersion"], str)
                and parameters["protocolVersion"] in {"2024-11-05", "2025-03-26", "2025-06-18", "2025-11-25"}
                and parameters["capabilities"] == {}
                and isinstance(parameters["clientInfo"], dict)
                and set(parameters["clientInfo"]) == {"name", "version"}
                and all(isinstance(value, str) and 0 < len(value) <= 128
                        for value in parameters["clientInfo"].values())
            )
        if operation in {"notifications/initialized", "tools/list"}:
            return parameters == {}
        if operation == "tools/call" and isinstance(parameters, dict):
            arguments = parameters.get("arguments")
            return (
                set(parameters) == {"name", "arguments"}
                and parameters["name"] == "find_proof"
                and isinstance(arguments, dict)
                and len(arguments) == 1
                and (
                    "tx" in arguments and _hash32(arguments["tx"])
                    or "hash" in arguments and isinstance(arguments["hash"], str)
                    and re.fullmatch(r"(?:0x)?[0-9a-fA-F]{64}", arguments["hash"]) is not None
                )
            )
        return False
    if origin != "https://mainnet.base.org" or path != "/" or not isinstance(parameters, list):
        return False
    if operation in {"eth_chainId", "eth_blockNumber"}:
        return parameters == []
    if operation in {"eth_getTransactionByHash", "eth_getTransactionReceipt"}:
        return len(parameters) == 1 and _hash32(parameters[0])
    if operation in {"eth_getBlockByNumber", "eth_getBlockByHash"}:
        return len(parameters) == 2 and parameters[1] is False and (
            _hash32(parameters[0]) if operation == "eth_getBlockByHash"
            else parameters[0] == "latest" or _quantity(parameters[0])
        )
    if operation == "eth_getCode":
        return len(parameters) == 2 and isinstance(parameters[0], str) and (
            parameters[0].lower() in POC_CONTRACTS
        ) and (parameters[1] == "latest" or _quantity(parameters[1]))
    if operation == "eth_call" and len(parameters) == 2 and isinstance(parameters[0], dict):
        query = parameters[0]
        return (
            set(query) == {"to", "data"} and isinstance(query["to"], str)
            and query["to"].lower() == POC_IDENTITY_REGISTRY
            and isinstance(query["data"], str)
            and query["data"] in {selector + f"{98097:064x}" for selector in ("0x6352211e", "0xc87b56dd")}
            and (parameters[1] == "latest" or _quantity(parameters[1]))
        )
    if operation == "eth_getLogs" and len(parameters) == 1 and isinstance(parameters[0], dict):
        query = parameters[0]
        topics = query.get("topics", [])
        return (
            not set(query) - {"address", "fromBlock", "toBlock", "topics"}
            and isinstance(query.get("address"), str)
            and re.fullmatch(r"0x[0-9a-fA-F]{40}", query["address"]) is not None
            and _quantity(query.get("fromBlock")) and _quantity(query.get("toBlock"))
            and 0 <= int(query["toBlock"], 16) - int(query["fromBlock"], 16) < 2000
            and isinstance(topics, list) and len(topics) <= 4
            and all(topic is None or _hash32(topic) for topic in topics)
        )
    return False


class NetworkPolicyError(ValueError):
    pass


@dataclass(frozen=True)
class HttpObservation:
    status: int
    body: bytes
    content_type: str = ""
    headers: dict[str, str] = field(default_factory=dict)


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
        self._readonly = False
        self._payment_required = False
        self.client = httpx.AsyncClient(
            follow_redirects=False,
            trust_env=False,
            timeout=httpx.Timeout(15, connect=5),
            transport=transport,
        )

    @classmethod
    def readonly_poc(cls, *, transport: httpx.AsyncBaseTransport | None = None) -> "SafeHttpClient":
        instance = cls.__new__(cls)
        instance.origins = POC_ORIGINS
        instance._readonly = True
        instance._payment_required = False
        instance.client = httpx.AsyncClient(
            follow_redirects=False, trust_env=False, timeout=httpx.Timeout(20, connect=5),
            transport=transport,
        )
        return instance

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
        headers: dict[str, str] | None = None,
    ) -> HttpObservation:
        if self._payment_required:
            raise NetworkPolicyError("PAYMENT_REQUIRED")
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
        if self._readonly:
            allowed = _readonly_request_allowed(method, origin, path, json) and request_id is None
        if not allowed:
            raise NetworkPolicyError("METHOD_OR_PATH_NOT_ALLOWED")
        request_headers = {"Accept-Encoding": "identity"}
        if headers:
            if not self._readonly or origin != "https://anchor.akashi-notari.com" or path != "/mcp":
                raise NetworkPolicyError("HEADERS_NOT_ALLOWED")
            for name, value in headers.items():
                if (
                    not isinstance(name, str) or name.lower() not in {"mcp-session-id", "mcp-protocol-version"}
                    or not isinstance(value, str) or re.fullmatch(r"[A-Za-z0-9._-]{1,256}", value) is None
                ):
                    raise NetworkPolicyError("HEADERS_NOT_ALLOWED")
                request_headers[name.lower()] = value
        if self._readonly and origin == "https://anchor.akashi-notari.com" and path == "/mcp":
            request_headers["Accept"] = "application/json, text/event-stream"
        if request_id:
            request_headers["Idempotency-Key"] = request_id
        if self._readonly:
            self.client.cookies.clear()
        async with asyncio.timeout(20 if self._readonly else 15):
            async with self.client.stream(
                method, origin + path, json=json, headers=request_headers
            ) as response:
                response_headers = {
                    name: response.headers[name]
                    for name in ("content-type", "mcp-session-id") if name in response.headers
                }
                if self._readonly and response.status_code == 402:
                    self._payment_required = True
                    return HttpObservation(402, b"", response.headers.get("content-type", ""), response_headers)
                if response.is_redirect:
                    raise NetworkPolicyError("REDIRECT_NOT_ALLOWED")
                if response.headers.get("content-encoding", "identity") != "identity":
                    raise NetworkPolicyError("ENCODING_NOT_ALLOWED")
                chunks = bytearray()
                async for chunk in response.aiter_bytes():
                    chunks.extend(chunk)
                    if len(chunks) > MAX_BODY:
                        raise NetworkPolicyError("RESPONSE_TOO_LARGE")
                content_type = response.headers.get("content-type", "").split(";")[0].strip()
                if self._readonly:
                    if content_type not in {
                        "", "application/json", "text/plain", "text/markdown", "text/html", "text/event-stream",
                    }:
                        raise NetworkPolicyError("CONTENT_TYPE_NOT_ALLOWED")
                elif content_type != "application/json":
                    raise NetworkPolicyError("EXPECTED_JSON")
                raw = bytes(chunks)
                if self._readonly:
                    return HttpObservation(response.status_code, raw, content_type, response_headers)
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
                return HttpObservation(response.status_code, raw, content_type, response_headers)
