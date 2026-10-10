"""Real PostgreSQL + Anvil + independent HTTP Agent, including dispatch crash recovery."""

import asyncio
import json
import os
import socket
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from uuid import UUID

import httpx
import pytest
from reputation_core.evidence import hash_json
from reputation_core.models import RunPlan
from reputation_platform.application.execution import ExecutionService
from reputation_platform.application.local_deploy import contract_abi
from reputation_platform.configuration import controlled_fixture_ports
from reputation_platform.infrastructure.db.jobs import JobQueue, Lease, LostLease
from reputation_platform.infrastructure.db.tables import (
    attempts,
    case_slots,
    dispatch_events,
    jobs,
    observations,
    runs,
)
from reputation_platform.worker.main import Worker
from sqlalchemy import func, select, update
from web3 import Web3

from tests.integration.test_identity import (
    AUTH,
    capture,
    challenge,
    flow,
    identity_chain,
    signed,
    verify,
)

pytestmark = [pytest.mark.chain, pytest.mark.postgres]
__all__ = ["flow", "identity_chain"]


@pytest.fixture
def prepared(flow, request):
    client, identity, samples, keys, web3, deployment, runtime = flow
    parameter = getattr(request, "param", "a")
    scenario = parameter if isinstance(parameter, dict) else {"sample": parameter}
    sample = scenario.get("sample", "a")
    ports = controlled_fixture_ports()
    port = ports[0] if sample == "a" else ports[1]
    replay = None
    if sample == "d":
        contract = web3.eth.contract(
            address=Web3.to_checksum_address(deployment.record.address),
            abi=contract_abi(identity.root, "DemoRecordRegistry"),
        )
        replay = (
            contract.events.RecordAnchored()
            .get_logs(
                from_block=0,
                argument_filters={"executor": Web3.to_checksum_address(samples["d"]["executor"])},
            )[0]["transactionHash"]
            .to_0x_hex()
        )
    config = {
        "deployment": deployment.model_dump(mode="json"),
        "metadata": samples[sample]["metadata"],
        "private_key": keys[f"executor-{scenario.get('executor_sample', sample)}"],
        "mode": "normal" if sample == "a" else "replay",
        "replay_tx_hash": replay,
        "registry_abi": contract_abi(identity.root, "DemoAgentRegistry"),
        "record_abi": contract_abi(identity.root, "DemoRecordRegistry"),
        **{
            field: scenario[field]
            for field in ("mode", "fault_seed", "failure_every", "delay_seconds")
            if field in scenario
        },
    }
    path = runtime / f"fixture-{sample}.json"
    path.write_text(json.dumps(config), encoding="utf-8")
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
        # Process/import startup is outside the task's separately frozen execution deadline.
        deadline = time.monotonic() + 90
        with httpx.Client(trust_env=False, timeout=1) as probe:
            while True:
                assert process.poll() is None, (
                    f"Test Agent could not start; stop the demo occupying port {port}"
                )
                try:
                    if probe.get(f"http://127.0.0.1:{port}/health").status_code == 200:
                        break
                except httpx.HTTPError:
                    pass
                assert time.monotonic() < deadline, "Real HTTP Agent did not start"
                time.sleep(0.1)
        _, snapshot, _ = capture(flow, sample)
        assert (
            verify(
                flow, snapshot, signed(flow, challenge(flow, snapshot, sample), sample)
            ).status_code
            == 200
        )
        grant_response = client.post(
            "/api/v1/access-grants",
            headers=AUTH,
            json={
                "snapshot_id": snapshot["snapshot_id"],
                "endpoint_id": f"fixture-{sample}",
                "max_tasks": 1,
                "expires_at": (datetime.now(UTC) + timedelta(hours=1))
                .isoformat(timespec="milliseconds")
                .replace("+00:00", "Z"),
                "consent_ref": "test operator consent",
            },
        )
        assert grant_response.status_code == 201, grant_response.text
        grant = grant_response.json()["grant"]
        body = {
            "snapshot_id": snapshot["snapshot_id"],
            "review_version": 1,
            "profile": "record-write-v1",
            "policy_version": "policy-v1",
            "grant_ids": [grant["grant_id"]],
            "suite_id": "m1-smoke-v1",
        }
        yield flow, body, grant
    finally:
        process.terminate()
        process.wait(timeout=15)


