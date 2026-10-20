"""Offline LLM configuration, protocol and credential-boundary regression tests."""

import hashlib
import json
import os
from pathlib import Path
import socket
import tempfile
import unittest
from unittest.mock import patch

import httpx

from reputation_core import BusinessClaim, ClaimCitation, DeclarationAnalysis, SourceDocument
from reputation_platform.llm import LEGACY_CONFIG, LLMConfig, request_body, response_text
from reputation_platform.model_analysis import declaration_target, parse_declarations
from reputation_platform.safe_http import PublicTarget, SafeHttpClient
from reputation_platform.settings import load_llm_config, load_llm_key_file


TEMP_ROOT = Path(__file__).resolve().parents[1] / "runtime/test-temp"
TEMP_ROOT.mkdir(parents=True, exist_ok=True)
PUBLIC_DNS = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))]
TEST_KEY = "unit-test-placeholder-provider-key"


def chat_output(text='{"claims": []}'):
    return {"choices": [{"finish_reason": "stop", "message": {"role": "assistant", "content": text}}]}


def responses_output(text='{"claims": []}'):
    return {"status": "completed", "output": [{"type": "message", "content": [
        {"type": "output_text", "text": text},
    ]}]}


class LLMProtocolTests(unittest.TestCase):
    def test_base_path_and_complete_endpoint_are_not_duplicated(self):
        cases = [
            ("https://example.org", "chat_completions", "https://example.org/chat/completions"),
            ("https://example.org/v1/", "chat_completions", "https://example.org/v1/chat/completions"),
            ("https://example.org/v1/chat/completions", "chat_completions", "https://example.org/v1/chat/completions"),
            ("https://example.org/custom/v4/", "chat_completions", "https://example.org/custom/v4/chat/completions"),
            ("https://example.org/v1", "responses", "https://example.org/v1/responses"),
            ("https://example.org/responses/", "responses", "https://example.org/responses"),
        ]
        for base_url, style, endpoint in cases:
            with self.subTest(base_url=base_url, style=style):
                self.assertEqual(LLMConfig(base_url, "unit-test-model", style).endpoint, endpoint)

    def test_rejects_unsafe_url_without_echoing_private_value(self):
        invalid = [
            "http://example.org/v1", "https://unit-test-user:unit-test-password@example.org/v1",
            "https://example.org/v1?token=unit-test-query", "https://example.org/v1#unit-test-fragment",
            "https://example.org:8443/v1", "https://localhost/v1", "https://example.local/v1",
            "https://example.internal/v1", "https://127.0.0.1/v1", "https://10.1.2.3/v1",
            "https://169.254.169.254/v1", "https://[::1]/v1", "https://198.18.0.1/v1",
            "https://example.org\\unit-test-private", "https://example.org/v1\n",
        ]
        for base_url in invalid:
            with self.subTest(base_url=base_url):
                with self.assertRaises(ValueError) as caught:
                    LLMConfig(base_url, "unit-test-model")
                self.assertNotIn(base_url, str(caught.exception))
                self.assertNotIn("unit-test-password", str(caught.exception))

    def test_rejects_protocol_path_mismatch_unknown_style_and_invalid_model(self):
        for base_url, model, style in [
            ("https://example.org/responses", "unit-test-model", "chat_completions"),
            ("https://example.org/chat/completions", "unit-test-model", "responses"),
            ("https://example.org/v1", "unit-test-model", "unsupported"),
            ("https://example.org/v1", "", "chat_completions"),
            ("https://example.org/v1", "unit-test-model\nsecret", "chat_completions"),
        ]:
            with self.subTest(style=style, model=model):
                with self.assertRaises(ValueError):
                    LLMConfig(base_url, model, style)

    def test_configuration_record_is_private_and_isolates_model_protocol_endpoint(self):
        configs = [
            LLMConfig("https://example.org/private-unit-test-path/v1", "unit-test-model-a"),
            LLMConfig("https://example.org/private-unit-test-path/v1", "unit-test-model-b"),
            LLMConfig("https://example.org/private-unit-test-path/v1", "unit-test-model-a", "responses"),
            LLMConfig("https://example.org/other-private-unit-test-path/v1", "unit-test-model-a"),
        ]
        self.assertEqual(len({config.fingerprint for config in configs}), len(configs))
        for config in configs:
            public_record = json.dumps(config.record()) + config.evidence_url + repr(config)
            self.assertNotIn(config.base_url, public_record)
            self.assertNotIn("private-unit-test-path", public_record)
        self.assertEqual(configs[0].fingerprint,
                         LLMConfig(configs[0].base_url + "/", configs[0].model).fingerprint)

    def test_chat_request_has_configured_model_and_no_provider_specific_parameters(self):
        config = LLMConfig("https://example.org/v1", "unit-test-qwen-compatible")
        schema = {"type": "object", "properties": {"claims": {"type": "array"}}}
        body = request_body("Extract claims", {"source": "真实声明"}, schema, "declarations", config.record())
        self.assertEqual(body["model"], config.model)
        self.assertFalse(body["stream"])
        self.assertEqual([message["role"] for message in body["messages"]], ["system", "user"])
        self.assertEqual(json.loads(body["messages"][1]["content"]), {"source": "真实声明"})
        self.assertIn(json.dumps(schema, ensure_ascii=False), body["messages"][0]["content"])
        self.assertTrue({"reasoning", "tools", "tool_choice", "max_output_tokens", "response_format"}.isdisjoint(body))

    def test_legacy_responses_body_keeps_existing_capabilities(self):
        body = request_body("Extract", {"source": "test"}, {"type": "object"}, "declarations", LEGACY_CONFIG.record())
        self.assertEqual(body["model"], "deepseek-flash")
        self.assertEqual(body["reasoning"], {"effort": "none"})
        self.assertEqual(body["tools"], [])
        self.assertEqual(body["text"]["format"]["type"], "json_schema")
        self.assertTrue(LEGACY_CONFIG.is_legacy)
        other = LLMConfig("https://example.org/v1", "unit-test-responses-model", "responses")
        other_body = request_body("Extract", {}, {"type": "object"}, "declarations", other.record())
        self.assertEqual(other_body["model"], other.model)
        self.assertNotIn("reasoning", other_body)
        self.assertNotIn("tool_choice", other_body)

    def test_chat_and_responses_normalize_to_the_same_text(self):
        expected = '{"claims": []}'
        self.assertEqual(response_text(chat_output(expected), "chat_completions"), expected)
        split = chat_output()
        split["choices"][0]["message"]["content"] = [{"type": "text", "text": expected[:5]}, {"type": "text", "text": expected[5:]}]
        self.assertEqual(response_text(split, "chat_completions"), expected)
        self.assertEqual(response_text(responses_output(expected), "responses"), expected)

    def test_chat_rejects_incomplete_refused_tool_and_malformed_responses(self):
        invalid = [{}, {"error": {"message": "unit-test-private-provider-error"}}, {"choices": []}]
        for finish_reason in ("length", "content_filter", "tool_calls", None):
            item = chat_output()
            item["choices"][0]["finish_reason"] = finish_reason
            invalid.append(item)
        for field, value in (("refusal", "refused"), ("tool_calls", [{"id": "unit-test-tool"}]),
                             ("function_call", {"name": "unit-test-function"}), ("content", None),
                             ("content", ""), ("content", [{"type": "image_url", "image_url": {}}])):
            item = chat_output()
            item["choices"][0]["message"][field] = value
            invalid.append(item)
        invalid.append({"choices": chat_output()["choices"] * 2})
        for item in invalid:
            with self.subTest(response=item):
                with self.assertRaises(ValueError) as caught:
                    response_text(item, "chat_completions")
                self.assertNotIn("unit-test-private-provider-error", str(caught.exception))
        with self.assertRaises(ValueError):
            response_text(chat_output(), "unsupported")

    def test_responses_rejects_incomplete_refusal_and_tools(self):
        for item in (
            {"status": "incomplete", "output": []},
            {"status": "completed", "output": [{"type": "function_call"}]},
            {"status": "completed", "output": [{"type": "message", "content": [{"type": "refusal", "refusal": "refused"}]}]},
            {"status": "completed", "output": []},
        ):
            with self.subTest(response=item):
                with self.assertRaises(ValueError):
                    response_text(item, "responses")


class LLMSettingsTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(dir=TEMP_ROOT)
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.config_path = self.root / "runtime/platform-config/llm.json"
        self.config_path.parent.mkdir(parents=True)
        self.environment = patch.dict(os.environ, {}, clear=True)
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.project_root = patch("reputation_platform.settings.PROJECT_ROOT", self.root)
        self.project_root.start()
        self.addCleanup(self.project_root.stop)

    def write_config(self, **overrides):
        value = {"base_url": "https://example.org/unit-test/v1", "model": "unit-test-file-model",
                 "api_style": "chat_completions", "api_key_file": "runtime/secrets/unit-test-key.txt"}
        value.update(overrides)
        self.config_path.write_text(json.dumps(value), encoding="utf-8")

    def test_absent_config_preserves_deepseek_legacy_and_key_fallback(self):
        self.assertEqual(load_llm_config(), LEGACY_CONFIG)
        self.assertEqual(load_llm_key_file(), self.root / "runtime/secrets/deepseek-api-key.txt")

    def test_unified_private_file_selects_endpoint_model_protocol_and_key(self):
        self.write_config()
        config = load_llm_config()
        self.assertEqual(config.endpoint, "https://example.org/unit-test/v1/chat/completions")
        self.assertEqual(config.model, "unit-test-file-model")
        self.assertEqual(load_llm_key_file(), self.root / "runtime/secrets/unit-test-key.txt")

    def test_environment_overrides_private_file_and_new_key_alias_overrides_old(self):
        self.write_config()
        with patch.dict(os.environ, {"REPUTATION_LLM_BASE_URL": "https://example.net/v1",
                                    "REPUTATION_LLM_MODEL": "unit-test-env-model",
                                    "REPUTATION_LLM_API_STYLE": "responses",
                                    "REPUTATION_LLM_API_KEY_FILE": "runtime/secrets/unit-test-new-key.txt",
                                    "REPUTATION_LLM_KEY_FILE": "runtime/secrets/unit-test-old-key.txt"}):
            config = load_llm_config()
            self.assertEqual(config.endpoint, "https://example.net/v1/responses")
            self.assertEqual(config.model, "unit-test-env-model")
            self.assertEqual(load_llm_key_file(), self.root / "runtime/secrets/unit-test-new-key.txt")
            explicit = Path("unit-test-explicit-key.txt")
            self.assertEqual(load_llm_key_file(explicit), explicit)

    def test_old_key_environment_and_pointer_still_work(self):
        with patch.dict(os.environ, {"REPUTATION_LLM_KEY_FILE": "runtime/secrets/unit-test-old-key.txt"}):
            self.assertEqual(load_llm_key_file(), self.root / "runtime/secrets/unit-test-old-key.txt")
        pointer = self.root / "runtime/platform-config/llm-key-file.txt"
        pointer.write_text("runtime/secrets/unit-test-pointer-key.txt", encoding="utf-8")
        self.assertEqual(load_llm_key_file(), self.root / "runtime/secrets/unit-test-pointer-key.txt")

    def test_partial_new_configuration_does_not_silently_fall_back_to_legacy(self):
        for variables in ({"REPUTATION_LLM_MODEL": "unit-test-model"},
                          {"REPUTATION_LLM_BASE_URL": "https://example.org/v1"}):
            with self.subTest(variables=variables), patch.dict(os.environ, variables):
                with self.assertRaises((RuntimeError, ValueError)):
                    load_llm_config()

    def test_malformed_config_and_invalid_key_pointer_have_sanitized_errors(self):
        self.config_path.write_text('{"base_url": "unit-test-private-value",', encoding="utf-8")
        with self.assertRaises((RuntimeError, ValueError)) as caught:
            load_llm_config()
        self.assertNotIn("unit-test-private-value", str(caught.exception))
        self.config_path.unlink()
        with patch.dict(os.environ, {"REPUTATION_LLM_API_KEY_FILE": "\n"}):
            with self.assertRaises((RuntimeError, ValueError)):
                load_llm_key_file()


