"""Extract declarations from retained source material; execute only with --execute."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import secrets
import sys

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = (ROOT / "runtime").resolve()
sys.path[:0] = [str(ROOT / "packages/core/src"), str(ROOT / "services/platform/src")]

from reputation_core import SourceDocument
from reputation_platform.model_analysis import BALANCE_ENDPOINT, declaration_target, parse_declarations
from reputation_platform.safe_http import PublicTarget, SafeHttpClient
from reputation_platform.settings import load_llm_config, load_llm_key_file


def write_json(path: Path, value: object) -> None:
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)


def sources_from_review(directory: Path, selected: list[str] | None) -> list[tuple[str, list[SourceDocument]]]:
    review = json.loads((directory / "review.json").read_text(encoding="utf-8"))
    result = []
    for item in review["documents"]:
        key = item["candidate"]
        if selected and key not in selected:
            continue
        projection = (directory / item["projection_file"]).resolve()
        original = (ROOT / item["raw_file"]).resolve()
        if not projection.is_relative_to(directory) or not original.is_relative_to(RUNTIME):
            raise ValueError("Source material must stay inside its retained runtime directories")
        body, raw = projection.read_bytes(), original.read_bytes()
        if (hashlib.sha256(body).hexdigest() != item["projection_sha256"]
                or hashlib.sha256(raw).hexdigest() != item["raw_sha256"]):
            raise ValueError("Retained material digest mismatch")
        result.append((key, [SourceDocument(source_id=key, url=item["source_url"],
            raw_sha256=item["raw_sha256"], projection_sha256=item["projection_sha256"],
            text=body.decode("utf-8"))]))
    if not result or len({key for key, _ in result}) != len(result):
        raise ValueError("Select at least one unique candidate with source material")
    if selected and set(selected) != {key for key, _ in result}:
        raise ValueError("A selected candidate is absent from the review material")
    return result


def payload(run: Path, observation) -> dict:
    if observation.http_status != 200 or not observation.body_complete or observation.error_kind:
        raise RuntimeError(f"Provider request stopped: HTTP={observation.http_status}, error={observation.error_kind}")
    return json.loads((run / observation.response_file).read_bytes())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("review", type=Path)
    parser.add_argument("--candidates", nargs="+")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--proxy")
    parser.add_argument("--key-file", type=Path)
    args = parser.parse_args()
    directory = args.review.resolve()
    if not directory.is_relative_to(RUNTIME) or not directory.is_dir():
        parser.error("Review material must be an existing directory inside this project's runtime")
    try:
        config = load_llm_config()
    except (RuntimeError, ValueError):
        parser.error("Invalid local LLM configuration; check the configuration template")
    materials = sources_from_review(directory, args.candidates)
    requests = [declaration_target("analysis-" + key, sources, config) for key, sources in materials]
    print(json.dumps({"execution_enabled": args.execute, "candidates": [key for key, _ in materials],
                      "llm_config": config.record(),
                      "source_characters": {key: sum(len(source.text) for source in sources) for key, sources in materials}},
                     ensure_ascii=False))
    if not args.execute:
        return 0
    now = datetime.now(timezone.utc)
    run = RUNTIME / f"model-analysis-{now:%Y%m%dT%H%M%SZ}-{secrets.token_hex(4)}"
    run.mkdir()
    write_json(run / "manifest.json", {"started_at": now.isoformat(), "material_directory": str(directory.relative_to(ROOT)),
        "llm_config": config.record(), "candidates": [key for key, _ in materials], "retries": 0,
        "scores_computed": False, "key_material_recorded": False})
    targets = ((PublicTarget("balance-before", BALANCE_ENDPOINT), *requests,
               PublicTarget("balance-after", BALANCE_ENDPOINT)) if config.is_legacy else tuple(requests))
    results = []
    stopped = None
    with SafeHttpClient(targets, enabled=True, proxy=args.proxy, provider_key_file=load_llm_key_file(args.key_file),
                        provider_config=config, pin_public_dns=True,
                        max_requests=len(targets), timeout_seconds=60) as client:
        try:
            if config.is_legacy:
                balance = payload(run, client.fetch("balance-before", run))
                if balance.get("is_available") is not True:
                    raise RuntimeError("DeepSeek balance is insufficient")
            for (key, sources), target in zip(materials, requests):
                write_json(run / f"{key}.sources.json", [source.model_dump() for source in sources])
                write_json(run / f"{key}.intent.json", {"request_key": target.key,
                    "prepared_at": datetime.now(timezone.utc).isoformat(), "request_body": target.json_body})
                response = payload(run, client.fetch(target.key, run))
                try:
                    analysis, rejected = parse_declarations(response, sources, config.api_style)
                except ValueError as exc:
                    results.append({"candidate": key, "status": "INVALID_OUTPUT", "reason": "LLM output failed validation", "usage": response.get("usage")})
                    print(f"{key}: INVALID_OUTPUT (retained; no retry)")
                    continue
                write_json(run / f"{key}.analysis.json", analysis.model_dump())
                write_json(run / f"{key}.review.json", {"accepted_claims": len(analysis.claims), "rejections": rejected})
                results.append({"candidate": key, "status": "PARTIAL" if rejected else "VALIDATED", "claim_count": len(analysis.claims),
                                "rejected_claims": len(rejected),
                                "usage": response.get("usage"), "model": response.get("model")})
                print(f"{key}: validated_claims={len(analysis.claims)}")
            if config.is_legacy:
                after = payload(run, client.fetch("balance-after", run))
                print("balance_available=" + str(after.get("is_available")))
        except (RuntimeError, ValueError, PermissionError) as exc:
            stopped = "LLM request stopped: " + type(exc).__name__
            print(stopped)
    write_json(run / "result.json", {"results": results, "stopped_reason": stopped, "scores_computed": False})
    print("evidence_directory=" + str(run))
    return 1 if stopped or any(item["status"] not in ("VALIDATED", "PARTIAL") for item in results) else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RuntimeError, ValueError, OSError):
        raise SystemExit("LLM operation failed; check local configuration and retained observation error_kind") from None
