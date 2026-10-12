"""Capture real controlled experiments or analyse retained Task 11 evidence offline."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import platform
import statistics
import subprocess
import sys
from collections import Counter
from datetime import datetime
from io import BytesIO
from pathlib import Path, PurePosixPath
from typing import Any
from uuid import UUID
from zipfile import BadZipFile, ZipFile

from reputation_core.models import RecordVerificationInput
from reputation_core.record_verifier import verify_record
from reputation_verifier.bundle import verify_bundle

ROOT = Path(__file__).resolve().parents[1]
METHODS = ("online", "receipt", "proposed")
OUTCOMES = ("PASS", "FAIL", "UNKNOWN", "NOT_APPLICABLE")
# Trust comes from the reviewed publication, never from hashes supplied by the input directory.
PUBLISHED_MANIFEST_SHA256 = "145fc0af0ae16039bea4d199338579a7e41f11dbacb22e79b439a44d8fee168f"


def publication_files(output: Path, trusted_sha256: str) -> dict[str, bytes]:
    path = output / "publication-manifest.json"
    if not path.is_file():
        raise ValueError("No trusted publication manifest; unsealed historical data cannot produce formal statistics")
    manifest_bytes = path.read_bytes()
    if hashlib.sha256(manifest_bytes).hexdigest() != trusted_sha256:
        raise ValueError("Publication manifest differs from the independently trusted SHA256")
    manifest = json.loads(manifest_bytes)
    if manifest.get("schema_version") != "task11-publication-v1":
        raise ValueError("Unsupported publication manifest format")
    files = manifest["files"]
    retained = {}
    for name, digest in files.items():
        relative = PurePosixPath(name)
        file = output / name
        if (relative.is_absolute() or ".." in relative.parts or "\\" in name
                or ":" in name or relative.as_posix() != name
                or not file.resolve().is_relative_to(output.resolve())):
            raise ValueError(f"Unsafe publication path: {name}")
        if not file.is_file():
            raise ValueError(f"Published file hash differs or file is missing: {name}")
        content = file.read_bytes()
        if hashlib.sha256(content).hexdigest() != digest:
            raise ValueError(f"Published file hash differs or file is missing: {name}")
        retained[name] = content
    required = {"execution.json", "plan.json", "source-snapshot.zip"}
    captures = {str(file.relative_to(output)).replace("\\", "/")
                for file in (output / "captures").rglob("*") if file.is_file()}
    if not required <= files.keys() or captures != {name for name in files if name.startswith("captures/")}:
        raise ValueError("Publication manifest does not cover the complete capture set")
    return retained


def timestamp(value: Any, field: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"Invalid timestamp: {field}") from error
    if parsed.utcoffset() is None:
        raise ValueError(f"Timestamp requires a timezone: {field}")
    return parsed


def validate_trace(capture: dict[str, Any], inputs: RecordVerificationInput) -> None:
    if capture["schema_version"] != "task11-capture-v1":
        raise ValueError("Unsupported capture format")
    if type(capture["repetition"]) is not int or capture["repetition"] < 0:
        raise ValueError("Invalid repetition")
    plan = capture["plan"]
    if (capture["run_id"] != plan["run_id"] or len(plan["slots"]) != 1
            or plan["slots"][0] != inputs.slot.model_dump(mode="json")):
        raise ValueError("Capture run or task differs from the frozen input")
    UUID(capture["run_id"])
    captured = timestamp(capture["captured_at"], "captured_at")
    planned = timestamp(plan["planning_time"], "planning_time")
    window = timestamp(inputs.slot.expected.window_start, "window_start")
    deadline = timestamp(inputs.slot.expected.deadline, "deadline")
    if not planned <= window < deadline or captured < planned:
        raise ValueError("Inconsistent capture/planning/task timestamps")
    measurements = capture["measurements"]
    # Stage durations are monotonic milliseconds; wall time is only a loose upper bound.
    duration_limit = (captured - planned).total_seconds() * 1000 + 1000
    for field in ("evaluate_ms", "verify_ms", "report_ms"):
        value = measurements.get(field)
        if type(value) not in (int, float) or not 0 <= value <= duration_limit or not math.isfinite(value):
            raise ValueError(f"Invalid finite millisecond duration or inconsistent capture time: {field}")
    if sum(measurements[field] for field in ("evaluate_ms", "verify_ms", "report_ms")) > duration_limit:
        raise ValueError("Stage durations exceed the recorded capture time")
    for field, records in (("rpc_attempts", "rpc_trace"), ("external_attempts", "http_trace"),
                           ("persisted_attempt_count", "attempts")):
        value = measurements.get(field)
        if type(value) is not int or value < 0 or value != len(capture[records]):
            raise ValueError(f"Invalid or inconsistent attempt count: {field}")
    for record in capture["observations"]:
        started = timestamp(record["started_at"], "observation.started_at")
        ended = timestamp(record["ended_at"], "observation.ended_at")
        if not planned <= started <= ended <= captured or record["slot_id"] != str(inputs.slot.slot_id):
            raise ValueError("Inconsistent observation timestamps or task identity")
        if record["latency_ms"] is not None and (type(record["latency_ms"]) is not int or record["latency_ms"] < 0):
            raise ValueError("Invalid observation latency_ms")
    for attempt in capture["attempts"]:
        if not planned <= timestamp(attempt["started_at"], "attempt.started_at") <= captured:
            raise ValueError("Inconsistent attempt timestamp")
    if capture["worker_outcome"] not in OUTCOMES or type(capture["worker_critical_risk"]) is not bool:
        raise ValueError("Invalid Worker outcome or critical risk")


def baseline_online(inputs: dict[str, Any]) -> str:
    status = (inputs.get("initial_agent_http") or {}).get("http_status")
    if type(status) is not int or not 100 <= status <= 599:
        return "UNKNOWN"
    return "FAIL" if status >= 500 else "PASS"


def baseline_receipt(inputs: dict[str, Any]) -> str:
    if inputs["slot"]["capability_id"] != "anchor_record":
        return "NOT_APPLICABLE"
    status = (inputs["evm"]["results"].get("receipt") or {}).get("status")
    if status in ("0x1", 1) and type(status) is not bool:
        return "PASS"
    if status in ("0x0", 0) and type(status) is not bool:
        return "FAIL"
    return "UNKNOWN"


def metrics(rows: list[dict[str, Any]], method: str) -> dict[str, Any]:
    distribution = {outcome: sum(row["methods"][method] == outcome for row in rows)
                    for outcome in OUTCOMES}
    applicable = [row for row in rows if row["ground_truth"]["outcome"] != "NOT_APPLICABLE"
                  and (method != "receipt" or row["task_type"] == "write")]
    known = [row for row in applicable if row["ground_truth"]["outcome"] in {"PASS", "FAIL"}]
    tp = sum(row["ground_truth"]["outcome"] == "FAIL" and row["methods"][method] == "FAIL" for row in known)
    fp = sum(row["ground_truth"]["outcome"] == "PASS" and row["methods"][method] == "FAIL" for row in known)
    fn = sum(row["ground_truth"]["outcome"] == "FAIL" and row["methods"][method] == "PASS" for row in known)
    tn = sum(row["ground_truth"]["outcome"] == "PASS" and row["methods"][method] == "PASS" for row in known)
    errors = sum(row["ground_truth"]["outcome"] == "FAIL" for row in known)
    healthy = sum(row["ground_truth"]["outcome"] == "PASS" for row in known)
    abstentions = sum(row["methods"][method] == "UNKNOWN" for row in known)
    unexpected_na = sum(row["methods"][method] == "NOT_APPLICABLE" for row in known)
    risk_cases = [row for row in applicable if row["ground_truth"]["critical_risk"]]
    risks = sum(row["critical_risk"] for row in risk_cases) if method == "proposed" else 0
    precision = tp / (tp + fp) if tp + fp else 0.0 if known else None
    recall = tp / errors if errors else None
    f1 = (None if precision is None or recall is None else
          2 * precision * recall / (precision + recall) if precision + recall else 0.0)
    return {
        "distribution": distribution, "method_applicable": len(applicable),
        "known_ground_truth": len(known), "ground_truth_errors": errors,
        "ground_truth_healthy": healthy, "tp": tp, "fp": fp, "fn": fn, "tn": tn,
        "abstentions_on_known_ground_truth": abstentions,
        "unexpected_na_on_known_ground_truth": unexpected_na,
        "missed_known_errors": errors - tp,
        "coverage": (tp + fp + fn + tn) / len(known) if known else None,
        "all_applicable_coverage": sum(row["methods"][method] in {"PASS", "FAIL"} for row in applicable) / len(applicable) if applicable else None,
        "known_error_detection_rate": tp / errors if errors else None,
        "false_positive_rate": fp / healthy if healthy else None,
        "false_negative_rate": fn / errors if errors else None,
        "precision": precision, "recall": recall, "f1": f1,
        "conditional_recall": tp / (tp + fn) if tp + fn else None,
        "critical_risks_expected": len(risk_cases), "critical_risks_detected": risks,
        "critical_risk_detection_rate": risks / len(risk_cases) if risk_cases else None,
        "denominators": "Applicability is predeclared: receipt only writes; other methods all planned applicable tasks. Binary metrics use known PASS/FAIL truth only. Unexpected predicted N/A remains in the known denominator. FN requires predicted PASS; UNKNOWN is an abstention. Precision=TP/(TP+FP), defined as zero with known samples but no FAIL predictions. Recall=TP/all known errors; conditional recall=TP/(TP+FN); F1 is the harmonic mean of precision and main recall (zero if both zero). FPR=FP/healthy truth; FNR=FN/error truth; missed known errors include abstentions.",
    }


def analyse(output: Path, trusted_manifest_sha256: str | None = None) -> dict[str, Any]:
    try:
        return _analyse(output, trusted_manifest_sha256 or PUBLISHED_MANIFEST_SHA256)
    except (KeyError, TypeError, OSError, json.JSONDecodeError, BadZipFile) as error:
        raise ValueError(f"Invalid or incomplete experiment data: {error}") from error


def _analyse(output: Path, trusted_manifest_sha256: str) -> dict[str, Any]:
    metadata_bytes = (output / "execution.json").read_bytes()
    metadata = json.loads(metadata_bytes)
    if type(metadata["exit_code"]) is not int or metadata["exit_code"] != 0:
        raise ValueError("Capture did not pass; retain the incomplete evidence for diagnosis")
    manifest_bytes = json.dumps(metadata["source_manifest"], sort_keys=True).encode()
    if hashlib.sha256(manifest_bytes).hexdigest() != metadata["source_manifest_sha256"]:
        raise ValueError("Retained source manifest hash differs")
    files = publication_files(output, trusted_manifest_sha256)
    if files["execution.json"] != metadata_bytes:
        raise ValueError("Execution metadata changed during validation")
    if metadata.get("source_changed_during_capture") != []:
        raise ValueError("Capture source was changed or its stability was not recorded")
    with ZipFile(BytesIO(files["source-snapshot.zip"])) as archive:
        if len(archive.namelist()) != len(metadata["source_manifest"]) or set(archive.namelist()) != set(metadata["source_manifest"]):
            raise ValueError("Frozen source snapshot differs from the source manifest")
        for name, digest in metadata["source_manifest"].items():
            if hashlib.sha256(archive.read(name)).hexdigest() != digest:
                raise ValueError(f"Frozen source snapshot hash differs: {name}")
    plan_bytes = files["plan.json"]
    if hashlib.sha256(plan_bytes).hexdigest() != metadata["plan_sha256"]:
        raise ValueError("Retained experiment plan hash differs")
    cases = json.loads(plan_bytes)["cases"]
    plan = {case["case_id"]: case for case in cases}
    if len(plan) != len(cases):
        raise ValueError("Duplicate cases in the frozen plan")
    if metadata["case_ids"] != list(plan) or type(metadata["repetitions"]) is not int or not 1 <= metadata["repetitions"] <= 5:
        raise ValueError("Capture metadata differs from the frozen plan")
    traces = sorted(output / name for name in files if name.startswith("captures/") and name.endswith("/trace.json"))
    if not traces:
        raise ValueError("No actual experiment captures found")
    rows = []
    expected = {(case, repeat) for case in metadata["case_ids"] for repeat in range(metadata["repetitions"])}
    observed = set()
    runs = set()
    slots = set()
    requests = set()
    for path in traces:
        capture = json.loads(files[path.relative_to(output).as_posix()])
        identity = (capture["case_id"], capture["repetition"])
        if identity in observed or capture["plan_sha256"] != metadata["plan_sha256"]:
            raise ValueError("Duplicate case or changed experiment plan")
        if capture["case_id"] not in plan or capture["ground_truth"] != plan[capture["case_id"]]["ground_truth"]:
            raise ValueError("Captured Ground Truth differs from the frozen independent plan")
        observed.add(identity)
        if capture["source_manifest_sha256"] != metadata["source_manifest_sha256"]:
            raise ValueError("Capture code differs from the recorded source manifest")
        source = path.parent / "input.json"
        bundle = path.parent / "bundle.zip"
        if path.parent.name != f"{capture['case_id']}-{capture['repetition']}" or any(
            f"captures/{path.parent.name}/{name}" not in files
            for name in ("trace.json", "input.json", "bundle.zip", "verifier.json")
        ):
            raise ValueError("Capture directory or manifest members differ from task identity")
        for file, expected_sha256 in ((source, capture["input_sha256"]), (bundle, capture["bundle_sha256"])):
            if hashlib.sha256(files[file.relative_to(output).as_posix()]).hexdigest() != expected_sha256:
                raise ValueError(f"Captured evidence hash differs: {file.name}")
        inputs = RecordVerificationInput.model_validate_json(files[source.relative_to(output).as_posix()])
        validate_trace(capture, inputs)
        request_id = inputs.slot.expected.request_id
        if capture["run_id"] in runs or inputs.slot.slot_id in slots or request_id in requests:
            raise ValueError("Duplicate run, slot or request identity")
        runs.add(capture["run_id"])
        slots.add(inputs.slot.slot_id)
        requests.add(request_id)
        replay = verify_record(inputs, (UUID(capture["input_evidence_id"]),))
        bundle_bytes = files[bundle.relative_to(output).as_posix()]
        independent = verify_bundle(BytesIO(bundle_bytes))
        with ZipFile(BytesIO(bundle_bytes)) as archive:
            bundle_plan = json.loads(archive.read("run_plan.json"))
            bundle_observations = json.loads(archive.read("observations.json"))
            bundle_core = json.loads(archive.read("report_core.json"))
            evidence = json.loads(archive.read("evidence_manifest.json"))["evidence"]
            input_records = [record for record in evidence if record["evidence_id"] == capture["input_evidence_id"]
                             and record["source"] == "record-verification-input"]
            if len(input_records) != 1 or archive.read(input_records[0]["path"]) != files[source.relative_to(output).as_posix()]:
                raise ValueError("Captured input differs from the Bundle evidence")
        observations_by_id = {record["observation_id"]: record for record in capture["observations"]}
        if (capture["plan"] != bundle_plan or capture["report_schema_version"] != bundle_core["schema_version"]
                or len(observations_by_id) != len(capture["observations"])
                or observations_by_id != {record["observation_id"]: record for record in bundle_observations}):
            raise ValueError("Captured plan, report version or observations differ from the Bundle")
        legacy_na = (capture["report_schema_version"] == "1.1.0"
                     and inputs.rule_version == "2" and str(replay.outcome) == "NOT_APPLICABLE")
        expected_assessment = "NOT_AVAILABLE_LEGACY_REPORT" if legacy_na else "MATCH"
        if independent["offline"] != "PASS" or independent["assessment_comparison"] != expected_assessment:
            raise ValueError(f"Independent verifier rejected {capture['case_id']}")
        task = independent["task_results"][0]
        if (str(replay.outcome) != task["outcome"] or replay.reason_code != task["reason_code"]
                or task["slot_id"] != str(inputs.slot.slot_id)):
            raise ValueError(f"Core replay and Bundle disagree for {capture['case_id']}")
        if (task["outcome"], task["reason_code"]) != (capture["worker_outcome"], capture["worker_reason"]):
            raise ValueError("Worker outcome or reason differs from independent replay")
        if not legacy_na and bool(independent["risk_assessment"]["critical_findings"]) != capture["worker_critical_risk"]:
            raise ValueError("Worker critical risk differs from independent replay")
        wire = inputs.model_dump(mode="json")
        task_type = "write" if inputs.slot.capability_id == "anchor_record" else "read"
        if capture["task_type"] != task_type:
            raise ValueError("Captured task applicability differs from the frozen task")
        rows.append({
            **capture, "methods": {"online": baseline_online(wire), "receipt": baseline_receipt(wire), "proposed": str(replay.outcome)},
            "proposed_reason": replay.reason_code, "critical_risk": replay.critical_conflict,
            "verifier_matches": (task["outcome"], task["reason_code"]) == (capture["worker_outcome"], capture["worker_reason"]),
            "verifier_critical_risk_matches": (None if legacy_na else bool(independent["risk_assessment"]["critical_findings"]) == capture["worker_critical_risk"]),
        })
    if observed != expected:
        raise ValueError("Capture set does not match all planned cases and repetitions")
    common = [row for row in rows if row["task_type"] == "write"]
    resources = {}
    for key in ("evaluate_ms", "verify_ms", "report_ms", "rpc_attempts", "external_attempts"):
        values = [row["measurements"][key] for row in rows]
        resources[key] = {"count": len(values), "total": sum(values), "mean": statistics.fmean(values), "median": statistics.median(values), "min": min(values), "max": max(values), "stdev": statistics.stdev(values) if len(values) > 1 else None}
    per_case_resources: dict[str, Any] = {}
    for case_id in metadata["case_ids"]:
        case_rows = [row for row in rows if row["case_id"] == case_id]
        per_case_resources[case_id] = {}
        for key in resources:
            values = [row["measurements"][key] for row in case_rows]
            per_case_resources[case_id][key] = {"repetitions": len(values), "mean": statistics.fmean(values), "min": min(values), "max": max(values), "stdev": statistics.stdev(values) if len(values) > 1 else None}
    return {
        "schema_version": "task11-real-result-v1", "rows": rows,
        "execution": metadata,
        "integrity": {"format": "VALID", "content": "MATCH_TRUSTED_PUBLICATION",
                      "publication_manifest_sha256": trusted_manifest_sha256,
                      "authenticity": "The trusted publication preserves recorded bytes and frozen source; hashes do not prove original execution or honest timing."},
        "method_applicable": {method: metrics(rows, method) for method in METHODS},
        "common_write_intersection": {method: metrics(common, method) for method in METHODS},
        "verifier": {"compared": len(rows), "matches": sum(row["verifier_matches"] for row in rows),
                     "risk_compared": sum(row["verifier_critical_risk_matches"] is not None for row in rows),
                     "risk_matches": sum(row["verifier_critical_risk_matches"] is True for row in rows),
                     "risk_not_available_legacy": sum(row["verifier_critical_risk_matches"] is None for row in rows)},
        "resources": resources, "per_case_resources": per_case_resources,
        "limitations": ["Controlled local PostgreSQL/Anvil cases do not estimate real-world prevalence or significance.", "The matrix has no distinct wrong-business-read fixture; read coverage demonstrates normal read PASS and receipt N/A, while write mismatch cases cover business inconsistency. Read-task detection should not be generalised until that fixture is added.", "Undeclared capability uses the existing capabilities-v1/rule-2 path; its legacy 1.1 report supports task replay but has no independent risk assessment. Risk consistency excludes these N/A reports explicitly.", "The intermittent fixture is configured failure_every=1 to select a deterministic service-failure slot; repeats do not estimate an intermittent failure probability.", "All methods reuse the same captured trace; resource timings describe the shared platform pipeline, not separate baseline benchmark runs.", "RPC attempts are instrumented in the platform process; controlled Agent subprocess RPC is outside that count.", "UNKNOWN is evidence abstention; read tasks are outside the receipt method and common-write denominator."],
    }


def display(value: Any) -> str:
    return "N/A" if value is None else f"{value:.3f}"


def write_outputs(result: dict[str, Any], output: Path) -> None:
    destination = output
    if destination.exists() and any(destination.iterdir()):
        raise ValueError("Analysis destination must be new or empty; frozen results are never overwritten")
    destination.mkdir(parents=True, exist_ok=True)
    (destination / "raw.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    summary = {key: value for key, value in result.items() if key != "rows"}
    (destination / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    with (destination / "results.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(("case_id", "repetition", "task_type", "ground_truth", "ground_truth_reason", *METHODS, "proposed_reason", "critical_risk", "verifier_matches"))
        for row in result["rows"]:
            writer.writerow((row["case_id"], row["repetition"], row["task_type"], row["ground_truth"]["outcome"], row["ground_truth"]["reason"], *(row["methods"][method] for method in METHODS), row["proposed_reason"], row["critical_risk"], row["verifier_matches"]))
    lines = ["# Task 11 actual controlled experiment", "", "Generated from retained input/Bundle bytes by `scripts/task11_comparison.py analyse`.", "",
             f"Integrity: {result['integrity']['content']}; publication SHA256 `{result['integrity']['publication_manifest_sha256']}`. {result['integrity']['authenticity']}", "",
             "Applicability is fixed before prediction: receipt only applies to write tasks. Ground Truth UNKNOWN is excluded from binary metrics. Prediction UNKNOWN is an abstention; FN requires prediction PASS. Unexpected predicted N/A stays in the known Ground Truth denominator.",
             "Precision=TP/(TP+FP) (zero with known samples and no FAIL predictions), main recall=TP/all known errors including abstentions, F1=harmonic mean of precision and main recall (zero if both zero), FPR=FP/healthy Ground Truth, FNR=predicted-PASS FN/error Ground Truth. Conditional recall=TP/(TP+FN) is separately retained in JSON. Missed known errors include abstentions; known coverage=all binary predictions/known Ground Truth.", "",
             "## Recorded environment", "", "```json", json.dumps(result["execution"].get("environment", {}), indent=2), "```", ""]
    lines.extend(("## Observed cases", "", "Counts below are real repeated tasks; they are not independent samples of production prevalence.", "", "| Scenario | Independent GT | Online | Receipt | Proposed | Proposed reason | Critical risk |", "|---|---|---|---|---|---|---|"))
    for case_id in result["execution"]["case_ids"]:
        case_rows = [row for row in result["rows"] if row["case_id"] == case_id]
        verdicts = [", ".join(f"{outcome} × {count}" for outcome, count in Counter(row["methods"][method] for row in case_rows).items()) for method in METHODS]
        reasons = ", ".join(sorted({row["proposed_reason"] or "—" for row in case_rows}))
        lines.append(f"| {case_id} | {case_rows[0]['ground_truth']['outcome']} | {verdicts[0]} | {verdicts[1]} | {verdicts[2]} | {reasons} | {sum(row['critical_risk'] for row in case_rows)}/{len(case_rows)} |")
    lines.append("")
    for scope in ("method_applicable", "common_write_intersection"):
        lines.extend((f"## {scope}", "", "| Method | PASS/FAIL/UNKNOWN/N/A | Known GT | TP/FP/FN | Abstention | Known coverage | Error detection | FPR/FNR | Precision/Recall/F1 | Key risks |", "|---|---|---:|---|---:|---:|---:|---|---|---|"))
        for method in METHODS:
            item = result[scope][method]
            distribution = "/".join(str(item["distribution"][outcome]) for outcome in OUTCOMES)
            lines.append(f"| {method} | {distribution} | {item['known_ground_truth']} | {item['tp']}/{item['fp']}/{item['fn']} | {item['abstentions_on_known_ground_truth']} | {display(item['coverage'])} | {display(item['known_error_detection_rate'])} | {display(item['false_positive_rate'])}/{display(item['false_negative_rate'])} | {display(item['precision'])}/{display(item['recall'])}/{display(item['f1'])} | {item['critical_risks_detected']}/{item['critical_risks_expected']} |")
        lines.append("")
    lines.extend(("## Verifier and measured costs", "", f"Independent Bundle consistency (outcome and reason): {result['verifier']['matches']}/{result['verifier']['compared']}; critical-risk consistency: {result['verifier']['risk_matches']}/{result['verifier']['risk_compared']}, with {result['verifier']['risk_not_available_legacy']} legacy N/A reports lacking risk assessment. Cost figures measure the shared platform pipeline on the same traces; they are not independent baseline runs.", "", "| Scenario | Repeats | Execution ms mean ± SD | Chain verify ms mean ± SD | Report ms mean ± SD | RPC provider attempts mean | Agent HTTP attempts mean |", "|---|---:|---|---|---|---:|---:|"))
    for case, resources in result["per_case_resources"].items():
        timing = [f"{display(resources[key]['mean'])} ± {display(resources[key]['stdev'])}" for key in ("evaluate_ms", "verify_ms", "report_ms")]
        lines.append(f"| {case} | {resources['evaluate_ms']['repetitions']} | {timing[0]} | {timing[1]} | {timing[2]} | {display(resources['rpc_attempts']['mean'])} | {display(resources['external_attempts']['mean'])} |")
    lines.extend(("## Limits", "", *(f"- {item}" for item in result["limitations"]), ""))
    (destination / "report.md").write_text("\n".join(lines), encoding="utf-8")
    chart = ['<svg xmlns="http://www.w3.org/2000/svg" width="680" height="250"><rect width="100%" height="100%" fill="white"/><text x="20" y="20">Known error detection on common write tasks</text>']
    for index, method in enumerate(METHODS):
        rate = result["common_write_intersection"][method]["known_error_detection_rate"]
        bar = 0 if rate is None else rate * 150
        chart.append(f'<rect x="{80 + index * 190}" y="{190 - bar}" width="90" height="{bar}" fill="#2563eb"/><text x="{80 + index * 190}" y="{180 - bar}">{display(rate)}</text><text x="{80 + index * 190}" y="215">{method}</text>')
    chart.append('<text x="20" y="240">Generated from captured evidence by scripts/task11_comparison.py</text></svg>')
    (destination / "metrics.svg").write_text("".join(chart) + "\n", encoding="utf-8", newline="\r\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("capture", "analyse"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--analysis-output", type=Path, help="New directory for recomputed results, outside retained input")
    parser.add_argument("--trusted-manifest-sha256", help="Expected publication digest obtained independently; defaults to the reviewed formal v2 publication")
    parser.add_argument("--repetitions", type=int, default=3)
    args = parser.parse_args()
    output = args.output.resolve()
    destination = args.analysis_output.resolve() if args.analysis_output else output / "analysis"
    if args.mode == "analyse" and destination.is_relative_to(output):
        parser.error("analyse requires --analysis-output outside the retained input directory")
    if destination.exists() and any(destination.iterdir()):
        parser.error("analysis output must be new or empty")
    trusted_sha256 = args.trusted_manifest_sha256
    if args.mode == "capture":
        if not 1 <= args.repetitions <= 5:
            parser.error("repetitions must be in [1, 5]")
        if output.exists() and any(output.iterdir()):
            parser.error("capture output must be new or empty; retained evidence is not overwritten")
        output.mkdir(parents=True, exist_ok=True)
        plan_path = ROOT / "fixtures/experiments/task11_cases.json"
        plan_bytes = plan_path.read_bytes()
        plan = json.loads(plan_bytes)
        (output / "plan.json").write_bytes(plan_bytes)
        manifest = {str(path.relative_to(ROOT)).replace("\\", "/"): hashlib.sha256(path.read_bytes()).hexdigest()
                    for directory in ("packages/core/src", "packages/verifier/src", "services/platform/src", "fixtures/agents/src")
                    for path in sorted((ROOT / directory).rglob("*.py"))}
        for name in ("scripts/task11_comparison.py", "fixtures/experiments/task11_cases.json", "tests/integration/test_task11_experiment.py", "tests/integration/task11_hash_agent.py", "tests/integration/test_controlled_scenarios.py", "tests/integration/test_execution.py", "tests/integration/test_identity.py", "tests/integration/test_formal_evaluation.py", "tests/integration/test_fixture_agents.py", "tests/integration/conftest.py", "configs/policies/policy-v1.json", "configs/toolchain.json", "uv.lock"):
            manifest[name] = hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
        manifest_bytes = json.dumps(manifest, sort_keys=True).encode()
        metadata = {"case_ids": [case["case_id"] for case in plan["cases"]], "repetitions": args.repetitions,
                    "plan_sha256": hashlib.sha256(plan_bytes).hexdigest(),
                    "source_manifest": manifest, "source_manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
                    "git_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
                    "git_dirty": bool(subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True)),
                    "environment": {"os": platform.platform(), "architecture": platform.machine(),
                                    "processor": platform.processor(), "logical_cpu_count": os.cpu_count(),
                                    "python": platform.python_version(),
                                    "anvil": subprocess.check_output(["anvil", "--version"], text=True).strip(),
                                    "postgres_binary": subprocess.check_output(["postgres", "--version"], text=True).strip()},
                    "exit_code": None}
        metadata_path = output / "execution.json"
        metadata_path.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
        with ZipFile(output / "source-snapshot.zip", "w") as archive:
            for name in manifest:
                archive.writestr(name, (ROOT / name).read_bytes())
        result = subprocess.run([sys.executable, "-m", "pytest", "tests/integration/test_task11_experiment.py", "-q"], cwd=ROOT, env={**os.environ, "TASK11_OUTPUT": str(output), "TASK11_REPETITIONS": str(args.repetitions), "TASK11_PLAN_SHA256": metadata["plan_sha256"], "TASK11_SOURCE_SHA256": metadata["source_manifest_sha256"]}, check=False)
        source_changed = [name for name, digest in manifest.items()
                          if hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != digest]
        metadata["source_changed_during_capture"] = source_changed
        metadata["exit_code"] = result.returncode or int(bool(source_changed))
        metadata_path.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
        if metadata["exit_code"]:
            return int(metadata["exit_code"])
        publication = {"schema_version": "task11-publication-v1", "files": {
            str(path.relative_to(output)).replace("\\", "/"): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(output.rglob("*")) if path.is_file()}}
        publication_bytes = (json.dumps(publication, indent=2) + "\n").encode()
        (output / "publication-manifest.json").write_bytes(publication_bytes)
        trusted_sha256 = hashlib.sha256(publication_bytes).hexdigest()
        print(f"Retain this capture publication SHA256 independently: {trusted_sha256}", flush=True)
    try:
        write_outputs(analyse(output, trusted_sha256), destination)
    except ValueError as error:
        parser.exit(1, f"Experiment rejected: {error}\n")
    print(f"Verified Task 11 evidence: {output}; analysis: {destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
