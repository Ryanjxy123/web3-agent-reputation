"""RPC contradictions cannot establish an Agent conflict under rule 5."""

from copy import deepcopy
from uuid import uuid4

import pytest
from reputation_core.models import RecordVerificationInput
from reputation_core.record_verifier import EVENT_TOPIC, preserve_rpc_unknown, verify_record
from reputation_core.reporting import build_report

from tests.unit.test_evidence_assessment import (
    changed_write_response,
    high_score_critical_arguments,
)


@pytest.fixture(scope="module")
def write_arguments():
    return high_score_critical_arguments()


@pytest.fixture
def completed_write_body(write_arguments):
    body = write_arguments["inputs"][-2].model_dump(mode="json")
    body["rule_version"] = "5"
    return body


@pytest.mark.parametrize("field,value", [
    ("transactionHash", "0x" + "ee" * 32),
    ("blockHash", "0x" + "ee" * 32),
    ("blockNumber", "0x3"),
    ("transactionIndex", "0x63"),
    ("removed", True),
])
@pytest.mark.parametrize("business_issue", [None, "agent_digest", "event_digest"])
def test_rule5_rejects_log_location_before_confirming_business_conflicts(
    completed_write_body, field, value, business_issue
):
    body = completed_write_body
    log = body["evm"]["results"]["receipt"]["logs"][0]
    log[field] = value
    if business_issue == "agent_digest":
        for response in (
            body["agent_result"], body["agent_response"]["result"],
            body["agent_http"]["response"]["result"],
        ):
            response["record_hash"] = "0x" + "ee" * 32
    elif business_issue == "event_digest":
        log["data"] = "0x" + "ee" * 32
    result = verify_record(RecordVerificationInput.model_validate(body), (uuid4(),))
    assert result.outcome == "UNKNOWN" and result.reason_code == "EVIDENCE_INCONSISTENT"
    assert not result.critical_conflict and result.task_link.verified_tx_hash is None
    assert not any(item.critical and item.outcome == "FAIL" for item in result.assertions)


@pytest.mark.parametrize("issue", ["unrelated_location", "duplicate_index", "descending_index"])
def test_rule5_validates_all_receipt_logs_even_unrelated_topics(completed_write_body, issue):
    body = completed_write_body
    logs = body["evm"]["results"]["receipt"]["logs"]
    unrelated = deepcopy(logs[0])
    unrelated["topics"] = ["0x" + "ee" * 32]
    if issue == "unrelated_location":
        unrelated.update(transactionHash="0x" + "ee" * 32, logIndex="0x13")
        logs.append(unrelated)
    elif issue == "duplicate_index":
        logs.append(unrelated)
    else:
        unrelated["logIndex"] = "0x13"
        logs.insert(0, unrelated)
    result = verify_record(RecordVerificationInput.model_validate(body), (uuid4(),))
    assert result.outcome == "UNKNOWN" and result.reason_code == "EVIDENCE_INCONSISTENT"
    assert not result.critical_conflict
    assert not any(item.critical and item.outcome == "FAIL" for item in result.assertions)


@pytest.mark.parametrize("logs", [{}, "", [None], [{"malformed": True}]])
def test_rule5_malformed_log_evidence_cannot_confirm_wrong_agent_digest(write_arguments, logs):
    body = changed_write_response(write_arguments["inputs"][-2], "record_hash")
    body["rule_version"] = "5"
    body["evm"]["results"]["receipt"]["logs"] = logs
    item = RecordVerificationInput.model_validate(body)
    result = verify_record(item, (uuid4(),))
    assert result.outcome == "UNKNOWN" and not result.critical_conflict
    assert result.reason_code == "PLATFORM_RPC_ERROR" and preserve_rpc_unknown(item, result)
    assert result.task_link.verified_tx_hash is None
    assert not any(item.critical and item.outcome == "FAIL" for item in result.assertions)


