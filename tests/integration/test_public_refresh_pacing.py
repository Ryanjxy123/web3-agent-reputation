"""New refresh sessions retain PostgreSQL pacing and share public RPC origin locks."""

import asyncio
import hashlib
import threading
import time
from uuid import UUID, uuid4

import httpx
import pytest
from reputation_core.models.public_evaluation import PublicReadonlyRunPlan
from reputation_platform.application.identity import IdentityService
from reputation_platform.application.public_execution import PublicReadonlyEgress
from reputation_platform.infrastructure.db.jobs import JobQueue
from reputation_platform.infrastructure.db.tables import audit_logs, runs
from reputation_platform.infrastructure.network import safe_http
from reputation_platform.infrastructure.network.safe_http import SafeHttpClient
from sqlalchemy import event, func, select
from sqlalchemy.exc import DBAPIError

from tests.integration.test_public_evaluation_flow import (
    AUTH as EVALUATION_AUTH,
)
from tests.integration.test_public_evaluation_flow import (
    create_run,
)
from tests.integration.test_public_evaluation_flow import (
    flow as evaluation_flow,
)
from tests.integration.test_public_identity_ingest import AUTH, capture, public_flow
from tests.unit.test_erc8004_reader import RegistryResponder

__all__ = ["evaluation_flow", "public_flow"]

pytestmark = pytest.mark.postgres


def test_new_service_and_worker_preserve_completed_refresh_gap(public_flow, monkeypatch):
    api, service, responder, agent_id = public_flow
    monkeypatch.setattr(safe_http, "PUBLIC_REQUEST_INTERVAL", 1)
    responder.change = lambda payload, result: None
    starts, completed, clients = [], [], []

    async def transport(request):
        starts.append(time.monotonic())
        response = responder(request)
        completed.append(time.monotonic())
        return response

    def factory(**kwargs):
        client = SafeHttpClient.public_readonly(
            transport=httpx.MockTransport(transport), resolver=lambda _: ["1.1.1.1"], **kwargs
        )
        clients.append(client)
        return client

    service.client_factory = factory
    first = capture(public_flow)
    restarted = IdentityService(
        service.db, evidence_root=service.evidence.root, client_factory=factory
    )
    second = capture((api, restarted, responder, agent_id))

    assert first["id"] != second["id"] and len(responder.requests) == 2
    assert first["snapshot_id"] is None and second["snapshot_id"] is None
    assert clients[0] is not clients[1] and all(client.client.is_closed for client in clients)
    assert starts[1] - completed[0] >= 0.95
    with service.db.connect() as connection:
        events = connection.execute(
            select(audit_logs.c.target, audit_logs.c.body).where(
                audit_logs.c.action == "public.egress", audit_logs.c.body["phase"].astext == "identity"
            )
        ).all()
    assert {target for target, _ in events} == {UUID(first["id"]), UUID(second["id"])}
    assert len(events) == 2


def test_identity_refresh_shares_rpc_guard_lock_and_completion_gap(evaluation_flow, monkeypatch):
    api, identity, responder, _, snapshot_id = evaluation_flow
    monkeypatch.setattr(safe_http, "PUBLIC_REQUEST_INTERVAL", 1)
    run_id, _, _ = create_run(evaluation_flow)
    with identity.db.connect() as connection:
        row = connection.execute(select(runs).where(runs.c.id == run_id)).mappings().one()
    slot = PublicReadonlyRunPlan.model_validate(row["plan"]).slots[0]
    agent_ref = api.get(f"/api/v1/snapshots/{snapshot_id}").json()["core"]["agent_ref"]
    # The API's existing registered agent is identified by its immutable reference.
    agent_id = next(
        item["id"] for item in api.get("/api/v1/agents").json()["items"]
        if item["agent_ref"] == agent_ref
    )
    refresh = api.post(f"/api/v1/agents/{agent_id}/refresh", json={}, headers=EVALUATION_AUTH)
    assert refresh.status_code == 202, refresh.text
    queue = JobQueue(identity.db, "identity-pacing-test")
    lease = queue.claim("ingest")
    assert lease is not None and str(lease.job_id) == refresh.json()["job_id"]
    identity_responder = RegistryResponder()
    identity_responder.change = lambda payload, result: None
    active, maximum = 0, 0
    started, completed = {}, {}

    async def scenario():
        evaluation_inflight = asyncio.Event()

        async def transport(request, phase):
            nonlocal active, maximum
            active += 1
            maximum = max(maximum, active)
            started[phase] = time.monotonic()
            if phase == "rpc":
                evaluation_inflight.set()
                await asyncio.sleep(0.2)
                response = responder(request)
            else:
                response = identity_responder(request)
            completed[phase] = time.monotonic()
            active -= 1
            return response

        def factory(**kwargs):
            return SafeHttpClient.public_readonly(
                transport=httpx.MockTransport(lambda request: transport(request, "identity")),
                resolver=lambda _: ["1.1.1.1"], **kwargs
            )

        restarted = IdentityService(
            identity.db, evidence_root=identity.evidence.root, client_factory=factory
        )

        async def evaluation_read():
            guard = PublicReadonlyEgress(identity.db, identity, row, slot, phase="verify")
            client = SafeHttpClient.public_readonly(
                enabled=True, before_request=guard,
                transport=httpx.MockTransport(lambda request: transport(request, "rpc")),
                resolver=lambda _: ["1.1.1.1"]
            )
            try:
                async with guard:
                    await client.request(
                        "POST", safe_http.PUBLIC_RPC_ORIGIN, "/",
                        json={"jsonrpc": "2.0", "id": 1, "method": "eth_chainId", "params": []}
                    )
            finally:
                await client.close()

        async def identity_read():
            # Start after the authorized evaluation socket has entered its transport.
            await evaluation_inflight.wait()
            await restarted.ingest(lease, queue)

        async with asyncio.timeout(10):
            await asyncio.gather(evaluation_read(), identity_read())

    asyncio.run(scenario())
    queue.complete(lease)
    job = api.get(f"/api/v1/jobs/{lease.job_id}", headers=EVALUATION_AUTH).json()
    assert job["state"] == "SUCCEEDED" and job["snapshot_id"] is None
    assert maximum == 1 and len(identity_responder.requests) == len(responder.requests) == 1
    assert started["identity"] - completed["rpc"] >= 0.95
    with identity.db.connect() as connection:
        events = list(connection.scalars(select(audit_logs.c.body).where(
            audit_logs.c.action == "public.egress", audit_logs.c.target.in_([run_id, lease.job_id])
        )))
    assert {event["phase"] for event in events} == {"verify", "identity"}
    assert len(events) == 2


