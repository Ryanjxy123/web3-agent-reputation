"""Offline checks for portable ZAN credentials and reuse of scoped safe networking."""

import io
import json
import logging
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import httpcore
import httpx

from reputation_platform import settings
from reputation_platform.safe_http import PublicTarget, SafeHttpClient
from test_llm_network import _RecordingStream, _dns, PUBLIC_IP


ENDPOINT = "https://api.zan.top/node/v1/base/mainnet"
TEST_TOKEN = "unit-test-zan-private-token"


class ZanConfigurationTests(unittest.TestCase):
    def setUp(self):
        base = Path(__file__).resolve().parents[1] / "runtime/test-temp"
        base.mkdir(parents=True, exist_ok=True)
        temporary = TemporaryDirectory(dir=base)
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.root_patch = patch.object(settings, "PROJECT_ROOT", self.root)
        self.root_patch.start()
        self.addCleanup(self.root_patch.stop)
        environment = patch.dict(os.environ, {}, clear=True)
        environment.start()
        self.addCleanup(environment.stop)

    def test_credential_selection_preserves_cli_env_pointer_and_legacy_priority(self):
        legacy = Path("legacy-credential.txt")
        self.assertEqual(settings.load_zan_key_file(fallback=legacy), legacy)
        self.assertEqual(settings.load_zan_key_file(), self.root / "runtime/secrets/zan-rpc-url.txt")
        conventional = self.root / "secrets/zan-base-rpc.txt"
        conventional.parent.mkdir()
        conventional.write_text("unit-test-placeholder", encoding="utf-8")
        self.assertEqual(settings.load_zan_key_file(fallback=legacy), conventional)
        pointer = self.root / "runtime/platform-config/zan-key-file.txt"
        pointer.parent.mkdir(parents=True)
        pointer.write_text("secrets/custom-zan.txt\n", encoding="utf-8-sig")
        self.assertEqual(settings.load_zan_key_file(fallback=legacy), self.root / "secrets/custom-zan.txt")
        os.environ["REPUTATION_ZAN_KEY_FILE"] = "secrets/env-zan.txt"
        self.assertEqual(settings.load_zan_key_file(), self.root / "secrets/env-zan.txt")
        self.assertEqual(settings.load_zan_key_file(Path("explicit.txt")), Path("explicit.txt"))
        del os.environ["REPUTATION_ZAN_KEY_FILE"]
        pointer.write_text("one\ntwo", encoding="utf-8")
        with self.assertRaises(RuntimeError):
            settings.load_zan_key_file()

    def _client(self, **kwargs):
        key = self.root / "unit-test-zan.txt"
        key.write_text(ENDPOINT + "/" + TEST_TOKEN, encoding="utf-8-sig")
        target = PublicTarget("zan", ENDPOINT, "POST", json_body={
            "jsonrpc": "2.0", "id": 1, "method": "eth_chainId", "params": [],
        })
        return SafeHttpClient((target,), enabled=True, zan_key_url_file=key, **kwargs)

    def test_zan_uses_own_proxy_and_dns_options_and_never_logs_credential(self):
        stream = _RecordingStream("http", body=b'{"jsonrpc":"2.0","id":1,"result":"0x2105"}')
        messages = io.StringIO()
        logger = logging.getLogger("httpx")
        handler, old_level = logging.StreamHandler(messages), logger.level
        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)
        self.addCleanup(logger.removeHandler, handler)
        self.addCleanup(logger.setLevel, old_level)
        with patch.dict(os.environ, {"REPUTATION_LLM_PROXY": "direct", "REPUTATION_LLM_DNS_MODE": "system",
                                    "REPUTATION_ZAN_PROXY": "http://127.0.0.1:31987"}), patch(
            "socket.getaddrinfo", return_value=_dns("198.18.0.100"),
        ), patch("reputation_platform.llm_network._doh_addresses", return_value=[PUBLIC_IP]), patch.object(
            httpcore.SyncBackend, "connect_tcp", return_value=stream,
        ) as dial, self._client() as client:
            observation = client.fetch("zan", self.root)
        self.assertEqual(observation.http_status, 200)
        self.assertEqual(dial.call_args.args[:2], ("127.0.0.1", 31987))
        self.assertIn(b"CONNECT 93.184.216.34:443", stream.writes[0])
        self.assertIn(("/base/mainnet/" + TEST_TOKEN).encode(), b"".join(stream.writes))
        self.assertEqual(observation.url, ENDPOINT)
        for path in self.root.glob("zan.*"):
            self.assertNotIn(TEST_TOKEN, path.read_text(encoding="utf-8"))
        self.assertNotIn(TEST_TOKEN, messages.getvalue())
        network = json.loads((self.root / "zan.network.json").read_text(encoding="utf-8"))
        self.assertEqual(network["dns_mode"], "auto")
        self.assertEqual(network["proxy"]["source"], "operator-env")

    def test_escaped_credential_echo_and_invalid_json_are_not_saved(self):
        escaped = "".join("\\u%04x" % ord(char) for char in TEST_TOKEN)
        for body in ('{"result":"' + escaped + '"}', "untrusted-text-" + TEST_TOKEN):
            with self.subTest(body_kind=body.startswith("{")):
                evidence = self.root / ("escaped" if body.startswith("{") else "invalid")
                evidence.mkdir()
                with patch.object(SafeHttpClient, "_check_public_destination"), self._client(
                    transport=httpx.MockTransport(lambda request: httpx.Response(200, content=body)),
                ) as client:
                    observation = client.fetch("zan", evidence)
                self.assertFalse(observation.body_complete)
                self.assertIn(observation.error_kind, ("provider_secret_echo_redacted", "invalid_provider_json"))
                raw = (evidence / observation.response_file).read_text(encoding="utf-8")
                self.assertNotIn(TEST_TOKEN, raw)
                self.assertNotIn(escaped, raw)

    def test_non_zan_requests_keep_the_previous_network_path(self):
        target = PublicTarget("public", "https://example.org")
        with SafeHttpClient((target,), pin_public_dns=True) as client:
            from reputation_platform.pinned_http import PinnedHTTPTransport
            self.assertIsInstance(client.client._transport, PinnedHTTPTransport)
