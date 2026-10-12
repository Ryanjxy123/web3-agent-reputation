"""Fresh public refresh budgets preserve durable admission and crash recovery on PostgreSQL."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import UUID

import httpx
import pytest
from fastapi.testclient import TestClient
from reputation_platform.api.app import create_app
from reputation_platform.application.identity import IdentityService
from reputation_platform.infrastructure.db.jobs import JobQueue, LostLease
from reputation_platform.infrastructure.db.tables import audit_logs, jobs, snapshots
from reputation_platform.infrastructure.network.safe_http import SafeHttpClient
from reputation_platform.worker.main import Worker
from sqlalchemy import func, select, text, update
from sqlalchemy.exc import DBAPIError

from tests.integration.test_public_identity_ingest import AUTH, capture, public_flow

__all__ = ["public_flow"]
pytestmark = pytest.mark.postgres


@pytest.fixture
def recovery_flow(public_flow):
    _, identity, responder, _ = public_flow
    clients = []

    def factory(**kwargs):
        client = SafeHttpClient.public_readonly(
            **kwargs, transport=httpx.MockTransport(responder), resolver=lambda host: ["1.1.1.1"],
        )
        clients.append(client)
        return client

    identity.client_factory = factory
    return public_flow, clients


def queued_refresh(flow, owner):
    api, identity, _, agent_id = flow
    response = api.post(f"/api/v1/agents/{agent_id}/refresh", json={}, headers=AUTH)
    assert response.status_code == 202, response.text
    queue = JobQueue(identity.db, owner)
    lease = queue.claim("ingest")
    assert lease is not None and str(lease.job_id) == response.json()["job_id"]
    return queue, lease


def admission_counts(identity):
    with identity.db.connect() as connection:
        return dict(connection.execute(
            select(audit_logs.c.target, func.count()).where(
                audit_logs.c.action == "public.egress",
                audit_logs.c.body["phase"].astext == "identity",
            ).group_by(audit_logs.c.target),
        ).all())


def test_eight_healthy_refreshes_get_separate_finite_budgets(recovery_flow):
    flow, clients = recovery_flow
    api, identity, responder, agent_id = flow
    results = []
    for _ in range(8):
        responder.block += 1
        result = capture(flow)
        assert result["snapshot_id"] is not None and result["reason_code"] is None
        results.append(result)
    assert len(responder.requests) == 80
    assert len(clients) == 8
    assert all(client._request_count == 10 and client.client.is_closed for client in clients)
    assert admission_counts(identity) == {UUID(result["id"]): 10 for result in results}
    history = api.get(f"/api/v1/agents/{agent_id}/snapshots").json()["items"]
    assert {snapshot["snapshot_id"] for snapshot in history} == {
        result["snapshot_id"] for result in results
    }
    assert api.get(f"/api/v1/agents/{agent_id}").json()["current_snapshot_id"] == results[-1]["snapshot_id"]
    with identity.db.connect() as connection:
        assert connection.scalar(select(func.count()).select_from(snapshots)) == 8
        assert connection.scalar(select(func.count()).select_from(audit_logs).where(
            audit_logs.c.action == "public.egress.complete",
            audit_logs.c.body["phase"].astext == "identity",
        )) == 16


def test_exhausted_session_reports_quota_then_new_approved_job_recovers(recovery_flow):
    flow, clients = recovery_flow
    api, identity, responder, agent_id = flow
    original = identity.client_factory

    def factory(**kwargs):
        client = original(**kwargs)
        if len(clients) == 1:
            client._request_count = 59
        return client

    identity.client_factory = factory
    exhausted = capture(flow)
    assert exhausted["snapshot_id"] is None
    assert exhausted["reason_code"] == "REQUEST_QUOTA_EXCEEDED"
    assert exhausted["public_identity"]["registration_outcome"] == "UNKNOWN"
    assert exhausted["public_identity"]["registration_reason"] == "PLATFORM_RPC_ERROR"
    assert exhausted["public_identity"]["metadata_reason"] == "MISSING_EVIDENCE"
    assert api.get(f"/api/v1/agents/{agent_id}").json()["status"] == "UNVERIFIED"
    assert len(responder.requests) == 5 and clients[0]._request_count == 64
    assert clients[0].public_stop_reason == "REQUEST_QUOTA_EXCEEDED"
    assert clients[0].client.is_closed
    restored = capture(flow)
    assert restored["snapshot_id"] is not None and restored["reason_code"] is None
    assert len(responder.requests) == 15 and len(clients) == 2
    assert clients[1]._request_count == 10 and clients[1].client.is_closed
    assert admission_counts(identity) == {UUID(exhausted["id"]): 5, UUID(restored["id"]): 10}


def test_concurrent_apis_only_admit_one_refresh_and_pending_duplicates_do_not_spend(recovery_flow):
    flow, clients = recovery_flow
    api, identity, responder, agent_id = flow
    barrier = Barrier(2)
    path = f"/api/v1/agents/{agent_id}/refresh"

    def refresh(client):
        barrier.wait(timeout=10)
        return client.post(path, json={}, headers=AUTH)

    with TestClient(create_app(identity.db, AUTH["Authorization"][7:])) as other:
        with ThreadPoolExecutor(max_workers=2) as executor:
            responses = list(executor.map(refresh, (api, other)))
    assert sorted(response.status_code for response in responses) == [202, 409]
    denied = next(response for response in responses if response.status_code == 409)
    assert denied.json()["error"]["code"] == "PUBLIC_REFRESH_PENDING"
    duplicate = api.post(path, json={}, headers=AUTH)
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "PUBLIC_REFRESH_PENDING"
    assert responder.requests == [] and clients == []
    with identity.db.connect() as connection:
        assert connection.scalar(select(func.count()).select_from(jobs).where(jobs.c.kind == "ingest")) == 1
    assert asyncio.run(Worker(identity.db, {"ingest": identity.ingest}).run_once())
    assert len(responder.requests) == 10 and len(clients) == 1


@pytest.mark.parametrize("saved", [False, True], ids=["before-result-save", "after-result-save"])
def test_restart_never_repeats_started_reads_or_duplicates_a_saved_snapshot(recovery_flow, monkeypatch, saved):
    flow, clients = recovery_flow
    api, identity, responder, _ = flow
    queue, lease = queued_refresh(flow, "interrupted-refresh")
    original = queue.fenced

    def interrupted(held, operation):
        if operation.__name__ == "save":
            if saved:
                original(held, operation)
            raise RuntimeError("simulated-refresh-save-crash")
        return original(held, operation)

    monkeypatch.setattr(queue, "fenced", interrupted)
    with pytest.raises(RuntimeError, match="simulated-refresh-save-crash"):
        asyncio.run(identity.ingest(lease, queue))
    assert len(responder.requests) == 10 and clients[0].client.is_closed
    before = api.get(f"/api/v1/jobs/{lease.job_id}", headers=AUTH).json()
    before_counts = admission_counts(identity)
    queue.retry(lease, "WORKER_HANDLER_ERROR", delay_seconds=0)
    restarted = IdentityService(identity.db, client_factory=identity.client_factory)
    restarted.evidence = identity.evidence
    assert asyncio.run(Worker(identity.db, {"ingest": restarted.ingest}).run_once())
    result = api.get(f"/api/v1/jobs/{lease.job_id}", headers=AUTH).json()
    assert result["state"] == "SUCCEEDED"
    assert len(responder.requests) == 10 and len(clients) == 1
    assert admission_counts(identity) == before_counts
    with identity.db.connect() as connection:
        assert connection.scalar(select(func.count()).select_from(snapshots)) == int(saved)
    if saved:
        assert result["snapshot_id"] == before["snapshot_id"]
        assert result["public_identity"] == before["public_identity"]
    else:
        assert result["snapshot_id"] is None
        assert result["public_identity"]["registration_reason"] == "DISPATCH_UNCERTAIN"


def test_database_start_failure_spends_nothing_and_same_job_can_retry(recovery_flow, monkeypatch):
    flow, clients = recovery_flow
    api, identity, responder, _ = flow
    queue, lease = queued_refresh(flow, "database-start-failure")
    original = queue.fenced

    def failing(held, operation):
        if operation.__name__ == "start_read":
            return original(held, lambda connection: connection.execute(text("SELECT 1 / 0")))
        return original(held, operation)

    monkeypatch.setattr(queue, "fenced", failing)
    with pytest.raises(DBAPIError):
        asyncio.run(identity.ingest(lease, queue))
    assert responder.requests == [] and clients == [] and admission_counts(identity) == {}
    with identity.db.connect() as connection:
        payload = connection.scalar(select(jobs.c.payload).where(jobs.c.id == lease.job_id))
        assert not payload.get("public_read_started")
    queue.retry(lease, "WORKER_HANDLER_ERROR", delay_seconds=0)
    monkeypatch.setattr(queue, "fenced", original)
    assert asyncio.run(Worker(identity.db, {"ingest": identity.ingest}).run_once())
    result = api.get(f"/api/v1/jobs/{lease.job_id}", headers=AUTH).json()
    assert result["state"] == "SUCCEEDED" and result["snapshot_id"] is not None
    assert len(responder.requests) == 10 and len(clients) == 1 and clients[0].client.is_closed


def test_cancellation_at_socket_boundary_closes_the_client(recovery_flow):
    flow, clients = recovery_flow
    _, identity, responder, _ = flow
    queue, lease = queued_refresh(flow, "cancelled-refresh")
    factory = identity.client_factory

    async def cancelled():
        started = asyncio.Event()

        def waiting_factory(**kwargs):
            guard = kwargs["before_request"]

            async def before(*args):
                await guard(*args)
                started.set()
                await asyncio.Future()

            kwargs["before_request"] = before
            return factory(**kwargs)

        identity.client_factory = waiting_factory
        task = asyncio.create_task(identity.ingest(lease, queue))
        await asyncio.wait_for(started.wait(), timeout=10)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(cancelled())
    assert responder.requests == [] and len(clients) == 1 and clients[0].client.is_closed
    assert admission_counts(identity) == {lease.job_id: 1}


def test_lost_lease_at_socket_boundary_never_dispatches_and_closes_the_client(recovery_flow):
    flow, clients = recovery_flow
    _, identity, responder, _ = flow
    queue, lease = queued_refresh(flow, "stale-refresh")
    factory = identity.client_factory

    def stale_factory(**kwargs):
        guard = kwargs["before_request"]

        async def before(*args):
            with identity.db.begin() as connection:
                connection.execute(update(jobs).where(jobs.c.id == lease.job_id).values(
                    lease_token=lease.token + 1,
                ))
            await guard(*args)

        kwargs["before_request"] = before
        return factory(**kwargs)

    identity.client_factory = stale_factory
    with pytest.raises(LostLease):
        asyncio.run(identity.ingest(lease, queue))
    assert responder.requests == [] and len(clients) == 1 and clients[0].client.is_closed
    assert admission_counts(identity) == {}
    with identity.db.connect() as connection:
        assert connection.scalar(select(func.count()).select_from(snapshots)) == 0
