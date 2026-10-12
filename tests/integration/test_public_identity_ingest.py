"""Public snapshots reuse real PostgreSQL, fenced ingest jobs and immutable history."""

import asyncio
import json
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi.testclient import TestClient
from reputation_core.evidence import hash_json
from reputation_core.models import AgentSnapshot, EvidenceRecord, Outcome
from reputation_platform.adapters.registries.erc8004 import AKASHI_REF, Erc8004RegistryReader
from reputation_platform.api.app import create_app
from reputation_platform.application.errors import ApplicationError
from reputation_platform.infrastructure import evidence_store
from reputation_platform.infrastructure.db.jobs import JobQueue
from reputation_platform.infrastructure.db.tables import bindings, evidence_blobs, jobs, snapshots
from reputation_platform.infrastructure.evidence_store import EvidenceStore
from reputation_platform.infrastructure.network.safe_http import SafeHttpClient
from reputation_platform.worker.main import Worker
from sqlalchemy import func, insert, select, update

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


def test_url_credentials_never_reach_new_snapshot_or_public_response(public_flow):
    api, service, responder, agent_id = public_flow
    first = capture(public_flow)
    safe_snapshot = api.get(f"/api/v1/snapshots/{first['snapshot_id']}")
    assert safe_snapshot.status_code == 200
    secret = "AUDIT_FAKE_CREDENTIAL_ONLY"
    metadata = json.loads(responder.registration)
    metadata["description"] = (
        f"Connection example https://audit-user:{secret}@anchor.akashi-notari.com/mcp"
    )
    responder.registration = json.dumps(metadata).encode()
    second = capture(public_flow)
    assert second["snapshot_id"] is None
    assert second["public_identity"]["metadata_outcome"] == "UNKNOWN"
    assert secret not in json.dumps(second)
    assert api.get(f"/api/v1/snapshots/{first['snapshot_id']}").json() == safe_snapshot.json()
    history = api.get(f"/api/v1/agents/{agent_id}/snapshots")
    assert history.status_code == 200 and secret not in history.text
    assert len(history.json()["items"]) == 1
    with service.db.connect() as connection:
        bodies = connection.execute(select(evidence_blobs.c.body)).scalars().all()
    assert all(secret not in json.dumps(body) for body in bodies)
    assert all(secret.encode() not in service.evidence.read(EvidenceRecord.model_validate(body))
               for body in bodies)


@pytest.mark.parametrize("location", ["nested_value", "dictionary_key", "public_identity"])
def test_historical_sensitive_snapshot_public_reads_fail_closed(public_flow, location):
    api, service, _, agent_id = public_flow
    first = capture(public_flow)
    safe = api.get(f"/api/v1/snapshots/{first['snapshot_id']}").json()
    historical = json.loads(json.dumps(safe))
    secret = "HISTORICAL_SYNTHETIC_CREDENTIAL_ONLY"
    url = f"https://audit-user:{secret}@anchor.akashi-notari.com/mcp"
    historical["snapshot_id"] = str(uuid4())
    if location == "nested_value":
        historical["core"]["normalized_metadata"]["legacy"] = {"examples": [url]}
    elif location == "dictionary_key":
        historical["core"]["normalized_metadata"][url] = "historical example"
    else:
        historical["public_identity"]["metadata"]["description"] = url
    historical["core"]["metadata_hash"] = hash_json(historical["core"]["normalized_metadata"])
    historical["snapshot_hash"] = hash_json({
        "core": historical["core"], "public_identity": historical["public_identity"],
    })
    AgentSnapshot.model_validate(historical)
    identifier = UUID(historical["snapshot_id"])
    # Append a synthetic legacy revision; never overwrite an immutable captured snapshot.
    with service.db.begin() as connection:
        connection.execute(insert(snapshots).values(
            id=identifier, agent_fk=UUID(agent_id), snapshot_hash=historical["snapshot_hash"],
            body=historical,
        ))
    for path, params in (
        (f"/api/v1/snapshots/{identifier}", {}),
        (f"/api/v1/agents/{agent_id}/snapshots", {}),
        (f"/api/v1/snapshots/{identifier}/readonly-association",
         {"protocol": "akashi-mcp-readonly-v1"}),
    ):
        response = api.get(path, params=params)
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "HISTORICAL_EVIDENCE_RESTRICTED"
        assert secret not in response.text
    assert api.get(f"/api/v1/snapshots/{first['snapshot_id']}").json() == safe
    older = api.get(f"/api/v1/agents/{agent_id}/snapshots", params={"cursor": str(identifier)})
    assert older.status_code == 200 and older.json()["items"] == [safe]
    with service.db.connect() as connection:
        stored = connection.execute(select(snapshots.c.body, snapshots.c.snapshot_hash).where(
            snapshots.c.id == identifier,
        )).one()
    assert stored.body == historical and stored.snapshot_hash == historical["snapshot_hash"]
    assert service.snapshot(identifier).model_dump(mode="json") == historical


def test_historical_sensitive_cas_association_is_restricted(public_flow, monkeypatch):
    api, service, _, agent_id = public_flow
    first = capture(public_flow)
    historical = api.get(f"/api/v1/snapshots/{first['snapshot_id']}").json()
    secret = "HISTORICAL_CAS_SYNTHETIC_CREDENTIAL_ONLY"
    content = {"legacy": [{"example": f"https://audit-user:{secret}@example.com"}]}
    with monkeypatch.context() as legacy:
        legacy.setattr(evidence_store, "redact", lambda value: value)
        extra = service.evidence.prepare_json(
            content, "legacy-synthetic", historical["core"]["captured_at"], "test",
        )
    original_bytes = service.evidence.read(extra)
    historical["snapshot_id"] = str(uuid4())
    historical["core"]["normalized_metadata"]["legacy_cas_hash"] = extra.blob_hash
    historical["core"]["metadata_hash"] = hash_json(historical["core"]["normalized_metadata"])
    historical["snapshot_hash"] = hash_json({
        "core": historical["core"], "public_identity": historical["public_identity"],
    })
    identifier = UUID(historical["snapshot_id"])
    with service.db.begin() as connection:
        extra = service.evidence.register(connection, extra)
        historical["evidence_refs"].append(str(extra.evidence_id))
        connection.execute(insert(snapshots).values(
            id=identifier, agent_fk=UUID(agent_id), snapshot_hash=historical["snapshot_hash"],
            body=historical,
        ))
    assert api.get(f"/api/v1/snapshots/{identifier}").status_code == 200
    response = api.get(f"/api/v1/snapshots/{identifier}/readonly-association",
                       params={"protocol": "akashi-mcp-readonly-v1"})
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "HISTORICAL_EVIDENCE_RESTRICTED"
    assert secret not in response.text
    assert service.evidence.read(extra) == original_bytes
    assert service.snapshot(identifier).model_dump(mode="json") == historical
