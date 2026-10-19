"""Select a cited prediction-history plan from retained metadata and requests, offline."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import secrets
import sys
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "runtime"
sys.path[:0] = [str(ROOT / "packages/core/src"), str(ROOT / "services/platform/src")]

from analyze_declarations import sources_from_review
from select_evaluation_plan import get_run, local_file, read_json, write_json
from reputation_core import (
    CandidateRecord, DeclarationAnalysis, PredictionHistoryDescriptor, PredictionToolDescriptor,
    ProbeObservation, SourceDocument, prediction_tool_supported, select_prediction_plan, validate_analysis,
)
from reputation_platform.model_analysis import prediction_tool_descriptors


def retained_observation(value: str) -> tuple[Path, ProbeObservation, Path, dict]:
    path = (ROOT / value).resolve()
    if not path.is_relative_to(RUNTIME) or not path.name.endswith(".observation.json"):
        raise ValueError("Observation must identify a retained public runtime observation")
    path = local_file(path.parent, path.name)
    observation = ProbeObservation.model_validate_json(path.read_bytes())
    if (observation.http_status != 200 or not observation.body_complete or observation.error_kind
            or observation.method != "GET" or not observation.response_file):
        raise ValueError("Source observation must be a complete, successful retained GET")
    response = local_file(path.parent, observation.response_file)
    if hashlib.sha256(response.read_bytes()).hexdigest() != observation.response_sha256:
        raise ValueError("Retained source response digest differs from its observation")
    payload = read_json(response)
    if not isinstance(payload, dict):
        raise ValueError("Expected a JSON object source")
    return path, observation, response, payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("analysis-run", "review-run", "metadata-observation", "admission-run", "candidate-key",
                 "mech", "service-id"):
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--history-observation", help="Existing request metadata; structure only, not a scored sample")
    args = parser.parse_args()
    analysis_run, review_run, admission_run = (get_run(value) for value in
                                               (args.analysis_run, args.review_run, args.admission_run))
    analysis_manifest_file = local_file(analysis_run, "manifest.json")
    if get_run(read_json(analysis_manifest_file)["material_directory"]) != review_run:
        raise ValueError("Analysis and supplied digest-verified review material differ")
    key, expected_sources = sources_from_review(review_run, [args.candidate_key])[0]
    sources_file = local_file(analysis_run, key + ".sources.json")
    sources = [SourceDocument.model_validate(item) for item in read_json(sources_file)]
    if sources != expected_sources:
        raise ValueError("Model SourceDocuments differ from verified review material")
    analysis_file = local_file(analysis_run, key + ".analysis.json")
    analysis = validate_analysis(DeclarationAnalysis.model_validate(read_json(analysis_file)), sources)
    metadata_path, observation, metadata_file, metadata = retained_observation(args.metadata_observation)
    matching_sources = [source for source in sources if source.url == observation.url
                        and source.raw_sha256 == observation.response_sha256]
    if len(matching_sources) != 1:
        raise ValueError("Metadata observation URL and digest must match one actual analysis source")
    source = matching_sources[0]
    declared_domain = metadata.get("operator", {}).get("domain") or metadata.get("url")
    expected_prefix = f"{args.mech.lower().removeprefix('0x')}-100.mech."
    domain_url = declared_domain if isinstance(declared_domain, str) and "://" in declared_domain else f"https://{declared_domain}"
    if not isinstance(declared_domain, str) or not (urlsplit(domain_url).hostname or "").startswith(expected_prefix):
        raise ValueError("Source metadata does not declare the configured Mech and chain in its operator domain")
    tools = prediction_tool_descriptors(metadata)
    supported_operations = {tool.operation for tool in tools if prediction_tool_supported(tool)}
    matched_claims = [claim for claim in analysis.claims if claim.operation in supported_operations]
    admission_file = local_file(admission_run, "admission-report.json")
    admission = read_json(admission_file)
    if admission.get("schema_version") != "candidate-admission-v1":
        raise ValueError("Unsupported candidate snapshot schema")
    candidates = [item for item in admission["candidates"] if item["key"] == key]
    if len(candidates) != 1:
        raise ValueError("Admission snapshot must contain exactly one matching candidate")
    candidate_data = dict(candidates[0])
    candidate_data.pop("ready_for_full_score", None)
    candidate = CandidateRecord.model_validate(candidate_data)
    inputs = {analysis_manifest_file, analysis_file, sources_file, metadata_path, metadata_file, admission_file,
              local_file(review_run, "review.json"), ROOT / "docs/adr/0008-prediction-history-policy.md"}
    review_items = [item for item in read_json(review_run / "review.json")["documents"] if item["candidate"] == key]
    inputs.update(local_file(review_run, item["projection_file"]) for item in review_items)
    history, history_file = {}, None
    if args.history_observation:
        history_path, _, history_file, history = retained_observation(args.history_observation)
        inputs.update({history_path, history_file})
    context = history.get("request_context", {})
    if not isinstance(context, dict):
        context = {}
    descriptor = PredictionHistoryDescriptor(
        candidate_key=key, claim_ids=[claim.claim_id for claim in matched_claims], tools=tools,
        chain_id=100, protocol="olas-mech-marketplace", metadata_source_id=source.source_id,
        metadata_source_file=metadata_file.relative_to(ROOT).as_posix(),
        input_format=metadata.get("inputFormat"), output_format=metadata.get("outputFormat"),
        published_mech=args.mech, service_id=args.service_id,
        history_shape="omen-binary-request-v1" if context.get("type") == "omen" else None,
        history_source_file=history_file.relative_to(ROOT).as_posix() if history_file else None,
        history_tool=history.get("tool"), history_context_type=context.get("type"),
        history_market=context.get("market_id"), history_prompt=history.get("prompt"),
    )
    selection = select_prediction_plan(analysis, candidate, descriptor)
    now = datetime.now(timezone.utc)
    run = RUNTIME / f"plan-selection-{now:%Y%m%dT%H%M%SZ}-{secrets.token_hex(4)}"
    run.mkdir()
    write_json(run / "manifest.json", {"created_at": now.isoformat(), "network_requests": 0,
        "scores_computed": False, "policy_id": selection.policy_id,
        "history_evidence_scope": "Structure only; pilot or eligibility evidence is not a formal measurement sample",
        "inputs": [{"path": path.relative_to(ROOT).as_posix(), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
                   for path in sorted(inputs)]})
    write_json(run / "descriptor.json", descriptor.model_dump(mode="json"))
    selected = set(selection.claim_ids)
    write_json(run / "selected-claims.json", [claim.model_dump(mode="json") for claim in matched_claims
                                              if claim.claim_id in selected])
    write_json(run / "selection.json", selection.model_dump(mode="json"))
    print(selection.model_dump_json(indent=2))
    print("evidence_directory=" + run.relative_to(ROOT).as_posix())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
