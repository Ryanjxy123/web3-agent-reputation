"""Four-state task attribution from frozen evidence, independent of platform services."""

import copy
import json
from pathlib import Path
from uuid import uuid4

import pytest
from eth_account import Account
from eth_account.messages import encode_typed_data
from pydantic import ValidationError
from reputation_core.binding import agent_key_hash, endpoint_hash, typed_data
from reputation_core.evidence import hash_json
from reputation_core.models import (
    BindingMessage,
    ClaimReview,
    Observation,
    RecordVerificationInput,
    RunPlan,
    TaskEnvelope,
)
from reputation_core.record_verifier import CALL_SELECTOR, seconds, verify_record
from reputation_core.reporting import build_report

from tests.factories import ADDRESS, DEADLINE, HASH, NOW, ZERO
from tests.unit.test_capability_rules import read_input


def task_input(capability="get_tx_status", *, status="SUCCESS", exists=True):
    data = read_input(capability, status=status, exists=exists).model_dump(mode="json")
    data["rule_version"] = "2"
    freeze_claims(data, [capability])
    data["agent_http"] = {
        "method": "GET",
        "origin": "http://127.0.0.1:19101",
        "path": "/tasks/" + data["slot"]["task"]["request_id"],
        "request_id": data["slot"]["task"]["request_id"],
        "http_status": 200,
        "response": copy.deepcopy(data["agent_response"]),
        "reason_code": None,
        "started_at": NOW,
        "ended_at": NOW,
    }
    return data


def freeze_claims(data, capabilities):
    core = data["snapshot"]["core"]
    core["normalized_metadata"] = {"capabilities": capabilities}
    core["metadata_hash"] = hash_json(core["normalized_metadata"])
    snapshot_hash = hash_json(core)
    data["snapshot"]["snapshot_hash"] = snapshot_hash
    data["review"]["snapshot_hash"] = snapshot_hash
    data["slot"]["expected"]["snapshot_hash"] = snapshot_hash
    data["slot"]["task"]["snapshot_hash"] = snapshot_hash
    if data.get("grant"):
        data["grant"]["snapshot_hash"] = snapshot_hash
    if data.get("registry_witness"):
        data["registry_witness"]["snapshot_core"] = copy.deepcopy(core)
    data["dispatch_payload_hash"] = hash_json(data["slot"]["task"])


def decide(data, evidence=True):
    inputs = RecordVerificationInput.model_validate(data)
    return verify_record(inputs, (uuid4(),) if evidence else ())


def claim_result(data, **changes):
    data["agent_result"].update(changes)
    data["agent_response"]["result"] = copy.deepcopy(data["agent_result"])
    data["agent_http"]["response"] = copy.deepcopy(data["agent_response"])


def excluded_input():
    data = task_input()
    freeze_claims(data, ["verify_record"])
    data["review"].update(
        confirmed_claims=["verify_record"], excluded_capabilities=["get_tx_status"]
    )
    data["slot"].update(
        applicability_reason="CAPABILITY_NOT_DECLARED", expected_outcome="NOT_APPLICABLE"
    )
    data.update(
        execution_reason="CAPABILITY_NOT_DECLARED",
        dispatch_started_at=None,
        dispatch_payload_hash=None,
        agent_http=None,
        agent_response=None,
        agent_result=None,
        agent_task_status=None,
        registry_witness=None,
        grant=None,
    )
    data["evm"].update(candidate_tx_hash=None, results={})
    return data


@pytest.mark.parametrize("capability", ["get_tx_status", "verify_record"])
def test_v2_truthful_task_pass_has_no_failure_reason(capability):
    result = decide(task_input(capability))
    assert result.outcome == "PASS" and result.reason_code is None
    assert all(item.rule_version == "2" for item in result.assertions)
    assert result.task_link.match_status == "PASS"


def test_business_failure_keeps_specific_reason_and_raw_proof():
    data = task_input("verify_record")
    claim_result(data, record_hash=ZERO, record_matches=False)
    result = decide(data)
    assert result.outcome == "FAIL" and result.reason_code == "RECORD_HASH_MISMATCH"
    assert result.task_link.verified_tx_hash is None


@pytest.mark.parametrize("status", [500, 502, 503])
def test_confirmed_service_error_is_agent_failure(status):
    data = task_input()
    response = {"error": "service unavailable"}
    data["agent_http"].update(http_status=status, response=response)
    data.update(agent_response=copy.deepcopy(response), agent_result=None, agent_task_status=None)
    result = decide(data)
    assert result.outcome == "FAIL" and result.reason_code == "AGENT_SERVICE_ERROR"


