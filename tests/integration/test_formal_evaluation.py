"""Formal multi-slot evaluation through real PostgreSQL, HTTP and Anvil evidence."""

import asyncio
import base64
import secrets
from collections import Counter
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from eth_account import Account
from reputation_core.case_templates import mutated_payload
from reputation_core.evidence import canonical_bytes, hash_json
from reputation_core.models import RecordVerificationResult, RunPlan
from reputation_core.record_verifier import verify_record
from reputation_platform.application.execution import ExecutionService
from reputation_platform.application.local_deploy import SetupJournal, contract_abi
from reputation_platform.application.reports import ReportService
from reputation_platform.application.verification import VerificationService
from reputation_platform.infrastructure.db.jobs import JobQueue
from reputation_platform.infrastructure.db.tables import (
    attempts,
    case_slots,
    dispatch_events,
    jobs,
    runs,
    snapshots,
    task_links,
)
from reputation_platform.infrastructure.network.safe_http import HttpObservation, SafeHttpClient
from reputation_platform.worker.main import Worker
from reputation_verifier.bundle import verify_bundle
from sqlalchemy import func, select
from web3 import Web3
from web3.types import RPCEndpoint

from tests.integration.test_capabilities import capability_prepared
from tests.integration.test_execution import InjectedCrash, crash, prepared
from tests.integration.test_identity import AUTH, capture, flow, identity_chain, signed, verify

__all__ = ["prepared", "capability_prepared", "flow", "identity_chain"]
pytestmark = [pytest.mark.chain, pytest.mark.postgres]


def scoped_snapshot(flow, previous_snapshot_id, capabilities):
    """Freeze a real narrower declaration; omitted claims must not silently disappear."""
    client, identity, samples, keys, web3, deployment, runtime = flow
    registry = web3.eth.contract(
        address=Web3.to_checksum_address(deployment.registry.address),
        abi=contract_abi(identity.root, "DemoAgentRegistry"),
    )
    metadata = {**samples["a"]["metadata"], "capabilities": list(capabilities)}
    uri = "data:application/json;base64," + base64.b64encode(canonical_bytes(metadata)).decode()
    SetupJournal(runtime / "formal-scope.sqlite3", web3).transact(
        "scope-declaration",
        keys["owner-a"],
        registry.functions.setAgentURI(int(samples["a"]["agent_ref"]["agent_id"]), uri),
    )
    with identity.db.connect() as connection:
        agent_id = connection.execute(
            select(snapshots.c.agent_fk).where(snapshots.c.id == UUID(previous_snapshot_id))
        ).scalar_one()
    _, snapshot, _ = capture(flow, agent_id=str(agent_id))
    response = client.post(
        f"/api/v1/snapshots/{snapshot['snapshot_id']}/claims/confirm",
        headers=AUTH,
        json={
            "confirmed_claims": list(capabilities),
            "reason": "Reviewed current scoped declaration",
            "expected_review_version": 0,
        },
    )
    assert response.status_code == 200, response.text
    if "anchor_record" in capabilities:
        response = client.post(
            f"/api/v1/snapshots/{snapshot['snapshot_id']}/bindings/challenge",
            headers=AUTH,
            json={
                "executor": samples["a"]["executor"],
                "endpoint_id": "fixture-a",
                "execution_chain_key": "local-demo",
            },
        )
        assert response.status_code == 200, response.text
        response = verify(flow, snapshot, signed(flow, response.json()))
        assert response.status_code == 200 and response.json()["status"] == "VERIFIED", (
            response.text
        )
    return snapshot["snapshot_id"]


def formal_request(flow, snapshot_id, review_version, capabilities, target, *, max_tasks=100):
    client, identity, _, _, web3, deployment, _ = flow
    response = client.post(
        "/api/v1/access-grants",
        headers=AUTH,
        json={
            "snapshot_id": snapshot_id,
            "endpoint_id": "fixture-a",
            "max_tasks": max_tasks,
            "capabilities": list(capabilities),
            "contract_allowlist": [target],
            "expires_at": (datetime.now(UTC) + timedelta(hours=1))
            .isoformat(timespec="milliseconds")
            .replace("+00:00", "Z"),
            "consent_ref": "Formal controlled evaluation consent",
        },
    )
    assert response.status_code == 201, response.text
    contract = web3.eth.contract(
        address=Web3.to_checksum_address(target),
        abi=contract_abi(identity.root, "DemoRecordRegistry"),
    )
    event = contract.events.RecordAnchored().get_logs(from_block=0)[0]["args"]
    return {
        "snapshot_id": snapshot_id,
        "review_version": review_version,
        "profile": "record-write-v1" if "anchor_record" in capabilities else "record-read-v1",
        "policy_version": "policy-v1",
        "grant_ids": [response.json()["grant"]["grant_id"]],
        "suite_id": "formal-evaluation-v1",
        "target_contract": target,
        "record_executor": event["executor"],
        "record_request_id": "0x" + bytes(event["requestId"]).hex(),
        "record_hash": "0x" + bytes(event["recordHash"]).hex(),
    }


