import os
import unittest
from unittest.mock import patch

from reputation_platform.llm_network_settings import ProxyRoute, select_proxy


class LLMProxySettingsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.environment = patch.dict(os.environ, {}, clear=True)
        self.environment.start()
        self.system = patch("reputation_platform.llm_network_settings._system_proxies", return_value={})
        self.system_reader = self.system.start()
        self.bypass = patch("reputation_platform.llm_network_settings._system_bypass", return_value=False)
        self.system_bypass = self.bypass.start()
        self.addCleanup(self.environment.stop)
        self.addCleanup(self.system.stop)
        self.addCleanup(self.bypass.stop)

    def test_direct_and_operator_override_precedence(self) -> None:
        self.assertEqual(select_proxy("https://example.org/v1").diagnostics(),
                         {"source": "direct", "kind": "direct", "auth": False})
        os.environ["HTTPS_PROXY"] = "http://environment.example:8080"
        explicit = select_proxy("https://example.org/v1", "https://explicit.example:8443")
        self.assertEqual(explicit.kind, "https")
        self.assertEqual(explicit.source, "explicit")
        os.environ["REPUTATION_LLM_PROXY"] = "socks5://operator.example:1080"
        dedicated = select_proxy("https://example.org/v1", "http://legacy.example:8888")
        self.assertEqual((dedicated.kind, dedicated.source), ("socks5", "llm-env"))
        os.environ["REPUTATION_LLM_PROXY"] = "direct"
        self.assertIsNone(select_proxy("https://example.org/v1", "http://legacy.example:8888").url)
        del os.environ["REPUTATION_LLM_PROXY"]
        self.assertIsNone(select_proxy("https://example.org/v1", "direct").url)

    def test_standard_environment_case_and_scheme_rules(self) -> None:
        # A plain mapping also tests POSIX case precedence on Windows.
        environment = {"HTTPS_PROXY": "http://upper.example:8080", "https_proxy": "https://lower.example:8443",
                       "ALL_PROXY": "socks5://fallback.example:1080"}
        with patch.object(os, "environ", environment):
            self.assertEqual(select_proxy("https://example.org").url, "https://lower.example:8443")
            del environment["https_proxy"]
            del environment["HTTPS_PROXY"]
            self.assertEqual(select_proxy("https://example.org").kind, "socks5")
            del environment["ALL_PROXY"]
            environment["HTTP_PROXY"] = "http://http-only.example:8080"
            self.system_reader.return_value = {"https": "http://system.example:8000"}
            self.assertEqual(select_proxy("https://example.org").diagnostics(),
                             {"source": "env", "kind": "direct", "auth": False})
        self.system_reader.assert_not_called()

    def test_no_proxy_applies_to_original_hostname_and_overrides(self) -> None:
        os.environ.update(HTTPS_PROXY="http://environment.example:8080", NO_PROXY=".example.org:443")
        self.assertIsNone(select_proxy("https://api.example.org/v1").url)
        self.assertEqual(select_proxy("https://api.example.org/v1", "http://explicit.example:8080").source,
                         "override-bypass")
        self.assertEqual(select_proxy("https://example.org.invalid").kind, "http")
        os.environ["no_proxy"] = "*"
        self.assertIsNone(select_proxy("https://unrelated.example").url)

    def test_system_settings_and_bypass_with_no_proxy_only(self) -> None:
        os.environ["NO_PROXY"] = "api.example.org"
        self.system_reader.return_value = {"https": "http://system.example:8080"}
        self.assertEqual(select_proxy("https://other.example.org").source, "system")
        self.assertEqual(select_proxy("https://other.example.org").kind, "http")
        self.assertIsNone(select_proxy("https://api.example.org").url)
        self.system_bypass.return_value = True
        self.assertIsNone(select_proxy("https://other.example.org").url)
        self.system_bypass.assert_called_with("other.example.org:443")

    def test_proxy_validation_and_diagnostics_never_include_private_values(self) -> None:
        private = "http://operator:private-placeholder@private-proxy.example:8080"
        route = select_proxy("https://example.org", private)
        self.assertEqual(route.diagnostics(), {"source": "explicit", "kind": "http", "auth": True})
        self.assertNotIn("operator", repr(route))
        self.assertNotIn("private", str(route.diagnostics()))
        for proxy in ("socks5h://proxy.example:1080", "file:///private", "http://proxy.example/path",
                      "http://proxy.example?secret=placeholder", "http://proxy.example#private",
                      "http://proxy.example:0", "http://proxy.example:99999", "http://proxy.example:bad",
                      "http://proxy.example\n", "http://proxy.example\\private", "proxy.example:8080", ""):
            with self.subTest(proxy_kind=proxy.split(":", 1)[0]):
                with self.assertRaises(ValueError) as error:
                    select_proxy("https://example.org", proxy)
                if proxy:
                    self.assertNotIn(proxy, str(error.exception))

    def test_system_failures_are_explicit_and_sanitized(self) -> None:
        self.system_reader.side_effect = OSError("private-system-value")
        with self.assertRaisesRegex(ValueError, "System proxy configuration") as error:
            select_proxy("https://example.org")
        self.assertNotIn("private-system-value", str(error.exception))
        self.system_reader.side_effect = None
        self.system_reader.return_value = {"https": "http://system.example:8080"}
        self.system_bypass.side_effect = ValueError("private-bypass-value")
        with self.assertRaisesRegex(ValueError, "System proxy bypass configuration") as error:
            select_proxy("https://example.org")
        self.assertNotIn("private-bypass-value", str(error.exception))

    def test_selection_does_not_resolve_or_connect_to_the_target(self) -> None:
        with patch("socket.getaddrinfo") as resolve, patch("socket.create_connection") as connect:
            self.assertIsInstance(select_proxy("https://example.org"), ProxyRoute)
        resolve.assert_not_called()
        connect.assert_not_called()


if __name__ == "__main__":
    unittest.main()
