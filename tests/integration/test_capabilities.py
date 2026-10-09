"""Actual HTTP Agent reads with PostgreSQL plans and independent Anvil evidence."""

import asyncio
import copy
import json
import os
import secrets
import subprocess
import sys
import time
from datetime import UTC, datetime, timedelta
from uuid import UUID

import httpx
import pytest
from eth_account import Account
from reputation_core.models import EvidenceRecord, RecordVerificationInput
from reputation_core.record_verifier import verify_record
from reputation_platform.application.execution import ExecutionService
from reputation_platform.application.local_deploy import SetupJournal, contract_abi
from reputation_platform.application.reports import ReportService
from reputation_platform.application.verification import VerificationService
from reputation_platform.configuration import controlled_fixture_ports
from reputation_platform.infrastructure.db.tables import bindings, evidence_blobs, jobs, runs
from reputation_platform.worker.main import Worker
from sqlalchemy import func, select
from web3 import Web3
from web3.types import RPCEndpoint

from tests.integration.test_identity import AUTH, capture, flow, identity_chain, signed, verify

__all__ = ["flow", "identity_chain"]
pytestmark = [pytest.mark.chain, pytest.mark.postgres]


@pytest.fixture
def capability_prepared(flow, request):
    client, identity, samples, keys, web3, deployment, runtime = flow
    target = deployment.record.address
    if getattr(request, "param", "default") == "alternate":
        artifact = json.loads(
            (
                identity.root / "contracts/out/DemoRecordRegistry.sol/DemoRecordRegistry.json"
            ).read_bytes()
        )
        factory = web3.eth.contract(abi=artifact["abi"], bytecode=artifact["bytecode"]["object"])
        receipt = SetupJournal(runtime / "alternate.sqlite3", web3).transact(
            "deploy-alternate", keys["admin"], factory.constructor()
        )
        target = receipt["contractAddress"].lower()
    config = {
        "deployment": deployment.model_dump(mode="json"),
        "metadata": samples["a"]["metadata"],
        "private_key": keys["executor-a"],
        "mode": "normal",
        "replay_tx_hash": None,
        "registry_abi": contract_abi(identity.root, "DemoAgentRegistry"),
        "record_abi": contract_abi(identity.root, "DemoRecordRegistry"),
        "record_contract_allowlist": [target],
    }
    path = runtime / "query-agent.json"
    path.write_text(json.dumps(config), encoding="utf-8")
    port = controlled_fixture_ports()[0]
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "fixture_agents.service:create_app",
            "--factory",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--no-access-log",
        ],
        env={
            **{
                key: value
                for key, value in os.environ.items()
                if key not in {"DATABASE_URL", "OPERATOR_TOKEN"}
            },
            "FIXTURE_CONFIG": str(path),
        },
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        until = time.monotonic() + 90
        with httpx.Client(trust_env=False, timeout=1) as probe:
            while True:
                assert process.poll() is None, f"Agent could not start on {port}"
                try:
                    if probe.get(f"http://127.0.0.1:{port}/health").status_code == 200:
                        break
                except httpx.HTTPError:
                    pass
                assert time.monotonic() < until
                time.sleep(0.1)
        _, snapshot, _ = capture(flow)
        response = client.post(
            f"/api/v1/snapshots/{snapshot['snapshot_id']}/claims/confirm",
            headers=AUTH,
            json={
                "confirmed_claims": ["get_tx_status", "verify_record"],
                "reason": "Explicitly reviewed read capabilities",
                "expected_review_version": 0,
            },
        )
        assert response.status_code == 200, response.text
        grant = client.post(
            "/api/v1/access-grants",
            headers=AUTH,
            json={
                "snapshot_id": snapshot["snapshot_id"],
                "endpoint_id": "fixture-a",
                "max_tasks": 10,
                "capabilities": ["get_tx_status", "verify_record"],
                "contract_allowlist": [target],
                "expires_at": (datetime.now(UTC) + timedelta(hours=1))
                .isoformat(timespec="milliseconds")
                .replace("+00:00", "Z"),
                "consent_ref": "Read-only test authorization",
            },
        )
        assert grant.status_code == 201, grant.text
        body = {
            "snapshot_id": snapshot["snapshot_id"],
            "review_version": 1,
            "profile": "record-read-v1",
            "policy_version": "policy-v1",
            "grant_ids": [grant.json()["grant"]["grant_id"]],
            "suite_id": "capabilities-v1",
        }
        with identity.db.connect() as connection:
            assert connection.scalar(select(func.count()).select_from(bindings)) == 0
        yield flow, body, target
    finally:
        process.terminate()
        process.wait(timeout=15)


