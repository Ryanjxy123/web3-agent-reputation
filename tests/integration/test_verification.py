"""Actual A/D RPC evidence and independent pure replay, with explicit rule perturbations."""

import asyncio
import copy
import secrets
import socket
from uuid import uuid4

import pytest
from reputation_core.models import EvidenceRecord, RecordVerificationInput
from reputation_core.record_verifier import verify_record
from reputation_platform.adapters.evm.collector import collect_task
from reputation_platform.application.execution import ExecutionService
from reputation_platform.application.local_deploy import SetupJournal, contract_abi
from reputation_platform.application.verification import VerificationService
from reputation_platform.infrastructure.db.tables import evidence_blobs
from reputation_platform.worker.main import Worker
from sqlalchemy import select
from web3 import Web3

from tests.integration.test_execution import create, flow, identity_chain, prepared
from tests.integration.test_fixture_agents import anvil_node

__all__ = ["flow", "identity_chain", "prepared"]
pytestmark = [pytest.mark.chain, pytest.mark.postgres]


def complete(prepared, existing=None):
    flow, _, _ = prepared
    run_id, plan = existing or create(prepared)
    verifier = VerificationService(flow[1].db, flow[1])
    worker = Worker(
        flow[1].db,
        {"evaluate": ExecutionService(flow[1].db, flow[1]).execute, "verify": verifier.verify},
    )
    assert asyncio.run(worker.run_once())
    assert asyncio.run(worker.run_once())
    result = verifier.result(run_id)
    response = flow[0].get(f"/api/v1/evaluations/{run_id}/verification")
    assert response.status_code == 200 and response.json() == result.model_dump(mode="json")
    record_id = result.assertions[0].evidence_refs[0]
    with flow[1].db.connect() as connection:
        record = EvidenceRecord.model_validate(
            connection.execute(
                select(evidence_blobs.c.body).where(evidence_blobs.c.id == record_id)
            ).scalar_one()
        )
    inputs = RecordVerificationInput.model_validate_json(flow[1].evidence.read(record))
    assert verify_record(inputs, (record_id,)) == result
    return result, inputs, record_id


def test_real_a_passes_only_after_independent_rpc_and_binding_checks(prepared):
    result, inputs, _ = complete(prepared)
    assert result.outcome == "PASS", [
        (item.rule_id, item.outcome, item.reason_code) for item in result.assertions
    ]
    assert all(item.outcome == "PASS" for item in result.assertions)
    assert result.task_link.verified_tx_hash == inputs.evm.candidate_tx_hash
    assert not result.critical_conflict


@pytest.mark.parametrize("prepared", ["d"], indirect=True)
def test_real_d_receipt_success_does_not_complete_current_task(prepared):
    result, inputs, _ = complete(prepared)
    assert inputs.evm.results["receipt"]["status"] == "0x1"
    assert result.outcome == "FAIL" and result.reason_code == "TASK_ID_MISMATCH"
    assert result.critical_conflict and result.task_link.verified_tx_hash is None
    failures = {item.reason_code for item in result.assertions if item.outcome == "FAIL"}
    assert "TASK_ID_MISMATCH" in failures and "RECORD_HASH_MISMATCH" in failures
    assert (
        next(item for item in result.assertions if item.rule_id == "receipt.success").outcome
        == "PASS"
    )


def test_saved_real_evidence_replay_detects_field_mutations_without_io(prepared):
    _, original, identifier = complete(prepared)
    # These are deterministic rule tests over captured evidence, not new chain transactions.
    mutations = [
        ("executor", "TX_WRONG_EXECUTOR"),
        ("target", "TX_WRONG_TARGET"),
        ("emitter", "LOG_EMITTER_MISMATCH"),
        ("hash", "RECORD_HASH_MISMATCH"),
        ("request", "TASK_ID_MISMATCH"),
        ("chain", "TX_WRONG_CHAIN"),
    ]
    for mutation, reason in mutations:
        changed = copy.deepcopy(original.model_dump(mode="json"))
        rpc = changed["evm"]["results"]
        if mutation in {"executor", "target"}:
            rpc["transaction"]["from" if mutation == "executor" else "to"] = "0x" + "11" * 20
        elif mutation == "emitter":
            rpc["receipt"]["logs"][0]["address"] = "0x" + "11" * 20
        elif mutation == "hash":
            rpc["receipt"]["logs"][0]["data"] = "0x" + "11" * 32
        elif mutation == "request":
            rpc["receipt"]["logs"][0]["topics"][2] = "0x" + "11" * 32
        else:
            rpc["transaction"]["chainId"] = "0x1"
        result = verify_record(RecordVerificationInput.model_validate(changed), (identifier,))
        assert result.outcome == "FAIL", mutation
        assert reason in {item.reason_code for item in result.assertions if item.outcome == "FAIL"}


def test_missing_receipt_reorg_and_changed_chain_are_unknown(prepared):
    _, original, identifier = complete(prepared)
    for mutation, expected in [
        ("receipt", "RPC_RECEIPT_NOT_FOUND"),
        ("canonical", "PENDING_FINALITY"),
        ("instance", "CHAIN_INSTANCE_CHANGED"),
    ]:
        changed = copy.deepcopy(original.model_dump(mode="json"))
        rpc = changed["evm"]["results"]
        if mutation == "receipt":
            rpc["receipt"] = None
        elif mutation == "canonical":
            rpc["receipt_canonical"]["hash"] = "0x" + "11" * 32
        else:
            rpc["deployment_instance"] = "0x" + "11" * 32
        result = verify_record(RecordVerificationInput.model_validate(changed), (identifier,))
        assert result.outcome == "UNKNOWN", mutation
        assert expected in {item.reason_code for item in result.assertions}
        assert result.task_link.verified_tx_hash is None
    empty = original.model_copy(
        update={
            "evm": original.evm.model_copy(
                update={"results": {}, "error_reason": "PLATFORM_RPC_ERROR"}
            )
        }
    )
    assert verify_record(empty, (uuid4(),)).outcome == "UNKNOWN"
    foreign_platform = original.model_copy(update={"platform_instance_id": "0x" + "12" * 32})
    rejected = verify_record(foreign_platform, (identifier,))
    assert rejected.outcome == "UNKNOWN" and rejected.reason_code == "BINDING_UNVERIFIED"


