"""Confirmed task conflicts survive both high formal scores and incomplete evidence."""

from copy import deepcopy
from uuid import uuid4

import pytest
from eth_account import Account
from eth_account.messages import encode_typed_data
from reputation_core.binding import typed_data
from reputation_core.case_templates import REJECTION_CASES, mutated_payload
from reputation_core.evidence import hash_json
from reputation_core.models import BindingMessage, Observation, RecordVerificationInput
from reputation_core.record_verifier import CALL_SELECTOR, EVENT_TOPIC, seconds, verify_record
from reputation_core.reporting import build_report

from tests.factories import NOW
from tests.unit.test_formal_scoring import complete_read_arguments
from tests.unit.test_task_outcomes import freeze_claims, reverted_anchor_input


def high_score_critical_arguments():
    """Fifty independent slots with one canonical successful transaction carrying a wrong digest."""
    arguments = complete_read_arguments()
    anchor = reverted_anchor_input(receipt_status="0x1").model_dump(mode="json")
    capabilities = ["verify_record", "anchor_record"]
    anchor["review"]["confirmed_claims"] = capabilities
    freeze_claims(anchor, capabilities)
    binding = anchor["binding"]
    binding["message"]["snapshot_hash"] = anchor["snapshot"]["snapshot_hash"]
    message = BindingMessage.model_validate(binding["message"])
    for field, role in (("owner_signature", 1), ("executor_signature", 2)):
        binding[field] = Account.sign_message(
            encode_typed_data(full_message=typed_data(
                message, binding["domain_chain_id"], binding["domain_registry"],
                binding["domain_salt"], role,
            )), "0x" + "01" * 32,
        ).signature.to_0x_hex()

    inputs = []
    observations = list(arguments["observations"])
    for index, original in enumerate(arguments["inputs"]):
        body = original.model_dump(mode="json")
        body["snapshot"] = deepcopy(anchor["snapshot"])
        body["review"] = deepcopy(anchor["review"])
        body["registry_witness"]["snapshot_core"] = deepcopy(anchor["snapshot"]["core"])
        for context in (body["slot"]["task"], body["slot"]["expected"], body["grant"]):
            context["snapshot_hash"] = anchor["snapshot"]["snapshot_hash"]
        if index == 19:
            # Twenty valid initial responses, including two measured 4000 ms responses: A=9800.
            initial = body["initial_agent_http"]
            initial.update(latency_ms=4000, ended_at="2026-10-02T12:00:04.000Z")
            initial["response"] = {
                "request_id": body["slot"]["task"]["request_id"], "task_status": "accepted",
                "status_path": "/tasks/" + body["slot"]["task"]["request_id"], "result": None,
            }
            observations[2 * index] = observations[2 * index].model_copy(update={
                "dispatch_state": "ACKNOWLEDGED", "accepted": True,
                "latency_ms": 4000, "ended_at": initial["ended_at"],
            })
        item = RecordVerificationInput.model_validate(body)
        inputs.append(item.model_copy(update={
            "dispatch_payload_hash": hash_json(mutated_payload(item.slot)),
        }))

    cases = ("normal",) * 7 + ("expired_deadline", "forbidden_contract", "unsupported_chain")
    for index, case in enumerate((*cases, *("normal",) * 10)):
        body = deepcopy(anchor)
        slot = body["slot"]
        request_id = "0x" + (index + 100).to_bytes(32, "big").hex()
        tx_hash = "0x" + (index + 1000).to_bytes(32, "big").hex()
        negative = case != "normal"
        slot.update(
            slot_id=str(uuid4()), slot_key=f"anchor-{index}", required_class=case,
            purpose="functional" if index < 10 else "behavioral",
            case_kind="negative" if negative else "positive",
        )
        slot["task"]["request_id"] = slot["expected"]["request_id"] = request_id
        if case == "forbidden_contract":
            slot["request_overrides"] = {"target_contract": "0x" + "22" * 20}
        body["rule_version"] = "5"
        body["evm"]["observed_at"] = "2026-10-02T12:00:02.000Z"
        http = body["agent_http"]
        http.update(request_id=request_id, ended_at="2026-10-02T12:00:00.100Z", latency_ms=100)
        if negative:
            status, code = REJECTION_CASES[case]
            response = {"accepted": False, "error": {"code": code}}
            http.update(http_status=status, response=response)
            body.update(agent_response=response, agent_result=None, agent_task_status=None,
                        execution_reason="SCHEMA_ERROR")
            body["evm"]["candidate_tx_hash"] = None
            initial = deepcopy(http)
        else:
            result = body["agent_result"]
            result["tx_hash"] = tx_hash
            response = {
                "request_id": request_id, "task_status": "succeeded",
                "status_path": "/tasks/" + request_id, "result": result,
            }
            body.update(agent_response=response, agent_task_status="succeeded", execution_reason=None)
            http.update(method="GET", path="/tasks/" + request_id, response=deepcopy(response),
                        ended_at="2026-10-02T12:00:02.000Z")
            initial = {
                **deepcopy(http), "method": "POST", "path": "/tasks",
                "ended_at": "2026-10-02T12:00:00.100Z",
                "response": {"request_id": request_id, "task_status": "accepted",
                             "status_path": "/tasks/" + request_id, "result": None},
            }
            rpc = body["evm"]["results"]
            block = {"number": "0x2", "hash": "0x" + "bb" * 32,
                     "timestamp": hex(seconds(NOW) + 1)}
            location = {"blockNumber": "0x2", "blockHash": block["hash"],
                        "transactionIndex": hex(index)}
            rpc["transaction"].update(
                **location, hash=tx_hash,
                input=CALL_SELECTOR + request_id[2:] + slot["task"]["record_hash"][2:],
            )
            rpc["receipt"].update(**location, transactionHash=tx_hash)
            rpc.update(receipt_block=block, receipt_canonical=deepcopy(block),
                       head={"number": "0x2", "hash": block["hash"]})
            rpc["receipt"]["logs"] = [{
                **location, "transactionHash": tx_hash, "logIndex": hex(index), "removed": False,
                "topics": [EVENT_TOPIC, "0x" + "0" * 24 + slot["expected"]["executor"][2:], request_id],
                "address": slot["task"]["target_contract"],
                "data": "0x" + "22" * 32 if index == 19 else slot["task"]["record_hash"],
            }]
            body["evm"]["candidate_tx_hash"] = tx_hash
        body["initial_agent_http"] = initial
        item = RecordVerificationInput.model_validate(body)
        item = item.model_copy(update={"dispatch_payload_hash": hash_json(mutated_payload(item.slot))})
        inputs.append(item)
        observations.extend((
            Observation(
                observation_id=uuid4(), slot_id=item.slot.slot_id, attempt_no=1,
                dispatch_state="DISPATCH_UNCERTAIN" if negative else "ACKNOWLEDGED",
                started_at=NOW, ended_at=initial["ended_at"], http_status=initial["http_status"],
                latency_ms=100, error_origin=None, reason_code=item.execution_reason,
                accepted=not negative, candidate_tx_hash=None, evidence_refs=(uuid4(),), diagnostic_only=False,
            ),
            Observation(
                observation_id=uuid4(), slot_id=item.slot.slot_id, attempt_no=2,
                dispatch_state="SETTLED", started_at="2026-10-02T12:00:05.000Z",
                ended_at="2026-10-02T12:00:05.000Z", http_status=None, latency_ms=None,
                error_origin=None, reason_code=item.execution_reason, accepted=not negative,
                candidate_tx_hash=item.evm.candidate_tx_hash, evidence_refs=(uuid4(),), diagnostic_only=True,
            ),
        ))
    arguments.update(inputs=tuple(inputs), observations=tuple(observations),
                     evidence_id=tuple(uuid4() for _ in inputs))
    arguments["plan"] = arguments["plan"].model_copy(update={
        "profile": "record-write-v1", "snapshot_hash": inputs[0].snapshot.snapshot_hash,
        "confirmed_capabilities": tuple(capabilities), "slots": tuple(item.slot for item in inputs),
    })
    return arguments