def create(prepared, key="execution-test", body=None):
    flow, original, _ = prepared
    response = flow[0].post(
        "/api/v1/evaluations", headers={**AUTH, "Idempotency-Key": key}, json=body or original
    )
    assert response.status_code == 202, response.text
    run_id = UUID(response.json()["run_id"])
    with flow[1].db.connect() as connection:
        plan = RunPlan.model_validate(
            connection.execute(select(runs.c.plan).where(runs.c.id == run_id)).scalar_one()
        )
    return run_id, plan


def records(flow, plan):
    contract = flow[4].eth.contract(
        address=Web3.to_checksum_address(flow[5].record.address),
        abi=contract_abi(flow[1].root, "DemoRecordRegistry"),
    )
    return contract.events.RecordAnchored().get_logs(
        from_block=0,
        argument_filters={"requestId": bytes.fromhex(plan.slots[0].task.request_id[2:])},
    )


def test_plan_is_persisted_before_dispatch_and_idempotency_is_payload_bound(prepared):
    flow, body, _ = prepared
    run_id, plan = create(prepared)
    slot = plan.slots[0]
    assert slot.purpose == "functional" and len(plan.slots) == 1
    assert hash_json(slot.synthetic_input) == slot.task.record_hash
    assert not records(flow, plan)
    repeated = flow[0].post(
        "/api/v1/evaluations", headers={**AUTH, "Idempotency-Key": "execution-test"}, json=body
    )
    assert repeated.json()["run_id"] == str(run_id)
    changed = flow[0].post(
        "/api/v1/evaluations",
        headers={**AUTH, "Idempotency-Key": "execution-test"},
        json={**body, "review_version": 2},
    )
    assert changed.status_code == 409 and changed.json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"
    with flow[1].db.connect() as connection:
        assert connection.scalar(select(func.count()).select_from(runs)) == 1
        assert connection.scalar(select(func.count()).select_from(case_slots)) == 1
        assert connection.scalar(select(func.count()).select_from(attempts)) == 0
        assert (
            connection.scalar(
                select(dispatch_events.c.state).where(dispatch_events.c.slot_fk == slot.slot_id)
            )
            == "NOT_SENT"
        )


def test_concurrent_same_key_creates_one_run_and_agent_admission_is_serial(prepared):
    flow, body, _ = prepared
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(
                lambda _: flow[0].post(
                    "/api/v1/evaluations", headers={**AUTH, "Idempotency-Key": "same"}, json=body
                ),
                range(2),
            )
        )
    assert [item.status_code for item in results] == [202, 202]
    assert results[0].json()["run_id"] == results[1].json()["run_id"]
    denied = flow[0].post(
        "/api/v1/evaluations", headers={**AUTH, "Idempotency-Key": "different"}, json=body
    )
    assert denied.json()["error"]["code"] == "AGENT_BUSY"


def test_real_http_execution_observes_one_candidate_and_reserves_quota(prepared):
    flow, body, _ = prepared
    run_id, plan = create(prepared)
    service = ExecutionService(flow[1].db, flow[1])
    assert asyncio.run(Worker(flow[1].db, {"evaluate": service.execute}).run_once())
    found = records(flow, plan)
    assert len(found) == 1
    result = flow[0].get(f"/api/v1/evaluations/{run_id}/observations").json()
    assert result[-1]["dispatch_state"] == "SETTLED"
    assert result[-1]["candidate_tx_hash"] == found[0]["transactionHash"].to_0x_hex()
    assert result[-1]["accepted"]
    denied = flow[0].post(
        "/api/v1/evaluations", headers={**AUTH, "Idempotency-Key": "over-quota"}, json=body
    )
    assert denied.json()["error"]["code"] == "GRANT_QUOTA_EXHAUSTED"


class InjectedCrash(BaseException):
    pass


def crash(stage):
    if stage == "after_send_before_ack":
        raise InjectedCrash()


