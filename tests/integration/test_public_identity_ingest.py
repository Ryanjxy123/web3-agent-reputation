"""Public snapshots reuse real PostgreSQL, fenced ingest jobs and immutable history."""

import asyncio
from uuid import UUID

import httpx
import pytest
from fastapi.testclient import TestClient
from reputation_core.models import Outcome
from reputation_platform.adapters.registries.erc8004 import AKASHI_REF, Erc8004RegistryReader
from reputation_platform.api.app import create_app
from reputation_platform.application.errors import ApplicationError
from reputation_platform.infrastructure.db.jobs import JobQueue
from reputation_platform.infrastructure.db.tables import bindings, evidence_blobs, jobs, snapshots
from reputation_platform.infrastructure.evidence_store import EvidenceStore
from reputation_platform.infrastructure.network.safe_http import SafeHttpClient
from reputation_platform.worker.main import Worker
from sqlalchemy import func, select, update

from tests.unit.test_erc8004_reader import ROOT, RegistryResponder

pytestmark = pytest.mark.postgres
AUTH = {"Authorization": "Bearer public-identity-test-token-at-least-32"}


@pytest.fixture
def public_flow(db, tmp_path, monkeypatch):
    from reputation_platform.infrastructure.network import safe_http
    monkeypatch.setenv("PUBLIC_READONLY_ENABLED", "1")
    monkeypatch.setattr(safe_http, "PUBLIC_REQUEST_INTERVAL", 0)
    app = create_app(db, AUTH["Authorization"][7:])
    service = app.state.identity
    service.evidence = EvidenceStore(tmp_path)
    responder = RegistryResponder()
    client = SafeHttpClient.public_readonly(enabled=True, transport=httpx.MockTransport(responder),
                                           resolver=lambda host: ["1.1.1.1"])
    service._public_reader = Erc8004RegistryReader(ROOT, client, service.evidence)
    with TestClient(app) as api:
        agent = api.post("/api/v1/agents", json={"agent_ref": AKASHI_REF.model_dump()}, headers=AUTH).json()
        yield api, service, responder, agent["id"]
    asyncio.run(client.close())


def capture(flow):
    api, service, _, agent_id = flow
    response = api.post(f"/api/v1/agents/{agent_id}/refresh", json={}, headers=AUTH)
    assert response.status_code == 202, response.text
    job_id = response.json()["job_id"]
    assert asyncio.run(Worker(service.db, {"ingest": service.ingest}).run_once())
    job = api.get(f"/api/v1/jobs/{job_id}", headers=AUTH).json()
    assert job["state"] == "SUCCEEDED", job
    return job


def test_public_snapshot_association_owner_change_and_history(public_flow):
    api, service, responder, agent_id = public_flow
    first = capture(public_flow)
    snapshot = api.get(f"/api/v1/snapshots/{first['snapshot_id']}").json()
    assert snapshot["core"]["declared_executor"] is None
    for protocol in ("akashi-http-readonly-v1", "akashi-mcp-readonly-v1"):
        association = api.get(f"/api/v1/snapshots/{first['snapshot_id']}/readonly-association",
                              params={"protocol": protocol})
        assert association.status_code == 200, association.text
        assert association.json()["registration_outcome"] == association.json()["endpoint_outcome"] == "PASS"
        assert association.json()["executor_outcome"] == association.json()["business_outcome"] == "UNKNOWN"
    with pytest.raises(ApplicationError, match="executor control"):
        service.current_identity(service.snapshot(UUID(first["snapshot_id"])))
    responder.owner, responder.block = "0x" + "34" * 20, 101
    second = capture(public_flow)
    latest = api.get(f"/api/v1/snapshots/{second['snapshot_id']}").json()
    assert latest["snapshot_hash"] != snapshot["snapshot_hash"]
    assert latest["core"]["owner"] != snapshot["core"]["owner"]
    assert api.get(f"/api/v1/snapshots/{first['snapshot_id']}").json() == snapshot
    assert api.get(f"/api/v1/agents/{agent_id}").json()["current_snapshot_id"] == second["snapshot_id"]
    stale = api.get(f"/api/v1/snapshots/{first['snapshot_id']}/readonly-association",
                    params={"protocol": "akashi-mcp-readonly-v1"})
    assert stale.status_code == 409 and stale.json()["error"]["code"] == "STALE_SNAPSHOT"
    with service.db.connect() as connection:
        assert connection.execute(select(func.count()).select_from(snapshots)).scalar_one() == 2
        assert connection.execute(select(func.count()).select_from(bindings)).scalar_one() == 0
        payload = connection.execute(select(jobs.c.payload).where(jobs.c.id == UUID(second["id"]))).scalar_one()
        assert payload["previous_snapshot_hash"] == snapshot["snapshot_hash"]
        assert connection.execute(select(func.count()).select_from(evidence_blobs)).scalar_one() > 0