def test_high_complete_score_cannot_hide_confirmed_wrong_digest():
    report = build_report(**high_score_critical_arguments())
    assert report.scores.evaluation_state == "COMPLETE" and report.scores.overall_score_bp == 9480
    assert report.scores.dimensions["availability"].score_bp == 9800
    assert report.scores.dimensions["consistency"].score_bp == 9600
    assert report.scores.dimensions["behavior"].score_bp == 9000
    assert report.evidence_sufficiency is not None and report.evidence_sufficiency.overall_allowed
    assert report.scores.critical_conflict and report.scores.advice == "NOT_RECOMMENDED"
    assert report.risk_assessment is not None
    assert report.risk_assessment.conclusion == "CONFIRMED_CRITICAL_CONFLICT"
    finding, = report.risk_assessment.critical_findings
    assert finding.rule_id == "record.hash" and finding.reason_code == "RECORD_HASH_MISMATCH"
    assert finding.evidence_refs
    assert len(report.risk_assessment.ordinary_failure_slots) == 1
    assert report.risk_assessment.evidence_gap_slots == ()


def test_confirmed_wrong_digest_survives_insufficient_availability():
    arguments = high_score_critical_arguments()
    arguments["inputs"] = arguments["inputs"][19:]
    arguments["evidence_id"] = arguments["evidence_id"][19:]
    retained = {item.slot.slot_id for item in arguments["inputs"]}
    arguments["observations"] = tuple(item for item in arguments["observations"] if item.slot_id in retained)
    arguments["plan"] = arguments["plan"].model_copy(update={
        "slots": tuple(item.slot for item in arguments["inputs"]),
    })
    report = build_report(**arguments)
    assert report.scores.evaluation_state == "PARTIAL" and report.scores.overall_score_bp is None
    assert report.evidence_sufficiency is not None
    assert "availability:samples" in report.evidence_sufficiency.missing_evidence
    assert not report.evidence_sufficiency.overall_allowed
    assert report.scores.critical_conflict and report.scores.advice == "NOT_RECOMMENDED"
    assert report.risk_assessment is not None
    assert report.risk_assessment.conclusion == "CONFIRMED_CRITICAL_CONFLICT"
    assert len(report.risk_assessment.critical_findings) == 1