def run_read(prepared, capability, **parameters):
    flow, body, _ = prepared
    response = flow[0].post(
        "/api/v1/evaluations",
        headers={**AUTH, "Idempotency-Key": secrets.token_hex(16)},
        json={**body, "capability_id": capability, **parameters},
    )
    assert response.status_code == 202, response.text
    run_id = UUID(response.json()["run_id"])
    verifier = VerificationService(flow[1].db, flow[1])
    worker = Worker(
        flow[1].db,
        {"evaluate": ExecutionService(flow[1].db, flow[1]).execute, "verify": verifier.verify},
    )
    assert asyncio.run(worker.run_once())
    assert asyncio.run(worker.run_once())
    result = verifier.result(run_id)
    identifier = result.assertions[0].evidence_refs[0]
    with flow[1].db.connect() as connection:
        record = EvidenceRecord.model_validate(
            connection.execute(
                select(evidence_blobs.c.body).where(evidence_blobs.c.id == identifier)
            ).scalar_one()
        )
        plan = connection.execute(select(runs.c.plan).where(runs.c.id == run_id)).scalar_one()
        assert plan["slots"][0]["expected"]["binding_id"] is None
    inputs = RecordVerificationInput.model_validate_json(flow[1].evidence.read(record))
    assert verify_record(inputs, (identifier,)) == result
    return result, inputs, identifier


@pytest.mark.parametrize("state", ["SUCCESS", "REVERTED", "NOT_FOUND", "PENDING"])
def test_get_tx_status_queries_all_states_without_executor_binding_or_new_write(
    capability_prepared, state
):
    flow, _, _ = capability_prepared
    _, identity, samples, keys, web3, deployment, runtime = flow
    contract = web3.eth.contract(
        address=Web3.to_checksum_address(deployment.record.address),
        abi=contract_abi(identity.root, "DemoRecordRegistry"),
    )
    event = contract.events.RecordAnchored().get_logs(from_block=0)[0]
    tx_hash = event["transactionHash"].to_0x_hex()
    if state == "NOT_FOUND":
        tx_hash = "0x" + secrets.token_hex(32)
    elif state == "REVERTED":
        account = Account.from_key(keys["executor-d"])
        tx = contract.functions.anchorRecord(
            event["args"]["requestId"], event["args"]["recordHash"]
        ).build_transaction(
            {
                "from": account.address,
                "nonce": web3.eth.get_transaction_count(account.address),
                "gas": 150_000,
                "gasPrice": web3.eth.gas_price,
                "chainId": 31337,
            }
        )
        tx_hash = web3.eth.send_raw_transaction(
            account.sign_transaction(tx).raw_transaction
        ).to_0x_hex()
        assert web3.eth.wait_for_transaction_receipt(tx_hash)["status"] == 0
    elif state == "PENDING":
        assert "error" not in web3.provider.make_request(RPCEndpoint("anvil_setAutomine"), [False])
        tx_hash = web3.eth.send_transaction(
            {"from": web3.eth.accounts[0], "to": web3.eth.accounts[1], "value": 0, "gas": 21_000}
        ).to_0x_hex()
    before = web3.eth.block_number
    try:
        result, inputs, _ = run_read(capability_prepared, "get_tx_status", query_tx_hash=tx_hash)
        assert result.outcome == ("UNKNOWN" if state == "NOT_FOUND" else "PASS"), [
            (a.rule_id, a.outcome, a.reason_code) for a in result.assertions
        ]
        assert inputs.agent_result.tx_status == state
        assert inputs.binding is None and web3.eth.block_number == before
        if state in {"NOT_FOUND", "PENDING"}:
            assert result.task_link.verified_tx_hash is None
    finally:
        if state == "PENDING":
            web3.provider.make_request(RPCEndpoint("anvil_setAutomine"), [True])
            web3.provider.make_request(RPCEndpoint("evm_mine"), [])


