"""Publication integrity and format checks use copies, never rerun or alter experiments."""

import csv
import hashlib
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from zipfile import ZipFile

import pytest

from scripts.task11_comparison import ROOT, analyse, main, write_outputs

FROZEN = ROOT / "docs/testing/experiments/task11/formal-20261012-three-repeats-v2"
TRACE = "captures/binding_changed-0/trace.json"
PUBLISHED_DIGEST = "145fc0af0ae16039bea4d199338579a7e41f11dbacb22e79b439a44d8fee168f"


def read_json(path):
    return json.loads(path.read_bytes())


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def change_json(path, keys, value):
    document = read_json(path)
    parent = document
    for key in keys[:-1]:
        parent = parent[key]
    parent[keys[-1]] = value
    write_json(path, document)


def seal_synthetic(directory):
    # This externally supplied test digest authorizes synthetic bytes, not historical execution.
    manifest = read_json(directory / "publication-manifest.json")
    manifest["files"] = {
        path.relative_to(directory).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(directory.rglob("*"))
        if path.is_file() and path.name != "publication-manifest.json"
    }
    write_json(directory / "publication-manifest.json", manifest)
    return hashlib.sha256((directory / "publication-manifest.json").read_bytes()).hexdigest()


@pytest.fixture
def retained(tmp_path):
    return Path(shutil.copytree(FROZEN, tmp_path / "retained"))


@pytest.fixture(scope="module")
def frozen_result():
    return analyse(FROZEN)


def test_frozen_36_replays_and_original_metrics_are_preserved(frozen_result):
    assert hashlib.sha256((FROZEN / "publication-manifest.json").read_bytes()).hexdigest() == PUBLISHED_DIGEST
    historical = read_json(FROZEN / "analysis/summary.json")
    assert len(frozen_result["rows"]) == 36
    for key in ("resources", "per_case_resources", "method_applicable", "common_write_intersection", "verifier"):
        assert frozen_result[key] == historical[key]
    assert frozen_result["verifier"] == {
        "compared": 36, "matches": 36, "risk_compared": 33, "risk_matches": 33,
        "risk_not_available_legacy": 3,
    }
    legacy = [row for row in frozen_result["rows"] if row["report_schema_version"] == "1.1.0"]
    assert len(legacy) == 3
    assert all(row["methods"]["proposed"] == "NOT_APPLICABLE" for row in legacy)
    assert all(row["verifier_critical_risk_matches"] is None for row in legacy)


@pytest.mark.parametrize(("keys", "value"), [
    (("measurements", "evaluate_ms"), 1.0),
    (("worker_outcome",), "PASS"),
    (("worker_reason",), "CHANGED_REASON"),
    (("worker_critical_risk",), True),
    (("input_sha256",), "0" * 64),
    (("captured_at",), "2026-10-12T00:00:00Z"),
])
def test_unmodified_publication_rejects_trace_tampering(retained, keys, value):
    change_json(retained / TRACE, keys, value)
    with pytest.raises(ValueError, match="hash differs"):
        analyse(retained)


@pytest.mark.parametrize("name", [
    "execution.json", "plan.json", "source-snapshot.zip",
    "captures/binding_changed-0/input.json", "captures/binding_changed-0/bundle.zip",
    "captures/binding_changed-0/verifier.json", "analysis/raw.json", "analysis/summary.json",
    "analysis/results.csv", "analysis/report.md", "analysis/metrics.svg",
])
def test_every_published_file_is_checked(retained, name):
    path = retained / name
    path.write_bytes(path.read_bytes() + b"tampered")
    with pytest.raises(ValueError):
        analyse(retained)


def test_self_consistent_replacement_manifest_is_not_a_trust_anchor(retained):
    change_json(retained / TRACE, ("measurements", "evaluate_ms"), 1.0)
    digest = seal_synthetic(retained)
    assert digest != PUBLISHED_DIGEST
    with pytest.raises(ValueError, match="independently trusted"):
        analyse(retained)


def test_unsealed_historical_data_cannot_be_used_for_formal_statistics(retained):
    (retained / "publication-manifest.json").unlink()
    with pytest.raises(ValueError, match="unsealed historical"):
        analyse(retained)


