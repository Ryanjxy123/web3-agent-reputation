"""Offline regressions for the LLM-only, address-pinned network transport."""

import ipaddress
import json
import socket
import ssl
import unittest
from unittest.mock import patch

import httpcore
import httpx

from reputation_platform.llm_network import LLMHTTPTransport, _doh_addresses


ORIGIN = "https://provider.example/v1/chat/completions"
PUBLIC_IP = "93.184.216.34"


def _dns(*addresses):
    return [
        (
            socket.AF_INET6 if ":" in address else socket.AF_INET,
            socket.SOCK_STREAM,
            socket.IPPROTO_TCP,
            "",
            (address, 443, 0, 0) if ":" in address else (address, 443),
        )
        for address in addresses
    ]


class _RecordingStream(httpcore.NetworkStream):
    def __init__(self, mode="direct", *, body=b"ok", status=200):
        self.reads = []
        if mode in ("http", "https"):
            self.reads.append(b"HTTP/1.1 200 Connection Established\r\n\r\n")
        elif mode == "socks5":
            self.reads.extend([
                b"\x05\x00",
                b"\x05\x00\x00\x01\x00\x00\x00\x00\x00\x00",
            ])
        self.reads.append(
            f"HTTP/1.1 {status} OK\r\nContent-Length: {len(body)}\r\n"
            "Connection: close\r\n\r\n".encode() + body
        )
        self.writes = []
        self.tls = []
        self.closed = False

    def read(self, max_bytes, timeout=None):
        result = self.reads.pop(0) if self.reads else b""
        if isinstance(result, Exception):
            raise result
        return result

    def write(self, buffer, timeout=None):
        self.writes.append(bytes(buffer))

    def start_tls(self, ssl_context, server_hostname=None, timeout=None):
        self.tls.append((server_hostname, ssl_context.check_hostname, ssl_context.verify_mode))
        return self

    def close(self):
        self.closed = True


