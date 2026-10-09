"""Frozen RPC unit cases; real HTTP/PostgreSQL/Anvil cases live in integration tests."""

from uuid import uuid4

import pytest
from reputation_core.evidence import hash_bytes, hash_json
from reputation_core.models import RecordVerificationInput, TaskEnvelope
from reputation_core.record_verifier import verify_record

from tests.factories import ADDRESS, DEADLINE, HASH, NOW, ZERO, agent, slot


def read_input(capability="get_tx_status", status="NOT_FOUND", exists=False):
    code = "0x6000"
    chain = {
        "chain_id": "31337",
        "genesis_hash": ZERO,
        "deployment_instance_id": HASH,
        "registry_code_hash": hash_bytes(bytes.fromhex(code[2:])),
    }
    chain["instance_hash"] = hash_json(chain)
    endpoint = {
        "endpoint_id": "local",
        "scheme": "http",
        "host": "127.0.0.1",
        "port": 19101,
        "path": "/tasks",
        "method": "POST",
        "protocol": "controlled-http-v1",
    }
    core = {
        "agent_ref": agent().model_dump(mode="json"),
        "source_type": "controlled",
        "owner": ADDRESS,
        "declared_executor": None,
        "agent_uri": "data:fixture",
        "registry_revision": 1,
        "metadata_hash": HASH,
        "normalized_metadata": {},
        "endpoints": [endpoint],
        "read_block_number": "1",
        "read_block_hash": HASH,
        "captured_at": NOW,
        "registry_chain": chain,
        "schema_version": "1.0.0",
    }
    snapshot_hash = hash_json(core)
    body = slot().model_dump(mode="json")
    body.update(capability_id=capability, synthetic_input=None)
    body["task"].update(
        capability_id=capability,
        snapshot_hash=snapshot_hash,
        chain_instance_id=chain["instance_hash"],
        read_block_number="1",
        read_block_hash=HASH,
    )
    if capability == "get_tx_status":
        body["task"].update(target_contract=None, record_hash=None, query_tx_hash=HASH)
    else:
        body["task"].update(record_executor=ADDRESS, record_request_id=HASH)
    body["expected"].update(
        snapshot_hash=snapshot_hash,
        execution_chain=chain,
        target_contract=body["task"]["target_contract"],
        record_hash=body["task"]["record_hash"],
        binding_id=None,
        target_code_hash=hash_bytes(bytes.fromhex(code[2:])),
        pre_dispatch_block="1",
        pre_dispatch_block_hash=HASH,
    )
    block = {"number": "0x1", "hash": HASH, "timestamp": "0x0"}
    rpc = {
        "chain_id": "0x7a69",
        "genesis": {"hash": ZERO},
        "head": block,
        "registry_code": code,
        "deployment_instance": HASH,
        "record_code": code,
        "pre_dispatch_block": block,
        "dispatch_block": block,
        "read_block": block,
        "read_canonical": block,
    }
    result = {
        "capability_id": capability,
        "chain_id": "31337",
        "read_block_number": "1",
        "read_block_hash": HASH,
    }
    if capability == "get_tx_status":
        result.update(tx_hash=HASH, tx_status=status)
        rpc.update(transaction=None, receipt=None)
        if status != "NOT_FOUND":
            rpc["transaction"] = {
                "hash": HASH,
                "blockHash": None,
                "blockNumber": None,
                "chainId": "0x7a69",
            }
        if status in {"SUCCESS", "REVERTED"}:
            rpc["transaction"].update(blockHash=HASH, blockNumber="0x1")
            rpc.update(
                receipt={
                    "transactionHash": HASH,
                    "blockHash": HASH,
                    "blockNumber": "0x1",
                    "status": "0x1" if status == "SUCCESS" else "0x0",
                },
                receipt_block=block,
                receipt_canonical=block,
            )
    else:
        actual_hash = HASH if exists else ZERO
        result.update(
            record_exists=exists,
            record_matches=exists,
            record_hash=actual_hash,
            record_executor=ADDRESS,
            record_request_id=HASH,
        )
        rpc["record_call"] = "0x" + str(int(exists)).rjust(64, "0") + actual_hash[2:]
    body["task"] = TaskEnvelope.model_validate(body["task"]).model_dump(mode="json")
    return RecordVerificationInput.model_validate(
        {
            "slot": body,
            "snapshot": {"snapshot_id": str(uuid4()), "core": core, "snapshot_hash": snapshot_hash},
            "review": {
                "snapshot_hash": snapshot_hash,
                "review_version": 1,
                "confirmed_claims": [capability],
                "mapping_evidence_ids": [],
                "actor": "operator",
                "reason": "fixture",
            },
            "review_version": 1,
            "platform_instance_id": HASH,
            "binding": None,
            "grant": {
                "grant_id": body["grant_id"],
                "snapshot_hash": snapshot_hash,
                "endpoint_ids": ["local"],
                "capabilities": [capability],
                "methods": ["POST", "GET"],
                "paths": ["/tasks", "/tasks/{request_id}"],
                "chain_instances": [chain["instance_hash"]],
                "contract_allowlist": [] if capability == "get_tx_status" else [ADDRESS],
                "max_tasks": 1,
                "interval_ms": 1000,
                "expires_at": DEADLINE,
                "operator": "operator",
                "consent_ref": "fixture",
            },
            "intent_persisted_at": NOW,
            "dispatch_started_at": NOW,
            "dispatch_payload_hash": hash_json(body["task"]),
            "registry_witness": {
                "snapshot_core": core,
                "owner_code": "0x",
                "executor_code": "0x",
                "read_method": "eth_call_at_block_number",
            },
            "execution_reason": None,
            "agent_result": result,
            "agent_task_status": "succeeded",
            "agent_response": {
                "request_id": body["task"]["request_id"],
                "task_status": "succeeded",
                "status_path": "/tasks/" + body["task"]["request_id"],
                "result": result,
            },
            "evm": {
                "candidate_tx_hash": HASH if capability == "get_tx_status" else None,
                "observed_at": NOW,
                "results": rpc,
            },
        }
    )