def test_real_wrong_executor_and_target_transactions_fail(prepared):
    flow, _, _ = prepared
    _, original, identifier = complete(prepared)
    _, identity, _, keys, web3, deployment, runtime = flow
    record = web3.eth.contract(
        address=Web3.to_checksum_address(deployment.record.address),
        abi=contract_abi(identity.root, "DemoRecordRegistry"),
    )
    registry = web3.eth.contract(
        address=Web3.to_checksum_address(deployment.registry.address),
        abi=contract_abi(identity.root, "DemoAgentRegistry"),
    )
    journal = SetupJournal(runtime / "negative-transactions.sqlite3", web3)
    for name, key, operation, reason in [
        (
            "wrong-executor",
            keys["executor-d"],
            record.functions.anchorRecord(
                original.slot.task.request_id, original.slot.task.record_hash
            ),
            "TX_WRONG_EXECUTOR",
        ),
        (
            "wrong-target",
            keys["executor-a"],
            registry.functions.register("data:application/json;base64,e30="),
            "TX_WRONG_TARGET",
        ),
    ]:
        receipt = journal.transact(name, key, operation)
        assert receipt["status"] == 1
        evidence = collect_task(
            deployment,
            original.slot,
            receipt["transactionHash"].to_0x_hex(),
            original.registry_witness.snapshot_core.read_block_number,
        )
        result = verify_record(original.model_copy(update={"evm": evidence}), (identifier,))
        assert result.outcome == "FAIL"
        assert reason in {item.reason_code for item in result.assertions if item.outcome == "FAIL"}


def test_real_matching_record_before_dispatch_is_not_current_execution(prepared):
    flow, _, _ = prepared
    run_id, plan = create(prepared)
    _, identity, _, keys, web3, deployment, runtime = flow
    record = web3.eth.contract(
        address=Web3.to_checksum_address(deployment.record.address),
        abi=contract_abi(identity.root, "DemoRecordRegistry"),
    )
    task = plan.slots[0].task
    receipt = SetupJournal(runtime / "early-record.sqlite3", web3).transact(
        "early",
        keys["executor-a"],
        record.functions.anchorRecord(task.request_id, task.record_hash),
    )
    result, inputs, identifier = complete(prepared, (run_id, plan))
    # The normal Agent returns its own duplicate transaction, which really reverts.
    assert result.outcome == "FAIL" and inputs.evm.results["receipt"]["status"] == "0x0"
    assert (
        next(item for item in result.assertions if item.rule_id == "receipt.success").reason_code
        == "TX_REVERTED"
    )
    # Independently collect the successful pre-existing candidate: matching fields alone are insufficient.
    early = collect_task(
        deployment,
        inputs.slot,
        receipt["transactionHash"].to_0x_hex(),
        inputs.registry_witness.snapshot_core.read_block_number,
    )
    assert early.results["receipt"]["status"] == "0x1"
    result = verify_record(inputs.model_copy(update={"evm": early}), (identifier,))
    rules = {item.rule_id: item for item in result.assertions}
    assert rules["record.request"].outcome == rules["record.hash"].outcome == "PASS"
    assert rules["record.window"].outcome == "FAIL"
    assert rules["record.window"].reason_code == "SEMANTIC_MISMATCH"
    assert result.outcome == "FAIL" and result.task_link.verified_tx_hash is None


def test_real_missing_transaction_and_other_anvil_are_unknown(prepared):
    flow, _, _ = prepared
    _, original, identifier = complete(prepared)
    dispatch_block = original.registry_witness.snapshot_core.read_block_number
    missing = collect_task(flow[5], original.slot, "0x" + secrets.token_hex(32), dispatch_block)
    assert missing.results["transaction"] is None and missing.results["receipt"] is None
    result = verify_record(original.model_copy(update={"evm": missing}), (identifier,))
    assert result.outcome == "UNKNOWN" and result.reason_code == "RPC_RECEIPT_NOT_FOUND"
    with anvil_node() as (url, _):
        changed = collect_task(
            flow[5].model_copy(update={"rpc_url": url}),
            original.slot,
            original.evm.candidate_tx_hash,
            dispatch_block,
        )
    result = verify_record(original.model_copy(update={"evm": changed}), (identifier,))
    assert result.outcome == "UNKNOWN" and result.reason_code == "CHAIN_INSTANCE_CHANGED"
    # An actual refused local connection, not a fabricated JSON-RPC error payload.
    with socket.socket() as unavailable:
        unavailable.bind(("127.0.0.1", 0))
        url = f"http://127.0.0.1:{unavailable.getsockname()[1]}"
        failed = collect_task(
            flow[5].model_copy(update={"rpc_url": url}),
            original.slot,
            original.evm.candidate_tx_hash,
            dispatch_block,
        )
    assert failed.error_reason == "PLATFORM_RPC_ERROR"
    result = verify_record(original.model_copy(update={"evm": failed}), (identifier,))
    assert result.outcome == "UNKNOWN" and result.reason_code == "PLATFORM_RPC_ERROR"