class LLMNetworkTests(unittest.TestCase):
    def _client(self, proxy=None):
        return httpx.Client(
            transport=LLMHTTPTransport((ORIGIN,), proxy=proxy),
            trust_env=False,
            follow_redirects=False,
            timeout=3,
        )

    def test_direct_dials_checked_ip_and_keeps_original_host_and_tls(self):
        stream = _RecordingStream()
        with patch("socket.getaddrinfo", return_value=_dns(PUBLIC_IP)) as dns, patch.object(
            httpcore.SyncBackend, "connect_tcp", return_value=stream,
        ) as dial, self._client() as client:
            response = client.post(ORIGIN, json={"model": "unit-test-model"})
        self.assertEqual(response.text, "ok")
        self.assertEqual(dial.call_args.args[:2], (PUBLIC_IP, 443))
        self.assertEqual(dns.call_count, 1)
        self.assertEqual(stream.tls, [("provider.example", True, ssl.CERT_REQUIRED)])
        self.assertIn(b"Host: provider.example\r\n", b"".join(stream.writes))

    def test_certificate_setup_precedes_network_budget_and_is_reused(self):
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        clock = [0.0]

        def configure_context(**kwargs):
            clock[0] += 4
            return context

        with patch("reputation_platform.llm_network.time.monotonic", side_effect=lambda: clock[0]), patch(
            "reputation_platform.llm_network.httpx.create_ssl_context", side_effect=configure_context,
        ) as configure, patch("socket.getaddrinfo", return_value=_dns(PUBLIC_IP)) as dns, patch.object(
            httpcore.SyncBackend, "connect_tcp", side_effect=lambda *args, **kwargs: _RecordingStream(),
        ) as dial, self._client() as client:
            for _ in range(2):
                self.assertEqual(client.get(ORIGIN).text, "ok")
        configure.assert_called_once_with(trust_env=False)
        self.assertEqual((dns.call_count, dial.call_count), (2, 2))

    def test_dns_still_consumes_the_original_network_budget(self):
        clock = [0.0]

        def slow_dns(*args, **kwargs):
            clock[0] += 4
            return _dns(PUBLIC_IP)

        with self._client() as client, patch("reputation_platform.llm_network.time.monotonic", side_effect=lambda: clock[0]), patch(
            "socket.getaddrinfo", side_effect=slow_dns,
        ), patch.object(httpcore.SyncBackend, "connect_tcp") as dial:
            with self.assertRaises(httpx.ConnectTimeout):
                client.get(ORIGIN)
        dial.assert_not_called()

    def test_http_proxy_uses_arbitrary_port_and_numeric_connect(self):
        stream = _RecordingStream("http")
        with patch("socket.getaddrinfo", return_value=_dns(PUBLIC_IP)), patch.object(
            httpcore.SyncBackend, "connect_tcp", return_value=stream,
        ) as dial, self._client("http://127.0.0.1:31987") as client:
            self.assertEqual(client.get(ORIGIN).status_code, 200)
        self.assertEqual(dial.call_args.args[:2], ("127.0.0.1", 31987))
        self.assertIn(b"CONNECT 93.184.216.34:443 HTTP/1.1\r\n", stream.writes[0])
        self.assertNotIn(b"provider.example", stream.writes[0])
        self.assertEqual(stream.tls, [("provider.example", True, ssl.CERT_REQUIRED)])
        self.assertIn(b"Host: provider.example\r\n", b"".join(stream.writes[1:]))

    def test_https_proxy_verifies_proxy_and_original_origin_certificates(self):
        stream = _RecordingStream("https")
        with patch("socket.getaddrinfo", return_value=_dns(PUBLIC_IP)), patch.object(
            httpcore.SyncBackend, "connect_tcp", return_value=stream,
        ), self._client("https://127.0.0.1:31988") as client:
            self.assertEqual(client.get(ORIGIN).status_code, 200)
        self.assertEqual(stream.tls, [
            ("127.0.0.1", True, ssl.CERT_REQUIRED),
            ("provider.example", True, ssl.CERT_REQUIRED),
        ])
        self.assertNotIn(b"provider.example", stream.writes[0])

    def test_proxy_authorization_is_limited_to_connect_and_not_diagnostics(self):
        stream = _RecordingStream("http")
        transport = LLMHTTPTransport(
            (ORIGIN,), proxy="http://unit-test-user:unit-test-password@127.0.0.1:31987",
        )
        with patch("socket.getaddrinfo", return_value=_dns(PUBLIC_IP)), patch.object(
            httpcore.SyncBackend, "connect_tcp", return_value=stream,
        ), httpx.Client(transport=transport, trust_env=False) as client:
            client.get(ORIGIN)
        self.assertIn(b"Proxy-Authorization: Basic ", stream.writes[0])
        self.assertNotIn(b"Proxy-Authorization", b"".join(stream.writes[1:]))
        diagnostic = json.dumps(transport.diagnostics)
        for private in ("unit-test-user", "unit-test-password", "provider.example"):
            self.assertNotIn(private, diagnostic)

    def test_socks_proxy_uses_numeric_destination_and_original_tls(self):
        stream = _RecordingStream("socks5")
        with patch("socket.getaddrinfo", return_value=_dns(PUBLIC_IP)), patch.object(
            httpcore.SyncBackend, "connect_tcp", return_value=stream,
        ) as dial, self._client("socks5://127.0.0.1:31989") as client:
            self.assertEqual(client.get(ORIGIN).status_code, 200)
        self.assertEqual(dial.call_args.args[:2], ("127.0.0.1", 31989))
        command = stream.writes[1]
        self.assertNotIn(b"provider.example", command)
        self.assertTrue(PUBLIC_IP.encode() in command or socket.inet_aton(PUBLIC_IP) in command)
        self.assertEqual(stream.tls, [("provider.example", True, ssl.CERT_REQUIRED)])

    def test_caller_cannot_replace_sni_host_or_capture_private_trace(self):
        stream = _RecordingStream("http")
        traces = []
        with patch("socket.getaddrinfo", return_value=_dns(PUBLIC_IP)), patch.object(
            httpcore.SyncBackend, "connect_tcp", return_value=stream,
        ), self._client("http://127.0.0.1:31987") as client:
            client.get(ORIGIN, extensions={
                "sni_hostname": "attacker.example",
                "trace": lambda *args, **kwargs: traces.append((args, kwargs)),
            })
        self.assertEqual(stream.tls, [("provider.example", True, ssl.CERT_REQUIRED)])
        self.assertEqual(traces, [])

    def test_complete_url_scope_prevents_alias_port_scheme_and_path_changes(self):
        for url in (
            "https://attacker.example/v1/chat/completions",
            "https://provider.example/other",
            "https://provider.example:444/v1/chat/completions",
            "http://provider.example/v1/chat/completions",
        ):
            with self.subTest(url=url), patch.object(
                httpcore.SyncBackend, "connect_tcp",
            ) as dial, self._client() as client:
                with self.assertRaises((ValueError, PermissionError, httpx.HTTPError)):
                    client.get(url)
                dial.assert_not_called()

    def test_non_public_or_mixed_dns_is_rejected_before_any_dial(self):
        for addresses in (
            ["127.0.0.1"], ["10.0.0.2"], ["169.254.169.254"], ["::1"],
            ["fd00::1"], ["192.168.1.2"], [PUBLIC_IP, "127.0.0.1"],
            ["198.18.0.100", PUBLIC_IP], ["198.18.0.100", "10.0.0.2"], [],
        ):
            with self.subTest(addresses=addresses), patch(
                "socket.getaddrinfo", return_value=_dns(*addresses),
            ), patch.object(httpcore.SyncBackend, "connect_tcp") as dial, patch(
                "reputation_platform.llm_network._doh_addresses",
            ) as doh, self._client("http://127.0.0.1:31987") as client:
                with self.assertRaises((PermissionError, httpx.HTTPError)):
                    client.get(ORIGIN)
                dial.assert_not_called()
                doh.assert_not_called()

    def test_fake_ip_without_proxy_is_rejected_without_doh_or_dial(self):
        with patch("socket.getaddrinfo", return_value=_dns("198.18.0.100")), patch.object(
            httpcore.SyncBackend, "connect_tcp",
        ) as dial, patch("reputation_platform.llm_network._doh_addresses") as doh, self._client() as client:
            with self.assertRaises((PermissionError, httpx.HTTPError)):
                client.get(ORIGIN)
        doh.assert_not_called()
        dial.assert_not_called()

    def test_fake_ip_uses_independent_checked_dns_and_numeric_proxy_connect(self):
        stream = _RecordingStream("http")
        transport = LLMHTTPTransport((ORIGIN,), proxy="http://127.0.0.1:31987")
        with patch("socket.getaddrinfo", return_value=_dns("198.18.0.100")), patch(
            "reputation_platform.llm_network._doh_addresses", return_value=[PUBLIC_IP],
        ) as doh, patch.object(httpcore.SyncBackend, "connect_tcp", return_value=stream), httpx.Client(
            transport=transport, trust_env=False,
        ) as client:
            self.assertEqual(client.get(ORIGIN).status_code, 200)
        doh.assert_called_once()
        self.assertEqual(doh.call_args.args[0], "provider.example")
        self.assertIn(b"CONNECT 93.184.216.34:443", stream.writes[0])
        self.assertNotIn(b"198.18.0.100", b"".join(stream.writes))
        self.assertEqual(stream.tls, [("provider.example", True, ssl.CERT_REQUIRED)])
        self.assertIn("fake", json.dumps(transport.diagnostics).lower())

    def test_untrusted_independent_dns_addresses_are_rejected(self):
        for addresses in (
            ["127.0.0.1"], ["169.254.169.254"], ["198.18.0.101"],
            [PUBLIC_IP, "::1"], [], ["not-an-ip"],
        ):
            with self.subTest(addresses=addresses), patch(
                "socket.getaddrinfo", return_value=_dns("198.18.0.100"),
            ), patch("reputation_platform.llm_network._doh_addresses", return_value=addresses), patch.object(
                httpcore.SyncBackend, "connect_tcp",
            ) as dial, self._client("http://127.0.0.1:31987") as client:
                with self.assertRaises((ValueError, PermissionError, httpx.HTTPError)):
                    client.get(ORIGIN)
                dial.assert_not_called()

    def test_second_request_rechecks_dns_and_does_not_reuse_old_public_result(self):
        stream = _RecordingStream()
        with patch("socket.getaddrinfo", side_effect=[_dns(PUBLIC_IP), _dns("127.0.0.1")]), patch.object(
            httpcore.SyncBackend, "connect_tcp", return_value=stream,
        ) as dial, self._client() as client:
            self.assertEqual(client.get(ORIGIN).status_code, 200)
            with self.assertRaises((PermissionError, httpx.HTTPError)):
                client.get(ORIGIN)
        self.assertEqual(dial.call_count, 1)

    def test_dns_failure_is_not_silently_retried_using_proxy_dns(self):
        with patch("socket.getaddrinfo", side_effect=socket.gaierror("unit-test DNS failure")), patch.object(
            httpcore.SyncBackend, "connect_tcp",
        ) as dial, patch("reputation_platform.llm_network._doh_addresses") as doh, self._client(
            "http://127.0.0.1:31987",
        ) as client:
            with self.assertRaises((PermissionError, httpx.HTTPError, socket.gaierror)):
                client.get(ORIGIN)
        dial.assert_not_called()
        doh.assert_not_called()

    def test_proxy_failure_and_timeout_have_safe_errors_and_no_retry(self):
        for error in (
            httpcore.ProxyError("unit-test proxy detail"),
            httpcore.ConnectError("unit-test connect detail"),
            httpcore.ConnectTimeout("unit-test timeout detail"),
        ):
            with self.subTest(error=type(error).__name__), patch(
                "socket.getaddrinfo", return_value=_dns(PUBLIC_IP),
            ), patch.object(httpcore.SyncBackend, "connect_tcp", side_effect=error) as dial, self._client(
                "http://unit-test-user:unit-test-password@127.0.0.1:31987",
            ) as client:
                with self.assertRaises(httpx.HTTPError) as raised:
                    client.get(ORIGIN)
                self.assertEqual(dial.call_count, 1)
                message = str(raised.exception)
                self.assertNotIn("unit-test", message)
                self.assertNotIn("provider.example", message)

    def test_public_ipv6_is_supported_and_proxy_authority_is_bracketed(self):
        address = "2606:4700:4700::1111"
        self.assertTrue(ipaddress.ip_address(address).is_global)
        stream = _RecordingStream("http")
        with patch("socket.getaddrinfo", return_value=_dns(address)), patch.object(
            httpcore.SyncBackend, "connect_tcp", return_value=stream,
        ), self._client("http://127.0.0.1:31987") as client:
            self.assertEqual(client.get(ORIGIN).status_code, 200)
        self.assertIn(b"CONNECT [2606:4700:4700::1111]:443", stream.writes[0])
        self.assertEqual(stream.tls, [("provider.example", True, ssl.CERT_REQUIRED)])

    def test_malformed_system_dns_is_a_sanitized_connection_failure(self):
        with patch("socket.getaddrinfo", return_value=_dns("unit-test-invalid-address")), patch.object(
            httpcore.SyncBackend, "connect_tcp",
        ) as dial, self._client() as client:
            with self.assertRaises((PermissionError, httpx.HTTPError)) as raised:
                client.get(ORIGIN)
        dial.assert_not_called()
        self.assertNotIn("unit-test-invalid-address", str(raised.exception))

    def test_read_timeout_is_sanitized(self):
        stream = _RecordingStream()
        stream.reads = [
            b"HTTP/1.1 200 OK\r\nContent-Length: 4\r\n\r\nok",
            httpcore.ReadTimeout("unit-test-private-detail"),
        ]
        with patch("socket.getaddrinfo", return_value=_dns(PUBLIC_IP)), patch.object(
            httpcore.SyncBackend, "connect_tcp", return_value=stream,
        ), self._client() as client:
            with self.assertRaises(httpx.TimeoutException) as raised:
                client.get(ORIGIN)
        self.assertNotIn("unit-test-private-detail", str(raised.exception))

    def test_response_close_failure_is_sanitized(self):
        class FailCloseStream(_RecordingStream):
            def close(self):
                raise httpcore.ConnectError("unit-test-private-detail")

        stream = FailCloseStream()
        with patch("socket.getaddrinfo", return_value=_dns(PUBLIC_IP)), patch.object(
            httpcore.SyncBackend, "connect_tcp", return_value=stream,
        ), self._client() as client:
            with client.stream("GET", ORIGIN) as response:
                with self.assertRaises(httpx.HTTPError) as raised:
                    response.close()
        self.assertNotIn("unit-test-private-detail", str(raised.exception))