@pytest.fixture(scope="module")
def completed_write():
    return high_score_critical_arguments()["inputs"][-2]


def changed_write_response(original, field):
    body = original.model_dump(mode="json")
    value = "1" if field == "chain_id" else "0x" + "ff" * (20 if field == "executor" else 32)
    for result in (body["agent_result"], body["agent_response"]["result"], body["agent_http"]["response"]["result"]):
        result[field] = value
    return body


@pytest.mark.parametrize("field,reason", [
    ("chain_id", "TX_WRONG_CHAIN"), ("executor", "TX_WRONG_EXECUTOR"),
    ("record_hash", "RECORD_HASH_MISMATCH"), ("tx_hash", "EVIDENCE_INCONSISTENT"),
])
@pytest.mark.parametrize("version", ["3", "4", "5"])
def test_write_response_fields_are_checked_only_by_new_version(completed_write, field, reason, version):
    body = changed_write_response(completed_write, field)
    body["rule_version"] = version
    result = verify_record(RecordVerificationInput.model_validate(body), (uuid4(),))
    assert all(assertion.rule_version == version for assertion in result.assertions)
    if version == "3":
        assert result.outcome == "PASS" and not result.critical_conflict
        assert not any(item.rule_id.startswith("agent.result.") for item in result.assertions)
    else:
        assert result.outcome == ("UNKNOWN" if field == "tx_hash" else "FAIL")
        assert result.reason_code == reason
        assert result.critical_conflict == (field != "tx_hash")
        assert result.task_link.verified_tx_hash is None


@pytest.mark.parametrize("issue", ["rpc", "noncanonical", "not_final", "malformed_tx", "malformed_logs", "logs_object", "logs_text", "missing_topics", "missing_http"])
def test_wrong_write_response_needs_valid_platform_evidence(completed_write, issue):
    body = changed_write_response(completed_write, "record_hash")
    rpc = body["evm"]["results"]
    if issue == "rpc":
        body["evm"].update(results={}, error_reason="PLATFORM_RPC_ERROR")
    elif issue == "noncanonical":
        rpc["receipt_canonical"]["hash"] = "0x" + "ff" * 32
    elif issue == "not_final":
        body["slot"]["expected"]["confirmation_depth"] = 2
    elif issue == "malformed_tx":
        rpc["transaction"].pop("chainId")
    elif issue == "malformed_logs":
        rpc["receipt"]["logs"] = [None]
    elif issue in {"logs_object", "logs_text"}:
        rpc["receipt"]["logs"] = {} if issue == "logs_object" else ""
    elif issue == "missing_topics":
        rpc["receipt"]["logs"] = [{"malformed": True}]
    else:
        body["agent_http"] = None
    result = verify_record(RecordVerificationInput.model_validate(body), (uuid4(),))
    assert result.outcome == "UNKNOWN" and not result.critical_conflict
    assert not any(item.critical and item.outcome == "FAIL" for item in result.assertions)


def test_failed_reverted_write_remains_ordinary_failure(completed_write):
    body = changed_write_response(completed_write, "record_hash")
    body["agent_task_status"] = "failed"
    body["agent_response"].update(task_status="failed", reason_code="AGENT_TASK_FAILED")
    body["agent_http"]["response"] = deepcopy(body["agent_response"])
    body["evm"]["results"]["receipt"]["status"] = "0x0"
    result = verify_record(RecordVerificationInput.model_validate(body), (uuid4(),))
    assert result.outcome == "FAIL" and result.reason_code == "TX_REVERTED"
    assert not result.critical_conflict
    assert not any(item.rule_id.startswith("agent.result.hash") for item in result.assertions)


def test_write_reconcile_without_returned_result_keeps_chain_judgement(completed_write):
    body = completed_write.model_dump(mode="json")
    body.update(agent_http=None, initial_agent_http=None, agent_response=None,
                agent_result=None, agent_task_status=None, execution_reason=None)
    result = verify_record(RecordVerificationInput.model_validate(body), (uuid4(),))
    assert result.outcome == "PASS" and result.task_link.verified_tx_hash == body["evm"]["candidate_tx_hash"]
    assert not any(item.rule_id.startswith("agent.result.") for item in result.assertions)
