"""Identity flow through authenticated API, real PostgreSQL leases and real Anvil reads."""

import asyncio
import base64
import copy
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from eth_account import Account
from eth_account.messages import encode_typed_data
from fastapi.testclient import TestClient
from reputation_core.binding import signatures_match
from reputation_core.evidence import canonical_bytes, hash_json
from reputation_core.models import ExecutorBinding
from reputation_platform.api.app import create_app
from reputation_platform.application.local_deploy import SetupJournal, contract_abi, deploy
from reputation_platform.application.local_seed import seed
from reputation_platform.infrastructure.db.jobs import JobQueue
from reputation_platform.infrastructure.db.tables import (
    binding_challenges,
    bindings,
    evidence_blobs,
    jobs,
    snapshots,
)
from reputation_platform.infrastructure.evidence_store import EvidenceStore
from reputation_platform.worker.main import Worker
from sqlalchemy import func, select, update
from web3 import Web3
from web3.types import RPCEndpoint

from tests.integration.test_fixture_agents import ROOT, anvil_node

pytestmark = [pytest.mark.chain, pytest.mark.postgres]
TOKEN = "identity-test-operator-token-at-least-32"
AUTH = {"Authorization": f"Bearer {TOKEN}"}


@pytest.fixture(scope="module")
def identity_chain(tmp_path_factory):
    with anvil_node() as (url, web3):
        runtime = tmp_path_factory.mktemp("identity-chain")
        deployment = deploy(ROOT, url, runtime)
        samples = seed(ROOT, deployment, runtime)
        keys = json.loads((runtime / "setup-secrets.json").read_bytes())["keys"]
        yield deployment, samples, keys, web3


@pytest.fixture
def flow(db, identity_chain, tmp_path):
    deployment, samples, keys, web3 = identity_chain
    checkpoint = web3.provider.make_request(RPCEndpoint("evm_snapshot"), [])["result"]
    app = create_app(db, TOKEN, deployment)
    app.state.identity.evidence = EvidenceStore(tmp_path / "evidence")
    with TestClient(app) as client:
        yield client, app.state.identity, samples, keys, web3, deployment, tmp_path
    assert web3.provider.make_request(RPCEndpoint("evm_revert"), [checkpoint])["result"]


def capture(flow, sample="a", agent_id=None):
    client, service, samples, *_ = flow
    if agent_id is None:
        response = client.post(
            "/api/v1/agents", json={"agent_ref": samples[sample]["agent_ref"]}, headers=AUTH
        )
        assert response.status_code == 201, response.text
        assert response.json()["status"] == "UNVERIFIED"
        assert response.json()["source_type"] == "controlled"
        agent_id = response.json()["id"]
    response = client.post(f"/api/v1/agents/{agent_id}/refresh", json={}, headers=AUTH)
    assert response.status_code == 202, response.text
    job_id = response.json()["job_id"]
    worker = Worker(service.db, {"ingest": service.ingest})
    assert asyncio.run(worker.run_once())
    job = client.get(f"/api/v1/jobs/{job_id}", headers=AUTH).json()
    assert job["state"] == "SUCCEEDED", job
    snapshot = client.get(f"/api/v1/snapshots/{job['snapshot_id']}").json()
    assert snapshot["snapshot_hash"] == hash_json(snapshot["core"])
    assert snapshot["evidence_refs"]
    return agent_id, snapshot, job_id


def confirm(flow, snapshot):
    response = flow[0].post(
        f"/api/v1/snapshots/{snapshot['snapshot_id']}/claims/confirm",
        headers=AUTH,
        json={
            "confirmed_claims": ["anchor_record"],
            "reason": "Operator checked controlled metadata",
            "expected_review_version": 0,
        },
    )
    assert response.status_code == 200, response.text
    return response


