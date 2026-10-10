"""Independent rule-6 RPC expectations and byte-for-byte rule-5 replay commitments."""

from copy import deepcopy
from uuid import UUID

import pytest
from reputation_core.evidence import hash_json
from reputation_core.models import RecordVerificationInput
from reputation_core.record_verifier import preserve_rpc_unknown, verify_record
from reputation_core.reporting import build_report

from tests.unit.test_evidence_assessment import high_score_critical_arguments
from tests.unit.test_task_outcomes import task_input

EVIDENCE_ID = UUID("00000000-0000-4000-8000-000000000004")
OTHER_HASH = "0x" + "ff" * 32
MISSING = "__missing__"


@pytest.fixture(scope="module")
def write_body():
    body = high_score_critical_arguments()["inputs"][-2].model_dump(mode="json")
    body["rule_version"] = "5"
    body["slot"]["slot_id"] = "00000000-0000-4000-8000-000000000001"
    body["slot"]["grant_id"] = body["grant"]["grant_id"] = "00000000-0000-4000-8000-000000000002"
    body["slot"]["expected"]["binding_id"] = body["binding"]["binding_id"] = (
        "00000000-0000-4000-8000-000000000003"
    )
    return body


def changed_body(original, path, value, version="6"):
    body = deepcopy(original)
    body["rule_version"] = version
    parent = body["evm"]["results"]
    for field in path[:-1]:
        parent = parent[field]
    if path:
        if value == MISSING:
            parent.pop(path[-1])
        else:
            parent[path[-1]] = value
    return body


def replay(body):
    inputs = RecordVerificationInput.model_validate(body)
    return inputs, verify_record(inputs, (EVIDENCE_ID,))


@pytest.mark.parametrize("path,value", [
    (("chain_id",), True),
    (("chain_id",), "0x07a69"),
    (("genesis", "hash"), True),
    (("deployment_instance",), "0x"),
    (("registry_code",), {}),
    (("record_code",), []),
    (("head", "number"), True),
    (("head", "hash"), True),
    (("pre_dispatch_block", "number"), True),
    (("dispatch_block", "hash"), True),
    (("transaction", "chainId"), MISSING),
    (("transaction", "chainId"), True),
    (("transaction", "from"), MISSING),
    (("transaction", "from"), True),
    (("transaction", "to"), MISSING),
    (("transaction", "to"), True),
    (("transaction", "input"), MISSING),
    (("transaction", "input"), {}),
    (("transaction", "blockNumber"), "0x02"),
    (("transaction", "transactionIndex"), True),
    (("receipt", "status"), MISSING),
    (("receipt", "status"), True),
    (("receipt", "status"), "0x2"),
    (("receipt", "transactionHash"), True),
    (("receipt", "blockHash"), MISSING),
    (("receipt", "blockNumber"), 2),
    (("receipt", "transactionIndex"), []),
    (("receipt", "logs"), None),
    (("receipt_block", "timestamp"), MISSING),
    (("receipt_block", "timestamp"), True),
    (("receipt_block", "number"), {}),
    (("receipt_canonical", "hash"), True),
])
def test_rule6_malformed_rpc_is_platform_unknown_before_business_judgement(write_body, path, value):
    inputs, result = replay(changed_body(write_body, path, value))
    assert result.outcome == "UNKNOWN" and result.reason_code == "PLATFORM_RPC_ERROR"
    assert not result.critical_conflict and result.task_link.verified_tx_hash is None
    assert not any(item.outcome == "FAIL" for item in result.assertions)
    assert preserve_rpc_unknown(inputs, result)


@pytest.mark.parametrize("path,value", [
    (("transaction", "hash"), OTHER_HASH),
    (("transaction", "chainId"), "0x1"),
    (("receipt", "transactionHash"), OTHER_HASH),
    (("transaction", "blockHash"), OTHER_HASH),
    (("transaction", "blockNumber"), "0x99"),
    (("receipt", "blockNumber"), "0x99"),
    (("receipt", "transactionIndex"), "0x99"),
    (("receipt_block", "hash"), OTHER_HASH),
    (("receipt_block", "number"), "0x99"),
    (("receipt_canonical", "number"), "0x99"),
    (("head", "hash"), OTHER_HASH),
])
def test_rule6_mutually_inconsistent_rpc_locations_are_recoverable_evidence_gaps(
    write_body, path, value,
):
    inputs, result = replay(changed_body(write_body, path, value))
    assert result.outcome == "UNKNOWN" and result.reason_code == "EVIDENCE_INCONSISTENT"
    assert not result.critical_conflict and result.task_link.verified_tx_hash is None
    evidence = next(item for item in result.assertions if item.rule_id == "receipt.evidence")
    assert evidence.outcome == "UNKNOWN" and evidence.expected is not None
    assert preserve_rpc_unknown(inputs, result)