def test_unknown_rpc_is_explicit_without_snapshot_or_repeated_calls(public_flow):
    api, service, responder, agent_id = public_flow
    responder.change = lambda payload, result: None
    job = capture(public_flow)
    assert job["snapshot_id"] is None
    assert job["public_identity"]["registration_outcome"] == Outcome.UNKNOWN
    assert api.get(f"/api/v1/agents/{agent_id}").json()["status"] == "UNVERIFIED"
    attempts = len(responder.requests)
    queue = JobQueue(service.db, "recovered-ingest")
    with service.db.begin() as connection:
        connection.execute(update(jobs).where(jobs.c.id == UUID(job["id"])).values(state="QUEUED"))
    lease = queue.claim()
    assert lease is not None
    asyncio.run(service.ingest(lease, queue))
    assert len(responder.requests) == attempts


def test_public_refresh_disabled_pending_and_auth(public_flow):
    api, service, _, agent_id = public_flow
    assert api.post(f"/api/v1/agents/{agent_id}/refresh", json={}).status_code == 401
    service.public_readonly_enabled = False
    rejected = api.post(f"/api/v1/agents/{agent_id}/refresh", json={}, headers=AUTH)
    assert rejected.status_code == 409 and rejected.json()["error"]["code"] == "PUBLIC_READONLY_DISABLED"
    service.public_readonly_enabled = True
    assert api.post(f"/api/v1/agents/{agent_id}/refresh", json={}, headers=AUTH).status_code == 202
    duplicate = api.post(f"/api/v1/agents/{agent_id}/refresh", json={}, headers=AUTH)
    assert duplicate.status_code == 409 and duplicate.json()["error"]["code"] == "PUBLIC_REFRESH_PENDING"


def test_unverified_refresh_invalidates_current_association_but_keeps_history(public_flow):
    api, service, responder, agent_id = public_flow
    first = capture(public_flow)
    before = api.get(f"/api/v1/snapshots/{first['snapshot_id']}").json()
    responder.owner = "0x" + "34" * 20
    responder.uri = "https://attacker.example/changed"
    responder.block += 1
    second = capture(public_flow)
    assert second["snapshot_id"] is None and second["public_identity"]["metadata_outcome"] == "UNKNOWN"
    assert api.get(f"/api/v1/agents/{agent_id}").json()["status"] == "UNVERIFIED"
    assert api.get(f"/api/v1/snapshots/{first['snapshot_id']}").json() == before
    association = api.get(f"/api/v1/snapshots/{first['snapshot_id']}/readonly-association",
                          params={"protocol": "akashi-mcp-readonly-v1"}).json()
    assert association["registration_outcome"] == association["endpoint_outcome"] == "UNKNOWN"
    with service.db.begin() as connection:
        with pytest.raises(ApplicationError, match="newer public identity"):
            service.require_current(connection, UUID(first["snapshot_id"]))


def test_crash_after_public_response_recovers_unknown_without_resend(public_flow, monkeypatch):
    api, service, responder, agent_id = public_flow
    response = api.post(f"/api/v1/agents/{agent_id}/refresh", json={}, headers=AUTH)
    job_id = UUID(response.json()["job_id"])
    queue = JobQueue(service.db, "interrupted-public-read")
    lease = queue.claim()
    assert lease is not None
    original = queue.fenced
    count = 0
    def interrupted(lease, operation):
        nonlocal count
        count += 1
        if count == 2:
            raise RuntimeError("simulated-crash-after-response")
        return original(lease, operation)
    monkeypatch.setattr(queue, "fenced", interrupted)
    with pytest.raises(RuntimeError, match="simulated-crash"):
        asyncio.run(service.ingest(lease, queue))
    assert len(responder.requests) == 10
    monkeypatch.setattr(queue, "fenced", original)
    asyncio.run(service.ingest(lease, queue))
    assert len(responder.requests) == 10
    queue.complete(lease)
    job = api.get(f"/api/v1/jobs/{job_id}", headers=AUTH).json()
    assert job["snapshot_id"] is None
    assert job["public_identity"]["registration_reason"] == "DISPATCH_UNCERTAIN"