def challenge(flow, snapshot, sample="a"):
    confirm(flow, snapshot)
    response = flow[0].post(
        f"/api/v1/snapshots/{snapshot['snapshot_id']}/bindings/challenge",
        headers=AUTH,
        json={
            "executor": flow[2][sample]["executor"],
            "endpoint_id": f"fixture-{sample}",
            "execution_chain_key": "local-demo",
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def signed(flow, challenge, sample="a"):
    return {
        "challenge_id": challenge["challenge_id"],
        **{
            f"{role}_signature": Account.sign_message(
                encode_typed_data(full_message=challenge[f"{role}_typed_data"]),
                flow[3][f"{role}-{sample}"],
            ).signature.to_0x_hex()
            for role in ("owner", "executor")
        },
    }


def verify(flow, snapshot, body):
    return flow[0].post(
        f"/api/v1/snapshots/{snapshot['snapshot_id']}/bindings/verify", headers=AUTH, json=body
    )


def test_real_dual_signatures_evidence_and_single_use_nonce(flow):
    agent_id, snapshot, _ = capture(flow)
    assert flow[0].get(f"/api/v1/agents/{agent_id}/snapshots").json() == {"items": [snapshot], "next_cursor": None}
    request = signed(flow, challenge(flow, snapshot))
    result = verify(flow, snapshot, request)
    assert result.status_code == 200, result.text
    proof = ExecutorBinding.model_validate(result.json())
    assert proof.status == "VERIFIED" and signatures_match(proof)
    assert len(proof.verification_evidence) == 2
    with flow[1].db.connect() as connection:
        records = connection.execute(select(evidence_blobs.c.body)).scalars().all()
    from reputation_core.models import EvidenceRecord

    for record in records:
        assert flow[1].evidence.read(EvidenceRecord.model_validate(record))
    assert verify(flow, snapshot, request).json()["error"]["code"] == "NONCE_CONSUMED"
    assert (
        flow[0].get(f"/api/v1/agents/{agent_id}").json()["current_snapshot_id"]
        == snapshot["snapshot_id"]
    )
    assert flow[0].post(f"/api/v1/agents/{agent_id}/refresh", json={}).status_code == 401


@pytest.mark.parametrize(
    "mutation", ["endpoint", "nonce", "chain", "agent", "role", "signer", "invalid"]
)
def test_signature_context_tampering_is_rejected(flow, mutation):
    _, snapshot, _ = capture(flow)
    original = challenge(flow, snapshot)
    modified = copy.deepcopy(original)
    for role in ("owner", "executor"):
        message = modified[f"{role}_typed_data"]["message"]
        if mutation in {"endpoint", "nonce", "agent"}:
            field = {"endpoint": "endpointHash", "nonce": "nonce", "agent": "agentKeyHash"}[
                mutation
            ]
            message[field] = "0x" + "ab" * 32
        elif mutation == "chain":
            modified[f"{role}_typed_data"]["domain"]["chainId"] = "31338"
        elif mutation == "role":
            message["signerRole"] = 2 if role == "owner" else 1
    request = signed(flow, modified, sample="d" if mutation == "signer" else "a")
    if mutation == "invalid":
        request["owner_signature"] = "0x" + "00" * 65
    response = verify(flow, snapshot, request)
    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == "SIGNATURE_INVALID"
    # Invalid attempts cannot consume a valid outstanding challenge.
    assert verify(flow, snapshot, signed(flow, original)).status_code == 200


def test_expired_nonce_wrong_snapshot_and_endpoint_rejected(flow):
    _, snapshot, _ = capture(flow)
    _, other, _ = capture(flow, "d")
    issued = challenge(flow, snapshot)
    request = signed(flow, issued)
    assert verify(flow, other, request).json()["error"]["code"] == "BINDING_CONTEXT_MISMATCH"
    response = flow[0].post(
        f"/api/v1/snapshots/{snapshot['snapshot_id']}/bindings/challenge",
        headers=AUTH,
        json={
            "executor": flow[2]["a"]["executor"],
            "endpoint_id": "fixture-d",
            "execution_chain_key": "local-demo",
        },
    )
    assert response.json()["error"]["code"] == "BINDING_CONTEXT_MISMATCH"
    with flow[1].db.begin() as connection:
        connection.execute(
            update(binding_challenges)
            .where(binding_challenges.c.id == UUID(issued["challenge_id"]))
            .values(deadline=datetime.now(UTC) - timedelta(seconds=1))
        )
    assert verify(flow, snapshot, request).json()["error"]["code"] == "NONCE_EXPIRED"


def test_concurrent_verification_consumes_nonce_once(flow):
    _, snapshot, _ = capture(flow)
    request = signed(flow, challenge(flow, snapshot))
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: verify(flow, snapshot, request), range(2)))
    assert sorted(response.status_code for response in results) == [200, 409]
    with flow[1].db.connect() as connection:
        assert connection.scalar(select(func.count()).select_from(bindings)) == 1


def test_refresh_does_not_inherit_binding_and_review_is_versioned(flow):
    agent, snapshot, _ = capture(flow)
    request = signed(flow, challenge(flow, snapshot))
    assert verify(flow, snapshot, request).status_code == 200
    conflict = flow[0].post(
        f"/api/v1/snapshots/{snapshot['snapshot_id']}/claims/confirm",
        headers=AUTH,
        json={
            "confirmed_claims": ["anchor_record"],
            "reason": "Repeated review",
            "expected_review_version": 0,
        },
    )
    assert conflict.json()["error"]["code"] == "REVIEW_CONFLICT"
    _, refreshed, _ = capture(flow, agent_id=agent)
    assert refreshed["snapshot_id"] != snapshot["snapshot_id"]
    assert flow[0].get(f"/api/v1/snapshots/{refreshed['snapshot_id']}/bindings").json() == []
    response = flow[0].post(
        f"/api/v1/snapshots/{snapshot['snapshot_id']}/bindings/challenge",
        headers=AUTH,
        json={
            "executor": flow[2]["a"]["executor"],
            "endpoint_id": "fixture-a",
            "execution_chain_key": "local-demo",
        },
    )
    assert response.json()["error"]["code"] == "STALE_SNAPSHOT"


