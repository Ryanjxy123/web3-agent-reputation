"""Version-3 case coverage and controlled refusals preserve earlier task rules."""

import copy

import pytest
from reputation_core.case_templates import REJECTION_CASES, mutated_payload
from reputation_core.evidence import hash_json
from reputation_core.models import CaseSlot

from tests.factories import NOW
from tests.unit.test_task_outcomes import (
    claim_result,
    decide,
    excluded_input,
    reverted_anchor_input,
    task_input,
)


def negative_input(capability, case):
    data = (
        reverted_anchor_input().model_dump(mode="json")
        if capability == "anchor_record" else task_input(capability)
    )
    data["rule_version"] = "3"
    data["slot"].update(case_kind="negative", required_class=case)
    if case == "forbidden_contract":
        data["slot"]["request_overrides"] = {"target_contract": "0x" + "22" * 20}
    data["dispatch_payload_hash"] = hash_json(mutated_payload(CaseSlot.model_validate(data["slot"])))
    status, code = REJECTION_CASES[case]
    response = {"accepted": False, "error": {"code": code}}
    http = {
        "method": "POST", "origin": "http://127.0.0.1:19101", "path": "/tasks",
        "request_id": data["slot"]["task"]["request_id"], "http_status": status,
        "response": response, "started_at": NOW, "ended_at": NOW,
    }
    data.update(
        agent_http=http, initial_agent_http=copy.deepcopy(http), agent_response=response,
        agent_result=None, agent_task_status=None, execution_reason="SCHEMA_ERROR",
    )
    data["evm"]["candidate_tx_hash"] = None
    return data


@pytest.mark.parametrize("capability,case", [
    ("get_tx_status", "invalid_format"), ("get_tx_status", "unsupported_chain"),
    ("verify_record", "invalid_format"), ("verify_record", "forbidden_contract"),
    ("anchor_record", "expired_deadline"), ("anchor_record", "forbidden_contract"),
    ("anchor_record", "unsupported_chain"),
])
def test_correct_refusal_is_functional_pass_without_claiming_execution(capability, case):
    data = negative_input(capability, case)
    result = decide(data)
    assert result.outcome == "PASS" and not result.critical_conflict
    assert result.task_link.completion_kind == "rejection"
    assert result.task_link.verified_tx_hash is None
    assert result.task_link.block_number is None and result.task_link.log_index is None
    assert all(item.outcome == "PASS" for item in result.assertions)
    assert data["slot"]["task"] != mutated_payload(CaseSlot.model_validate(data["slot"]))


@pytest.mark.parametrize("change", ["wrong_code", "accepted", "service_error"])
def test_confirmed_noncompliant_refusal_is_failure_without_malice_inference(change):
    data = negative_input("get_tx_status", "unsupported_chain")
    response = {"accepted": False, "error": {"code": "OTHER_REJECTION"}}
    status = 403
    if change == "accepted":
        response, status = {"accepted": True}, 202
    elif change == "service_error":
        response, status = {"error": "unavailable"}, 503
    for field in ("agent_http", "initial_agent_http"):
        data[field].update(response=response, http_status=status)
    data["agent_response"] = response
    result = decide(data)
    assert result.outcome == "FAIL" and not result.critical_conflict


@pytest.mark.parametrize("change", [
    "actual_payload_hash", "initial_absent", "initial_differs", "endpoint", "platform_rpc",
    "allowed_target", "missing_http", "rate_limit", "no_response",
])
def test_insufficient_refusal_evidence_is_unknown(change):
    data = negative_input("verify_record", "forbidden_contract")
    if change == "actual_payload_hash":
        data["dispatch_payload_hash"] = hash_json(data["slot"]["task"])
    elif change == "initial_absent":
        data.pop("initial_agent_http")
    elif change == "initial_differs":
        data["initial_agent_http"]["http_status"] = 500
    elif change == "endpoint":
        data["agent_http"]["origin"] = "http://127.0.0.1:19102"
    elif change == "platform_rpc":
        data["evm"].update(error_reason="PLATFORM_RPC_ERROR", results={})
    elif change == "allowed_target":
        data["grant"]["contract_allowlist"].append(data["slot"]["request_overrides"]["target_contract"])
    elif change == "missing_http":
        data.update(agent_http=None, initial_agent_http=None, agent_response=None)
    else:
        for field in ("agent_http", "initial_agent_http"):
            data[field].update(http_status=429 if change == "rate_limit" else None, response=None)
        data["agent_response"] = None
    result = decide(data)
    assert result.outcome == "UNKNOWN" and not result.critical_conflict