@pytest.mark.parametrize("field,value", [
    ("topics", {}), ("topics", [None]), ("data", "0xnothex"),
    ("data", "0x11"), ("topics", [EVENT_TOPIC]),
    ("topics", [EVENT_TOPIC, "0x" + "ee" * 32, "0x" + "01" * 32]),
    ("address", "0x11"), ("removed", 1),
])
def test_rule5_malformed_log_fields_are_preserved_as_platform_evidence_gap(
    write_arguments, field, value
):
    body = changed_write_response(write_arguments["inputs"][-2], "record_hash")
    body["rule_version"] = "5"
    body["evm"]["results"]["receipt"]["logs"][0][field] = value
    item = RecordVerificationInput.model_validate(body)
    result = verify_record(item, (uuid4(),))
    assert result.outcome == "UNKNOWN" and result.reason_code == "PLATFORM_RPC_ERROR"
    assert not result.critical_conflict and preserve_rpc_unknown(item, result)
    gap = next(assertion for assertion in result.assertions if assertion.rule_id == "receipt.logs")
    assert gap.outcome == "UNKNOWN" and gap.expected is not None
    assert not any(assertion.critical and assertion.outcome == "FAIL" for assertion in result.assertions)


def test_rule4_keeps_its_historical_log_location_conflict(write_arguments):
    body = write_arguments["inputs"][-2].model_dump(mode="json")
    body["rule_version"] = "4"
    body["evm"]["results"]["receipt"]["logs"][0]["transactionHash"] = "0x" + "ee" * 32
    result = verify_record(RecordVerificationInput.model_validate(body), (uuid4(),))
    assert result.outcome == "FAIL" and result.reason_code == "SEMANTIC_MISMATCH"
    assert result.critical_conflict
    location = next(item for item in result.assertions if item.rule_id == "record.location")
    assert location.rule_version == "4" and location.outcome == "FAIL" and location.critical


@pytest.mark.parametrize("issue,rule,reason", [
    ("target", "tx.target", "TX_WRONG_TARGET"),
    ("digest", "record.hash", "RECORD_HASH_MISMATCH"),
    ("request", "record.request", "TASK_ID_MISMATCH"),
])
def test_rule5_keeps_confirmed_task_conflicts_with_valid_receipt_evidence(
    completed_write_body, issue, rule, reason
):
    body = completed_write_body
    rpc = body["evm"]["results"]
    if issue == "target":
        rpc["transaction"]["to"] = "0x" + "ee" * 20
    elif issue == "digest":
        rpc["receipt"]["logs"][0]["data"] = "0x" + "ee" * 32
    else:
        rpc["receipt"]["logs"][0]["topics"][2] = "0x" + "ee" * 32
    result = verify_record(RecordVerificationInput.model_validate(body), (uuid4(),))
    assert result.outcome == "FAIL" and result.reason_code == reason
    assert result.critical_conflict
    finding = next(item for item in result.assertions if item.rule_id == rule)
    assert finding.rule_version == "5" and finding.critical and finding.outcome == "FAIL"


def test_rule5_accepts_correct_receipt_with_unrelated_ordered_log(completed_write_body):
    body = completed_write_body
    logs = body["evm"]["results"]["receipt"]["logs"]
    unrelated = deepcopy(logs[0])
    unrelated.update(topics=["0x" + "ee" * 32], data="0x11", logIndex="0x13")
    logs.append(unrelated)
    result = verify_record(RecordVerificationInput.model_validate(body), (uuid4(),))
    assert result.outcome == "PASS" and not result.critical_conflict
    assert result.task_link.verified_tx_hash == body["evm"]["candidate_tx_hash"]


