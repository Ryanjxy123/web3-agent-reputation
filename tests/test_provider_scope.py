import socket
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

import httpx

from reputation_platform.safe_http import PublicTarget, SafeHttpClient


class ProviderScopeTests(unittest.TestCase):
    def test_provider_secret_is_scoped_and_not_recorded(self):
        temporary_root = Path(__file__).resolve().parents[1] / "runtime/test-temp"
        temporary_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=temporary_root) as temporary:
            directory = Path(temporary)
            key = directory / "provider.txt"
            key.write_text("unit-test-provider-key", encoding="utf-8")
            with self.assertRaises(ValueError):
                SafeHttpClient((PublicTarget("foreign", "https://example.org/data"),),
                               enabled=True, provider_key_file=key)
            calls = []
            def respond(request):
                calls.append(request.headers.get("authorization"))
                return httpx.Response(200, json={"is_available": True})
            public = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))]
            with patch("socket.getaddrinfo", return_value=public), SafeHttpClient(
                (PublicTarget("provider", "https://api.deepseek.com/user/balance"),),
                enabled=True, provider_key_file=key, transport=httpx.MockTransport(respond),
            ) as client:
                observation = client.fetch("provider", directory)
            self.assertEqual(calls, ["Bearer unit-test-provider-key"])
            self.assertNotIn("unit-test-provider-key", observation.model_dump_json())
            self.assertNotIn(b"unit-test-provider-key", (directory / observation.response_file).read_bytes())
