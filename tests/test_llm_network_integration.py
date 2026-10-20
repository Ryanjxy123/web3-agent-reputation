"""Offline integration of LLM routing, credential scope and public evidence."""

import json
import logging
import os
from pathlib import Path
import socket
import tempfile
from contextlib import contextmanager
from threading import Thread
import unittest
from unittest.mock import patch

import httpcore
import httpx

from reputation_platform.llm import LLMConfig
from reputation_platform.llm_network import LLMHTTPTransport, sanitized_network_logs
from reputation_platform.llm_network_settings import ProxyRoute
from reputation_platform.safe_http import PublicTarget, SafeHttpClient
from test_llm_network import PUBLIC_IP, _RecordingStream, _dns


TEMP_ROOT = Path(__file__).resolve().parents[1] / "runtime/test-temp"
TEMP_ROOT.mkdir(parents=True, exist_ok=True)
TEST_KEY = "unit-test-integration-key"


@contextmanager
def _debug_records():
    messages = []

    class Collector(logging.Handler):
        def emit(self, record):
            messages.append(record.getMessage())

    root = logging.getLogger()
    handler = Collector()
    loggers = [logging.getLogger(name) for name in (
        "httpx", "httpcore.connection", "httpcore.proxy", "httpcore.socks",
        "httpcore.http11", "httpcore.http2", "unit-test-application",
    )]
    levels = [(logger, logger.level) for logger in [root, *loggers]]
    root.addHandler(handler)
    for logger, _ in levels:
        logger.setLevel(logging.DEBUG)
    try:
        yield messages
    finally:
        root.removeHandler(handler)
        for logger, level in levels:
            logger.setLevel(level)


class LLMNetworkIntegrationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(dir=TEMP_ROOT)
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.key_file = self.directory / "unit-test-key.txt"
        self.key_file.write_text(TEST_KEY, encoding="utf-8")
        self.config = LLMConfig("https://private-provider.example/private-unit-test-path/v1", "unit-test-model")
        environment = patch.dict(os.environ, {}, clear=True)
        environment.start()
        self.addCleanup(environment.stop)

    def _client(self, target=None, **kwargs):
        target = target or PublicTarget("llm", self.config.endpoint, "POST", json_body={"model": self.config.model})
        return SafeHttpClient((target,), enabled=True, provider_key_file=self.key_file,
                              provider_config=self.config, **kwargs)

    def test_no_replacement_transport_automatically_uses_llm_public_ip_pinning(self):
        stream = _RecordingStream(body=b'{"choices": []}')
        with patch("reputation_platform.llm_network_settings.select_proxy", return_value=ProxyRoute(None, "unit-test")) as route, patch(
            "socket.getaddrinfo", return_value=_dns(PUBLIC_IP),
        ) as dns, patch.object(httpcore.SyncBackend, "connect_tcp", return_value=stream) as dial, self._client() as client:
            observation = client.fetch("llm", self.directory)
            self.assertIsInstance(client._network_transport, LLMHTTPTransport)
        route.assert_called_once_with(self.config.endpoint, None)
        dns.assert_called_once_with("private-provider.example", 443, type=socket.SOCK_STREAM)
        self.assertEqual(dial.call_args.args[:2], (PUBLIC_IP, 443))
        self.assertIsNone(observation.error_kind)
        self.assertEqual(observation.http_status, 200)
        self.assertEqual(observation.url, self.config.evidence_url)
        wire = b"".join(stream.writes)
        self.assertIn(("Authorization: Bearer " + TEST_KEY).encode(), wire)
        evidence = (self.directory / "llm.observation.json").read_text(encoding="utf-8")
        network = (self.directory / "llm.network.json").read_text(encoding="utf-8")
        for private in (TEST_KEY, "private-provider.example", "private-unit-test-path"):
            self.assertNotIn(private, evidence + network)
        self.assertEqual(json.loads(network)["safety"], "public_ip_pinned")

    def test_standard_proxy_environment_is_used_only_by_llm_connection(self):
        stream = _RecordingStream("http", body=b'{"choices": []}')
        with patch.dict(os.environ, {"HTTPS_PROXY": "http://127.0.0.1:31987"}), patch(
            "socket.getaddrinfo", return_value=_dns(PUBLIC_IP),
        ), patch.object(httpcore.SyncBackend, "connect_tcp", return_value=stream) as dial, self._client() as client:
            observation = client.fetch("llm", self.directory)
        self.assertIsNone(observation.error_kind)
        self.assertEqual(dial.call_args.args[:2], ("127.0.0.1", 31987))
        network = json.loads((self.directory / "llm.network.json").read_text(encoding="utf-8"))
        self.assertEqual(network["proxy"]["source"], "env")
        self.assertEqual(network["proxy"]["kind"], "http")

    def test_models_discovery_is_explicit_get_without_inference_body(self):
        target = PublicTarget("models", self.config.models_endpoint)
        stream = _RecordingStream(body=b'{"data":[{"id":"unit-test-model"}]}')
        with patch("reputation_platform.llm_network_settings.select_proxy", return_value=ProxyRoute(None, "unit-test")), patch(
            "socket.getaddrinfo", return_value=_dns(PUBLIC_IP),
        ), patch.object(httpcore.SyncBackend, "connect_tcp", return_value=stream), self._client(
            target, provider_models_check=True,
        ) as client:
            observation = client.fetch("models", self.directory)
        self.assertIsNone(observation.error_kind)
        self.assertIsNone(observation.request_json)
        request = b"".join(stream.writes)
        header, body = request.split(b"\r\n\r\n", 1)
        self.assertTrue(header.startswith(b"GET /private-unit-test-path/v1/models HTTP/1.1"))
        self.assertEqual(body, b"")
        self.assertIn(("Authorization: Bearer " + TEST_KEY).encode(), header)

    def test_key_cannot_be_sent_to_discovery_without_opt_in_or_to_arbitrary_scope(self):
        cases = [
            (PublicTarget("llm", self.config.models_endpoint), False),
            (PublicTarget("llm", self.config.endpoint), False),
            (PublicTarget("llm", "https://other.example/v1/models"), True),
            (PublicTarget("llm", self.config.models_endpoint + "/other"), True),
            (PublicTarget("llm", self.config.models_endpoint, "POST"), True),
            (PublicTarget("llm", self.config.models_endpoint, json_body={}), True),
            (PublicTarget("llm", self.config.endpoint, "POST", json_body={"model": "unit-test-model"}), True),
        ]
        for target, opt_in in cases:
            with self.subTest(method=target.method, url=target.url, opt_in=opt_in), patch.object(
                httpcore.SyncBackend, "connect_tcp",
            ) as dial:
                with self.assertRaises(ValueError):
                    self._client(target, provider_models_check=opt_in)
                dial.assert_not_called()

    def test_models_discovery_requires_operator_configuration(self):
        for key_file in (None, self.key_file):
            with self.subTest(key_file=key_file is not None), self.assertRaises(ValueError):
                SafeHttpClient((PublicTarget("models", self.config.models_endpoint),), enabled=True,
                               provider_key_file=key_file, provider_models_check=True)

    def test_mock_replacement_transport_ignores_system_and_environment_proxy(self):
        requests = []

        def respond(request):
            requests.append(request)
            return httpx.Response(200, json={"choices": []})

        with patch.dict(os.environ, {"HTTPS_PROXY": "http://127.0.0.1:31987"}), patch(
            "reputation_platform.llm_network_settings.select_proxy",
        ) as route, patch("socket.getaddrinfo", return_value=_dns(PUBLIC_IP)), patch.object(
            httpcore.SyncBackend, "connect_tcp",
        ) as dial, self._client(transport=httpx.MockTransport(respond)) as client:
            observation = client.fetch("llm", self.directory)
        self.assertIsNone(observation.error_kind)
        self.assertEqual(len(requests), 1)
        self.assertEqual(requests[0].url, self.config.endpoint)
        self.assertEqual(requests[0].headers["Authorization"], "Bearer " + TEST_KEY)
        route.assert_not_called()
        dial.assert_not_called()
        self.assertFalse((self.directory / "llm.network.json").exists())

    def test_authorized_models_scope_cannot_be_mutated_after_construction(self):
        with patch("reputation_platform.llm_network_settings.select_proxy", return_value=ProxyRoute(None, "unit-test")), self._client(
            PublicTarget("models", self.config.models_endpoint), provider_models_check=True,
        ) as client, patch.object(httpcore.SyncBackend, "connect_tcp") as dial:
            client.targets["models"] = PublicTarget("models", self.config.endpoint, "POST")
            with self.assertRaises(ValueError):
                client.fetch("models", self.directory)
        dial.assert_not_called()

    def test_models_scope_cannot_gain_a_request_body_after_construction(self):
        with patch("reputation_platform.llm_network_settings.select_proxy", return_value=ProxyRoute(None, "unit-test")), self._client(
            PublicTarget("models", self.config.models_endpoint), provider_models_check=True,
        ) as client, patch("socket.getaddrinfo", return_value=_dns(PUBLIC_IP)), patch.object(
            httpcore.SyncBackend, "connect_tcp", side_effect=AssertionError("Models body must be rejected before dial"),
        ) as dial:
            client.targets["models"] = PublicTarget("models", self.config.models_endpoint, json_body={"input": "unit-test"})
            with self.assertRaises(ValueError):
                client.fetch("models", self.directory)
        dial.assert_not_called()

    def test_fetch_hides_private_library_debug_logs_but_keeps_other_logs(self):
        stream = _RecordingStream("http", body=b'{"choices": []}')
        proxy = "http://unit-test-proxy-user:unit-test-proxy-password@127.0.0.1:31987"

        def connect(*args, **kwargs):
            for name in ("httpx", "httpcore.connection", "httpcore.proxy", "httpcore.socks",
                         "httpcore.http11", "httpcore.http2"):
                logging.getLogger(name).debug(
                    "unit-test-private-network url=%s key=%s proxy=%s", self.config.endpoint, TEST_KEY, proxy,
                )
            logging.getLogger("unit-test-application").warning("unit-test-application-visible")
            return stream

        with _debug_records() as messages, patch(
            "reputation_platform.llm_network_settings.select_proxy", return_value=ProxyRoute(proxy, "unit-test"),
        ), patch("socket.getaddrinfo", return_value=_dns(PUBLIC_IP)), patch.object(
            httpcore.SyncBackend, "connect_tcp", side_effect=connect,
        ), self._client() as client:
            observation = client.fetch("llm", self.directory)
            logging.getLogger("httpx").info("unit-test-outside-httpx-visible")
            logging.getLogger("httpcore.connection").debug("unit-test-outside-httpcore-visible")
        self.assertIsNone(observation.error_kind)
        output = "\n".join(messages)
        for private in (
            TEST_KEY, self.config.endpoint, "private-provider.example", "private-unit-test-path",
            "unit-test-proxy-user", "unit-test-proxy-password", "unit-test-private-network",
        ):
            self.assertNotIn(private, output)
        self.assertIn("unit-test-application-visible", output)
        self.assertIn("unit-test-outside-httpx-visible", output)
        self.assertIn("unit-test-outside-httpcore-visible", output)

    def test_private_log_context_is_nested_and_does_not_silence_other_threads(self):
        logger = logging.getLogger("httpcore.connection")
        with _debug_records() as messages:
            with sanitized_network_logs():
                logger.warning("unit-test-current-thread-hidden")
                with sanitized_network_logs():
                    logger.warning("unit-test-nested-hidden")
                logger.warning("unit-test-outer-context-still-hidden")
                thread = Thread(target=lambda: logger.warning("unit-test-other-thread-visible"))
                thread.start()
                thread.join(timeout=3)
                self.assertFalse(thread.is_alive())
            logger.warning("unit-test-context-reset-visible")
        self.assertEqual(messages, ["unit-test-other-thread-visible", "unit-test-context-reset-visible"])