@pytest.mark.parametrize("status,case", [
    ("SUCCESS", "success"), ("REVERTED", "revert"), ("PENDING", "pending"),
    ("NOT_FOUND", "not_found"),
])
def test_formal_read_cases_are_decided_from_independent_frozen_rpc(status, case):
    data = task_input(status=status)
    data["rule_version"] = "3"
    data["slot"]["required_class"] = case
    assert decide(data).outcome == "PASS"


def test_not_found_v3_is_scoped_to_frozen_observation_and_v2_remains_unknown():
    data = task_input(status="NOT_FOUND")
    assert decide(data).outcome == "UNKNOWN"
    data["rule_version"] = "3"
    data["slot"]["required_class"] = "not_found"
    result = decide(data)
    status = next(item for item in result.assertions if item.rule_id == "query.status")
    assert result.outcome == "PASS"
    assert status.expected["scope"] == "frozen_rpc_observation"
    assert result.task_link.verified_tx_hash is None
    claim_result(data, tx_status="SUCCESS")
    assert decide(data).outcome == "FAIL"
    data["evm"]["results"].pop("receipt")
    assert decide(data).outcome == "UNKNOWN"


@pytest.mark.parametrize("capability", ["get_tx_status", "verify_record"])
def test_missing_required_fixture_class_does_not_penalize_truthful_agent(capability):
    data = task_input(capability, status="NOT_FOUND", exists=False)
    data["rule_version"] = "3"
    data["slot"]["required_class"] = "success" if capability == "get_tx_status" else "match"
    result = decide(data)
    assert result.outcome == "UNKNOWN" and result.reason_code == "MISSING_EVIDENCE"
    assert not any(item.outcome == "FAIL" for item in result.assertions)


def test_formal_na_cannot_contain_initial_http_dispatch():
    data = excluded_input()
    data["rule_version"] = "3"
    assert decide(data).outcome == "NOT_APPLICABLE"
    data["initial_agent_http"] = {"method": "POST"}
    assert decide(data).outcome == "UNKNOWN"


def test_positive_probe_cannot_hide_wire_mutations():
    data = task_input()
    data["rule_version"] = "3"
    data["slot"].update(purpose="availability", request_overrides={"query_tx_hash": "bad"})
    with pytest.raises(ValueError):
        mutated_payload(CaseSlot.model_validate(data["slot"]))


@pytest.mark.parametrize("capability,case", [
    ("get_tx_status", "unsupported_chain"), ("verify_record", "forbidden_contract"),
    ("anchor_record", "expired_deadline"),
])
@pytest.mark.parametrize("missing", ["http", "rpc_error"])
def test_rejection_without_complete_evidence_never_passes(capability, case, missing):
    data = negative_input(capability, case)
    if missing == "http":
        data.update(agent_http=None, initial_agent_http=None, agent_response=None)
    else:
        data["evm"]["error_reason"] = "PLATFORM_RPC_ERROR"
    assert decide(data).outcome == "UNKNOWN"


@pytest.mark.parametrize("candidate", [None, "0x" + "55" * 32])
def test_not_found_cannot_use_null_reads_for_another_transaction(candidate):
    data = task_input(status="NOT_FOUND")
    data["rule_version"] = "3"
    data["slot"]["required_class"] = "not_found"
    data["evm"]["candidate_tx_hash"] = candidate
    result = decide(data)
    assert result.outcome == "UNKNOWN" and result.reason_code == "EVIDENCE_INCONSISTENT"


@pytest.mark.parametrize("issue", ["noncanonical", "not_final", "malformed_receipt"])
def test_unconfirmed_write_mismatch_cannot_create_critical_conflict(issue):
    data = reverted_anchor_input().model_dump(mode="json")
    data["rule_version"] = "3"
    data["slot"]["required_class"] = "normal"
    data["evm"]["results"]["transaction"]["to"] = "0x" + "22" * 20
    if issue == "noncanonical":
        data["evm"]["results"]["receipt_canonical"] = {
            **data["evm"]["results"]["receipt_canonical"], "hash": "0x" + "55" * 32,
        }
    elif issue == "not_final":
        data["slot"]["expected"]["confirmation_depth"] = 2
    else:
        data["evm"]["results"]["receipt"]["status"] = "malformed"
    result = decide(data)
    assert not result.critical_conflict
    assert not any(item.critical and item.outcome == "FAIL" for item in result.assertions)