def test_received_invalid_schema_is_failure_without_fabricated_parsed_response():
    data = task_input()
    response = {"request_id": "invalid", "task_status": "succeeded"}
    data["agent_http"]["response"] = response
    data.update(agent_response=copy.deepcopy(response), agent_result=None, agent_task_status=None)
    result = decide(data)
    assert result.outcome == "FAIL" and result.reason_code == "SCHEMA_ERROR"


def test_valid_json_null_is_agent_schema_failure_while_invalid_json_remains_unknown():
    data = task_input()
    data["agent_http"]["response"] = None
    data.update(agent_response=None, agent_result=None, agent_task_status=None)
    result = decide(data)
    assert result.outcome == "FAIL" and result.reason_code == "SCHEMA_ERROR"


@pytest.mark.parametrize("reason", ["INTERNAL_ERROR", "CAPABILITY_EXPLICITLY_UNSUPPORTED"])
def test_declared_capability_execution_failure_is_not_not_applicable(reason):
    data = task_input()
    response = {
        **data["agent_response"],
        "task_status": "failed",
        "result": None,
        "reason_code": reason,
    }
    data.update(agent_response=response, agent_result=None, agent_task_status="failed")
    data["agent_http"]["response"] = copy.deepcopy(response)
    result = decide(data)
    assert result.outcome == "FAIL"
    assert result.reason_code == (
        "CAPABILITY_EXPLICITLY_UNSUPPORTED"
        if reason == "CAPABILITY_EXPLICITLY_UNSUPPORTED"
        else "AGENT_TASK_FAILED"
    )


@pytest.mark.parametrize("reason", ["PLATFORM_RPC_ERROR", "PLATFORM_NETWORK_ERROR"])
def test_platform_observation_errors_do_not_fail_agent(reason):
    data = task_input()
    if reason == "PLATFORM_RPC_ERROR":
        data["evm"].update(results={}, error_reason=reason)
    else:
        data.update(
            agent_http=None,
            agent_response=None,
            agent_result=None,
            agent_task_status=None,
            execution_reason=reason,
        )
    result = decide(data)
    assert result.outcome == "UNKNOWN" and result.reason_code == reason


def test_execution_reason_alone_does_not_prove_schema_failure():
    data = task_input()
    data.update(
        agent_http=None,
        agent_response=None,
        agent_result=None,
        agent_task_status=None,
        execution_reason="SCHEMA_ERROR",
    )
    assert decide(data).outcome == "UNKNOWN"


def test_agent_unsupported_reason_without_observable_response_proves_no_failure():
    data = task_input()
    data.update(
        agent_http=None,
        agent_response=None,
        agent_result=None,
        agent_task_status=None,
        execution_reason="CAPABILITY_EXPLICITLY_UNSUPPORTED",
    )
    assert decide(data).outcome == "UNKNOWN"


@pytest.mark.parametrize("change", ["chain", "canonical", "window"])
def test_context_gaps_prevent_agent_business_failure(change):
    data = task_input()
    claim_result(data, tx_status="REVERTED")
    if change == "chain":
        data["evm"]["results"]["chain_id"] = "0x1"
    elif change == "canonical":
        data["evm"]["results"]["read_canonical"]["hash"] = ZERO
    else:
        data["dispatch_started_at"] = "2026-10-02T12:02:00.000Z"
    result = decide(data)
    assert result.outcome == "UNKNOWN" and result.task_link.verified_tx_hash is None


def test_observed_service_failure_does_not_need_healthy_chain_rpc():
    data = task_input()
    data["agent_http"].update(http_status=500, response={"error": "service unavailable"})
    data.update(
        agent_response={"error": "service unavailable"}, agent_result=None, agent_task_status=None
    )
    data["evm"].update(results={}, error_reason="PLATFORM_RPC_ERROR")
    result = decide(data)
    assert result.outcome == "FAIL" and result.reason_code == "AGENT_SERVICE_ERROR"


def test_http_body_and_parsed_result_conflict_is_evidence_gap():
    data = task_input()
    data["agent_result"]["tx_status"] = "REVERTED"
    result = decide(data)
    assert result.outcome == "UNKNOWN" and result.task_link.verified_tx_hash is None


