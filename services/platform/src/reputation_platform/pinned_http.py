"""HTTPS over a checked numeric destination, with the original TLS/HTTP origin."""

from contextlib import contextmanager
import ipaddress
import socket
import time
from urllib.parse import urlsplit

import httpcore
import httpx


@contextmanager
def _mapped_errors():
    try:
        yield
    except httpcore.TimeoutException:
        raise httpx.TimeoutException("Pinned HTTPS transport timed out") from None
    except (httpcore.NetworkError, httpcore.ProtocolError, httpcore.ProxyError,
            httpcore.UnsupportedProtocol) as error:
        raise httpx.TransportError("Pinned HTTPS transport: " + type(error).__name__) from None
    except socket.gaierror:
        raise httpx.ConnectError("Pinned HTTPS DNS resolution failed") from None


class PinnedBackend(httpcore.NetworkBackend):
    def __init__(self, hosts: frozenset[str], proxy: str | None) -> None:
        self.hosts = hosts
        self.proxy = None
        if proxy is not None:
            parsed = urlsplit(proxy)
            if (parsed.scheme != "http" or parsed.hostname != "127.0.0.1" or parsed.port != 7897
                or parsed.username or parsed.password or parsed.path not in ("", "/")
                or parsed.query or parsed.fragment):
                raise ValueError("Pinned reads only support the operator HTTP proxy at 127.0.0.1:7897")
            self.proxy = ("127.0.0.1", 7897)
        self.backend = httpcore.SyncBackend()

    def connect_tcp(self, host, port, timeout=None, local_address=None, socket_options=None):
        if host not in self.hosts or port != 443:
            raise PermissionError("Origin is outside the pinned HTTPS scope")
        addresses = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
        ips = [ipaddress.ip_address(item[4][0]) for item in addresses]
        if not ips or any(not ip.is_global for ip in ips):
            raise PermissionError("Origin resolved to a non-public destination")
        ip = str(ips[0])
        destination = self.proxy or (ip, port)
        deadline = time.monotonic() + (timeout if timeout is not None else 15)
        stream = self.backend.connect_tcp(*destination, timeout=timeout,
            local_address=local_address, socket_options=socket_options)
        if self.proxy is None:
            return stream
        authority = f"[{ip}]:443" if ":" in ip else f"{ip}:443"
        try:
            stream.write(f"CONNECT {authority} HTTP/1.1\r\nHost: {authority}\r\n\r\n".encode("ascii"),
                         timeout=max(0, deadline - time.monotonic()))
            header = bytearray()
            while b"\r\n\r\n" not in header:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise httpcore.ConnectTimeout("Proxy CONNECT deadline reached")
                if len(header) >= 8192:
                    raise httpcore.ProxyError("Proxy CONNECT response headers too large")
                chunk = stream.read(min(1024, 8192 - len(header)), timeout=remaining)
                if not chunk:
                    raise httpcore.ProxyError("Proxy CONNECT response incomplete")
                header.extend(chunk)
            head, trailing = header.split(b"\r\n\r\n", 1)
            status = head.split(b"\r\n", 1)[0].split(b" ", 2)
            if (len(status) < 2 or status[0] not in (b"HTTP/1.0", b"HTTP/1.1")
                or status[1] != b"200" or trailing):
                raise httpcore.ProxyError("Proxy did not establish the requested IP tunnel")
            return stream
        except BaseException:
            stream.close()
            raise


class _ResponseStream(httpx.SyncByteStream):
    def __init__(self, stream) -> None:
        self.stream = stream

    def __iter__(self):
        with _mapped_errors():
            yield from self.stream

    def close(self) -> None:
        with _mapped_errors():
            self.stream.close()


class PinnedHTTPTransport(httpx.BaseTransport):
    def __init__(self, urls: tuple[str, ...], proxy: str | None) -> None:
        hosts = frozenset(httpx.URL(url).raw_host.decode("ascii") for url in urls)
        self.pool = httpcore.ConnectionPool(network_backend=PinnedBackend(hosts, proxy),
            max_connections=4, max_keepalive_connections=0, http2=False, retries=0)

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        if request.url.scheme != "https" or request.url.port not in (None, 443):
            raise PermissionError("Pinned transport only permits HTTPS on port 443")
        # No extension may replace the certificate/SNI name of the original URL.
        extensions = {key: value for key, value in request.extensions.items() if key != "sni_hostname"}
        wire = httpcore.Request(method=request.method,
            url=httpcore.URL(scheme=request.url.raw_scheme, host=request.url.raw_host,
                             port=request.url.port, target=request.url.raw_path),
            headers=request.headers.raw, content=request.stream, extensions=extensions)
        with _mapped_errors():
            response = self.pool.handle_request(wire)
        return httpx.Response(response.status, headers=response.headers,
            stream=_ResponseStream(response.stream), extensions=response.extensions)

    def close(self) -> None:
        with _mapped_errors():
            self.pool.close()
