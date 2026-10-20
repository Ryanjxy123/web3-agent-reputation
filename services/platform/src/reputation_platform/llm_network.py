"""Scoped provider public-IP pinning using httpcore's HTTP/SOCKS proxy protocols."""

import ipaddress
import json
import logging
import os
import socket
import time
from contextlib import contextmanager
from contextvars import ContextVar

import httpcore
import httpx

from reputation_platform.llm_network_settings import _validate_proxy


_FAKE_IP = ipaddress.ip_network("198.18.0.0/15")
_PRIVATE_NETWORK_CONTEXT = ContextVar("llm_private_network_context", default=False)


class _PrivateLogFilter(logging.Filter):
    def filter(self, record):
        # Library INFO/DEBUG messages may include private URLs, CONNECT auth or
        # headers. Keep only our structured, sanitized diagnostics in this scope.
        return not _PRIVATE_NETWORK_CONTEXT.get()


for _logger_name in ("httpx", "httpcore.connection", "httpcore.proxy", "httpcore.socks",
                     "httpcore.http11", "httpcore.http2"):
    logging.getLogger(_logger_name).addFilter(_PrivateLogFilter())


@contextmanager
def sanitized_network_logs():
    token = _PRIVATE_NETWORK_CONTEXT.set(True)
    try:
        yield
    finally:
        _PRIVATE_NETWORK_CONTEXT.reset(token)


def _public_addresses(values: list[str]) -> list[str]:
    try:
        addresses = [ipaddress.ip_address(value) for value in values]
    except ValueError:
        raise PermissionError("Invalid DNS answer") from None
    if not addresses or any(not address.is_global or address.is_multicast for address in addresses):
        raise PermissionError("Non-public DNS answer")
    return list(dict.fromkeys(str(address) for address in addresses))


def _doh_addresses(host: str, proxy: str, timeout: float) -> list[str]:
    """Fixed, certificate-verified bootstrap; never sends the LLM key to DNS."""
    deadline = time.monotonic() + timeout
    addresses = []
    # This IP is the resolver's documented HTTPS endpoint, not a destination allowlist.
    with httpx.Client(proxy=proxy, trust_env=False, follow_redirects=False) as client:
        for record_type in ("A", "AAAA"):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise httpx.ConnectTimeout("Independent DNS timeout")
            with client.stream("GET", "https://1.1.1.1/dns-query",
                               params={"name": host, "type": record_type},
                               headers={"Accept": "application/dns-json"}, timeout=remaining) as response:
                if response.status_code != 200:
                    raise httpx.ConnectError("Independent DNS HTTPS request failed")
                body = bytearray()
                for chunk in response.iter_bytes():
                    body.extend(chunk)
                    if len(body) > 65_536:
                        raise httpx.ConnectError("Independent DNS response too large")
                    if time.monotonic() > deadline:
                        raise httpx.ConnectTimeout("Independent DNS timeout")
            try:
                payload = json.loads(body)
                if (not isinstance(payload, dict) or payload.get("Status") != 0
                        or payload.get("TC", False) is not False):
                    raise ValueError
                answers = payload.get("Answer", [])
                if not isinstance(answers, list):
                    raise ValueError
                for answer in answers:
                    if not isinstance(answer, dict) or answer.get("type") not in (1, 5, 28):
                        raise ValueError
                    if answer["type"] in (1, 28):
                        value = ipaddress.ip_address(answer["data"])
                        if value.version != (4 if answer["type"] == 1 else 6):
                            raise ValueError
                        addresses.append(str(value))
                    elif not isinstance(answer.get("data"), str):
                        raise ValueError
            except (ValueError, TypeError, KeyError, UnicodeError):
                raise httpx.ConnectError("Invalid independent DNS response") from None
    return _public_addresses(addresses)


def _remaining(deadline: float, timeout: float | None) -> float:
    left = deadline - time.monotonic()
    if left <= 0:
        raise httpcore.ConnectTimeout("Provider total network timeout")
    return min(left, timeout) if timeout is not None else left


