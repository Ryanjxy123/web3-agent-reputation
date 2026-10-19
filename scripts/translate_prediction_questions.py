"""Prepare Chinese question materials offline; --execute translates only fixed formal cohorts."""

from datetime import datetime, timezone
import argparse
import json
from pathlib import Path
import secrets
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "packages/core/src"), str(ROOT / "services/platform/src")]

from reputation_platform.model_analysis import BALANCE_ENDPOINT
from reputation_platform.question_translation import (
    QuestionMaterials, TranslationBatch, parse_translations,
    prepare_questions, reference, translation_target, verify_cached_translation,
)
from reputation_platform.safe_http import PublicTarget, SafeHttpClient
from reputation_platform.settings import load_llm_key_file

CACHE = ROOT / "runtime/question-translation-cache"


def write_json(path: Path, value: object) -> None:
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)


def apply_cache(materials: QuestionMaterials) -> list:
    pending = []
    for question in materials.questions:
        cached = CACHE / f"{question.question_sha256}.translation.json"
        attempted = CACHE / f"{question.question_sha256}.attempt.json"
        if cached.is_file():
            translated, proofs = verify_cached_translation(cached, question)
            question.question_zh, question.plain_language_zh = translated.question_zh, translated.plain_language_zh
            question.translation_status = "TRANSLATED"
            question.translation_evidence = proofs
            materials.sources.extend(question.translation_evidence)
        elif attempted.is_file():
            question.translation_status = "REVIEW_REQUIRED"
            question.translation_evidence = [reference(attempted)]
            materials.sources.extend(question.translation_evidence)
        else:
            pending.append(question)
    return pending


def payload(client: SafeHttpClient, key: str, run: Path) -> tuple[dict, Path]:
    observed = client.fetch(key, run)
    if observed.http_status != 200 or observed.error_kind or not observed.body_complete or not observed.response_file:
        raise RuntimeError(f"Provider read incomplete: HTTP={observed.http_status}, error={observed.error_kind}")
    response_file = run / observed.response_file
    return json.loads(response_file.read_bytes()), response_file


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundles", type=Path, nargs="+", required=True)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--proxy")
    parser.add_argument("--key-file", type=Path)
    args = parser.parse_args()
    if args.execute and not args.proxy:
        parser.error("Execution requires an explicit proxy")
    now = datetime.now(timezone.utc)
    materials = prepare_questions(args.bundles, now)
    pending = apply_cache(materials)
    batches = [pending[index:index + 7] for index in range(0, len(pending), 7)]
    targets = [translation_target(f"translate-batch-{index + 1:03d}", batch) for index, batch in enumerate(batches)]
    run = ROOT / "runtime" / f"question-translation-{now:%Y%m%dT%H%M%SZ}-{secrets.token_hex(4)}"
    run.mkdir()
    manifest = {"created_at": now.isoformat(), "execution_enabled": args.execute,
        "purpose": "Chinese reading aid; never probability evaluation, task execution or scoring",
        "question_count": len(materials.questions), "pending_question_count": len(pending),
        "batch_size": 7, "retries": 0, "scores_computed": False, "key_material_recorded": False,
        "inputs": [source.model_dump() for source in materials.sources]}
    write_json(run / "manifest.json", manifest)
    write_json(run / "translation.schema.json", TranslationBatch.model_json_schema())
    write_json(run / "materials.schema.json", QuestionMaterials.model_json_schema())
    write_json(run / "prepared-materials.json", materials.model_dump(mode="json"))
    results, stopped, attempted_calls = [], None, 0
    if args.execute and targets:
        CACHE.mkdir(exist_ok=True)
        scoped = (PublicTarget("balance-before", BALANCE_ENDPOINT), *targets, PublicTarget("balance-after", BALANCE_ENDPOINT))
        with SafeHttpClient(scoped, enabled=True, proxy=args.proxy, max_requests=len(scoped),
                            timeout_seconds=60, provider_key_file=load_llm_key_file(args.key_file)) as client:
            try:
                balance, _ = payload(client, "balance-before", run)
                if balance.get("is_available") is not True:
                    raise RuntimeError("DeepSeek balance is insufficient; no automatic top-up")
                for batch, target in zip(batches, targets):
                    batch_questions = [{"question_sha256": item.question_sha256,
                                        "original_question": item.original_question} for item in batch]
                    write_json(run / f"{target.key}.intent.json", {"request_body": target.json_body})
                    for question in batch:
                        write_json(CACHE / f"{question.question_sha256}.attempt.json",
                                   {"question_sha256": question.question_sha256,
                                    "original_question": question.original_question,
                                    "run": run.relative_to(ROOT).as_posix(), "request_key": target.key})
                    attempted_calls += 1
                    response, response_file = payload(client, target.key, run)
                    try:
                        translations = parse_translations(response, batch)
                    except ValueError as error:
                        results.append({"request_key": target.key, "status": "INVALID_OUTPUT", "reason": str(error),
                                        "usage": response.get("usage")})
                        for question in batch:
                            question.translation_status = "REVIEW_REQUIRED"
                        continue
                    by_digest = {item.question_sha256: item for item in batch}
                    proof = reference(response_file)
                    observation_proof = reference(run / f"{target.key}.observation.json")
                    for translated in translations:
                        cached = CACHE / f"{translated.question_sha256}.translation.json"
                        write_json(cached, {"translation": translated.model_dump(), "batch_questions": batch_questions,
                                            "provider_response": proof.model_dump(),
                                            "provider_observation": observation_proof.model_dump(), "model": response.get("model")})
                        question = by_digest[translated.question_sha256]
                        question.question_zh, question.plain_language_zh = translated.question_zh, translated.plain_language_zh
                        question.translation_status = "TRANSLATED"
                        question.translation_evidence = [reference(cached), proof, observation_proof]
                        materials.sources.extend(question.translation_evidence)
                    results.append({"request_key": target.key, "status": "TRANSLATED", "question_count": len(translations),
                                    "usage": response.get("usage"), "model": response.get("model")})
                after, _ = payload(client, "balance-after", run)
                if after.get("is_available") is not True:
                    stopped = "DeepSeek balance is insufficient; notify operator, no automatic top-up"
            except (RuntimeError, ValueError, OSError) as error:
                stopped = str(error)
    for question in materials.questions:
        if question.translation_status != "TRANSLATED" and (CACHE / f"{question.question_sha256}.attempt.json").is_file():
            question.translation_status = "REVIEW_REQUIRED"
            question.translation_evidence = [reference(CACHE / f"{question.question_sha256}.attempt.json")]
            materials.sources.extend(question.translation_evidence)
    write_json(run / "materials.json", materials.model_dump(mode="json"))
    write_json(run / "result.json", {"results": results, "stopped_reason": stopped,
        "model_calls_attempted": attempted_calls, "translated_questions": sum(
            item.translation_status == "TRANSLATED" for item in materials.questions),
        "review_required_questions": sum(item.translation_status == "REVIEW_REQUIRED" for item in materials.questions),
        "scores_computed": False})
    print(json.dumps({"run": run.relative_to(ROOT).as_posix(), "questions": len(materials.questions),
        "cached_or_translated": sum(item.translation_status == "TRANSLATED" for item in materials.questions),
        "model_calls_attempted": attempted_calls, "stopped_reason": stopped}, ensure_ascii=False))
    return 1 if stopped or any(item.translation_status == "REVIEW_REQUIRED" for item in materials.questions) else 0


if __name__ == "__main__":
    raise SystemExit(main())
