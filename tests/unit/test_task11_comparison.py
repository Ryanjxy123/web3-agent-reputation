"""Metric boundary tests; these synthetic rows are not experiment observations."""
from typing import Any

import pytest

from scripts.task11_comparison import analyse, baseline_online, baseline_receipt, metrics


def row(truth, online, receipt, proposed):
    return {"ground_truth": {"outcome": truth, "critical_risk": False},
            "methods": {"online": online, "receipt": receipt, "proposed": proposed},
            "task_type": "read" if receipt == "NOT_APPLICABLE" else "write",
            "critical_risk": False}


def test_receipt_read_tasks_are_outside_method_scope_and_unknown_is_abstention():
    rows = [row("FAIL", "PASS", "NOT_APPLICABLE", "FAIL"),
            row("FAIL", "UNKNOWN", "UNKNOWN", "UNKNOWN"),
            row("FAIL", "PASS", "PASS", "FAIL")]
    receipt = metrics(rows, "receipt")
    assert receipt["method_applicable"] == 2 and receipt["ground_truth_errors"] == 2
    assert receipt["fn"] == 1 and receipt["abstentions_on_known_ground_truth"] == 1
    assert receipt["false_negative_rate"] == 0.5 and receipt["coverage"] == 0.5
    assert receipt["f1"] == 0


def test_zero_and_false_positive_f1_and_rates():
    empty = metrics([row("UNKNOWN", "UNKNOWN", "UNKNOWN", "UNKNOWN")], "proposed")
    assert empty["precision"] is None and empty["f1"] is None
    actual = metrics([row("PASS", "PASS", "PASS", "FAIL"),
                      row("FAIL", "PASS", "PASS", "PASS")], "proposed")
    assert actual["fp"] == 1 and actual["fn"] == 1 and actual["f1"] == 0
    assert actual["false_positive_rate"] == 1 and actual["false_negative_rate"] == 1


def test_main_recall_and_f1_include_known_error_abstentions():
    result = metrics([row("FAIL", "PASS", "PASS", "FAIL"),
                      row("FAIL", "UNKNOWN", "UNKNOWN", "UNKNOWN")], "proposed")
    assert result["precision"] == result["conditional_recall"] == 1
    assert result["recall"] == result["known_error_detection_rate"] == 0.5
    assert result["f1"] == pytest.approx(2 / 3)
    assert result["fn"] == 0 and result["missed_known_errors"] == 1


def test_baselines_use_http_and_receipt_only_and_preserve_read_na():
    inputs: dict[str, Any] = {"slot": {"capability_id": "anchor_record"},
              "initial_agent_http": {"http_status": 200},
              "evm": {"results": {"receipt": {"status": "0x1"}}}}
    assert baseline_online(inputs) == baseline_receipt(inputs) == "PASS"
    inputs["slot"]["capability_id"] = "verify_record"
    assert baseline_receipt(inputs) == "NOT_APPLICABLE"
    inputs["initial_agent_http"]["http_status"] = 503
    assert baseline_online(inputs) == "FAIL"


def test_unexpected_na_does_not_change_predeclared_scope():
    values = row("FAIL", "PASS", "PASS", "NOT_APPLICABLE")
    result = metrics([values], "proposed")
    assert result["method_applicable"] == result["known_ground_truth"] == 1
    assert result["unexpected_na_on_known_ground_truth"] == 1
    assert result["coverage"] == result["known_error_detection_rate"] == 0


def test_failed_capture_cannot_be_analyzed_as_a_completed_experiment(tmp_path):
    (tmp_path / "execution.json").write_text('{"exit_code": 1}', encoding="utf-8")
    with pytest.raises(ValueError, match="Capture did not pass"):
        analyse(tmp_path)


def test_tampered_source_manifest_is_rejected_before_replay(tmp_path):
    (tmp_path / "execution.json").write_text(
        '{"exit_code": 0, "source_manifest": {"changed.py": "changed"}, '
        '"source_manifest_sha256": "original"}', encoding="utf-8")
    with pytest.raises(ValueError, match="source manifest hash"):
        analyse(tmp_path)