def test_cancelled_lock_acquisition_releases_postgres_session_lock(db):
    origin = safe_http.PUBLIC_RPC_ORIGIN
    key = int.from_bytes(hashlib.sha256(origin.encode()).digest()[:8], "big", signed=True)
    acquired, resume = threading.Event(), threading.Event()
    guard = PublicReadonlyEgress(db, IdentityService(db), {"id": uuid4()}, None, origin=origin)
    witness = db.connect().execution_options(isolation_level="AUTOCOMMIT")

    def pause_after_acquisition(connection, cursor, statement, parameters, context, executemany):
        if "pg_try_advisory_lock" in statement and connection is not witness:
            acquired.set()
            assert resume.wait(5), "test did not release the completed PostgreSQL call"

    event.listen(db, "after_cursor_execute", pause_after_acquisition)

    async def cancel_at_acquisition():
        task = asyncio.create_task(guard.__aenter__())
        try:
            assert await asyncio.to_thread(acquired.wait, 3)
            task.cancel()
            resume.set()
            with pytest.raises(asyncio.CancelledError):
                await task
        finally:
            resume.set()
            if not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)

    try:
        asyncio.run(cancel_at_acquisition())
        assert witness.scalar(select(func.pg_try_advisory_lock(key))), (
            "cancelled acquisition left an origin lock held by a pooled PostgreSQL session"
        )
    finally:
        resume.set()
        event.remove(db, "after_cursor_execute", pause_after_acquisition)
        witness.scalar(select(func.pg_advisory_unlock_all()))
        witness.close()
        # Close any returned session, including a leaked lock from the regression under test.
        db.dispose()


def test_failed_completion_audit_preserves_gap_and_propagates_db_error(public_flow, monkeypatch):
    api, identity, responder, agent_id = public_flow
    monkeypatch.setattr(safe_http, "PUBLIC_REQUEST_INTERVAL", 1)
    refresh = api.post(f"/api/v1/agents/{agent_id}/refresh", json={}, headers=AUTH)
    assert refresh.status_code == 202, refresh.text
    queue = JobQueue(identity.db, "completion-failure-test")
    lease = queue.claim("ingest")
    assert lease is not None
    responder.change = lambda payload, result: None
    starts, completed = [], []
    original_audit = identity.audit
    failed = False

    def fail_completion(connection, actor, action, target, body):
        nonlocal failed
        if action == "public.egress.complete" and not failed:
            failed = True
            connection.exec_driver_sql("SELECT 1 / 0")
        return original_audit(connection, actor, action, target, body)

    monkeypatch.setattr(identity, "audit", fail_completion)

    async def transport(request):
        starts.append(time.monotonic())
        if len(starts) == 1:
            # The start audit is already older than the interval when this socket finishes.
            await asyncio.sleep(1.05)
        response = responder(request)
        completed.append(time.monotonic())
        return response

    async def read():
        guard = PublicReadonlyEgress(
            identity.db, identity, {"id": lease.job_id}, None,
            lease=lease, queue=queue, phase="identity", origin=safe_http.PUBLIC_RPC_ORIGIN
        )
        client = SafeHttpClient.public_readonly(
            enabled=True, before_request=guard,
            transport=httpx.MockTransport(transport), resolver=lambda _: ["1.1.1.1"]
        )
        try:
            async with guard:
                await client.request(
                    "POST", safe_http.PUBLIC_RPC_ORIGIN, "/",
                    json={"jsonrpc": "2.0", "id": 1, "method": "eth_chainId", "params": []}
                )
        finally:
            await client.close()

    async def scenario():
        with pytest.raises(DBAPIError):
            await read()
        await read()

    asyncio.run(scenario())
    assert failed and len(responder.requests) == 2
    assert starts[1] - completed[0] >= 0.95
    with identity.db.connect() as connection:
        events = list(connection.scalars(select(audit_logs.c.action).where(
            audit_logs.c.target == lease.job_id,
            audit_logs.c.action.in_(["public.egress", "public.egress.complete"])
        )))
    assert events.count("public.egress") == 2 and events.count("public.egress.complete") == 1