def test_explicit_independent_digest_allows_valid_synthetic_data(retained):
    change_json(retained / TRACE, ("measurements", "evaluate_ms"), 1.0)
    result = analyse(retained, seal_synthetic(retained))
    original = read_json(FROZEN / TRACE)["measurements"]["evaluate_ms"]
    total = read_json(FROZEN / "analysis/summary.json")["resources"]["evaluate_ms"]["total"]
    assert result["resources"]["evaluate_ms"]["total"] == pytest.approx(total - original + 1)
    assert "do not prove original execution" in result["integrity"]["authenticity"]


@pytest.mark.parametrize(("field", "value"), [
    ("evaluate_ms", -1), ("evaluate_ms", float("nan")), ("evaluate_ms", float("inf")),
    ("evaluate_ms", float("-inf")), ("evaluate_ms", True), ("evaluate_ms", "1"),
    ("evaluate_ms", None), ("evaluate_ms", 1e9), ("verify_ms", None), ("report_ms", None),
])
def test_invalid_millisecond_durations_are_rejected_even_with_trusted_bytes(retained, field, value):
    change_json(retained / TRACE, ("measurements", field), value)
    with pytest.raises(ValueError, match="millisecond duration"):
        analyse(retained, seal_synthetic(retained))


@pytest.mark.parametrize(("field", "value"), [
    ("rpc_attempts", -1), ("rpc_attempts", True), ("rpc_attempts", 1.5),
    ("rpc_attempts", "1"), ("rpc_attempts", None), ("rpc_attempts", 999),
    ("external_attempts", 999), ("persisted_attempt_count", 999),
])
def test_attempt_counters_are_integer_and_match_recorded_operations(retained, field, value):
    change_json(retained / TRACE, ("measurements", field), value)
    with pytest.raises(ValueError, match="attempt count"):
        analyse(retained, seal_synthetic(retained))


@pytest.mark.parametrize("field", [
    "captured_at", "run_id", "plan", "measurements", "worker_outcome", "worker_reason",
    "worker_critical_risk", "input_evidence_id", "ground_truth", "case_id", "repetition",
])
def test_required_trace_fields_are_not_silently_defaulted(retained, field):
    trace = read_json(retained / TRACE)
    del trace[field]
    write_json(retained / TRACE, trace)
    with pytest.raises(ValueError):
        analyse(retained, seal_synthetic(retained))


@pytest.mark.parametrize(("keys", "value"), [
    (("captured_at",), "2026-10-11T17:25:58"),
    (("captured_at",), "not-a-time"),
    (("captured_at",), "2020-01-01T00:00:00Z"),
    (("plan", "planning_time"), "2026-10-11T17:25:51"),
    (("plan", "planning_time"), "2099-01-01T00:00:00Z"),
    (("attempts", 0, "started_at"), "2026-10-11T17:25:52"),
    (("attempts", 0, "started_at"), "not-a-time"),
    (("attempts", 0, "started_at"), "2099-01-01T00:00:00Z"),
    (("observations", 0, "started_at"), "2026-10-11T17:25:52"),
    (("observations", 0, "ended_at"), "2020-01-01T00:00:00Z"),
    (("observations", 0, "slot_id"), "00000000-0000-0000-0000-000000000000"),
    (("observations", 0, "latency_ms"), -1),
    (("worker_outcome",), "PASS"),
    (("worker_reason",), "CHANGED_REASON"),
    (("worker_critical_risk",), True),
    (("worker_critical_risk",), 1),
    (("run_id",), "00000000-0000-0000-0000-000000000000"),
    (("input_evidence_id",), "not-a-uuid"),
    (("repetition",), True),
    (("repetition",), -1),
    (("task_type",), "read"),
])
def test_inconsistent_trace_semantics_are_rejected_with_an_independent_digest(retained, keys, value):
    change_json(retained / TRACE, keys, value)
    with pytest.raises(ValueError):
        analyse(retained, seal_synthetic(retained))


def test_missing_capture_is_rejected_after_resealing(retained):
    shutil.rmtree(retained / "captures/binding_changed-0")
    with pytest.raises(ValueError, match="Capture set"):
        analyse(retained, seal_synthetic(retained))