@pytest.mark.parametrize("issue", ["canonical_fork", "insufficient_confirmations"])
def test_rule6_genuine_finality_uncertainty_is_not_a_malformed_rpc_gap(write_body, issue):
    body = changed_body(write_body, (), None)
    if issue == "canonical_fork":
        body["evm"]["results"]["receipt_canonical"]["hash"] = OTHER_HASH
    else:
        body["slot"]["expected"]["confirmation_depth"] = 2
    inputs, result = replay(body)
    assert result.outcome == "UNKNOWN" and result.reason_code == "PENDING_FINALITY"
    assert not result.critical_conflict and not preserve_rpc_unknown(inputs, result)


@pytest.mark.parametrize("field", ["pre_dispatch_block", "dispatch_block"])
def test_rule6_fixed_height_rpc_response_cannot_keep_a_different_number(write_body, field):
    inputs, result = replay(changed_body(write_body, (field, "number"), "0x99"))
    assert result.outcome == "UNKNOWN" and result.reason_code == "EVIDENCE_INCONSISTENT"
    assert not result.critical_conflict and preserve_rpc_unknown(inputs, result)


@pytest.mark.parametrize("field,value,reason", [
    ("from", "0x" + "ff" * 20, "TX_WRONG_EXECUTOR"),
    ("to", "0x" + "ff" * 20, "TX_WRONG_TARGET"),
    ("to", None, "TX_WRONG_TARGET"),
    ("input", "0x", "SEMANTIC_MISMATCH"),
])
def test_rule6_well_formed_wrong_business_transaction_still_confirms_critical_failure(
    write_body, field, value, reason,
):
    _, result = replay(changed_body(write_body, ("transaction", field), value))
    assert result.outcome == "FAIL" and result.reason_code == reason and result.critical_conflict
    assert any(item.outcome == "FAIL" and item.critical for item in result.assertions)


@pytest.mark.parametrize("path,value", [
    (("receipt", "status"), MISSING),
    (("receipt", "transactionHash"), OTHER_HASH),
    (("head", "hash"), True),
])
def test_rule6_rpc_gap_cannot_confirm_agent_returned_wrong_digest(write_body, path, value):
    body = changed_body(write_body, path, value)
    for response in (body["agent_result"], body["agent_response"]["result"],
                     body["agent_http"]["response"]["result"]):
        response["record_hash"] = OTHER_HASH
    _, result = replay(body)
    assert result.outcome == "UNKNOWN" and not result.critical_conflict
    assert not any(item.outcome == "FAIL" and item.critical for item in result.assertions)


@pytest.mark.parametrize("path,value,reason", [
    (("receipt", "status"), MISSING, "PLATFORM_RPC_ERROR"),
    (("receipt", "status"), True, "PLATFORM_RPC_ERROR"),
    (("receipt", "status"), "0x2", "PLATFORM_RPC_ERROR"),
    (("receipt", "transactionHash"), OTHER_HASH, "EVIDENCE_INCONSISTENT"),
    (("transaction", "blockNumber"), "0x99", "EVIDENCE_INCONSISTENT"),
    (("receipt_block", "hash"), OTHER_HASH, "EVIDENCE_INCONSISTENT"),
    (("transaction", "chainId"), "0x1", "EVIDENCE_INCONSISTENT"),
    (("head", "hash"), True, "PLATFORM_RPC_ERROR"),
])
def test_rule6_status_query_checks_rpc_without_requiring_write_fields(path, value, reason):
    body = task_input()
    body["slot"]["required_class"] = "success"
    inputs, result = replay(changed_body(body, path, value))
    assert result.outcome == "UNKNOWN" and result.reason_code == reason
    assert not result.critical_conflict and preserve_rpc_unknown(inputs, result)


def test_rule6_status_query_accepts_its_minimum_relevant_rpc_fields():
    body = task_input()
    body["slot"]["required_class"] = "success"
    _, result = replay(changed_body(body, (), None))
    assert result.outcome == "PASS" and not result.critical_conflict


