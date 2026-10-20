"""Explicitly scoped, bounded HTTP reads; never follows remote instructions."""

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import socket
import time
from urllib.parse import urlsplit

import httpx

from reputation_core import MeasurementPurpose, ProbeObservation, Verdict
from reputation_platform.llm import LLMConfig


@dataclass(frozen=True)
class PublicTarget:
    key: str
    url: str
    method: str = "GET"
    purpose: MeasurementPurpose = MeasurementPurpose.BACKGROUND
    json_body: dict | None = None
    headers: dict[str, str] | None = None


def _contains_private(value: object, private: tuple[str, ...]) -> bool:
    if isinstance(value, str):
        return any(item in value for item in private)
    if isinstance(value, list):
        return any(_contains_private(item, private) for item in value)
    if isinstance(value, dict):
        return any(_contains_private(item, private) for pair in value.items() for item in pair)
    return False


class SafeHttpClient:
    """Operator-listed HTTPS requests; provider credentials have a fixed scope."""

    def __init__(
        self, targets: tuple[PublicTarget, ...], *, enabled: bool = False,
        proxy: str | None = None, max_requests: int = 8,
        max_body_bytes: int = 1_048_576, timeout_seconds: float = 15,
        transport: httpx.BaseTransport | None = None,
        provider_key_file: Path | None = None,
        provider_config: LLMConfig | None = None,
        provider_models_check: bool = False,
        zan_key_url_file: Path | None = None,
        pin_public_dns: bool = False,
    ) -> None:
        self.targets = {target.key: target for target in targets}
        if len(self.targets) != len(targets):
            raise ValueError("Duplicate target key")
        for target in targets:
            parsed = urlsplit(target.url)
            if (not re.fullmatch(r"[a-z0-9-]+", target.key)
                or parsed.scheme != "https" or not parsed.hostname
                or parsed.username or parsed.password or parsed.fragment
                or parsed.port not in (None, 443)
                or target.method not in ("GET", "POST")):
                raise ValueError("Targets must be explicitly scoped HTTPS reads")
            self._check_public_headers(target)
        self.enabled = enabled
        self.remaining = max_requests
        self.max_body_bytes = max_body_bytes
        self.timeout_seconds = timeout_seconds
        self.stopped_hosts: set[str] = set()
        self._provider_headers = {}
        self._provider_secret = b""
        self._provider_scopes = {}
        self._provider_models_check = provider_models_check
        self._provider_evidence_urls = {}
        self._private_values = []
        self._zan_key_scope = zan_key_url_file is not None
        self._zan_rpc_methods = {}
        self._llm_network = provider_config is not None and transport is None
        self._zan_network = zan_key_url_file is not None and transport is None
        self._network_transport = None
        self._network_route = None
        self._pin_public_dns = pin_public_dns or self._llm_network or self._zan_network
        self._proxy = proxy
        if pin_public_dns and transport is not None:
            raise ValueError("Pinned DNS cannot be combined with a replacement transport")
        if provider_key_file is not None and zan_key_url_file is not None:
            raise ValueError("LLM and ZAN credentials are mutually exclusive")
        if provider_config is not None and provider_key_file is None:
            raise ValueError("LLM API key file is required")
        if provider_models_check and provider_config is None:
            raise ValueError("Model discovery requires an operator LLM configuration")
        if provider_key_file is not None:
            permitted = {("https://api.deepseek.com/responses", "POST"),
                         ("https://api.deepseek.com/user/balance", "GET")}
            if provider_config is not None:
                permitted = {(provider_config.endpoint, "POST")}
                if provider_config.is_legacy:
                    permitted.add(("https://api.deepseek.com/user/balance", "GET"))
                if provider_models_check:
                    permitted = {(provider_config.models_endpoint, "GET")}
                    if any(target.json_body is not None for target in targets):
                        raise ValueError("Model discovery only permits an empty GET request")
            if not enabled or not targets or any((target.url, target.method) not in permitted for target in targets):
                raise ValueError("Provider credentials require the exact operator-configured LLM endpoint")
            try:
                secret = provider_key_file.read_text(encoding="utf-8-sig").strip()
            except (OSError, UnicodeError):
                raise ValueError("LLM API key file is missing or unreadable") from None
            if not secret or any(ord(char) < 33 or ord(char) > 126 for char in secret):
                raise ValueError("Provider key file must contain one nonempty line")
            self._provider_headers = {"Authorization": "Bearer " + secret}
            self._provider_secret = secret.encode("utf-8")
            self._provider_scopes = {target.key: (target.url, target.method) for target in targets}
            if provider_config is not None:
                self._provider_evidence_urls = {target.key: provider_config.evidence_url
                    for target in targets if target.url in (provider_config.endpoint, provider_config.models_endpoint)}
                values = {provider_config.base_url.rstrip("/"), provider_config.endpoint,
                          urlsplit(provider_config.endpoint).netloc}
                self._private_values = [value.encode("utf-8") for value in sorted(values, key=len, reverse=True)]
        if zan_key_url_file is not None:
            if not enabled or not targets:
                raise ValueError("ZAN credentials require explicitly enabled fixed read-only targets")
            for target in targets:
                self._check_zan_target(target)
                self._zan_rpc_methods[target.key] = target.json_body["method"]
            try:
                key_url = zan_key_url_file.read_text(encoding="utf-8-sig").strip()
            except (OSError, UnicodeError):
                raise ValueError("ZAN RPC credential file is missing or unreadable") from None
            match = re.fullmatch(r"https://api\.zan\.top/node/v1/base/mainnet/([A-Za-z0-9._~-]+)", key_url)
            if not match:
                raise ValueError("ZAN key file must contain one official Base mainnet key URL")
            secret = match.group(1)
            self._provider_secret = secret.encode("utf-8")
        self.client = None if self._pin_public_dns else httpx.Client(
            proxy=proxy, transport=transport, trust_env=False,
            timeout=timeout_seconds, follow_redirects=False,
            headers={"User-Agent": "Web3Reputation-ReadOnlyFeasibility/0.1"},
        )

    def __enter__(self) -> "SafeHttpClient":
        self._ensure_client()
        return self

    def __exit__(self, *_: object) -> None:
        if self.client is not None:
            self.client.close()

    def _ensure_client(self) -> None:
        if self.client is None:
            urls = tuple(target.url for target in self.targets.values())
            if self._llm_network or self._zan_network:
                from reputation_platform.llm_network import LLMHTTPTransport
                from reputation_platform.llm_network_settings import select_proxy

                if self._zan_network:
                    self._network_route = select_proxy(urls[0], self._proxy, override_variable="REPUTATION_ZAN_PROXY")
                    urls = tuple(url + "/" + self._provider_secret.decode("utf-8") for url in urls)
                    self._network_transport = LLMHTTPTransport(urls, self._network_route.url,
                        dns_mode=os.environ.get("REPUTATION_ZAN_DNS_MODE", "auto"))
                else:
                    self._network_route = select_proxy(urls[0], self._proxy)
                    self._network_transport = LLMHTTPTransport(urls, self._network_route.url)
                transport = self._network_transport
            else:
                from reputation_platform.pinned_http import PinnedHTTPTransport

                transport = PinnedHTTPTransport(urls, self._proxy)

            self.client = httpx.Client(
                transport=transport,
                trust_env=False, timeout=self.timeout_seconds, follow_redirects=False,
                headers={"User-Agent": "Web3Reputation-ReadOnlyFeasibility/0.1"},
            )

    @staticmethod
    def _check_public_headers(target: PublicTarget) -> None:
        if target.headers is not None and (not isinstance(target.headers, dict) or any(
            not isinstance(key, str) or key.lower() not in {"accept", "mcp-protocol-version"}
            or not isinstance(value, str) or "\r" in value or "\n" in value
            for key, value in target.headers.items()
        )):
            raise ValueError("Public request headers only permit Accept and MCP-Protocol-Version")

    @staticmethod
    def _check_zan_target(target: PublicTarget) -> None:
        endpoints = {"https://api.zan.top/node/v1/base/mainnet",
                     "https://api.zan.top/node/v1/bsc/mainnet"}
        methods = {"eth_chainId", "eth_blockNumber", "eth_getBlockByNumber",
                   "eth_getTransactionByHash", "eth_getTransactionReceipt", "eth_call",
                   "eth_getLogs", "eth_getCode", "eth_getBalance"}
        rpc_method = target.json_body.get("method") if isinstance(target.json_body, dict) else None
        if (target.url not in endpoints or target.method != "POST"
            or not isinstance(target.json_body, dict) or target.json_body.get("jsonrpc") != "2.0"
            or not isinstance(rpc_method, str) or rpc_method not in methods):
            raise ValueError("ZAN credentials only allow fixed Base/BSC read-only JSON-RPC targets")

    @staticmethod
    def _check_public_destination(url: str) -> None:
        host = urlsplit(url).hostname
        addresses = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
        if not addresses or any(
            not ipaddress.ip_address(address[4][0]).is_global
            for address in addresses
        ):
            raise PermissionError("Non-public destination")

    def fetch(self, key: str, directory: Path) -> ProbeObservation:
        if self._provider_scopes or self._zan_key_scope:
            from reputation_platform.llm_network import sanitized_network_logs

            with sanitized_network_logs():
                return self._fetch(key, directory)
        return self._fetch(key, directory)

    def _fetch(self, key: str, directory: Path) -> ProbeObservation:
        if not self.enabled:
            raise PermissionError("Public reads are disabled")
        target = self.targets[key]
        self._check_public_headers(target)
        if self._provider_scopes and self._provider_scopes.get(key) != (target.url, target.method):
            raise ValueError("LLM endpoint changed after scope approval")
        if self._provider_models_check and target.json_body is not None:
            raise ValueError("Model discovery only permits an empty GET request")
        if self._zan_key_scope:
            self._check_zan_target(target)
            if target.json_body["method"] != self._zan_rpc_methods[key]:
                raise ValueError("ZAN RPC method changed after scope approval")
        if self.remaining <= 0 or urlsplit(target.url).hostname in self.stopped_hosts:
            raise PermissionError("Request budget exhausted or host stop condition")
        self.remaining -= 1
        observed_at = datetime.now(timezone.utc)
        started = time.monotonic()
        status = None
        error = None
        complete = False
        body = bytearray()
        outcome = Verdict.UNKNOWN
        try:
            if not self._pin_public_dns:
                self._check_public_destination(target.url)
            self._ensure_client()
            # Only the wire URL includes the ZAN credential; targets and evidence stay public.
            transport_url = target.url + "/" + self._provider_secret.decode("utf-8") if self._zan_key_scope else target.url
            with self.client.stream(target.method, transport_url, json=target.json_body,
                                    headers={**(target.headers or {}), **self._provider_headers}) as response:
                status = response.status_code
                if status in (401, 402, 403, 429):
                    self.stopped_hosts.add(urlsplit(target.url).hostname)
                for chunk in response.iter_bytes():
                    room = self.max_body_bytes - len(body)
                    body.extend(chunk[:room])
                    if len(chunk) > room:
                        error = "response_too_large"
                        break
                    if time.monotonic() - started > self.timeout_seconds:
                        error = "total_timeout"
                        break
                else:
                    complete = True
                if error is None:
                    if 200 <= status < 300:
                        # Fetching a payload cannot prove a business assertion.
                        if target.purpose in (MeasurementPurpose.BACKGROUND, MeasurementPurpose.AVAILABILITY):
                            outcome = Verdict.PASS
                    elif status in (301, 302, 303, 307, 308):
                        error = "redirect_not_followed"
                    elif status == 429:
                        error = "rate_limited"
                    elif status == 402:
                        error = "payment_required"
                    elif status in (401, 403):
                        error = "access_denied"
                    else:
                        error = "http_status_not_success"
        except PermissionError:
            error = "destination_policy_blocked"
        except (socket.gaierror, httpx.HTTPError) as exc:
            error = type(exc).__name__
        response_file = None
        digest = None
        if (self._provider_scopes or self._zan_key_scope) and body:
            # Decode before checking: JSON escaping must not hide a credential or private URL.
            try:
                decoded = json.loads(body)
                secret_echo = _contains_private(decoded, (self._provider_secret.decode("utf-8"),))
                config_echo = _contains_private(decoded, tuple(value.decode("utf-8") for value in self._private_values))
            except (ValueError, UnicodeError, RecursionError):
                body = bytearray(b'{"error":"invalid_provider_json"}')
                error, complete, outcome = "invalid_provider_json", False, Verdict.UNKNOWN
            else:
                if secret_echo or config_echo:
                    body = bytearray(b'{"error":"provider_private_echo_redacted","redaction":"[REDACTED]"}'
                                     if self._zan_key_scope else b'{"error":"provider_private_echo_redacted"}')
                    error = "provider_secret_echo_redacted" if secret_echo else "provider_config_echo_redacted"
                    complete, outcome = False, Verdict.UNKNOWN
        if self._provider_secret and self._provider_secret in body:
            body = body.replace(self._provider_secret, b"[REDACTED]")
            error, complete, outcome = "provider_secret_echo_redacted", False, Verdict.UNKNOWN
        for private in self._private_values:
            if private in body:
                body = body.replace(private, b"[REDACTED]")
                error, complete, outcome = "provider_config_echo_redacted", False, Verdict.UNKNOWN
        if body or status is not None:
            response_file = f"{key}.response.bin"
            with (directory / response_file).open("xb") as stream:
                stream.write(body)
            digest = hashlib.sha256(body).hexdigest()
        observation = ProbeObservation(
            request_key=key, purpose=target.purpose, url=self._provider_evidence_urls.get(key, target.url),
            method=target.method,
            request_json=(json.dumps(target.json_body, sort_keys=True) if target.json_body is not None else None),
            observed_at=observed_at, http_status=status,
            elapsed_ms=round((time.monotonic() - started) * 1000, 2),
            outcome=outcome, error_kind=error, response_file=response_file,
            response_sha256=digest, body_complete=complete,
        )
        with (directory / f"{key}.observation.json").open("x", encoding="utf-8") as stream:
            stream.write(observation.model_dump_json(indent=2))
        if self._network_transport is not None:
            with (directory / f"{key}.network.json").open("x", encoding="utf-8") as stream:
                json.dump({**self._network_transport.diagnostics,
                           "proxy": self._network_route.diagnostics()}, stream, indent=2)
        return observation
