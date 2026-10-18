"""Build an offline candidate admission snapshot from reviewed public evidence."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import secrets
import sys

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "runtime"
sys.path[:0] = [str(ROOT / "packages/core/src"), str(ROOT / "services/platform/src")]

from reputation_core import AdmissionReport, CandidateRecord, ProbeObservation, assess_candidate
from reputation_platform.admission_report import render_admission_report


def public_evidence(value: str) -> Path:
    path = (ROOT / value).resolve()
    if (not path.is_relative_to(RUNTIME) or not path.is_file()
            or not path.name.endswith((".observation.json", ".response.bin"))
            or any(part.startswith(".") or part.lower() in {"secrets", "platform-config"}
                   or ".private" in part.lower() for part in path.relative_to(RUNTIME).parts)):
        raise ValueError("Evidence must be a retained public runtime observation or response")
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("config", type=Path, nargs="?", help="Existing positional config form")
    parser.add_argument("--config", dest="config_option", type=Path)
    args = parser.parse_args()
    if args.config is not None and args.config_option is not None:
        parser.error("Supply config either positionally or with --config")
    selected_config = args.config_option or args.config
    if selected_config is None:
        parser.error("An explicit config is required")
    config_path = selected_config.resolve()
    if not config_path.is_relative_to(ROOT / "configs") or not config_path.is_file():
        parser.error("config must be an existing public JSON file in this project's configs")
    config = json.loads(config_path.read_bytes())
    records = [CandidateRecord.model_validate(item) for item in config["candidates"]]
    if len({record.key for record in records}) != len(records):
        raise ValueError("Candidate keys must be unique")

    files = {config_path}
    frozen_sources = {}
    for item in config.get("source_inputs", []):
        path = public_evidence(item["path"])
        if hashlib.sha256(path.read_bytes()).hexdigest() != item["sha256"]:
            raise ValueError("A frozen source observation or response digest differs")
        frozen_sources[path] = item["sha256"]
        files.add(path)
    observations = {}
    candidates = []
    for record in records:
        checks = []
        for check in record.checks:
            references = []
            for value in check.evidence:
                path = public_evidence(value)
                if frozen_sources and path not in frozen_sources:
                    raise ValueError("A candidate evidence reference is outside its frozen input list")
                files.add(path)
                references.append(path.relative_to(ROOT).as_posix())
                if path.name.endswith(".observation.json"):
                    observation = ProbeObservation.model_validate_json(path.read_bytes())
                    if observation.response_file:
                        response = public_evidence(
                            (path.parent / observation.response_file).relative_to(ROOT).as_posix()
                        )
                        if response.parent != path.parent:
                            raise ValueError("An observation response must remain in its evidence run")
                        if frozen_sources and response not in frozen_sources:
                            raise ValueError("An observation response is outside the frozen input list")
                        if hashlib.sha256(response.read_bytes()).hexdigest() != observation.response_sha256:
                            raise ValueError("A retained response differs from its observation digest")
                        files.add(response)
                        response_reference = response.relative_to(ROOT).as_posix()
                        references.append(response_reference)
                        observation = observation.model_copy(update={"response_file": response_reference})
                    observations[path] = observation
            checks.append(check.model_copy(update={"evidence": list(dict.fromkeys(references))}))
        reviewed = record.model_copy(update={"checks": checks})
        candidates.append(assess_candidate(reviewed))

    now = datetime.now(timezone.utc)
    report = AdmissionReport(assessed_at=now, candidates=candidates)
    observed = [observations[path] for path in sorted(observations)]
    retained_summary = config.get("retained_requests_summary")
    if retained_summary and retained_summary["distinct_observations"] != len(observed):
        raise ValueError("Retained request count differs from the distinct referenced observations")
    manifest = {
        "schema_version": "candidate-review-input-manifest-v1",
        "generated_at": now.isoformat(),
        "review_scope": config["review_scope"],
        "network_requests_performed": 0,
        "scores_computed": False,
        "observation_count": len(observed),
        "inputs": [{"path": path.relative_to(ROOT).as_posix(),
                    "sha256": hashlib.sha256(path.read_bytes()).hexdigest()} for path in sorted(files)],
    }
    if retained_summary:
        manifest["retained_requests_summary"] = retained_summary
    output = RUNTIME / f"admission-report-{now:%Y%m%dT%H%M%SZ}-{secrets.token_hex(4)}"
    output.mkdir()
    documents = {
        "admission-report.json": report.model_dump_json(indent=2),
        "admission-report.html": render_admission_report(report, observed),
        "observations.json": json.dumps([item.model_dump(mode="json") for item in observed],
                                        ensure_ascii=False, indent=2),
        "manifest.json": json.dumps(manifest, ensure_ascii=False, indent=2),
    }
    for name, content in documents.items():
        with (output / name).open("x", encoding="utf-8") as stream:
            stream.write(content)
    print(f"candidate_count={len(candidates)} ready_for_full_score="
          f"{sum(candidate.ready_for_full_score for candidate in candidates)} "
          f"retained_observations={len(observed)} network_requests_performed=0 scores_computed=false")
    print(f"report={output.relative_to(ROOT).as_posix()}")


if __name__ == "__main__":
    main()
