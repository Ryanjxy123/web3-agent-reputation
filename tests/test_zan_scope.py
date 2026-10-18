import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import httpx

from reputation_platform.safe_http import PublicTarget, SafeHttpClient


class ZanScopeTests(unittest.TestCase):
    def test_key_is_scoped_to_fixed_readonly_targets_and_never_recorded(self) -> None:
        secret = "unit-test-zan-key"
        endpoints = ("https://api.zan.top/node/v1/base/mainnet",
                     "https://api.zan.top/node/v1/bsc/mainnet")
        targets = tuple(PublicTarget(f"zan-{chain}", url, "POST", json_body={
            "jsonrpc": "2.0", "id": index, "method": "eth_chainId", "params": [],
        }) for index, (chain, url) in enumerate(zip(("base", "bsc", "error"), (*endpoints, endpoints[0])), 1))
        calls = []

        def respond(request: httpx.Request) -> httpx.Response:
            calls.append((str(request.url), request.headers.get("Authorization")))
            body = json.loads(request.content)
            if body["id"] == 3:
                raise httpx.ConnectError("Private wire URL: " + str(request.url), request=request)
            return httpx.Response(200, json={"jsonrpc": "2.0", "id": body["id"],
                                            "result": "0x2105" if body["id"] == 1 else secret})

        temporary_root = Path(__file__).resolve().parents[1] / "runtime/test-temp"
        temporary_root.mkdir(parents=True, exist_ok=True)
        with TemporaryDirectory(dir=temporary_root) as temporary:
            directory = Path(temporary)
            key = directory / "fake-zan-url.txt"
            key.write_text(endpoints[0] + "/" + secret, encoding="utf-8")
            evidence = directory / "evidence"
            evidence.mkdir()
            with patch.object(SafeHttpClient, "_check_public_destination"), SafeHttpClient(
                targets, enabled=True, zan_key_url_file=key, max_requests=3,
                transport=httpx.MockTransport(respond),
            ) as client:
                first = client.fetch("zan-base", evidence)
                echoed = client.fetch("zan-bsc", evidence)
                error = client.fetch("zan-error", evidence)
                targets[1].json_body["method"] = "eth_blockNumber"
                with self.assertRaisesRegex(ValueError, "changed after scope approval"):
                    client.fetch("zan-bsc", evidence)
                targets[1].json_body["method"] = "eth_sendRawTransaction"
                with self.assertRaises(ValueError):
                    client.fetch("zan-bsc", evidence)
            self.assertEqual(calls, [(url + "/" + secret, None) for url in (*endpoints, endpoints[0])])
            self.assertEqual(first.url, endpoints[0])
            self.assertEqual(echoed.url, endpoints[1])
            self.assertIsNone(first.error_kind)
            self.assertEqual(echoed.error_kind, "provider_secret_echo_redacted")
            self.assertFalse(echoed.body_complete)
            self.assertEqual(error.error_kind, "ConnectError")
            self.assertEqual(error.url, endpoints[0])
            self.assertNotIn(secret, error.model_dump_json())
            for path in evidence.iterdir():
                self.assertNotIn(secret, path.read_text(encoding="utf-8"))
            self.assertIn("[REDACTED]", (evidence / echoed.response_file).read_text(encoding="utf-8"))

            for url, method in (("https://example.test/rpc", "eth_chainId"),
                                (endpoints[0] + "/unexpected-key", "eth_chainId"),
                                (endpoints[0] + "?network=other", "eth_chainId"),
                                (endpoints[0], "eth_sendRawTransaction")):
                with self.subTest(url=url, method=method), self.assertRaises(ValueError):
                    SafeHttpClient((PublicTarget("rejected", url, "POST", json_body={
                        "jsonrpc": "2.0", "id": 1, "method": method, "params": [],
                    }),), enabled=True, zan_key_url_file=directory / "does-not-exist")
            with self.assertRaisesRegex(ValueError, "mutually exclusive"):
                SafeHttpClient((), enabled=True, provider_key_file=directory / "deepseek",
                               zan_key_url_file=key)