class LLMDeclarationTests(unittest.TestCase):
    def setUp(self):
        text = "This unit test Agent returns the BNB balance of a wallet."
        digest = hashlib.sha256(text.encode()).hexdigest()
        self.sources = [SourceDocument(source_id="unit-test-source", url="https://example.test/docs",
            raw_sha256=digest, projection_sha256=digest, text=text)]
        self.analysis = DeclarationAnalysis(claims=[BusinessClaim(
            claim_id="unit-test-balance", operation="get_balance", description="读取钱包 BNB 余额",
            inputs=["wallet"], outputs=["BNB balance"], constraints=["read only"], access="free",
            citations=[ClaimCitation(source_id="unit-test-source", quote="returns the BNB balance of a wallet")],
        )], gaps=[])

    def test_chat_and_legacy_responses_preserve_validated_declaration_interface(self):
        for style, output in (("chat_completions", chat_output), ("responses", responses_output)):
            with self.subTest(style=style):
                config = LLMConfig("https://example.org/v1", "unit-test-model", style)
                target = declaration_target("unit-test-declarations", self.sources, config)
                self.assertEqual(target.url, config.endpoint)
                self.assertEqual(target.json_body["model"], config.model)
                analysis, rejected = parse_declarations(output(self.analysis.model_dump_json()), self.sources, style)
                self.assertEqual(analysis, self.analysis)
                self.assertEqual(rejected, [])
        # Existing callers omit api_style, retaining the frozen Responses default.
        analysis, rejected = parse_declarations(responses_output(self.analysis.model_dump_json()), self.sources)
        self.assertEqual(analysis, self.analysis)
        self.assertEqual(rejected, [])

    def test_new_protocol_still_rejects_fabricated_source_quotes(self):
        fabricated = self.analysis.model_copy(deep=True)
        fabricated.claims[0].citations[0].quote = "unit test Agent transfers funds"
        for style, output in (("chat_completions", chat_output), ("responses", responses_output)):
            with self.subTest(style=style):
                analysis, rejected = parse_declarations(output(fabricated.model_dump_json()), self.sources, style)
                self.assertEqual(analysis.claims, [])
                self.assertEqual(len(rejected), 1)
                self.assertIn("quote not found", rejected[0])

    def test_bad_declaration_json_errors_do_not_echo_provider_text(self):
        for style, output in (("chat_completions", chat_output), ("responses", responses_output)):
            with self.subTest(style=style):
                with self.assertRaises(ValueError) as caught:
                    parse_declarations(output('{"private": "unit-test-private-provider-text"}'), self.sources, style)
                self.assertNotIn("unit-test-private-provider-text", str(caught.exception))


class LLMTransportTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(dir=TEMP_ROOT)
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.key = self.directory / "unit-test-key.txt"
        self.key.write_text(TEST_KEY, encoding="utf-8")
        self.config = LLMConfig("https://example.org/unit-test-private-path/v1", "unit-test-model")
        self.target = PublicTarget("unit-test-llm", self.config.endpoint, "POST", json_body={"model": self.config.model})

    def client(self, handler, *, target=None, **kwargs):
        return SafeHttpClient((target or self.target,), enabled=True, provider_key_file=self.key,
                              provider_config=self.config, transport=httpx.MockTransport(handler), **kwargs)

    def test_custom_model_endpoint_key_reach_only_authorized_mock_endpoint(self):
        calls = []
        def respond(request):
            calls.append((str(request.url), request.headers.get("authorization"), json.loads(request.content)))
            return httpx.Response(200, json=chat_output())
        with patch("socket.getaddrinfo", return_value=PUBLIC_DNS), self.client(respond) as client:
            observation = client.fetch(self.target.key, self.directory)
        self.assertEqual(calls, [(self.config.endpoint, "Bearer " + TEST_KEY, {"model": "unit-test-model"})])
        self.assertEqual(observation.http_status, 200)
        self.assertEqual(observation.url, self.config.evidence_url)
        evidence = (self.directory / f"{self.target.key}.observation.json").read_text(encoding="utf-8")
        self.assertNotIn(TEST_KEY, evidence)
        self.assertNotIn(self.config.base_url, evidence)
        self.assertNotIn("unit-test-private-path", evidence)

    def test_switching_configuration_changes_wire_endpoint_model_and_key(self):
        for index, (base_url, model, style) in enumerate((
            ("https://example.org/v1", "unit-test-deepseek-model", "chat_completions"),
            ("https://example.net/compatible/v1", "unit-test-qwen-model", "chat_completions"),
            ("https://example.org/v4", "unit-test-glm-model", "chat_completions"),
            ("https://example.net/v1", "unit-test-openai-model", "responses"),
        )):
            with self.subTest(model=model):
                config = LLMConfig(base_url, model, style)
                secret = f"unit-test-switched-key-{index}"
                self.key.write_text(secret, encoding="utf-8")
                target = PublicTarget(f"unit-test-switch-{index}", config.endpoint, "POST",
                    json_body=request_body("Extract", {}, {"type": "object"}, "declarations", config.record()))
                calls = []
                def respond(request):
                    calls.append((str(request.url), request.headers.get("authorization"), json.loads(request.content)["model"]))
                    return httpx.Response(200, json=chat_output() if style == "chat_completions" else responses_output())
                with patch("socket.getaddrinfo", return_value=PUBLIC_DNS), SafeHttpClient(
                    (target,), enabled=True, provider_key_file=self.key, provider_config=config,
                    transport=httpx.MockTransport(respond),
                ) as client:
                    observation = client.fetch(target.key, self.directory)
                self.assertEqual(calls, [(config.endpoint, "Bearer " + secret, model)])
                response = json.loads((self.directory / observation.response_file).read_bytes())
                self.assertEqual(response_text(response, style), '{"claims": []}')

    def test_credentials_cannot_follow_another_target_or_unauthorized_balance_request(self):
        for target in (PublicTarget("unit-test-foreign", "https://example.net/v1/chat/completions", "POST"),
                       PublicTarget("unit-test-balance", "https://api.deepseek.com/user/balance"),
                       PublicTarget("unit-test-wrong-method", self.config.endpoint)):
            with self.subTest(target=target.key):
                with self.assertRaises(ValueError):
                    self.client(lambda request: httpx.Response(200), target=target)

    def test_echoed_key_and_private_endpoint_are_removed_from_evidence(self):
        def respond(request):
            return httpx.Response(400, json={"error": {"message": TEST_KEY + " " + self.config.endpoint}})
        with patch("socket.getaddrinfo", return_value=PUBLIC_DNS), self.client(respond) as client:
            observation = client.fetch(self.target.key, self.directory)
        public_bytes = b"".join(path.read_bytes() for path in self.directory.iterdir() if path != self.key)
        self.assertNotIn(TEST_KEY.encode(), public_bytes)
        self.assertNotIn(self.config.endpoint.encode(), public_bytes)
        self.assertNotIn(self.config.base_url.encode(), public_bytes)
        self.assertFalse(observation.body_complete)
        self.assertIsNotNone(observation.error_kind)

    def test_json_escaped_key_and_endpoint_cannot_survive_in_saved_evidence(self):
        secret = 'unit-test-secret-with-"quote'
        self.key.write_text(secret, encoding="utf-8")
        escaped = json.dumps({"error": {"message": [secret + " " + self.config.endpoint]}}).replace("/", "\\/")
        with patch("socket.getaddrinfo", return_value=PUBLIC_DNS), self.client(
            lambda request: httpx.Response(400, content=escaped.encode())
        ) as client:
            observation = client.fetch(self.target.key, self.directory)
        body = (self.directory / observation.response_file).read_bytes()
        self.assertEqual(json.loads(body), {"error": "provider_private_echo_redacted"})
        self.assertNotIn(b"unit-test-secret-with-", body)
        self.assertNotIn(b"unit-test-private-path", body)
        self.assertEqual(observation.error_kind, "provider_secret_echo_redacted")
        self.assertFalse(observation.body_complete)

    def test_unicode_escaped_private_endpoint_in_json_object_key_is_rejected(self):
        escaped_url = "".join("\\u%04x" % ord(char) for char in self.config.endpoint)
        body = ('{"error":{"' + escaped_url + '":["unit-test-provider-error"]}}').encode()
        with patch("socket.getaddrinfo", return_value=PUBLIC_DNS), self.client(
            lambda request: httpx.Response(400, content=body)
        ) as client:
            observation = client.fetch(self.target.key, self.directory)
        stored = json.loads((self.directory / observation.response_file).read_bytes())
        self.assertEqual(stored, {"error": "provider_private_echo_redacted"})
        self.assertEqual(observation.error_kind, "provider_config_echo_redacted")
        self.assertFalse(observation.body_complete)

    def test_non_json_and_truncated_json_provider_errors_never_save_original_text(self):
        for index, original in enumerate((
            ("<html>" + TEST_KEY + " " + self.config.endpoint + "</html>").encode(),
            json.dumps({"error": TEST_KEY + " " + self.config.endpoint}).encode()[:-1],
        )):
            with self.subTest(index=index):
                directory = self.directory / str(index)
                directory.mkdir()
                with patch("socket.getaddrinfo", return_value=PUBLIC_DNS), self.client(
                    lambda request: httpx.Response(502, content=original)
                ) as client:
                    observation = client.fetch(self.target.key, directory)
                stored = (directory / observation.response_file).read_bytes()
                self.assertEqual(json.loads(stored), {"error": "invalid_provider_json"})
                self.assertEqual(observation.error_kind, "invalid_provider_json")
                self.assertFalse(observation.body_complete)

    def test_missing_empty_or_multiline_key_never_sends_a_request(self):
        for content in (None, "", "unit-test-first-line\nunit-test-second-line"):
            with self.subTest(content=content):
                if content is None:
                    self.key.unlink(missing_ok=True)
                else:
                    self.key.write_text(content, encoding="utf-8")
                with self.assertRaises((OSError, ValueError, RuntimeError)):
                    self.client(lambda request: self.fail("Invalid credential reached transport"))

    def test_timeout_is_bounded_sanitized_and_not_retried(self):
        calls = []
        def timeout(request):
            calls.append(request)
            raise httpx.ReadTimeout(TEST_KEY + " " + self.config.endpoint, request=request)
        with patch("socket.getaddrinfo", return_value=PUBLIC_DNS), self.client(timeout) as client:
            observation = client.fetch(self.target.key, self.directory)
        self.assertEqual(len(calls), 1)
        self.assertEqual(observation.error_kind, "ReadTimeout")
        self.assertNotIn(TEST_KEY, observation.model_dump_json())
        self.assertNotIn(self.config.endpoint, observation.model_dump_json())

    def test_dns_resolving_to_private_address_is_blocked_before_transport(self):
        addresses = PUBLIC_DNS + [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 443))]
        with patch("socket.getaddrinfo", return_value=addresses), self.client(
            lambda request: self.fail("Private DNS answer reached transport")
        ) as client:
            observation = client.fetch(self.target.key, self.directory)
        self.assertEqual(observation.error_kind, "destination_policy_blocked")

    def test_rate_limit_stops_further_requests(self):
        calls = []
        def respond(request):
            calls.append(request)
            return httpx.Response(429)
        with patch("socket.getaddrinfo", return_value=PUBLIC_DNS), self.client(respond) as client:
            observation = client.fetch(self.target.key, self.directory)
            with self.assertRaises(PermissionError):
                client.fetch(self.target.key, self.directory)
        self.assertEqual(observation.error_kind, "rate_limited")
        self.assertEqual(len(calls), 1)


if __name__ == "__main__":
    unittest.main()