def create_formal(flow, body):
    response = flow[0].post(
        "/api/v1/evaluations", headers={**AUTH, "Idempotency-Key": secrets.token_hex(16)}, json=body
    )
    assert response.status_code == 202, response.text
    run_id = UUID(response.json()["run_id"])
    with flow[1].db.connect() as connection:
        plan = RunPlan.model_validate(
            connection.execute(select(runs.c.plan).where(runs.c.id == run_id)).scalar_one()
        )
        assert connection.scalar(
            select(func.count()).select_from(case_slots).where(case_slots.c.run_fk == run_id)
        ) == len(plan.slots)
        assert connection.scalar(select(func.count()).select_from(attempts)) == 0
        intents = dict(
            connection.execute(
                select(dispatch_events.c.slot_fk, dispatch_events.c.body)
                .join(case_slots, dispatch_events.c.slot_fk == case_slots.c.id)
                .where(case_slots.c.run_fk == run_id, dispatch_events.c.state == "NOT_SENT")
            ).all()
        )
        for slot in plan.slots:
            assert intents[slot.slot_id]["payload_hash"] == hash_json(mutated_payload(slot))
    assert plan.template_version == "capabilities@3"
    assert len({slot.task.request_id for slot in plan.slots}) == len(plan.slots)
    return run_id, plan


def run_formal(flow, run_id, tmp_path):
    identity = flow[1]
    verifier = VerificationService(identity.db, identity)
    reports = ReportService(identity.db, identity)
    worker = Worker(
        identity.db,
        {
            "evaluate": ExecutionService(identity.db, identity).execute,
            "verify": verifier.verify,
            "report": reports.freeze,
        },
    )
    for kind in ("evaluate", "verify", "report"):
        assert asyncio.run(worker.run_once())
        with identity.db.connect() as connection:
            row = connection.execute(
                select(jobs.c.state, jobs.c.last_error).where(
                    jobs.c.kind == kind, jobs.c.run_fk == run_id
                )
            ).one()
            assert row.state == "SUCCEEDED", (kind, row)
    results = verifier.results(run_id)
    response = flow[0].get(f"/api/v1/evaluations/{run_id}/verification")
    assert response.status_code == 200 and len(response.json()) == len(results)
    report = reports.for_run(run_id)
    assert report.core.schema_version == "1.2.0"
    assert len(report.core.task_results) == len(results)
    destination = tmp_path / "formal-bundle.zip"
    destination.write_bytes(reports.export(report.report_id))
    independent = verify_bundle(str(destination))
    assert independent["offline"] == "PASS"
    assert independent["task_count_comparison"] == "MATCH"
    assert independent["task_counts"] == report.core.task_counts.model_dump(mode="json")
    return report, results


def test_formal_write_evaluation_freezes_independent_dimensions_and_all_case_classes(
    prepared, tmp_path
):
    flow, original, _ = prepared
    capabilities = ("verify_record", "anchor_record")
    snapshot_id = scoped_snapshot(flow, original["snapshot_id"], capabilities)
    body = formal_request(flow, snapshot_id, 1, capabilities, flow[5].record.address)
    run_id, plan = create_formal(flow, body)
    assert Counter(slot.purpose.value for slot in plan.slots) == {
        "availability": 20,
        "functional": 20,
        "behavioral": 10,
    }
    report, results = run_formal(flow, run_id, tmp_path)
    assert all(result.outcome == "PASS" for result in results), [
        (slot.required_class, result.outcome, result.reason_code)
        for slot, result in zip(plan.slots, results, strict=True)
    ]
    assert report.core.scores.evaluation_state == "COMPLETE"
    assert report.core.scores.overall_score_bp == 10000
    assert not report.core.scores.critical_conflict
    assert report.core.raw_statistics["behavior"]["decided"] == 10
    assert report.core.raw_statistics["availability"]["decided"] == 20
    assert len({item.input_evidence_id for item in report.core.task_results}) == 50


