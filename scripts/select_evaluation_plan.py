"""Select the frozen historical-liquidity plan from retained evidence, entirely offline."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import secrets
import sys

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = (ROOT / "runtime").resolve()
sys.path[:0] = [str(ROOT / "packages/core/src"), str(ROOT / "services/platform/src")]

from analyze_declarations import sources_from_review
from reputation_core import CandidateRecord, DeclarationAnalysis, SourceDocument, validate_analysis
from reputation_core.planning import LiquidityHistoryDescriptor, select_plan

INCREASE_LABEL = re.compile(r"(?<![A-Za-z])Increase(?=BNB|\b)")
READ_ONLY = re.compile(r"read[-‐‑]only\s+JSON", re.IGNORECASE)


def get_run(value: str) -> Path:
    path = (ROOT / value).resolve()
    if path == RUNTIME or not path.is_relative_to(RUNTIME) or not path.is_dir():
        raise ValueError("Each run must be an existing subdirectory of this repository's runtime")
    return path


def local_file(directory: Path, name: str) -> Path:
    path = (directory / name).resolve()
    if not path.is_relative_to(directory) or not path.is_file():
        raise ValueError("Retained input files must stay inside their selected run directory")
    return path


def read_json(path: Path):
    return json.loads(path.read_bytes())


def write_json(path: Path, value: object) -> None:
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", type=Path, required=True, help="Explicit operator-owned profile under configs/pilots")
    for name in ("analysis-run", "admission-run", "history-run", "source-run"):
        parser.add_argument("--" + name, required=True)
    args = parser.parse_args()
    analysis_run, admission_run, history_run, source_run = (
        get_run(getattr(args, name + "_run")) for name in ("analysis", "admission", "history", "source")
    )
    config_path = (ROOT / args.profile).resolve()
    if not config_path.is_relative_to(ROOT / "configs/pilots") or config_path.suffix != ".json":
        parser.error("Operator profile must be a JSON file under configs/pilots")
    config = read_json(config_path)
    if config["policy_version"] != "liquidity-history-v1":
        raise ValueError("No adapter is implemented for this pilot policy")
    analysis_manifest = read_json(local_file(analysis_run, "manifest.json"))
    model_run = get_run(analysis_manifest["source_run"]) if "source_run" in analysis_manifest else analysis_run
    model_manifest = read_json(local_file(model_run, "manifest.json"))
    if get_run(model_manifest["material_directory"]) != source_run:
        raise ValueError("The analysis and supplied source-review run do not refer to the same material")
    materials = sources_from_review(source_run, None)
    relevant = [(key, sources) for key, sources in materials if any(
        config["history_source_url"] in source.text and INCREASE_LABEL.search(source.text)
        for source in sources
    )]
    if len(relevant) != 1:
        print(json.dumps({"status": "NEEDS_INFO", "network_requests": 0, "reasons": [
            "A unique source package must contain both the Increase business label and the frozen record endpoint"
        ]}))
        return 1
    key, expected_sources = relevant[0]
    source_file = local_file(model_run, key + ".sources.json")
    sources = [SourceDocument.model_validate(item) for item in read_json(source_file)]
    if sources != expected_sources:
        raise ValueError("Complete model SourceDocuments differ from the digest-verified review material")
    analysis_file = local_file(analysis_run, key + ".analysis.json")
    analysis = validate_analysis(DeclarationAnalysis.model_validate(read_json(analysis_file)), sources)
    increase_claims, record_claims = [], []
    for claim in analysis.claims:
        quoted = "\n".join(citation.quote for citation in claim.citations)
        if claim.operation.strip().casefold() == "increase" and INCREASE_LABEL.search(quoted):
            increase_claims.append(claim)
        if config["history_source_url"] in quoted and READ_ONLY.search(quoted):
            record_claims.append(claim)
    gaps = []
    if not increase_claims:
        gaps.append("No source-cited Increase operation label was found")
    if not record_claims:
        gaps.append("No claim cites the configured record endpoint as read-only JSON")
    selected_ids = {claim.claim_id for claim in increase_claims + record_claims} if not gaps else set()
    matched = [claim for claim in analysis.claims if claim.claim_id in selected_ids]
    admission_file = local_file(admission_run, "admission-report.json")
    report = read_json(admission_file)
    if report.get("schema_version") != "candidate-admission-v1":
        raise ValueError("Unsupported background admission report schema")
    candidates = [item for item in report["candidates"] if item["key"] == key]
    if len(candidates) != 1:
        raise ValueError("The background report must contain exactly one corresponding candidate")
    candidate_data = dict(candidates[0])
    candidate_data.pop("ready_for_full_score", None)
    candidate = CandidateRecord.model_validate(candidate_data)
    history_file = local_file(history_run, "brain-agent.response.bin")
    observation_file = local_file(history_run, "brain-agent.observation.json")
    history_hash = hashlib.sha256(history_file.read_bytes()).hexdigest()
    observation = read_json(observation_file)
    if history_hash != config["history_response_sha256"] or history_hash != observation["response_sha256"]:
        raise ValueError("History response does not match both the frozen configuration and its observation")
    if observation["url"] != config["history_source_url"]:
        raise ValueError("History observation does not identify the frozen record endpoint")
    history = read_json(history_file)
    shape_ok = (isinstance(history, dict) and isinstance(history.get("history"), list)
                and isinstance(history.get("last"), dict))
    rows = history["history"] if shape_ok else []
    indices = config["functional_indices"] + config["behavioral_indices"]
    if len(indices) != len(set(indices)):
        raise ValueError("Frozen functional and behavioral tasks overlap")
    for index in indices:
        if (type(index) is not int or not 0 <= index < len(rows) or not isinstance(rows[index], dict)
            or not isinstance(rows[index].get("steps"), dict)
            or not isinstance(rows[index]["steps"].get("increase"), dict)):
            shape_ok = False
    if not shape_ok:
        gaps.append("Frozen task locations do not expose the supported history/increase structure")
    if observation["http_status"] != 200 or not observation["body_complete"] or observation["error_kind"]:
        shape_ok = False
        gaps.append("The retained history observation is incomplete or was not a successful public read")
    descriptor = LiquidityHistoryDescriptor(
        candidate_key=candidate.key, claim_ids=[claim.claim_id for claim in matched],
        chain_id=config["chain_id"], protocol="pancakeswap-v3-npm",
        history_shape="run-history-increase-v1" if shape_ok else None,
        history_source_file=history_file.relative_to(ROOT).as_posix(), history_json_path="$.history",
        published_execution_wallet=config["execution_wallet"], trusted_manager=config["position_manager"],
    )
    selection = select_plan(analysis, candidate, descriptor)
    selection.reasons.extend(gaps)
    now = datetime.now(timezone.utc)
    run = RUNTIME / f"plan-selection-{now:%Y%m%dT%H%M%SZ}-{secrets.token_hex(4)}"
    run.mkdir()
    inputs = [config_path, analysis_file, source_file, admission_file, history_file, observation_file,
              local_file(source_run, "review.json"), local_file(model_run, "manifest.json")]
    write_json(run / "manifest.json", {"created_at": now.isoformat(), "network_requests": 0,
        "scores_computed": False, "source_documents": [{"source_id": source.source_id,
        "raw_sha256": source.raw_sha256, "projection_sha256": source.projection_sha256} for source in sources],
        "inputs": [{"path": path.relative_to(ROOT).as_posix(), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
                   for path in inputs]})
    write_json(run / "descriptor.json", descriptor.model_dump(mode="json"))
    write_json(run / "selected-claims.json", [claim.model_dump(mode="json") for claim in matched])
    write_json(run / "selection.json", selection.model_dump(mode="json"))
    print(selection.model_dump_json(indent=2))
    print("evidence_directory=" + str(run))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