def test_send_before_ack_crash_reconciles_original_request_without_second_post(prepared):
    flow, _, _ = prepared
    run_id, plan = create(prepared)
    deployment_file = flow[6] / "worker-deployment.json"
    deployment_file.write_text(flow[5].model_dump_json(), encoding="utf-8")
    child = subprocess.run(
        [
            sys.executable,
            "-c",
            """
import asyncio, os
from reputation_platform.application.execution import ExecutionService
from reputation_platform.infrastructure.db.connection import engine
from reputation_platform.worker.main import Worker
def fault(stage):
    if stage == 'after_send_before_ack':
        os._exit(86)
db = engine()
asyncio.run(Worker(db, {'evaluate': ExecutionService(db, fault_hook=fault).execute}).run_once())
""",
        ],
        env={
            **os.environ,
            "LOCAL_CHAIN_CONFIG": str(deployment_file),
            "EVIDENCE_ROOT": str(flow[1].evidence.root),
        },
        capture_output=True,
        timeout=45,
    )
    assert child.returncode == 86, (
        "Worker must actually exit after the HTTP send and before ACK persistence"
    )
    with flow[1].db.begin() as connection:
        row = connection.execute(select(jobs).where(jobs.c.run_fk == run_id)).mappings().one()
        lease = Lease(
            row["id"],
            row["lease_token"],
            row["kind"],
            row["run_fk"],
            row["payload"],
            row["attempts"],
        )
        queue = JobQueue(flow[1].db, row["lease_owner"])
        assert connection.scalar(select(func.count()).select_from(observations)) == 0
        connection.execute(
            update(jobs)
            .where(jobs.c.id == lease.job_id)
            .values(lease_until=datetime.now(UTC) - timedelta(seconds=1))
        )
    recovered = ExecutionService(flow[1].db, flow[1])
    assert asyncio.run(Worker(flow[1].db, {"evaluate": recovered.execute}).run_once())
    assert len(records(flow, plan)) == 1
    with flow[1].db.connect() as connection:
        methods = (
            connection.execute(select(attempts.c.body).order_by(attempts.c.attempt_no))
            .scalars()
            .all()
        )
    assert [item["method"] for item in methods].count("POST") == 1
    assert any(item["method"] == "GET" for item in methods)
    with pytest.raises(LostLease):
        queue.complete(lease)


@pytest.mark.parametrize("operation", ["cancel", "revoke"])
def test_pre_dispatch_cancellation_or_revocation_never_sends(prepared, operation):
    flow, _, grant = prepared
    run_id, plan = create(prepared)
    route = (
        f"/api/v1/evaluations/{run_id}/cancel"
        if operation == "cancel"
        else f"/api/v1/access-grants/{grant['grant_id']}/revoke"
    )
    assert (
        flow[0]
        .post(route, headers=AUTH, json={"reason": "Operator withdrew permission"})
        .status_code
        == 200
    )
    assert asyncio.run(
        Worker(flow[1].db, {"evaluate": ExecutionService(flow[1].db, flow[1]).execute}).run_once()
    )
    assert not records(flow, plan)
    result = flow[0].get(f"/api/v1/evaluations/{run_id}/observations").json()[-1]
    assert result["reason_code"] == (
        "CANCELLED_BY_OPERATOR" if operation == "cancel" else "ACCESS_NOT_GRANTED"
    )
    with flow[1].db.connect() as connection:
        assert (
            connection.scalar(
                select(func.count())
                .select_from(attempts)
                .where(attempts.c.body["method"].astext == "POST")
            )
            == 0
        )


def test_cancel_after_send_preserves_transaction_and_reconciles(prepared):
    flow, _, _ = prepared
    run_id, plan = create(prepared)
    queue = JobQueue(flow[1].db, "cancel-crash-worker")
    lease = queue.claim("evaluate")
    with pytest.raises(InjectedCrash):
        asyncio.run(ExecutionService(flow[1].db, flow[1], fault_hook=crash).execute(lease, queue))
    assert (
        flow[0]
        .post(
            f"/api/v1/evaluations/{run_id}/cancel",
            headers=AUTH,
            json={"reason": "Stop further writes"},
        )
        .status_code
        == 200
    )
    with flow[1].db.begin() as connection:
        connection.execute(
            update(jobs)
            .where(jobs.c.id == lease.job_id)
            .values(lease_until=datetime.now(UTC) - timedelta(seconds=1))
        )
    assert asyncio.run(
        Worker(flow[1].db, {"evaluate": ExecutionService(flow[1].db, flow[1]).execute}).run_once()
    )
    assert len(records(flow, plan)) == 1
    result = flow[0].get(f"/api/v1/evaluations/{run_id}/observations").json()[-1]
    assert result["candidate_tx_hash"] and result["reason_code"] is None