def test_real_log_location_gap_can_be_preserved_after_rpc_recovers(completed_write_body):
    body = completed_write_body
    body["evm"]["results"]["receipt"]["logs"][0]["transactionHash"] = "0x" + "ee" * 32
    item = RecordVerificationInput.model_validate(body)
    result = verify_record(item, (uuid4(),))
    log_gap = next(assertion for assertion in result.assertions if assertion.rule_id == "receipt.logs")
    assert log_gap.outcome == "UNKNOWN" and log_gap.expected is not None
    assert preserve_rpc_unknown(item, result)


def test_unavailable_placeholder_log_assertion_cannot_enable_rpc_recovery_exception(
    completed_write_body
):
    body = completed_write_body
    body["agent_http"]["request_id"] = "0x" + "ee" * 32
    item = RecordVerificationInput.model_validate(body)
    result = verify_record(item, (uuid4(),))
    assert result.outcome == "UNKNOWN" and result.reason_code == "EVIDENCE_INCONSISTENT"
    log_gap = next(assertion for assertion in result.assertions if assertion.rule_id == "receipt.logs")
    assert log_gap.outcome == "UNKNOWN" and log_gap.reason_code == "EVIDENCE_INCONSISTENT"
    assert log_gap.expected is None
    assert not preserve_rpc_unknown(item, result)


def test_decided_business_failure_cannot_enable_rpc_recovery_exception(completed_write_body):
    body = completed_write_body
    body["evm"]["results"]["receipt"]["logs"][0]["data"] = "0x" + "ee" * 32
    item = RecordVerificationInput.model_validate(body)
    result = verify_record(item, (uuid4(),))
    assert result.outcome == "FAIL" and result.critical_conflict
    assert not preserve_rpc_unknown(item, result)


@pytest.mark.parametrize("version", ["1", "2", "3", "4", "5"])
def test_explicit_historical_rpc_error_preservation_keeps_version_boundary(write_arguments, version):
    body = write_arguments["inputs"][-2].model_dump(mode="json")
    body["rule_version"] = version
    body["evm"].update(results={}, error_reason="PLATFORM_RPC_ERROR")
    item = RecordVerificationInput.model_validate(body)
    result = verify_record(item, (uuid4(),))
    assert result.outcome == "UNKNOWN"
    assert preserve_rpc_unknown(item, result) == (version != "1")


def test_invalid_rpc_log_retains_scores_but_cannot_meet_behavior_sample_gate(write_arguments):
    arguments = dict(write_arguments)
    inputs = []
    for index, original in enumerate(arguments["inputs"]):
        body = original.model_dump(mode="json")
        body["rule_version"] = "5"
        if index == len(arguments["inputs"]) - 1:
            body["evm"]["results"]["receipt"]["logs"][0]["data"] = body["slot"]["task"]["record_hash"]
        elif index == len(arguments["inputs"]) - 2:
            body["evm"]["results"]["receipt"]["logs"][0]["transactionHash"] = "0x" + "ee" * 32
        inputs.append(RecordVerificationInput.model_validate(body))
    arguments["inputs"] = tuple(inputs)
    arguments["plan"] = arguments["plan"].model_copy(update={"template_version": "capabilities@5"})
    report = build_report(**arguments, report_schema_version="1.4.0")
    assert report.schema_version == "1.4.0"
    assert report.scores.evaluation_state == "PARTIAL" and report.scores.overall_score_bp is None
    assert report.scores.dimensions["availability"].score_bp == 9800
    assert report.scores.dimensions["consistency"].score_bp == 9600
    assert report.scores.dimensions["behavior"].observed_score_bp == 10000
    assert report.raw_statistics["behavior"]["decided"] == 9
    assert report.raw_statistics["behavior"]["correct"] == 9
    assert report.task_counts.unknown_count == 1
    assert "behavior:samples" in report.evidence_sufficiency.missing_evidence
    assert report.risk_assessment.conclusion == "NO_CONFIRMED_CRITICAL_CONFLICT"
    assert report.risk_assessment.critical_findings == ()
    assert len(report.risk_assessment.evidence_gap_slots) == 1