class IndependentDNSTests(unittest.TestCase):
    """The resolver is a fixed HTTPS bootstrap, never a new untrusted destination."""

    def _query(self, handler, *, timeout=3):
        real_client = httpx.Client
        options = []

        def client_factory(**kwargs):
            options.append(kwargs)
            return real_client(
                transport=httpx.MockTransport(handler), trust_env=False, follow_redirects=False,
            )

        with patch("reputation_platform.llm_network.httpx.Client", side_effect=client_factory):
            result = _doh_addresses("provider.example", "http://127.0.0.1:31987", timeout)
        self.assertEqual(options, [{
            "proxy": "http://127.0.0.1:31987", "trust_env": False, "follow_redirects": False,
        }])
        return result

    def test_fixed_https_resolver_queries_a_and_aaaa_without_llm_authorization(self):
        requests = []

        def handler(request):
            requests.append(request)
            self.assertEqual(request.method, "GET")
            self.assertEqual(request.url.scheme, "https")
            self.assertEqual(request.url.host, "1.1.1.1")
            self.assertEqual(request.url.path, "/dns-query")
            self.assertEqual(request.url.params["name"], "provider.example")
            self.assertEqual(request.headers["Accept"], "application/dns-json")
            self.assertNotIn("Authorization", request.headers)
            self.assertNotIn("Proxy-Authorization", request.headers)
            record = request.url.params["type"]
            answer = {"type": 1, "data": PUBLIC_IP} if record == "A" else {
                "type": 28, "data": "2606:4700:4700::1111",
            }
            return httpx.Response(200, json={"Status": 0, "Answer": [answer]})

        self.assertEqual(self._query(handler), [PUBLIC_IP, "2606:4700:4700::1111"])
        self.assertEqual([request.url.params["type"] for request in requests], ["A", "AAAA"])

    def test_rejects_failed_truncated_malformed_and_nonpublic_answers(self):
        invalid = [
            [], {"Status": 3}, {"Status": 0, "TC": True},
            {"Status": 0, "Answer": "not-a-list"},
            {"Status": 0, "Answer": [{"type": 15, "data": "provider.example"}]},
            {"Status": 0, "Answer": [{"type": 1}]},
            {"Status": 0, "Answer": [{"type": 1, "data": "invalid-ip"}]},
            {"Status": 0, "Answer": [{"type": 1, "data": "2606:4700:4700::1111"}]},
            {"Status": 0, "Answer": [{"type": 28, "data": PUBLIC_IP}]},
            {"Status": 0, "Answer": [{"type": 5, "data": 7}]},
            {"Status": 0, "Answer": [{"type": 1, "data": "169.254.169.254"}]},
            {"Status": 0, "Answer": [{"type": 1, "data": "198.18.0.100"}]},
            {"Status": 0, "Answer": []},
            {"Status": 0, "Answer": [
                {"type": 1, "data": PUBLIC_IP}, {"type": 28, "data": "::1"},
            ]},
        ]
        for payload in invalid:
            with self.subTest(payload=payload), self.assertRaises((PermissionError, httpx.HTTPError)):
                self._query(lambda request: httpx.Response(200, json=payload))

    def test_redirect_http_error_invalid_json_and_large_body_fail_closed(self):
        for response in (
            httpx.Response(302, headers={"Location": "http://127.0.0.1/private"}),
            httpx.Response(503, json={}),
            httpx.Response(200, content=b"not JSON"),
            httpx.Response(200, content=b" " * 65_537),
        ):
            requests = []

            def handler(request):
                requests.append(request)
                return response

            with self.subTest(status=response.status_code, size=len(response.content)):
                with self.assertRaises(httpx.HTTPError):
                    self._query(handler)
                self.assertEqual(len(requests), 1)

    def test_unavailable_proxy_and_timeout_do_not_retry(self):
        for error in (httpx.ProxyError("unit-test unavailable"), httpx.ReadTimeout("unit-test timeout")):
            calls = []

            def handler(request):
                calls.append(request)
                raise error

            with self.subTest(error=type(error).__name__), self.assertRaises(httpx.HTTPError):
                self._query(handler)
            self.assertEqual(len(calls), 1)

    def test_public_a_does_not_hide_private_aaaa(self):
        def handler(request):
            answer = {"type": 1, "data": PUBLIC_IP} if request.url.params["type"] == "A" else {
                "type": 28, "data": "::1",
            }
            return httpx.Response(200, json={"Status": 0, "Answer": [answer]})

        with self.assertRaises(PermissionError):
            self._query(handler)