def test_duplicate_capture_is_rejected_after_resealing(retained):
    shutil.copytree(retained / "captures/binding_changed-0", retained / "captures/duplicate")
    with pytest.raises(ValueError, match="Duplicate"):
        analyse(retained, seal_synthetic(retained))


def test_duplicate_ground_truth_plan_case_is_not_silently_overwritten(retained):
    plan = read_json(retained / "plan.json")
    plan["cases"].append(plan["cases"][0])
    write_json(retained / "plan.json", plan)
    digest = hashlib.sha256((retained / "plan.json").read_bytes()).hexdigest()
    change_json(retained / "execution.json", ("plan_sha256",), digest)
    for path in (retained / "captures").glob("*/trace.json"):
        change_json(path, ("plan_sha256",), digest)
    with pytest.raises(ValueError, match="Duplicate"):
        analyse(retained, seal_synthetic(retained))


def test_sequential_stage_durations_cannot_exceed_total_capture_time(retained):
    capture = read_json(retained / TRACE)
    elapsed_ms = (datetime.fromisoformat(capture["captured_at"])
                  - datetime.fromisoformat(capture["plan"]["planning_time"])).total_seconds() * 1000
    for field in ("evaluate_ms", "verify_ms", "report_ms"):
        capture["measurements"][field] = elapsed_ms * 0.8
    write_json(retained / TRACE, capture)
    with pytest.raises(ValueError, match="duration"):
        analyse(retained, seal_synthetic(retained))


def test_statistics_never_consume_bytes_changed_after_the_publication_check(monkeypatch):
    path = FROZEN / TRACE
    changed = read_json(path)
    changed["measurements"]["evaluate_ms"] = 1.0
    altered = json.dumps(changed).encode()
    original_bytes, original_text = Path.read_bytes, Path.read_text
    reads = 0

    def replaced_bytes(candidate):
        nonlocal reads
        if candidate == path:
            reads += 1
            if reads > 1:
                return altered
        return original_bytes(candidate)

    def replaced_text(candidate, *args, **kwargs):
        if candidate == path and reads:
            return altered.decode()
        return original_text(candidate, *args, **kwargs)

    historical = read_json(FROZEN / "analysis/summary.json")
    monkeypatch.setattr(Path, "read_bytes", replaced_bytes)
    monkeypatch.setattr(Path, "read_text", replaced_text)
    try:
        result = analyse(FROZEN)
    except ValueError:
        return
    assert reads >= 1
    assert result["resources"] == historical["resources"]


@pytest.mark.parametrize(("keys", "value"), [
    (("plan", "profile"), "changed-profile"),
    (("observations", 0, "accepted"), True),
    (("report_schema_version",), "1.1.0"),
    (("input_evidence_id",), "00000000-0000-4000-8000-000000000000"),
])
def test_trace_must_agree_with_its_original_bundle_documents(retained, keys, value):
    change_json(retained / TRACE, keys, value)
    with pytest.raises(ValueError, match="Bundle|bundle"):
        analyse(retained, seal_synthetic(retained))


def test_synchronized_trace_run_ids_must_still_match_the_original_bundle(retained):
    trace = read_json(retained / TRACE)
    trace["run_id"] = trace["plan"]["run_id"] = "00000000-0000-4000-8000-000000000000"
    write_json(retained / TRACE, trace)
    with pytest.raises(ValueError, match="Bundle|bundle"):
        analyse(retained, seal_synthetic(retained))


@pytest.mark.parametrize("identity", ["run_id", "slot_id", "request_id"])
def test_duplicate_execution_identity_is_rejected_before_replay(retained, identity):
    first = read_json(retained / "captures/binding_changed-0/trace.json")
    path = retained / "captures/binding_changed-1/trace.json"
    second = read_json(path)
    source = path.parent / "input.json"
    inputs = read_json(source)
    if identity == "run_id":
        second["run_id"] = second["plan"]["run_id"] = first["run_id"]
    elif identity == "slot_id":
        inputs["slot"]["slot_id"] = first["plan"]["slots"][0]["slot_id"]
        for observation in second["observations"]:
            observation["slot_id"] = inputs["slot"]["slot_id"]
    else:
        inputs["slot"]["expected"]["request_id"] = first["plan"]["slots"][0]["expected"]["request_id"]
        inputs["slot"]["task"]["request_id"] = inputs["slot"]["expected"]["request_id"]
    second["plan"]["slots"][0] = inputs["slot"]
    write_json(source, inputs)
    second["input_sha256"] = hashlib.sha256(source.read_bytes()).hexdigest()
    write_json(path, second)
    with pytest.raises(ValueError, match="Duplicate run, slot or request|Bundle|bundle"):
        analyse(retained, seal_synthetic(retained))