def test_formal_read_queries_success_revert_pending_and_negative_cases_without_new_writes(
    capability_prepared, tmp_path
):
    flow, original, target = capability_prepared
    capabilities = ("get_tx_status", "verify_record")
    snapshot_id = scoped_snapshot(flow, original["snapshot_id"], capabilities)
    body = formal_request(flow, snapshot_id, 1, capabilities, target)
    contract = flow[4].eth.contract(
        address=Web3.to_checksum_address(target),
        abi=contract_abi(flow[1].root, "DemoRecordRegistry"),
    )
    event = contract.events.RecordAnchored().get_logs(from_block=0)[0]
    account = Account.from_key(flow[3]["executor-d"])
    revert_event = contract.events.RecordAnchored().get_logs(
        from_block=0, argument_filters={"executor": account.address}
    )[0]
    tx = contract.functions.anchorRecord(
        revert_event["args"]["requestId"], revert_event["args"]["recordHash"]
    ).build_transaction(
        {
            "from": account.address,
            "nonce": flow[4].eth.get_transaction_count(account.address),
            "gas": 150_000,
            "gasPrice": flow[4].eth.gas_price,
            "chainId": 31337,
        }
    )
    reverted = (
        flow[4].eth.send_raw_transaction(account.sign_transaction(tx).raw_transaction).to_0x_hex()
    )
    assert flow[4].eth.wait_for_transaction_receipt(reverted)["status"] == 0
    assert "error" not in flow[4].provider.make_request(RPCEndpoint("anvil_setAutomine"), [False])
    pending = (
        flow[4]
        .eth.send_transaction(
            {
                "from": flow[4].eth.accounts[0],
                "to": flow[4].eth.accounts[1],
                "value": 0,
                "gas": 21_000,
            }
        )
        .to_0x_hex()
    )
    body["transaction_cases"] = {
        "success": event["transactionHash"].to_0x_hex(),
        "revert": reverted,
        "pending": pending,
    }
    before = flow[4].eth.block_number
    try:
        run_id, plan = create_formal(flow, body)
        report, results = run_formal(flow, run_id, tmp_path)
        assert len(plan.slots) == 40 and all(result.outcome == "PASS" for result in results)
        assert report.core.scores.evaluation_state == "COMPLETE"
        assert report.core.scores.overall_score_bp == 10000
        assert report.core.scores.dimensions["behavior"].state == "NOT_APPLICABLE"
        assert flow[4].eth.block_number == before
    finally:
        flow[4].provider.make_request(RPCEndpoint("anvil_setAutomine"), [True])
        flow[4].provider.make_request(RPCEndpoint("evm_mine"), [])


def test_formal_only_write_stays_partial_without_safe_availability_samples(prepared, tmp_path):
    flow, original, _ = prepared
    body = formal_request(
        flow, original["snapshot_id"], 1, ("anchor_record",), flow[5].record.address
    )
    run_id, plan = create_formal(flow, body)
    assert Counter(slot.purpose.value for slot in plan.slots) == {
        "functional": 10,
        "behavioral": 10,
    }
    report, results = run_formal(flow, run_id, tmp_path)
    assert all(result.outcome == "PASS" for result in results)
    assert report.core.scores.evaluation_state == "PARTIAL"
    assert report.core.scores.overall_score_bp is None
    assert report.core.raw_statistics["availability"]["planned"] == 0


def test_formal_reserves_all_slots_against_the_grant_before_dispatch(prepared):
    flow, original, _ = prepared
    body = formal_request(
        flow, original["snapshot_id"], 1, ("anchor_record",), flow[5].record.address, max_tasks=19
    )
    response = flow[0].post(
        "/api/v1/evaluations", headers={**AUTH, "Idempotency-Key": "formal-quota"}, json=body
    )
    assert (
        response.status_code == 409 and response.json()["error"]["code"] == "GRANT_QUOTA_EXHAUSTED"
    )
    with flow[1].db.connect() as connection:
        assert connection.scalar(select(func.count()).select_from(runs)) == 0
        assert connection.scalar(select(func.count()).select_from(attempts)) == 0


def test_formal_execution_and_verification_resume_without_replaying_completed_slots(prepared):
    flow, original, _ = prepared
    body = formal_request(
        flow, original["snapshot_id"], 1, ("anchor_record",), flow[5].record.address
    )
    run_id, plan = create_formal(flow, body)
    queue = JobQueue(flow[1].db, "formal-resume", lease_seconds=300)
    lease = queue.claim("evaluate")
    assert lease is not None
    service = ExecutionService(flow[1].db, flow[1])
    row = service.evaluations.row(run_id)
    asyncio.run(service.execute_slot(lease, queue, row, plan, plan.slots[0]))
    with flow[1].db.connect() as connection:
        assert (
            connection.scalar(select(func.count()).select_from(jobs).where(jobs.c.kind == "verify"))
            == 0
        )
        posts = connection.scalar(
            select(func.count())
            .select_from(attempts)
            .where(
                attempts.c.slot_fk == plan.slots[0].slot_id,
                attempts.c.body["method"].astext == "POST",
            )
        )
    asyncio.run(service.execute(lease, queue))
    queue.complete(lease)
    with flow[1].db.connect() as connection:
        assert (
            connection.scalar(
                select(func.count())
                .select_from(attempts)
                .where(
                    attempts.c.slot_fk == plan.slots[0].slot_id,
                    attempts.c.body["method"].astext == "POST",
                )
            )
            == posts
        )
    lease = queue.claim("verify")
    assert lease is not None
    verifier = VerificationService(flow[1].db, flow[1])
    asyncio.run(verifier.verify_slot(lease, queue, plan.slots[0].slot_id, len(plan.slots)))
    with flow[1].db.connect() as connection:
        assert (
            connection.scalar(select(func.count()).select_from(jobs).where(jobs.c.kind == "report"))
            == 0
        )
    asyncio.run(verifier.verify(lease, queue))
    queue.complete(lease)
    with flow[1].db.connect() as connection:
        assert connection.scalar(select(func.count()).select_from(task_links)) == len(plan.slots)
    assert len(verifier.results(run_id)) == len(plan.slots)