@pytest.mark.parametrize("partial", [False, True])
def test_rule6_confirmed_risk_survives_high_scores_and_partial_reports(partial):
    arguments = high_score_critical_arguments()
    arguments["inputs"] = tuple(
        item.model_copy(update={"rule_version": "6"}) for item in arguments["inputs"]
    )
    if partial:
        arguments["inputs"] = arguments["inputs"][19:]
        arguments["evidence_id"] = arguments["evidence_id"][19:]
        retained = {item.slot.slot_id for item in arguments["inputs"]}
        arguments["observations"] = tuple(
            item for item in arguments["observations"] if item.slot_id in retained
        )
    arguments["plan"] = arguments["plan"].model_copy(update={
        "template_version": "capabilities@6",
        "slots": tuple(item.slot for item in arguments["inputs"]),
    })
    report = build_report(**arguments, report_schema_version="1.5.0")
    assert report.scores.evaluation_state == ("PARTIAL" if partial else "COMPLETE")
    assert report.scores.overall_score_bp == (None if partial else 9480)
    if not partial:
        assert report.scores.dimensions["availability"].score_bp == 9800
        assert report.scores.dimensions["consistency"].score_bp == 9600
        assert report.scores.dimensions["behavior"].score_bp == 9000
    assert report.scores.advice == "NOT_RECOMMENDED" and report.scores.critical_conflict
    assert report.evidence_sufficiency.overall_allowed == (not partial)
    assert report.risk_assessment.conclusion == "CONFIRMED_CRITICAL_CONFLICT"
    finding, = report.risk_assessment.critical_findings
    assert finding.rule_id == "record.hash" and finding.reason_code == "RECORD_HASH_MISMATCH"
    assert finding.evidence_refs


# These commitments were captured from main 68ee882 before rule 6 existed.
# They protect all old assertion fields, identifiers, task-link fields and reason priority.
@pytest.mark.parametrize("path,value,commitment", [
    ((), None, "0x27905f94cc80e3906d3dbccd8ebb04c93876a4dd8604117d28a7fd0ff9b3823e"),
    (("receipt", "status"), MISSING, "0x86b6cf7a42f875f0ded06b8571bf6b496f43937506ce425ca12a5208fea78e1f"),
    (("receipt", "status"), "0x2", "0x491b4b04ec56fe82176f7f3f2b27ae2ca5b0802cee509bf1c2f6237b4f70d6f1"),
    (("receipt", "transactionHash"), OTHER_HASH, "0x491b4b04ec56fe82176f7f3f2b27ae2ca5b0802cee509bf1c2f6237b4f70d6f1"),
    (("receipt", "blockNumber"), "0x99", "0x491b4b04ec56fe82176f7f3f2b27ae2ca5b0802cee509bf1c2f6237b4f70d6f1"),
    (("receipt", "transactionIndex"), "0x99", "0x491b4b04ec56fe82176f7f3f2b27ae2ca5b0802cee509bf1c2f6237b4f70d6f1"),
    (("receipt_block", "hash"), OTHER_HASH, "0x491b4b04ec56fe82176f7f3f2b27ae2ca5b0802cee509bf1c2f6237b4f70d6f1"),
    (("receipt_block", "number"), "0x99", "0x491b4b04ec56fe82176f7f3f2b27ae2ca5b0802cee509bf1c2f6237b4f70d6f1"),
    (("transaction", "from"), True, "0x475b4ea5dd2f0fbe206434a3f1cc731977afd9ee94ac0e4dd77ec5d10244dc29"),
    (("transaction", "to"), None, "0x80642fe216c8e571be9d301c095f0b75741634ea367f3c0149a0cf8c220a8c76"),
    (("transaction", "input"), {}, "0x079c5df993cfb89395213771a3d88ddc5cd2c8212615291033bbce4769ce4c9a"),
    (("head", "number"), True, "0x86b6cf7a42f875f0ded06b8571bf6b496f43937506ce425ca12a5208fea78e1f"),
    (("receipt_block", "timestamp"), MISSING, "0xb78df8392f6ac1c6087020c20912c0f84d0f5730105ef111bfa4c59302c2f1aa"),
    (("head", "hash"), True, "0x27905f94cc80e3906d3dbccd8ebb04c93876a4dd8604117d28a7fd0ff9b3823e"),
    (("deployment_instance",), "0x", "0xd01c9361fc7a1bb0a24327001566cace94ef040fd479e559ed39399c6506cba8"),
    (("receipt_canonical", "hash"), OTHER_HASH, "0x491b4b04ec56fe82176f7f3f2b27ae2ca5b0802cee509bf1c2f6237b4f70d6f1"),
])
def test_rule5_keeps_its_complete_historical_replay(write_body, path, value, commitment):
    _, result = replay(changed_body(write_body, path, value, version="5"))
    assert hash_json(result.model_dump(mode="json")) == commitment