@pytest.mark.parametrize(
    "changes",
    [
        {"http_status": []},
        {"http_status": {}},
        {"http_status": True},
        {"http_status": "500"},
        {"started_at": "zz", "ended_at": "zz", "http_status": 500},
        {"started_at": [], "ended_at": []},
    ],
)
def test_malformed_frozen_http_envelope_is_unknown_not_agent_failure(changes):
    data = task_input()
    data["agent_http"].update(changes)
    assert decide(data).outcome == "UNKNOWN"


def test_no_saved_evidence_cannot_decide_service_failure():
    data = task_input()
    data["agent_http"].update(http_status=500, response={})
    assert decide(data, evidence=False).outcome == "UNKNOWN"


@pytest.mark.parametrize("gap", ["payload_mismatch", "no_authorization", "late_dispatch"])
def test_service_error_does_not_fail_agent_for_invalid_platform_dispatch(gap):
    data = task_input()
    data["agent_http"].update(http_status=500, response={"error": "service unavailable"})
    data.update(
        agent_response={"error": "service unavailable"}, agent_result=None, agent_task_status=None
    )
    if gap == "payload_mismatch":
        data["dispatch_payload_hash"] = ZERO
    elif gap == "no_authorization":
        data["grant"] = None
    else:
        data["dispatch_started_at"] = "2026-10-02T12:02:00.000Z"
        data["agent_http"]["started_at"] = data["agent_http"]["ended_at"] = data[
            "dispatch_started_at"
        ]
    assert decide(data).outcome == "UNKNOWN"


@pytest.mark.parametrize("scope", ["ungranted_endpoint", "ungranted_method"])
def test_service_failure_requires_the_observed_http_scope_to_be_granted(scope):
    data = task_input()
    if scope == "ungranted_endpoint":
        endpoint = {
            **data["snapshot"]["core"]["endpoints"][0],
            "endpoint_id": "other",
            "port": 19102,
        }
        data["snapshot"]["core"]["endpoints"].append(endpoint)
        freeze_claims(data, ["get_tx_status"])
        data["agent_http"]["origin"] = "http://127.0.0.1:19102"
    else:
        data["grant"]["methods"] = ["POST"]
    data["agent_http"].update(http_status=500, response={"error": "service unavailable"})
    data.update(
        agent_response={"error": "service unavailable"}, agent_result=None, agent_task_status=None
    )
    assert decide(data).outcome == "UNKNOWN"


def test_pre_dispatch_frozen_exclusion_is_not_applicable_without_rpc():
    result = decide(excluded_input())
    assert result.outcome == "NOT_APPLICABLE" and result.reason_code == "CAPABILITY_NOT_DECLARED"
    assert result.task_link.match_status == "NOT_APPLICABLE"
    assert result.task_link.verified_tx_hash is None


@pytest.mark.parametrize(
    "change", ["no_review_exclusion", "positive_metadata", "already_dispatched", "marker_only"]
)
def test_not_applicable_requires_complete_prior_exclusion_evidence(change):
    data = excluded_input()
    if change == "no_review_exclusion":
        data["review"]["excluded_capabilities"] = []
    elif change == "positive_metadata":
        freeze_claims(data, ["verify_record", "get_tx_status"])
        data["dispatch_payload_hash"] = None
    elif change == "already_dispatched":
        data["dispatch_started_at"] = NOW
        data["dispatch_payload_hash"] = hash_json(data["slot"]["task"])
    else:
        data = task_input()
        data["slot"]["applicability_reason"] = "CAPABILITY_NOT_DECLARED"
    assert decide(data).outcome != "NOT_APPLICABLE"


def test_review_cannot_confirm_and_exclude_the_same_capability():
    body = task_input()["review"]
    body["excluded_capabilities"] = body["confirmed_claims"]
    with pytest.raises(ValidationError):
        ClaimReview.model_validate(body)


@pytest.mark.parametrize("declared", [[], [True], [{}]])
def test_not_applicable_requires_a_well_formed_frozen_declaration(declared):
    data = excluded_input()
    freeze_claims(data, declared)
    data["dispatch_payload_hash"] = None
    assert decide(data).outcome == "UNKNOWN"


def test_rule_versions_are_explicit_and_generate_distinct_stable_assertions():
    inputs = RecordVerificationInput.model_validate(task_input())
    reference = (uuid4(),)
    result = verify_record(inputs, reference)
    restored = RecordVerificationInput.model_validate_json(inputs.model_dump_json())
    assert verify_record(restored, reference) == result
    legacy = inputs.model_copy(update={"rule_version": "1", "agent_http": None})
    old = verify_record(legacy, reference)
    assert {item.assertion_id for item in result.assertions}.isdisjoint(
        item.assertion_id for item in old.assertions
    )
    with pytest.raises(ValidationError):
        RecordVerificationInput.model_validate(
            {**inputs.model_dump(mode="json"), "rule_version": "4"}
        )


