"""Fixed-block RPC gaps preserve their original UNKNOWN without changing rule 5."""

from copy import deepcopy
from uuid import UUID

import pytest
from reputation_core.evidence import hash_json
from reputation_core.models import RecordVerificationInput
from reputation_core.record_verifier import preserve_rpc_unknown, verify_record

from tests.unit.test_task_outcomes import task_input

EVIDENCE = UUID("00000000-0000-4000-8000-000000000004")
OTHER_HASH = "0x" + "ff" * 32


def query_body(capability, version="6"):
    body = task_input(capability)
    body["rule_version"] = version
    body["slot"]["required_class"] = "match" if capability == "verify_record" else "success"
    body["slot"]["slot_id"] = "00000000-0000-4000-8000-000000000001"
    body["slot"]["grant_id"] = body["grant"]["grant_id"] = (
        "00000000-0000-4000-8000-000000000002"
    )
    return body


def changed(original, path, value):
    body = deepcopy(original)
    parent = body["evm"]["results"]
    for field in path[:-1]:
        parent = parent[field]
    if path:
        parent[path[-1]] = value
    return body


def replay(body):
    inputs = RecordVerificationInput.model_validate(body)
    return inputs, verify_record(inputs, (EVIDENCE,))


@pytest.mark.parametrize("capability", ["verify_record", "get_tx_status"])
@pytest.mark.parametrize("path,value,reason", [
    (("read_block",), None, "PLATFORM_RPC_ERROR"),
    (("read_block", "hash"), True, "PLATFORM_RPC_ERROR"),
    (("read_block", "number"), True, "PLATFORM_RPC_ERROR"),
    (("read_canonical",), None, "PLATFORM_RPC_ERROR"),
    (("read_canonical", "hash"), "0x", "PLATFORM_RPC_ERROR"),
    (("read_canonical", "number"), "0x01", "PLATFORM_RPC_ERROR"),
    (("read_block", "hash"), OTHER_HASH, "EVIDENCE_INCONSISTENT"),
    (("read_block", "number"), "0x99", "EVIDENCE_INCONSISTENT"),
    (("read_canonical", "number"), "0x99", "EVIDENCE_INCONSISTENT"),
])
def test_fixed_block_rpc_gap_is_observed_unknown_and_recovery_keeps_it(
    capability, path, value, reason,
):
    healthy = query_body(capability)
    inputs, result = replay(changed(healthy, path, value))
    assert result.outcome == "UNKNOWN" and result.reason_code == reason
    assert not result.critical_conflict and result.task_link.verified_tx_hash is None
    assert not any(item.outcome == "FAIL" for item in result.assertions)
    assertion = next(item for item in result.assertions if item.rule_id == "query.evidence")
    assert assertion.outcome == "UNKNOWN" and assertion.expected is not None
    assert assertion.observed is not None and assertion.evidence_refs == (EVIDENCE,)
    assert preserve_rpc_unknown(inputs, result)
    _, recovered = replay(healthy)
    assert recovered.outcome == "PASS" and not recovered.critical_conflict


@pytest.mark.parametrize("value", [
    None,
    True,
    "0x",
    "0x" + "01" * 65,
    "0x" + "0" * 63 + "2" + "ff" * 32,
    "0x" + "00" * 32 + "ff" * 32,
    "0x" + "0" * 63 + "1" + "00" * 32,
])
def test_invalid_get_record_abi_is_platform_unknown_with_a_recoverable_observation(value):
    inputs, result = replay(changed(query_body("verify_record"), ("record_call",), value))
    assert result.outcome == "UNKNOWN" and result.reason_code == "PLATFORM_RPC_ERROR"
    assert not result.critical_conflict and preserve_rpc_unknown(inputs, result)
    assert not any(item.outcome == "FAIL" for item in result.assertions)
    assertion = next(item for item in result.assertions if item.rule_id == "query.evidence")
    assert assertion.observed["record_call"] == value and assertion.expected is not None


@pytest.mark.parametrize("capability", ["verify_record", "get_tx_status"])
def test_canonical_query_fork_remains_stale_and_cannot_claim_rpc_recovery(capability):
    inputs, result = replay(changed(
        query_body(capability), ("read_canonical", "hash"), OTHER_HASH,
    ))
    assert result.outcome == "UNKNOWN" and result.reason_code == "STALE_EVIDENCE"
    assert not result.critical_conflict and not preserve_rpc_unknown(inputs, result)


def test_correct_abi_with_wrong_agent_record_output_remains_business_failure():
    body = query_body("verify_record")
    for response in (body["agent_result"], body["agent_response"]["result"],
                     body["agent_http"]["response"]["result"]):
        response["record_hash"] = OTHER_HASH
    inputs, result = replay(body)
    assert result.outcome == "FAIL" and result.reason_code == "RECORD_HASH_MISMATCH"
    assert not preserve_rpc_unknown(inputs, result)


@pytest.mark.parametrize("capability", ["verify_record", "get_tx_status"])
def test_missing_evidence_placeholder_cannot_enable_rpc_unknown_preservation(capability):
    body = query_body(capability)
    body["agent_http"] = None
    body["agent_result"] = None
    body["agent_response"] = None
    body["agent_task_status"] = None
    inputs, result = replay(body)
    assert result.outcome == "UNKNOWN" and not preserve_rpc_unknown(inputs, result)
    assert all(item.expected is None for item in result.assertions if item.rule_id == "query.evidence")


# Whole-result hashes captured from main 68ee882, before rule 6 existed.
@pytest.mark.parametrize("capability,path,value,commitment", [
    ("verify_record", (), None,
     "0xc35aedae583860d43012659e7e489af7d349d355fdb94814c4c8d3b26e32f88b"),
    ("get_tx_status", (), None,
     "0x0fe46f5f8cb048d501d1f9ed77fc082eec16b5512d9fb3a580b875333c2b9558"),
    ("verify_record", ("record_call",), "0x",
     "0xc0bcbd3d95d9af65771ff4c73c802381f7a984085a3724627943152f9e8b2faa"),
    ("verify_record", ("record_call",), "0x" + "0" * 63 + "2" + "ff" * 32,
     "0xc0bcbd3d95d9af65771ff4c73c802381f7a984085a3724627943152f9e8b2faa"),
    ("verify_record", ("read_block", "hash"), True,
     "0xe592429a85c6bbd618cd202529e2e9545234735d30d61594ff8da02d473e1cb8"),
    ("get_tx_status", ("read_canonical", "number"), "0x99",
     "0xebabb23c4c437ea8f2682eed935dce9685b288aff9c150554ed26c450ff8b31f"),
    ("verify_record", ("read_canonical", "hash"), OTHER_HASH,
     "0x494b0d389442847ec0d419a36312da9dd07948ad5e480d466a4fefb433ef2204"),
])
def test_rule5_fixed_block_and_abi_replay_remains_byte_for_byte(capability, path, value, commitment):
    _, result = replay(changed(query_body(capability, "5"), path, value))
    assert hash_json(result.model_dump(mode="json")) == commitment
