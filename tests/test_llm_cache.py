"""Retained LLM evidence remains verifiable across local model configuration changes."""

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from reputation_platform.llm import LEGACY_CONFIG, LLMConfig
from reputation_platform.question_translation import (
    QuestionMaterial, QuestionMaterials, load_verified_translations, question_digest,
    reference, translation_target, verify_cached_translation,
)


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))


class LLMCacheTests(unittest.TestCase):
    def setUp(self):
        temporary_root = ROOT / "runtime/test-temp"
        temporary_root.mkdir(parents=True, exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(dir=temporary_root)
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.run = self.root / "runtime/model-run"
        self.run.mkdir(parents=True)
        question = "Will the example event happen?"
        self.question = QuestionMaterial(question_sha256=question_digest(question), original_question=question, contexts=[])
        self.chat = LLMConfig("https://provider.example/v1", "example-model")

    def write(self, path, data):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    def fixture(self, config=LEGACY_CONFIG, *, legacy=False):
        translated = {"question_sha256": self.question.question_sha256,
            "original_question": self.question.original_question,
            "question_zh": "示例事件会发生吗？", "plain_language_zh": "这道题询问示例事件是否会发生。"}
        content = json.dumps({"schema_version": "prediction-question-translation-v1", "translations": [translated]}, ensure_ascii=False)
        response = ({"choices": [{"finish_reason": "stop", "message": {"role": "assistant", "content": content}}]}
            if config.api_style == "chat_completions" else
            {"status": "completed", "output": [{"type": "message", "content": [{"type": "output_text", "text": content}]}]})
        response_file = self.run / "batch.response.bin"
        self.write(response_file, response)
        target = translation_target("batch", [self.question], config)
        observation_file = self.run / "batch.observation.json"
        self.write(observation_file, {"request_key": "batch", "purpose": "background",
            "url": config.endpoint if legacy else config.evidence_url, "method": "POST",
            "request_json": json.dumps(target.json_body, ensure_ascii=False),
            "observed_at": datetime.now(timezone.utc).isoformat(), "http_status": 200,
            "elapsed_ms": 1.0, "outcome": "PASS", "error_kind": None,
            "response_file": response_file.name, "response_sha256": hashlib.sha256(response_file.read_bytes()).hexdigest(),
            "body_complete": True})
        directory = self.root / "runtime/question-translation-cache"
        if not config.is_legacy:
            directory /= config.fingerprint
        cached = directory / f"{self.question.question_sha256}.translation.json"
        data = {"translation": translated,
            "batch_questions": [{"question_sha256": self.question.question_sha256,
                                 "original_question": self.question.original_question}],
            "provider_response": reference(response_file, self.root).model_dump(),
            "provider_observation": reference(observation_file, self.root).model_dump()}
        if not legacy:
            data["llm_config"] = config.record()
        self.write(cached, data)
        return cached, data, observation_file

    def test_legacy_cache_verifies_independently_of_current_configuration(self):
        cached, _, _ = self.fixture(legacy=True)
        with patch.dict(os.environ, {"REPUTATION_LLM_MODEL": "another-model", "REPUTATION_LLM_API_STYLE": "chat_completions"}):
            translated, proofs = verify_cached_translation(cached, self.question, self.root)
        self.assertEqual(translated.question_sha256, self.question.question_sha256)
        self.assertEqual(len(proofs), 3)

    def test_chat_cache_rebuilds_and_wrong_configuration_is_rejected(self):
        cached, _, _ = self.fixture(self.chat)
        translated, _ = verify_cached_translation(cached, self.question, self.root, config=self.chat)
        self.assertIn("示例", translated.question_zh)
        with self.assertRaises(ValueError):
            verify_cached_translation(cached, self.question, self.root,
                config=LLMConfig(self.chat.base_url, "another-model"))

    def test_changed_record_namespace_request_and_response_are_rejected(self):
        cached, data, observation_file = self.fixture(self.chat)
        changed = {**data, "llm_config": {**data["llm_config"], "model": "changed-model"}}
        self.write(cached, changed)
        with self.assertRaises(ValueError):
            verify_cached_translation(cached, self.question, self.root)
        self.write(cached, data)
        moved = cached.parent.parent / ("f" * 64) / cached.name
        self.write(moved, data)
        with self.assertRaises(ValueError):
            verify_cached_translation(moved, self.question, self.root)
        observed = json.loads(observation_file.read_bytes())
        request = json.loads(observed["request_json"])
        request["model"] = "changed-model"
        observed["request_json"] = json.dumps(request)
        self.write(observation_file, observed)
        data["provider_observation"] = reference(observation_file, self.root).model_dump()
        self.write(cached, data)
        with self.assertRaises(ValueError):
            verify_cached_translation(cached, self.question, self.root)
        cached, _, _ = self.fixture(self.chat)
        (self.run / "batch.response.bin").write_bytes(b"{}")
        with self.assertRaises(ValueError):
            verify_cached_translation(cached, self.question, self.root)

    def test_old_and_new_cache_materials_load_without_current_provider(self):
        for config, legacy in ((LEGACY_CONFIG, True), (self.chat, False)):
            with self.subTest(api_style=config.api_style):
                cached, _, _ = self.fixture(config, legacy=legacy)
                translated, proofs = verify_cached_translation(cached, self.question, self.root)
                question = self.question.model_copy(update={"translation_status": "TRANSLATED",
                    "question_zh": translated.question_zh, "plain_language_zh": translated.plain_language_zh,
                    "translation_evidence": proofs})
                materials = QuestionMaterials(prepared_at=datetime.now(timezone.utc), sources=[], questions=[question])
                self.write(self.run / "materials.json", materials.model_dump(mode="json"))
                self.write(self.run / "manifest.json", {"inputs": []})
                loaded, _ = load_verified_translations(self.run, self.root)
                self.assertEqual(loaded[self.question.question_sha256], translated.model_dump())

    def test_duplicate_cache_evidence_is_rejected(self):
        cached, data, _ = self.fixture(self.chat)
        translated, proofs = verify_cached_translation(cached, self.question, self.root)
        duplicate = cached.parent.parent / ("e" * 64) / cached.name
        self.write(duplicate, data)
        question = self.question.model_copy(update={"translation_status": "TRANSLATED",
            "question_zh": translated.question_zh, "plain_language_zh": translated.plain_language_zh,
            "translation_evidence": [*proofs, reference(duplicate, self.root)]})
        materials = QuestionMaterials(prepared_at=datetime.now(timezone.utc), sources=[], questions=[question])
        self.write(self.run / "materials.json", materials.model_dump(mode="json"))
        self.write(self.run / "manifest.json", {"inputs": []})
        with self.assertRaises(ValueError):
            load_verified_translations(self.run, self.root)

    def test_switching_model_does_not_reuse_another_models_attempt(self):
        from translate_prediction_questions import apply_cache, cache_directory

        with patch("translate_prediction_questions.CACHE", self.root / "runtime/question-translation-cache"):
            attempt = cache_directory(self.chat) / f"{self.question.question_sha256}.attempt.json"
            self.write(attempt, {"llm_config": self.chat.record()})
            old = QuestionMaterials(prepared_at=datetime.now(timezone.utc), sources=[], questions=[self.question.model_copy()])
            self.assertEqual(apply_cache(old, self.chat), [])
            self.assertEqual(old.questions[0].translation_status, "REVIEW_REQUIRED")
            switched = QuestionMaterials(prepared_at=datetime.now(timezone.utc), sources=[], questions=[self.question.model_copy()])
            pending = apply_cache(switched, LLMConfig(self.chat.base_url, "another-model"))
            self.assertEqual(len(pending), 1)
            self.assertEqual(switched.questions[0].translation_status, "PENDING")

    def test_declaration_inventory_rebuilds_legacy_and_chat_and_rejects_tampering(self):
        import build_capability_inventory as inventory
        from reputation_core import DeclarationAnalysis, SourceDocument
        from reputation_platform.model_analysis import declaration_target

        text = "This example agent reads a wallet balance."
        digest = hashlib.sha256(text.encode()).hexdigest()
        source = SourceDocument(source_id="fixture", url="https://example.test/docs",
            raw_sha256=digest, projection_sha256=digest, text=text)
        analysis = DeclarationAnalysis(claims=[{
            "claim_id": "balance", "operation": "read_balance", "description": "读取余额",
            "inputs": ["wallet"], "outputs": ["balance"], "constraints": ["read only"],
            "access": "unknown", "citations": [{"source_id": "fixture", "quote": "reads a wallet balance"}],
        }], gaps=[])
        review = self.root / "runtime/review-run"
        review.mkdir()
        manifest_file = self.run / "manifest.json"
        observation_file = self.run / "analysis-fixture.observation.json"
        response_file = self.run / "analysis-fixture.response.bin"
        for config in (LEGACY_CONFIG, self.chat):
            with self.subTest(api_style=config.api_style), patch.object(inventory, "ROOT", self.root), patch.object(inventory, "INPUTS", {}):
                manifest = {"inputs": [], "material_directory": review.relative_to(self.root).as_posix()}
                if not config.is_legacy:
                    manifest["llm_config"] = config.record()
                self.write(manifest_file, manifest)
                self.write(self.run / "fixture.sources.json", [source.model_dump()])
                self.write(self.run / "fixture.analysis.json", analysis.model_dump())
                content = analysis.model_dump_json()
                response = ({"choices": [{"finish_reason": "stop", "message": {"role": "assistant", "content": content}}]}
                    if config.api_style == "chat_completions" else
                    {"status": "completed", "output": [{"type": "message", "content": [{"type": "output_text", "text": content}]}]})
                self.write(response_file, response)
                observed = {"request_key": "analysis-fixture", "purpose": "background",
                    "url": config.endpoint if config.is_legacy else config.evidence_url,
                    "method": "POST", "request_json": json.dumps(declaration_target("analysis-fixture", [source], config).json_body),
                    "observed_at": datetime.now(timezone.utc).isoformat(), "http_status": 200,
                    "elapsed_ms": 1.0, "outcome": "PASS", "error_kind": None,
                    "response_file": response_file.name, "response_sha256": hashlib.sha256(response_file.read_bytes()).hexdigest(),
                    "body_complete": True}
                self.write(observation_file, observed)
                stored, rejected = inventory.validated_asset(review, self.run, "fixture", [source])
                self.assertEqual(stored, analysis)
                self.assertEqual(rejected, [])
                request = json.loads(observed["request_json"])
                request["model"] = "changed-model"
                self.write(observation_file, {**observed, "request_json": json.dumps(request)})
                with self.assertRaises(ValueError):
                    inventory.validated_asset(review, self.run, "fixture", [source])
                self.write(observation_file, {**observed, "url": "https://wrong-provider.example/"})
                with self.assertRaises(ValueError):
                    inventory.validated_asset(review, self.run, "fixture", [source])
                if not config.is_legacy:
                    self.write(observation_file, observed)
                    self.write(manifest_file, {**manifest, "llm_config": {**config.record(), "model": "changed-model"}})
                    with self.assertRaises(ValueError):
                        inventory.validated_asset(review, self.run, "fixture", [source])


if __name__ == "__main__":
    unittest.main()