def test_legacy_version_defaults_preserve_wire_and_generic_failure_reason():
    legacy = read_input(status="SUCCESS")
    body = legacy.model_dump(mode="json")
    assert "rule_version" not in body and "agent_http" not in body
    assert "excluded_capabilities" not in body["review"]
    assert "applicability_reason" not in body["slot"]
    body["agent_result"]["tx_status"] = "REVERTED"
    body["agent_response"]["result"] = copy.deepcopy(body["agent_result"])
    result = decide(body)
    assert result.outcome == "FAIL" and result.reason_code == "SEMANTIC_MISMATCH"
    assert all(item.rule_version == "1" for item in result.assertions)


def reverted_anchor_input(*, receipt_status="0x0"):
    data = task_input("verify_record", status="SUCCESS", exists=True)
    body = data
    signing_key = "0x" + "01" * 32
    account = Account.from_key(signing_key)
    executor = account.address.lower()
    synthetic = {"kind": "fixture-credential", "challenge": "0x" + "44" * 32}
    record_hash = hash_json(synthetic)
    slot, task, facts = body["slot"], body["slot"]["task"], body["slot"]["expected"]
    slot.update(capability_id="anchor_record", expected_outcome="PASS", synthetic_input=synthetic)
    task.update(
        capability_id="anchor_record",
        target_contract=ADDRESS,
        record_hash=record_hash,
        query_tx_hash=None,
        record_executor=None,
        record_request_id=None,
        read_block_number=None,
        read_block_hash=None,
    )
    slot["task"] = TaskEnvelope.model_validate(task).model_dump(mode="json")
    body["snapshot"]["core"]["owner"] = executor
    body["review"].update(confirmed_claims=["anchor_record"], excluded_capabilities=[])
    freeze_claims(body, ["anchor_record"])
    task = body["slot"]["task"]
    facts.update(
        executor=executor,
        target_contract=ADDRESS,
        record_hash=record_hash,
        binding_id=str(uuid4()),
    )
    agent_ref = body["snapshot"]["core"]["agent_ref"]
    message = BindingMessage(
        agent_key_hash=agent_key_hash(RecordVerificationInput.model_validate(body).snapshot.core.agent_ref),
        snapshot_hash=body["snapshot"]["snapshot_hash"],
        executor=executor,
        endpoint_hash=endpoint_hash(RecordVerificationInput.model_validate(body).snapshot.core.endpoints[0]),
        execution_chain_id=facts["execution_chain"]["chain_id"],
        execution_chain_instance_hash=facts["execution_chain"]["instance_hash"],
        nonce="0x" + "55" * 32,
        issued_at=seconds(NOW) - 1,
        deadline=seconds(DEADLINE) + 60,
    )
    message_body = message.model_dump(mode="json")
    proof_id = facts["binding_id"]
    binding = {
        "binding_id": proof_id,
        "message": message_body,
        "owner": executor,
        "owner_signature": Account.sign_message(
            encode_typed_data(
                full_message=typed_data(
                    message,
                    agent_ref["chain_id"],
                    agent_ref["registry_address"],
                    body["platform_instance_id"],
                    1,
                )
            ), signing_key
        ).signature.to_0x_hex(),
        "executor_signature": Account.sign_message(
            encode_typed_data(
                full_message=typed_data(
                    message,
                    agent_ref["chain_id"],
                    agent_ref["registry_address"],
                    body["platform_instance_id"],
                    2,
                )
            ), signing_key
        ).signature.to_0x_hex(),
        "domain_chain_id": agent_ref["chain_id"],
        "domain_registry": agent_ref["registry_address"],
        "domain_salt": body["platform_instance_id"],
        "status": "VERIFIED",
        "reason_code": None,
        "verification_evidence": [str(uuid4())],
    }
    body.update(binding=binding, registry_witness={
        "snapshot_core": body["snapshot"]["core"],
        "owner_code": "0x",
        "executor_code": "0x",
        "read_method": "eth_call_at_block_number",
    })
    body["grant"].update(
        capabilities=["anchor_record"], contract_allowlist=[ADDRESS]
    )
    result = {
        "chain_id": "31337",
        "tx_hash": HASH,
        "executor": executor,
        "record_hash": record_hash,
    }
    response = {
        "request_id": task["request_id"],
        "task_status": "failed",
        "status_path": "/tasks/" + task["request_id"],
        "result": result,
        "reason_code": "BUSINESS_REJECTED",
    }
    body.update(
        agent_http={
            "method": "POST",
            "origin": "http://127.0.0.1:19101",
            "path": "/tasks",
            "request_id": task["request_id"],
            "http_status": 200,
            "response": response,
            "reason_code": None,
            "started_at": NOW,
            "ended_at": NOW,
        },
        agent_response=response,
        agent_result=result,
        agent_task_status="failed",
        execution_reason="AGENT_TASK_FAILED",
    )
    rpc = body["evm"]["results"]
    block = rpc["read_block"]
    rpc.update(
        transaction={
            "hash": HASH,
            "chainId": "0x7a69",
            "from": executor,
            "to": ADDRESS,
            "input": CALL_SELECTOR + task["request_id"][2:] + record_hash[2:],
            "blockHash": HASH,
            "blockNumber": "0x1",
            "transactionIndex": "0x0",
        },
        receipt={
            "transactionHash": HASH,
            "blockHash": HASH,
            "blockNumber": "0x1",
            "transactionIndex": "0x0",
            "status": receipt_status,
            "logs": [],
        },
        receipt_block=block,
        receipt_canonical=block,
        head={"number": "0x1", "hash": HASH},
    )
    body["evm"].update(candidate_tx_hash=HASH, error_reason=None)
    body["dispatch_payload_hash"] = hash_json(task)
    return RecordVerificationInput.model_validate(body)