def test_formal_negative_crash_preserves_unknown_without_resending_a_rejected_probe(prepared):
    flow, original, _ = prepared
    body = formal_request(
        flow, original["snapshot_id"], 1, ("anchor_record",), flow[5].record.address
    )
    run_id, plan = create_formal(flow, body)
    slot = next(slot for slot in plan.slots if slot.required_class == "expired_deadline")
    queue = JobQueue(flow[1].db, "negative-crash", lease_seconds=300)
    lease = queue.claim("evaluate")
    assert lease is not None
    service = ExecutionService(flow[1].db, flow[1], fault_hook=crash)
    row = service.evaluations.row(run_id)
    before = flow[4].eth.block_number
    with pytest.raises(InjectedCrash):
        asyncio.run(service.execute_slot(lease, queue, row, plan, slot))
    asyncio.run(ExecutionService(flow[1].db, flow[1]).execute_slot(lease, queue, row, plan, slot))
    verifier = VerificationService(flow[1].db, flow[1])
    inputs = verifier.inputs(run_id, slot.slot_id)
    assert inputs.initial_agent_http is None
    assert inputs.execution_reason == "DISPATCH_UNCERTAIN"
    assert flow[4].eth.block_number == before
    with flow[1].db.connect() as connection:
        assert (
            connection.scalar(
                select(func.count())
                .select_from(attempts)
                .where(
                    attempts.c.slot_fk == slot.slot_id, attempts.c.body["method"].astext == "POST"
                )
            )
            == 1
        )
    assert verify_record(inputs, ()).outcome == "UNKNOWN"


def test_formal_accepted_negative_is_failed_after_one_post_without_polling(prepared, monkeypatch):
    flow, original, _ = prepared
    body = formal_request(
        flow, original["snapshot_id"], 1, ("anchor_record",), flow[5].record.address
    )
    run_id, plan = create_formal(flow, body)
    slot = next(slot for slot in plan.slots if slot.required_class == "expired_deadline")
    requests = []

    async def accept_invalid(self, method, origin, path, *, json=None, request_id=None):
        requests.append((method, path))
        assert method == "POST" and path == "/tasks"
        assert json == mutated_payload(slot) and request_id == slot.task.request_id
        return HttpObservation(202, canonical_bytes({
            "request_id": request_id, "task_status": "accepted",
            "status_path": "/tasks/" + request_id, "result": None,
        }))

    monkeypatch.setattr(SafeHttpClient, "request", accept_invalid)
    queue = JobQueue(flow[1].db, "accepted-negative", lease_seconds=300)
    lease = queue.claim("evaluate")
    assert lease is not None
    service = ExecutionService(flow[1].db, flow[1])
    before = flow[4].eth.block_number
    asyncio.run(service.execute_slot(lease, queue, service.evaluations.row(run_id), plan, slot))
    assert requests == [("POST", "/tasks")]
    with flow[1].db.connect() as connection:
        methods = connection.execute(
            select(attempts.c.body["method"].astext).where(attempts.c.slot_fk == slot.slot_id)
        ).scalars().all()
    assert methods == ["POST"]
    verifier = VerificationService(flow[1].db, flow[1])
    inputs = verifier.inputs(run_id, slot.slot_id)
    assert inputs.initial_agent_http == inputs.agent_http
    assert inputs.agent_task_status == "accepted"
    asyncio.run(verifier.verify_slot(lease, queue, slot.slot_id, len(plan.slots)))
    with flow[1].db.connect() as connection:
        result = RecordVerificationResult.model_validate(connection.execute(
            select(task_links.c.body).where(task_links.c.slot_fk == slot.slot_id)
        ).scalar_one())
    assert result.outcome == "FAIL" and result.reason_code == "AGENT_TASK_FAILED"
    assert not result.critical_conflict and result.task_link.verified_tx_hash is None
    assert verify_record(inputs, result.assertions[0].evidence_refs) == result
    assert flow[4].eth.block_number == before