def decide(data):
    # Hash the parsed wire, exactly as the Worker persists its frozen dispatch.
    data = data.model_copy(
        update={"dispatch_payload_hash": hash_json(data.slot.task.model_dump(mode="json"))}
    )
    return verify_record(data, (uuid4(),))


@pytest.mark.parametrize("status", ["SUCCESS", "REVERTED", "PENDING"])
def test_transaction_queries_check_results_not_transaction_success(status):
    result = decide(read_input(status=status))
    assert result.outcome == "PASS"
    assert result.task_link.verified_tx_hash == (
        HASH if status in {"SUCCESS", "REVERTED"} else None
    )


def test_unseen_transaction_is_unknown_regardless_of_agent_claim():
    for status in ("PENDING", "NOT_FOUND"):
        data = read_input(status="NOT_FOUND")
        changed = data.agent_result.model_copy(update={"tx_status": status})
        raw = {**data.agent_response, "result": changed.model_dump(mode="json")}
        assert (
            decide(data.model_copy(update={"agent_result": changed, "agent_response": raw})).outcome
            == "UNKNOWN"
        )


def test_only_explicit_unmined_transaction_is_independently_pending():
    data = read_input(status="PENDING")
    rpc = {**data.evm.results, "transaction": {"hash": HASH}}
    assert (
        decide(
            data.model_copy(update={"evm": data.evm.model_copy(update={"results": rpc})})
        ).outcome
        == "UNKNOWN"
    )


@pytest.mark.parametrize("exists", [True, False])
def test_record_queries_accept_truthful_presence_or_absence(exists):
    result = decide(read_input("verify_record", exists=exists))
    assert result.outcome == "PASS" and result.task_link.verified_tx_hash is None


def test_rpc_hash_conflict_is_unknown_while_agent_query_hash_conflict_fails():
    data = read_input(status="SUCCESS")
    rpc = {**data.evm.results, "transaction": {**data.evm.results["transaction"], "hash": ZERO}}
    assert (
        decide(
            data.model_copy(update={"evm": data.evm.model_copy(update={"results": rpc})})
        ).outcome
        == "UNKNOWN"
    )
    wrong = data.agent_result.model_copy(update={"tx_hash": ZERO})
    raw = {**data.agent_response, "result": wrong.model_dump(mode="json")}
    assert (
        decide(data.model_copy(update={"agent_result": wrong, "agent_response": raw})).outcome
        == "FAIL"
    )


@pytest.mark.parametrize("capability", ["get_tx_status", "verify_record"])
def test_false_query_output_fails_but_rpc_failure_is_unknown(capability):
    data = read_input(capability, status="SUCCESS")
    wrong = data.agent_result.model_copy(
        update={"tx_status": "REVERTED"}
        if capability == "get_tx_status"
        else {"record_exists": True}
    )
    raw = {**data.agent_response, "result": wrong.model_dump(mode="json")}
    assert (
        decide(data.model_copy(update={"agent_result": wrong, "agent_response": raw})).outcome
        == "FAIL"
    )
    failed = data.evm.model_copy(update={"results": {}, "error_reason": "PLATFORM_RPC_ERROR"})
    assert decide(data.model_copy(update={"evm": failed})).outcome == "UNKNOWN"


def test_later_mining_cannot_rewrite_historical_query():
    data = read_input(status="SUCCESS")
    rpc = dict(data.evm.results)
    rpc["receipt"] = {**rpc["receipt"], "blockNumber": "0x2"}
    result = decide(data.model_copy(update={"evm": data.evm.model_copy(update={"results": rpc})}))
    assert result.outcome == "UNKNOWN" and result.task_link.verified_tx_hash is None


def test_query_reorg_and_malformed_rpc_are_unknown():
    for label, value in [
        ("read_canonical", {"number": "0x1", "hash": ZERO}),
        ("record_call", "0x02"),
    ]:
        data = read_input("verify_record", exists=True)
        rpc = {**data.evm.results, label: value}
        assert (
            decide(
                data.model_copy(update={"evm": data.evm.model_copy(update={"results": rpc})})
            ).outcome
            == "UNKNOWN"
        )