def test_crash_before_send_uses_lookup_then_bounded_same_payload_repost(prepared):
    flow, _, _ = prepared
    _, plan = create(prepared)
    queue = JobQueue(flow[1].db, "before-send-crash")
    lease = queue.claim("evaluate")

    def before_send(stage):
        if stage == "before_send":
            raise InjectedCrash()

    with pytest.raises(InjectedCrash):
        asyncio.run(
            ExecutionService(flow[1].db, flow[1], fault_hook=before_send).execute(lease, queue)
        )
    assert not records(flow, plan)
    with flow[1].db.begin() as connection:
        connection.execute(
            update(jobs)
            .where(jobs.c.id == lease.job_id)
            .values(lease_until=datetime.now(UTC) - timedelta(seconds=1))
        )
    assert asyncio.run(
        Worker(flow[1].db, {"evaluate": ExecutionService(flow[1].db, flow[1]).execute}).run_once()
    )
    assert len(records(flow, plan)) == 1
    with flow[1].db.connect() as connection:
        rows = (
            connection.execute(select(attempts.c.body).order_by(attempts.c.attempt_no))
            .scalars()
            .all()
        )
    assert [row["method"] for row in rows][:3] == ["POST", "GET", "POST"]
    assert len({row["payload_hash"] for row in rows}) == 1


def test_revocation_after_send_uses_rpc_without_more_agent_http(prepared):
    flow, _, grant = prepared
    run_id, plan = create(prepared)
    queue = JobQueue(flow[1].db, "revoke-after-send")
    lease = queue.claim("evaluate")
    with pytest.raises(InjectedCrash):
        asyncio.run(ExecutionService(flow[1].db, flow[1], fault_hook=crash).execute(lease, queue))
    until = time.monotonic() + 10
    while not records(flow, plan):
        assert time.monotonic() < until
        time.sleep(0.1)
    flow[0].post(
        f"/api/v1/access-grants/{grant['grant_id']}/revoke",
        headers=AUTH,
        json={"reason": "Stop Agent HTTP"},
    ).raise_for_status()
    with flow[1].db.begin() as connection:
        connection.execute(
            update(jobs)
            .where(jobs.c.id == lease.job_id)
            .values(lease_until=datetime.now(UTC) - timedelta(seconds=1))
        )
    assert asyncio.run(
        Worker(flow[1].db, {"evaluate": ExecutionService(flow[1].db, flow[1]).execute}).run_once()
    )
    result = flow[0].get(f"/api/v1/evaluations/{run_id}/observations").json()[-1]
    assert result["candidate_tx_hash"] == records(flow, plan)[0]["transactionHash"].to_0x_hex()
    with flow[1].db.connect() as connection:
        assert connection.scalar(select(func.count()).select_from(attempts)) == 1


def test_unavailable_trusted_rpc_is_unknown_and_never_dispatches(prepared):
    flow, _, _ = prepared
    run_id, plan = create(prepared)
    with socket.socket() as unused:
        unused.bind(("127.0.0.1", 0))
        closed_port = unused.getsockname()[1]
        # Bound but not listening: an actual refused RPC connection, no fake transport.
        flow[1]._deployment = flow[5].model_copy(
            update={"rpc_url": f"http://127.0.0.1:{closed_port}"}
        )
        assert asyncio.run(
            Worker(
                flow[1].db, {"evaluate": ExecutionService(flow[1].db, flow[1]).execute}
            ).run_once()
        )
    result = flow[0].get(f"/api/v1/evaluations/{run_id}/observations").json()[-1]
    assert result["reason_code"] == "PLATFORM_RPC_ERROR"
    assert not records(flow, plan)
    state = flow[0].get(f"/api/v1/evaluations/{run_id}").json()
    assert state["unknown"] == 1 and state["settled"] == 1


def test_slow_execution_context_leaves_lease_heartbeat_running(prepared, monkeypatch):
    flow, _, _ = prepared
    run_id, plan = create(prepared)
    identity = flow[1]
    original = identity.snapshot

    def slow_snapshot(*args, **kwargs):
        time.sleep(2)
        return original(*args, **kwargs)

    monkeypatch.setattr(identity, "snapshot", slow_snapshot)
    worker = Worker(
        identity.db, {"evaluate": ExecutionService(identity.db, identity).execute}, lease_seconds=1
    )
    assert asyncio.run(worker.run_once())
    with identity.db.connect() as connection:
        assert connection.scalar(
            select(jobs.c.state).where(jobs.c.kind == "evaluate", jobs.c.run_fk == run_id)
        ) == "SUCCEEDED"
    assert len(records(flow, plan)) == 1