@pytest.mark.parametrize("kind", ["matching", "mismatched", "absent"])
def test_verify_record_queries_existing_missing_and_mismatched_records(capability_prepared, kind):
    flow, _, target = capability_prepared
    contract = flow[4].eth.contract(
        address=Web3.to_checksum_address(target),
        abi=contract_abi(flow[1].root, "DemoRecordRegistry"),
    )
    event = contract.events.RecordAnchored().get_logs(from_block=0)[0]["args"]
    request_id = "0x" + bytes(event["requestId"]).hex()
    record_hash = "0x" + bytes(event["recordHash"]).hex()
    if kind == "mismatched":
        record_hash = "0x" + secrets.token_hex(32)
    elif kind == "absent":
        request_id = "0x" + secrets.token_hex(32)
    before = flow[4].eth.block_number
    result, inputs, _ = run_read(
        capability_prepared,
        "verify_record",
        target_contract=target,
        record_executor=event["executor"],
        record_request_id=request_id,
        record_hash=record_hash,
    )
    assert result.outcome == "PASS", [
        (a.rule_id, a.outcome, a.reason_code) for a in result.assertions
    ]
    assert inputs.agent_result.record_exists == (kind != "absent")
    assert inputs.agent_result.record_matches == (kind == "matching")
    assert result.task_link.verified_tx_hash is None and flow[4].eth.block_number == before


@pytest.mark.parametrize("capability_prepared", ["alternate"], indirect=True)
def test_record_queries_use_explicit_target_and_detect_claim_tampering(capability_prepared):
    flow, _, target = capability_prepared
    contract = flow[4].eth.contract(
        address=Web3.to_checksum_address(target),
        abi=contract_abi(flow[1].root, "DemoRecordRegistry"),
    )
    request_id, digest = "0x" + secrets.token_hex(32), "0x" + secrets.token_hex(32)
    SetupJournal(flow[6] / "record.sqlite3", flow[4]).transact(
        "record", flow[3]["executor-a"], contract.functions.anchorRecord(request_id, digest)
    )
    result, inputs, identifier = run_read(
        capability_prepared,
        "verify_record",
        target_contract=target,
        record_executor=flow[2]["a"]["executor"],
        record_request_id=request_id,
        record_hash=digest,
    )
    assert result.outcome == "PASS" and target != flow[5].record.address
    changed = copy.deepcopy(inputs.model_dump(mode="json"))
    changed["agent_result"]["record_matches"] = False
    assert (
        verify_record(RecordVerificationInput.model_validate(changed), (identifier,)).outcome
        != "PASS"
    )
    changed["agent_response"]["result"]["record_matches"] = False
    assert (
        verify_record(RecordVerificationInput.model_validate(changed), (identifier,)).outcome
        == "FAIL"
    )
    changed = copy.deepcopy(inputs.model_dump(mode="json"))
    changed["evm"]["results"]["record_call"] = "0x01"
    assert (
        verify_record(RecordVerificationInput.model_validate(changed), (identifier,)).outcome
        == "UNKNOWN"
    )
    changed["evm"]["results"] = {}
    changed["evm"]["error_reason"] = "PLATFORM_RPC_ERROR"
    assert (
        verify_record(RecordVerificationInput.model_validate(changed), (identifier,)).outcome
        == "UNKNOWN"
    )


