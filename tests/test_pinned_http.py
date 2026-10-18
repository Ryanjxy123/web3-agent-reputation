from pathlib import Path
import socket
import ssl
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import httpcore

from reputation_platform.safe_http import PublicTarget, SafeHttpClient


class _RecordingStream(httpcore.NetworkStream):
    def __init__(self, proxy: bool) -> None:
        self.reads = ([b"HTTP/1.1 200 Connection Established\r\n\r\n"] if proxy else []) + [
            b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\nConnection: close\r\n\r\nok"
        ]
        self.writes = []
        self.tls = None

    def read(self, max_bytes, timeout=None):
        return self.reads.pop(0) if self.reads else b""

    def write(self, buffer, timeout=None):
        self.writes.append(buffer)

    def start_tls(self, ssl_context, server_hostname=None, timeout=None):
        self.tls = (server_hostname, ssl_context.check_hostname, ssl_context.verify_mode)
        return self

    def close(self):
        pass


class PinnedHTTPTests(unittest.TestCase):
    def test_checked_ip_keeps_origin_tls_host_and_allowed_protocol_headers(self) -> None:
        targets = (
            PublicTarget("pinned", "https://example.org/document.json", headers={
                "Accept": "application/json", "MCP-Protocol-Version": "2025-03-26",
            }),
            PublicTarget("unused", "https://unused.example.org/card.json"),
        )
        public = (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("93.184.216.34", 443))
        private = (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("127.0.0.1", 443))
        temporary_root = Path(__file__).resolve().parents[1] / "runtime/test-temp"
        temporary_root.mkdir(parents=True, exist_ok=True)
        with TemporaryDirectory(dir=temporary_root) as temporary:
            for name, proxy in (("proxy", "http://127.0.0.1:7897"), ("direct", None)):
                with self.subTest(connection=name):
                    directory = Path(temporary) / name
                    directory.mkdir()
                    stream = _RecordingStream(proxy is not None)
                    with patch("socket.getaddrinfo", return_value=[public]) as dns, patch.object(
                        httpcore.SyncBackend, "connect_tcp", return_value=stream,
                    ) as dial, SafeHttpClient(
                        targets, enabled=True, proxy=proxy, pin_public_dns=True,
                    ) as client:
                        dns.assert_not_called()
                        observation = client.fetch("pinned", directory)
                    dns.assert_called_once_with("example.org", 443, type=socket.SOCK_STREAM)
                    self.assertEqual(dial.call_args.args, ("127.0.0.1", 7897) if proxy else ("93.184.216.34", 443))
                    self.assertEqual(stream.tls, ("example.org", True, ssl.CERT_REQUIRED))
                    if proxy:
                        self.assertEqual(stream.writes[0], b"CONNECT 93.184.216.34:443 HTTP/1.1\r\nHost: 93.184.216.34:443\r\n\r\n")
                    request = b"".join(stream.writes[1:] if proxy else stream.writes).lower()
                    self.assertIn(b"host: example.org\r\n", request)
                    self.assertIn(b"accept: application/json\r\n", request)
                    self.assertIn(b"mcp-protocol-version: 2025-03-26\r\n", request)
                    self.assertEqual(observation.url, targets[0].url)
                    self.assertIsNone(observation.error_kind)
                    self.assertEqual((directory / observation.response_file).read_bytes(), b"ok")

            directory = Path(temporary) / "blocked"
            directory.mkdir()
            with patch("socket.getaddrinfo", return_value=[public, private]), patch.object(
                httpcore.SyncBackend, "connect_tcp",
            ) as dial, SafeHttpClient(targets, enabled=True, pin_public_dns=True) as client:
                blocked = client.fetch("pinned", directory)
            dial.assert_not_called()
            self.assertEqual(blocked.error_kind, "destination_policy_blocked")
            self.assertIsNone(blocked.http_status)
            with self.assertRaises(ValueError):
                SafeHttpClient((PublicTarget("bad", targets[0].url, headers={"Authorization": "no"}),))