def test_frozen_source_zip_must_match_the_recorded_source_manifest(retained):
    source = retained / "source-snapshot.zip"
    with ZipFile(source) as archive:
        files = [(info, archive.read(info)) for info in archive.infolist()]
    with ZipFile(source, "w") as archive:
        for index, (info, data) in enumerate(files):
            archive.writestr(info, data + b"changed" if index == 0 else data)
    with pytest.raises(ValueError, match="source snapshot hash differs"):
        analyse(retained, seal_synthetic(retained))


def test_outputs_are_consistent_and_cannot_overwrite_a_frozen_result(frozen_result, tmp_path):
    destination = tmp_path / "analysis"
    write_outputs(frozen_result, destination)
    assert read_json(destination / "raw.json") == frozen_result
    summary = read_json(destination / "summary.json")
    assert summary == {key: value for key, value in frozen_result.items() if key != "rows"}
    with (destination / "results.csv").open(newline="", encoding="utf-8") as stream:
        records = list(csv.DictReader(stream))
    assert len(records) == 36
    for recorded, row in zip(records, frozen_result["rows"], strict=True):
        assert recorded["case_id"] == row["case_id"]
        assert all(recorded[method] == outcome for method, outcome in row["methods"].items())
    assert (destination / "metrics.svg").read_bytes() == (FROZEN / "analysis/metrics.svg").read_bytes()
    assert "36/36" in (destination / "report.md").read_text(encoding="utf-8")
    before = {path.name: path.read_bytes() for path in destination.iterdir()}
    with pytest.raises(ValueError, match="never overwritten"):
        write_outputs(frozen_result, destination)
    assert before == {path.name: path.read_bytes() for path in destination.iterdir()}


def test_cli_analyses_to_a_new_directory_and_preserves_frozen_input(retained, tmp_path, monkeypatch):
    before = {path.relative_to(retained): path.read_bytes() for path in retained.rglob("*") if path.is_file()}
    destination = tmp_path / "new-analysis"
    monkeypatch.setattr(sys, "argv", ["task11_comparison.py", "analyse", "--output", str(retained),
                                      "--analysis-output", str(destination)])
    assert main() == 0
    assert read_json(destination / "summary.json")["verifier"]["compared"] == 36
    assert before == {path.relative_to(retained): path.read_bytes() for path in retained.rglob("*") if path.is_file()}


@pytest.mark.parametrize("destination", [None, "analysis", "captures/new-output"])
def test_cli_refuses_output_inside_retained_input(retained, monkeypatch, destination):
    arguments = ["task11_comparison.py", "analyse", "--output", str(retained)]
    if destination is not None:
        arguments += ["--analysis-output", str(retained / destination)]
    monkeypatch.setattr(sys, "argv", arguments)
    with pytest.raises(SystemExit) as error:
        main()
    assert error.value.code != 0


def test_capture_runner_refuses_a_plan_different_from_the_frozen_capture_hash():
    completed = subprocess.run(
        [sys.executable, "-c", "import tests.integration.test_task11_experiment"],
        cwd=ROOT, env={**os.environ, "TASK11_PLAN_SHA256": "0" * 64},
        capture_output=True, text=True, timeout=30, check=False,
    )
    assert completed.returncode != 0
    assert "Executed experiment plan differs from the frozen capture plan" in completed.stderr


def test_oversized_integer_duration_is_rejected_without_numeric_overflow(retained):
    change_json(retained / TRACE, ("measurements", "evaluate_ms"), 10**500)
    with pytest.raises(ValueError, match="millisecond duration"):
        analyse(retained, seal_synthetic(retained))