@pytest.mark.parametrize("capability", ["get_tx_status", "verify_record"])
def test_read_reports_freeze_export_and_leave_scores_partial(capability_prepared, capability):
    flow, _, target = capability_prepared
    contract = flow[4].eth.contract(
        address=Web3.to_checksum_address(target),
        abi=contract_abi(flow[1].root, "DemoRecordRegistry"),
    )
    event = contract.events.RecordAnchored().get_logs(from_block=0)[0]
    values = (
        {"query_tx_hash": event["transactionHash"].to_0x_hex()}
        if capability == "get_tx_status"
        else {
            "target_contract": target,
            "record_executor": event["args"]["executor"],
            "record_request_id": "0x" + bytes(event["args"]["requestId"]).hex(),
            "record_hash": "0x" + bytes(event["args"]["recordHash"]).hex(),
        }
    )
    result, inputs, _ = run_read(capability_prepared, capability, **values)
    assert result.outcome == "PASS"
    reports = ReportService(flow[1].db, flow[1])
    errors = []

    async def freeze_checked(lease, queue):
        try:
            await reports.freeze(lease, queue)
        except Exception as exc:
            errors.append(exc)
            raise

    assert asyncio.run(Worker(flow[1].db, {"report": freeze_checked}).run_once())
    if errors:
        raise errors[0]
    with flow[1].db.connect() as connection:
        run_id = connection.execute(select(runs.c.id)).scalar_one()
        state = connection.execute(select(jobs.c.state).where(jobs.c.kind == "report")).scalar_one()
    assert state == "SUCCEEDED"
    report = reports.for_run(run_id)
    assert (
        report.core.scores.evaluation_state == "PARTIAL"
        and report.core.scores.overall_score_bp is None
    )
    assert report.core.raw_statistics["capabilities"][0]["capability_id"] == capability
    exported = flow[0].get(f"/api/v1/reports/{report.report_id}/bundle")
    assert exported.status_code == 200 and exported.content.startswith(b"PK")


def test_query_api_rejects_wrong_scope_and_invalid_inputs_before_dispatch(capability_prepared):
    flow, body, target = capability_prepared
    event = (
        flow[4]
        .eth.contract(
            address=Web3.to_checksum_address(target),
            abi=contract_abi(flow[1].root, "DemoRecordRegistry"),
        )
        .events.RecordAnchored()
        .get_logs(from_block=0)[0]
    )
    parameters = {
        "capability_id": "verify_record",
        "target_contract": target,
        "record_executor": event["args"]["executor"],
        "record_request_id": "0x" + bytes(event["args"]["requestId"]).hex(),
        "record_hash": "0x" + bytes(event["args"]["recordHash"]).hex(),
    }
    for change, expected in [
        ({"target_contract": flow[5].anchor.address}, 409),
        ({"record_request_id": "0x123"}, 422),
        ({"profile": "record-write-v1"}, 422),
    ]:
        response = flow[0].post(
            "/api/v1/evaluations",
            headers={**AUTH, "Idempotency-Key": secrets.token_hex(16)},
            json={**body, **parameters, **change},
        )
        assert response.status_code == expected, response.text
    with flow[1].db.connect() as connection:
        assert connection.scalar(select(func.count()).select_from(runs)) == 0


def test_record_query_stays_at_frozen_block_when_record_appears_later(capability_prepared):
    flow, body, target = capability_prepared
    request_id, digest = "0x" + secrets.token_hex(32), "0x" + secrets.token_hex(32)
    parameters = {
        "capability_id": "verify_record",
        "target_contract": target,
        "record_executor": flow[2]["a"]["executor"],
        "record_request_id": request_id,
        "record_hash": digest,
    }
    response = flow[0].post(
        "/api/v1/evaluations",
        headers={**AUTH, "Idempotency-Key": "frozen-record-query"},
        json={**body, **parameters},
    )
    assert response.status_code == 202, response.text
    run_id = UUID(response.json()["run_id"])
    contract = flow[4].eth.contract(
        address=Web3.to_checksum_address(target),
        abi=contract_abi(flow[1].root, "DemoRecordRegistry"),
    )
    SetupJournal(flow[6] / "post-plan-record.sqlite3", flow[4]).transact(
        "later", flow[3]["executor-a"], contract.functions.anchorRecord(request_id, digest)
    )
    verifier = VerificationService(flow[1].db, flow[1])
    worker = Worker(
        flow[1].db,
        {"evaluate": ExecutionService(flow[1].db, flow[1]).execute, "verify": verifier.verify},
    )
    assert asyncio.run(worker.run_once()) and asyncio.run(worker.run_once())
    result = verifier.result(run_id)
    inputs = verifier.inputs(run_id)
    assert result.outcome == "PASS" and inputs.agent_result.record_exists is False
    assert contract.functions.getRecord(
        Web3.to_checksum_address(flow[2]["a"]["executor"]), request_id
    ).call()[0]