def test_on_chain_identity_change_invalidates_outstanding_challenge(flow):
    _, snapshot, _ = capture(flow)
    request = signed(flow, challenge(flow, snapshot))
    registry = flow[4].eth.contract(
        address=Web3.to_checksum_address(flow[5].registry.address),
        abi=contract_abi(ROOT, "DemoAgentRegistry"),
    )
    metadata = {**flow[2]["a"]["metadata"], "description": "Changed service statement"}
    uri = "data:application/json;base64," + base64.b64encode(canonical_bytes(metadata)).decode()
    SetupJournal(flow[6] / "change.sqlite3", flow[4]).transact(
        "change-uri",
        flow[3]["owner-a"],
        registry.functions.setAgentURI(int(flow[2]["a"]["agent_ref"]["agent_id"]), uri),
    )
    assert verify(flow, snapshot, request).json()["error"]["code"] == "IDENTITY_CHANGED"


def test_ingest_commit_before_completion_reclaims_same_snapshot(flow):
    client, service, samples, *_ = flow
    agent = client.post(
        "/api/v1/agents", headers=AUTH, json={"agent_ref": samples["a"]["agent_ref"]}
    ).json()["id"]
    job = client.post(f"/api/v1/agents/{agent}/refresh", headers=AUTH, json={}).json()["job_id"]
    queue = JobQueue(service.db, "crash-test")
    lease = queue.claim()
    asyncio.run(service.ingest(lease, queue))
    with service.db.begin() as connection:
        connection.execute(
            update(jobs)
            .where(jobs.c.id == UUID(job))
            .values(lease_until=datetime.now(UTC) - timedelta(seconds=1))
        )
    worker = Worker(service.db, {"ingest": service.ingest})
    assert asyncio.run(worker.run_once())
    with service.db.connect() as connection:
        assert connection.scalar(select(func.count()).select_from(snapshots)) == 1
        assert connection.scalar(select(jobs.c.state).where(jobs.c.id == UUID(job))) == "SUCCEEDED"


def test_contract_executor_binding_is_unknown(flow):
    _, snapshot, _ = capture(flow)
    issued = challenge(flow, snapshot)
    # Real chain account-code change represents an unsupported contract-wallet executor.
    flow[4].provider.make_request(
        RPCEndpoint("anvil_setCode"), [flow[2]["a"]["executor"], "0x60006000f3"]
    )
    result = verify(flow, snapshot, signed(flow, issued))
    assert result.status_code == 200, result.text
    assert result.json()["status"] == "UNKNOWN"
    assert result.json()["reason_code"] == "BINDING_UNVERIFIED"


def test_metadata_credentials_are_rejected_before_snapshot_or_evidence(flow):
    client, service, samples, keys, web3, deployment, runtime = flow
    registry = web3.eth.contract(
        address=Web3.to_checksum_address(deployment.registry.address),
        abi=contract_abi(ROOT, "DemoAgentRegistry"),
    )
    metadata = {**samples["a"]["metadata"], "api_key": "do-not-save-this-value"}
    uri = "data:application/json;base64," + base64.b64encode(canonical_bytes(metadata)).decode()
    SetupJournal(runtime / "metadata.sqlite3", web3).transact(
        "unsafe-metadata",
        keys["owner-a"],
        registry.functions.setAgentURI(int(samples["a"]["agent_ref"]["agent_id"]), uri),
    )
    agent = client.post(
        "/api/v1/agents", json={"agent_ref": samples["a"]["agent_ref"]}, headers=AUTH
    ).json()["id"]
    job = client.post(f"/api/v1/agents/{agent}/refresh", json={}, headers=AUTH).json()["job_id"]
    assert asyncio.run(Worker(service.db, {"ingest": service.ingest}).run_once())
    status = client.get(f"/api/v1/jobs/{job}", headers=AUTH)
    assert status.json()["state"] == "FAILED"
    assert status.json()["reason_code"] == "UNSUPPORTED_METADATA"
    assert "do-not-save-this-value" not in status.text
    with service.db.connect() as connection:
        assert connection.scalar(select(func.count()).select_from(snapshots)) == 0
        assert connection.scalar(select(func.count()).select_from(evidence_blobs)) == 0


def test_competing_refresh_cannot_silently_replace_newer_snapshot(flow):
    client, service, samples, *_ = flow
    agent = client.post(
        "/api/v1/agents", json={"agent_ref": samples["a"]["agent_ref"]}, headers=AUTH
    ).json()["id"]
    queued = [
        client.post(f"/api/v1/agents/{agent}/refresh", json={}, headers=AUTH).json()["job_id"]
        for _ in range(2)
    ]
    worker = Worker(service.db, {"ingest": service.ingest})
    assert asyncio.run(worker.run_once()) and asyncio.run(worker.run_once())
    states = [client.get(f"/api/v1/jobs/{job}", headers=AUTH).json() for job in queued]
    assert [state["state"] for state in states] == ["SUCCEEDED", "FAILED"]
    assert states[1]["reason_code"] == "SNAPSHOT_CONFLICT"