class _OriginStream(httpcore.NetworkStream):
    """Keep original certificate identity while httpcore tunnels to a numeric IP.

    httpcore.HTTPProxy does not consume the sni_hostname extension. Only its
    target TLS name is adapted here; CONNECT/SOCKS and TLS remain library code.
    An HTTPS proxy's first TLS layer keeps the proxy's own identity.
    """

    def __init__(self, stream, host: str, deadline: float, proxy_tls: bool):
        self.stream, self.host = stream, host
        self.deadline, self.proxy_tls = deadline, proxy_tls

    def read(self, max_bytes, timeout=None):
        return self.stream.read(max_bytes, _remaining(self.deadline, timeout))

    def write(self, buffer, timeout=None):
        self.stream.write(buffer, _remaining(self.deadline, timeout))

    def start_tls(self, ssl_context, server_hostname=None, timeout=None):
        hostname = server_hostname if self.proxy_tls else self.host
        stream = self.stream.start_tls(ssl_context=ssl_context, server_hostname=hostname,
                                       timeout=_remaining(self.deadline, timeout))
        return _OriginStream(stream, self.host, self.deadline, False)

    def get_extra_info(self, info):
        return self.stream.get_extra_info(info)

    def close(self):
        self.stream.close()


class _Backend(httpcore.SyncBackend):
    def __init__(self, host: str, deadline: float, proxy_tls: bool):
        self.host, self.deadline, self.proxy_tls = host, deadline, proxy_tls

    def connect_tcp(self, host, port, timeout=None, local_address=None, socket_options=None):
        stream = super().connect_tcp(host, port, timeout=_remaining(self.deadline, timeout),
                                     local_address=local_address, socket_options=socket_options)
        return _OriginStream(stream, self.host, self.deadline, self.proxy_tls)


def _safe_error(exc: Exception) -> httpx.HTTPError:
    if isinstance(exc, (httpcore.TimeoutException, httpx.TimeoutException)):
        return httpx.ConnectTimeout("Provider network timeout; inspect sanitized network diagnostics")
    if isinstance(exc, (httpcore.ProxyError, httpx.ProxyError)):
        return httpx.ProxyError("Provider proxy connection failed; inspect proxy settings")
    return httpx.ConnectError("Provider network connection failed; inspect sanitized network diagnostics")


class _ResponseStream(httpx.SyncByteStream):
    def __init__(self, stream, pool, diagnostics):
        self.stream, self.pool, self.diagnostics = stream, pool, diagnostics

    def __iter__(self):
        try:
            yield from self.stream
        except (httpcore.NetworkError, httpcore.ProtocolError, httpcore.TimeoutException) as exc:
            self.diagnostics["error"] = type(exc).__name__
            raise _safe_error(exc) from None

    def close(self):
        try:
            try:
                self.stream.close()
            finally:
                self.pool.close()
        except (httpcore.NetworkError, httpcore.ProtocolError, httpcore.TimeoutException, OSError) as exc:
            self.diagnostics["error"] = type(exc).__name__
            raise _safe_error(exc) from None