@pytest.mark.parametrize("capability_prepared", ["alternate"], indirect=True)
@pytest.mark.parametrize("changed_code", [False, True])
def test_anchor_uses_another_authorized_contract_and_rejects_code_change(
    capability_prepared, changed_code
):
    flow, body, target = capability_prepared
    client = flow[0]
    snapshot_id = body["snapshot_id"]
    snapshot = client.get(f"/api/v1/snapshots/{snapshot_id}").json()
    reviewed = client.post(
        f"/api/v1/snapshots/{snapshot_id}/claims/confirm",
        headers=AUTH,
        json={
            "confirmed_claims": ["anchor_record"],
            "reason": "Explicit write capability",
            "expected_review_version": 1,
        },
    )
    assert reviewed.status_code == 200, reviewed.text
    challenge_response = client.post(
        f"/api/v1/snapshots/{snapshot_id}/bindings/challenge",
        headers=AUTH,
        json={
            "executor": flow[2]["a"]["executor"],
            "endpoint_id": "fixture-a",
            "execution_chain_key": "local-demo",
        },
    )
    assert challenge_response.status_code == 200, challenge_response.text
    assert verify(flow, snapshot, signed(flow, challenge_response.json())).status_code == 200
    grant = client.post(
        "/api/v1/access-grants",
        headers=AUTH,
        json={
            "snapshot_id": snapshot_id,
            "endpoint_id": "fixture-a",
            "max_tasks": 1,
            "capabilities": ["anchor_record"],
            "contract_allowlist": [target],
            "expires_at": (datetime.now(UTC) + timedelta(hours=1))
            .isoformat(timespec="milliseconds")
            .replace("+00:00", "Z"),
            "consent_ref": "Explicit synthetic write test",
        },
    )
    assert grant.status_code == 201, grant.text
    response = client.post(
        "/api/v1/evaluations",
        headers={**AUTH, "Idempotency-Key": "alternate-anchor"},
        json={
            **body,
            "review_version": 2,
            "profile": "record-write-v1",
            "capability_id": "anchor_record",
            "target_contract": target,
            "grant_ids": [grant.json()["grant"]["grant_id"]],
        },
    )
    assert response.status_code == 202, response.text
    run_id = UUID(response.json()["run_id"])
    if changed_code:
        assert "error" not in flow[4].provider.make_request(
            RPCEndpoint("anvil_setCode"), [target, "0x"]
        )
    verifier = VerificationService(flow[1].db, flow[1])
    worker = Worker(
        flow[1].db,
        {"evaluate": ExecutionService(flow[1].db, flow[1]).execute, "verify": verifier.verify},
    )
    assert asyncio.run(worker.run_once())
    assert asyncio.run(worker.run_once())
    result = verifier.result(run_id)
    if changed_code:
        assert result.outcome == "UNKNOWN" and result.task_link.verified_tx_hash is None
        observed = client.get(f"/api/v1/evaluations/{run_id}/observations").json()
        assert observed[-1]["reason_code"] == "CHAIN_INSTANCE_CHANGED"
        return
    assert result.outcome == "PASS", [
        (a.rule_id, a.outcome, a.reason_code) for a in result.assertions
    ]
    transaction = flow[4].eth.get_transaction(result.task_link.verified_tx_hash)
    assert transaction["to"].lower() == target != flow[5].record.address