@pytest.mark.parametrize(
    ("receipt_status", "rpc_error", "reason"),
    [("0x0", None, "TX_REVERTED"), ("0x0", "PLATFORM_RPC_ERROR", "AGENT_TASK_FAILED")],
)
def test_failed_write_with_candidate_uses_reverted_receipt_only_when_independently_observed(
    receipt_status, rpc_error, reason
):
    data = reverted_anchor_input(receipt_status=receipt_status)
    if rpc_error:
        data = data.model_copy(
            update={
                "evm": data.evm.model_copy(
                    update={"results": {}, "error_reason": rpc_error}
                )
            }
        )
    result = verify_record(data, (uuid4(),))
    assert result.outcome == "FAIL" and result.reason_code == reason


def report_for_read_input(data):
    policy = json.loads(
        (Path(__file__).resolve().parents[2] / "configs/policies/policy-v1.json").read_text()
    )
    input_model = RecordVerificationInput.model_validate(data)
    plan = RunPlan(
        run_id=uuid4(),
        snapshot_hash=input_model.snapshot.snapshot_hash,
        review_version=input_model.review_version,
        policy_version="policy-v1",
        policy_hash=hash_json(policy),
        profile="record-read-v1",
        confirmed_capabilities=input_model.review.confirmed_claims,
        suite_id="capabilities-v1",
        template_version="capabilities@2",
        planning_time=NOW,
        slots=(input_model.slot,),
    )
    observation = Observation(
        observation_id=uuid4(),
        slot_id=input_model.slot.slot_id,
        attempt_no=1,
        dispatch_state="SETTLED",
        started_at=NOW,
        ended_at=NOW,
        latency_ms=None,
        error_origin="platform" if input_model.evm.error_reason else None,
        reason_code=input_model.execution_reason,
        accepted=input_model.slot.applicability_reason is None,
        candidate_tx_hash=None,
        evidence_refs=(uuid4(),),
        diagnostic_only=False,
    )
    return build_report(
        plan,
        input_model,
        uuid4(),
        (observation,),
        policy,
        evaluated_at="2026-10-02T12:00:01.000Z",
        code_version="0" * 40,
        manifest_hash="0x" + "11" * 32,
        previous_report_hash="0x" + "00" * 32,
    )


@pytest.mark.parametrize("case", ["not-applicable", "early-rpc-error"])
def test_report_settlement_accepts_not_applicable_and_early_rpc_unknown_reads(case):
    if case == "not-applicable":
        data = excluded_input()
    else:
        data = task_input()
        data["execution_reason"] = "PLATFORM_RPC_ERROR"
        data["evm"].update(
            candidate_tx_hash=None, results={}, error_reason="PLATFORM_RPC_ERROR"
        )
    report = report_for_read_input(data)
    assert report.raw_statistics["capabilities"][0]["decided"] == 0