class LLMHTTPTransport(httpx.BaseTransport):
    """Exact authorized URLs, fresh DNS checks, numeric destination and verified TLS.

    proxy=None means direct. Only scope-approved LLM/ZAN provider reads opt in;
    untrusted Agent endpoints cannot select this transport or its proxy.
    """

    def __init__(self, urls: tuple[str, ...], proxy: str | None = None, *, dns_mode: str | None = None):
        self.urls = frozenset(str(httpx.URL(url)) for url in urls)
        for url in self.urls:
            parsed = httpx.URL(url)
            if (parsed.scheme != "https" or not parsed.host or parsed.userinfo
                    or parsed.port not in (None, 443) or parsed.fragment):
                raise ValueError("Provider network requires scoped HTTPS URLs")
        self.proxy = _validate_proxy(proxy) if proxy is not None else None
        self.dns_mode = dns_mode if dns_mode is not None else os.environ.get("REPUTATION_LLM_DNS_MODE", "auto")
        if self.dns_mode not in {"auto", "system"}:
            raise ValueError("Provider DNS mode must be auto or system")
        # Load trust stores once during configuration, before any network deadline.
        self._ssl_context = httpx.create_ssl_context(trust_env=False)
        self._proxy_ssl_context = (httpcore.default_ssl_context()
                                   if self.proxy and httpx.URL(self.proxy).scheme == "https" else None)
        self.diagnostics = {"route": httpx.URL(proxy).scheme if proxy else "direct",
                            "dns_mode": self.dns_mode, "fake_ip": False,
                            "dns_source": "system", "safety": "not_checked", "stage": "not_started", "error": None}

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        if str(request.url) not in self.urls or request.url.scheme != "https":
            raise PermissionError("Provider URL is outside authorized scope")
        self.diagnostics.update(fake_ip=False, dns_source="system", safety="not_checked", stage="system_dns", error=None)
        timeouts = request.extensions.get("timeout", {})
        budget = timeouts.get("connect")
        if budget is None:
            budget = 15.0
        deadline = time.monotonic() + budget
        pool = None
        try:
            answers = socket.getaddrinfo(request.url.host, 443, type=socket.SOCK_STREAM)
            values = list(dict.fromkeys(answer[4][0] for answer in answers))
            try:
                resolved = [ipaddress.ip_address(value) for value in values]
            except ValueError:
                raise PermissionError("Invalid system DNS answer") from None
            fake = bool(resolved) and all(address in _FAKE_IP for address in resolved)
            self.diagnostics["fake_ip"] = any(address in _FAKE_IP for address in resolved)
            if fake:
                if not self.proxy or self.dns_mode == "system":
                    raise PermissionError("Fake-IP DNS requires an operator proxy and auto DNS mode")
                self.diagnostics["dns_source"] = "https_bootstrap"
                self.diagnostics["stage"] = "independent_dns"
                values = _doh_addresses(request.url.host, self.proxy, _remaining(deadline, None))
            addresses = _public_addresses(values)
            self.diagnostics["safety"] = "public_ip_pinned"
            self.diagnostics["stage"] = "target_connect"
            # Fresh pool per request prevents cross-host reuse when origins share an IP.
            proxy = httpx.Proxy(self.proxy) if self.proxy else None
            backend = _Backend(request.url.host, deadline, proxy is not None and proxy.url.scheme == "https")
            options = dict(network_backend=backend, ssl_context=self._ssl_context,
                           retries=0, max_connections=1, max_keepalive_connections=0)
            if proxy:
                pool_type = httpcore.SOCKSProxy if proxy.url.scheme == "socks5" else httpcore.HTTPProxy
                if self._proxy_ssl_context is not None:
                    options["proxy_ssl_context"] = self._proxy_ssl_context
                pool = pool_type(proxy_url=str(proxy.url), proxy_auth=proxy.raw_auth, **options)
            else:
                pool = httpcore.ConnectionPool(**options)
            ip = addresses[0]
            wire_host = f"[{ip}]" if proxy and proxy.url.scheme != "socks5" and ":" in ip else ip
            # The stream adapter supplies origin SNI. Passing this extension to
            # HTTPProxy would also overwrite an HTTPS proxy's *first* TLS name.
            extensions = {"timeout": {name: _remaining(deadline, value) for name, value in timeouts.items()}}
            headers = [(key, value) for key, value in request.headers.raw
                       if key.lower() not in {b"host", b"proxy-authorization"}]
            headers.append((b"Host", request.url.netloc))
            response = pool.handle_request(httpcore.Request(
                method=request.method,
                url=httpcore.URL(scheme=b"https", host=wire_host.encode(), port=443, target=request.url.raw_path),
                headers=headers, content=request.stream, extensions=extensions))
            self.diagnostics["stage"] = "response"
            return httpx.Response(response.status, headers=response.headers,
                                  stream=_ResponseStream(response.stream, pool, self.diagnostics))
        except PermissionError:
            self.diagnostics.update(safety="blocked", error="destination_policy_blocked")
            if pool is not None:
                pool.close()
            raise PermissionError("Provider destination blocked: inspect sanitized network diagnostics") from None
        except (socket.gaierror, httpcore.NetworkError, httpcore.ProtocolError, httpcore.TimeoutException,
                httpcore.ProxyError, httpx.HTTPError) as exc:
            self.diagnostics["error"] = "system_dns_failed" if isinstance(exc, socket.gaierror) else type(exc).__name__
            if pool is not None:
                pool.close()
            raise _safe_error(exc) from None
