import socket
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

import httpx

from reputation_core import MeasurementPurpose, Verdict
from reputation_platform.safe_http import PublicTarget, SafeHttpClient

TEMP_ROOT = Path(__file__).resolve().parents[1] / "runtime" / "test-temp"
TEMP_ROOT.mkdir(parents=True, exist_ok=True)


class SafeHttpTests(unittest.TestCase):
    def test_http_success_is_not_a_functional_verdict(self):
        public = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))]
        target = PublicTarget("unverified-business", "https://example.org/data", purpose=MeasurementPurpose.FUNCTIONAL)
        with tempfile.TemporaryDirectory(dir=TEMP_ROOT) as temporary, patch("socket.getaddrinfo", return_value=public), SafeHttpClient(
            (target,), enabled=True, transport=httpx.MockTransport(lambda request: httpx.Response(200, json={"success": True}))
        ) as client:
            observation = client.fetch(target.key, Path(temporary))
            self.assertEqual(observation.http_status, 200)
            self.assertTrue(observation.body_complete)
            self.assertEqual(observation.outcome, Verdict.UNKNOWN)

    def test_disabled_private_and_redirect_never_reach_another_destination(self):
        calls = []

        def respond(request):
            calls.append(str(request.url))
            return httpx.Response(302, headers={"location": "http://127.0.0.1/secret"})

        target = PublicTarget("fixture", "https://example.org/data")
        with tempfile.TemporaryDirectory(dir=TEMP_ROOT) as temporary:
            directory = Path(temporary)
            with SafeHttpClient((target,), transport=httpx.MockTransport(respond)) as client:
                with self.assertRaises(PermissionError):
                    client.fetch("fixture", directory)
            self.assertEqual(calls, [])
            private = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 443))]
            with patch("socket.getaddrinfo", return_value=private), SafeHttpClient(
                (target,), enabled=True, transport=httpx.MockTransport(respond)
            ) as client:
                observation = client.fetch("fixture", directory)
                self.assertEqual(observation.error_kind, "destination_policy_blocked")
            self.assertEqual(calls, [])
        public = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))]
        with tempfile.TemporaryDirectory(dir=TEMP_ROOT) as temporary, patch("socket.getaddrinfo", return_value=public), SafeHttpClient(
            (target,), enabled=True, transport=httpx.MockTransport(respond)
        ) as client:
            observation = client.fetch("fixture", Path(temporary))
            self.assertEqual(observation.error_kind, "redirect_not_followed")
            self.assertEqual(len(calls), 1)
            self.assertEqual(observation.outcome, Verdict.UNKNOWN)

    def test_raw_evidence_is_bounded_and_rate_limit_stops_run(self):
        public = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))]
        targets = (PublicTarget("oversize", "https://example.org/large"), PublicTarget("limited", "https://example.org/limited"))
        def respond(request):
            return httpx.Response(429) if request.url.path == "/limited" else httpx.Response(200, content=b"abcdef")
        with tempfile.TemporaryDirectory(dir=TEMP_ROOT) as temporary, patch("socket.getaddrinfo", return_value=public), SafeHttpClient(
            targets, enabled=True, max_body_bytes=3, transport=httpx.MockTransport(respond)
        ) as client:
            directory = Path(temporary)
            observation = client.fetch("oversize", directory)
            self.assertFalse(observation.body_complete)
            self.assertEqual(observation.outcome, Verdict.UNKNOWN)
            self.assertEqual((directory / observation.response_file).read_bytes(), b"abc")
            client.fetch("limited", directory)
            with self.assertRaises(PermissionError):
                client.fetch("limited", directory)
