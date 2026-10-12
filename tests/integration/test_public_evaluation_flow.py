"""Offline transport replay through real PG/jobs; no third-party traffic or writes."""

import asyncio
import json
import time
from datetime import UTC, datetime, timedelta
from uuid import UUID

import httpx
import pytest
from fastapi.testclient import TestClient
from reputation_core.evidence import canonical_bytes, strict_json
from reputation_core.models import Outcome
from reputation_platform.adapters.registries.erc8004 import AKASHI_REF
from reputation_platform.api.app import create_app
from reputation_platform.application.execution import ExecutionService
from reputation_platform.application.public_execution import PublicReadonlyEgress
from reputation_platform.application.public_verification import PublicReadonlyVerificationService
from reputation_platform.application.reports import ReportService
from reputation_platform.application.verification import VerificationService
from reputation_platform.infrastructure.db.jobs import JobQueue, LostLease
from reputation_platform.infrastructure.db.tables import audit_logs, jobs, runs, task_links
from reputation_platform.infrastructure.evidence_store import EvidenceStore
from reputation_platform.infrastructure.network.safe_http import SafeHttpClient
from reputation_platform.worker.main import Worker
from sqlalchemy import insert, select, update
from sqlalchemy.exc import IntegrityError

from tests.integration.test_identity import identity_chain
from tests.unit.test_public_evaluation_core import POC, ROOT, make_input

__all__ = ["identity_chain"]

pytestmark = pytest.mark.postgres
AUTH = {"Authorization": "Bearer public-evaluation-token-at-least-32"}


class OfflinePublicResponder:
    def __init__(self):
        self.template = make_input()
        self.requests = []
        self.times = []
        self.payment = False
        self.unsafe_tool = False
        self.block_rpc = False
        self.responses = {}
        for packet in self.template.packets:
            value = packet.body
            if not isinstance(value, dict) or "response" not in value:
                continue
            if value["origin"] == "https://mainnet.base.org":
                request = value["request_json"]
                key = (request["method"], canonical_bytes(request["params"]))
                self.responses[key] = value["response"]["json"]["result"]
            elif value["path"] in {"/.well-known/agent-registration.json", "/openapi.json"}:
                self.responses[value["path"]] = value["response"]["json"]
        head = self.responses[
            (
                "eth_getBlockByNumber",
                canonical_bytes([hex(int(self.template.slot.task.read_block_number)), False]),
            )
        ]
        self.responses[("eth_getBlockByNumber", canonical_bytes(["latest", False]))] = head
        self.proof = strict_json((POC / "025-positive-http-1.body").read_bytes())

    def __call__(self, request):
        self.requests.append(request)
        self.times.append(time.monotonic())
        if request.url.host == "mainnet.base.org":
            payload = json.loads(request.content)
            if self.block_rpc:
                return httpx.Response(503, json={"error": "offline unavailable"})
            result = self.responses[(payload["method"], canonical_bytes(payload["params"]))]
            return httpx.Response(
                200, json={"jsonrpc": "2.0", "id": payload["id"], "result": result}
            )
        if request.url.path in self.responses:
            return httpx.Response(200, json=self.responses[request.url.path])
        if self.payment:
            return httpx.Response(402, json={"paymentRequired": True})
        if request.url.path == "/proof":
            query = dict(request.url.params)
            if "tx" in query:
                return httpx.Response(200, json=self.proof)
            if query["hash"] == "not-a-sha256":
                return httpx.Response(400, json={"error": "invalid hash"})
            return httpx.Response(
                200, json={"hash": query["hash"], "anchored": False, "proofs": [], "unsearched": []}
            )
        payload = json.loads(request.content)
        method = payload["method"]
        if method == "notifications/initialized":
            return httpx.Response(202)
        if method == "initialize":
            result = {"protocolVersion": "2025-11-25"}
        elif method == "tools/list":
            result = {
                "tools": [
                    {"name": "find_proof", "annotations": {"readOnlyHint": not self.unsafe_tool}}
                ]
            }
        else:
            result = {"structuredContent": self.proof}
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": payload["id"], "result": result})


@pytest.fixture
def flow(db, tmp_path, monkeypatch):
    from reputation_platform.infrastructure.network import safe_http

    monkeypatch.setenv("PUBLIC_READONLY_ENABLED", "1")
    monkeypatch.setattr(safe_http, "PUBLIC_REQUEST_INTERVAL", 0)
    app = create_app(db, AUTH["Authorization"][7:])
    identity = app.state.identity
    identity.evidence = EvidenceStore(tmp_path)
    responder = OfflinePublicResponder()

    def factory(**kwargs):
        return SafeHttpClient.public_readonly(
            transport=httpx.MockTransport(responder), resolver=lambda _: ["1.1.1.1"], **kwargs
        )

    identity.client_factory = factory
    with TestClient(app) as api:
        agent = api.post(
            "/api/v1/agents", json={"agent_ref": AKASHI_REF.model_dump()}, headers=AUTH
        ).json()
        refresh = api.post(f"/api/v1/agents/{agent['id']}/refresh", json={}, headers=AUTH)
        assert refresh.status_code == 202, refresh.text
        assert asyncio.run(Worker(db, {"ingest": identity.ingest}).run_once())
        job = api.get(f"/api/v1/jobs/{refresh.json()['job_id']}", headers=AUTH).json()
        assert job["state"] == "SUCCEEDED" and job["snapshot_id"], job
        snapshot_id = job["snapshot_id"]
        confirm = api.post(
            f"/api/v1/snapshots/{snapshot_id}/claims/confirm",
            headers=AUTH,
            json={
                "confirmed_claims": ["verify_record"],
                "reason": "manual offline protocol mapping review",
                "expected_review_version": 0,
            },
        )
        assert confirm.status_code == 200, confirm.text
        responder.requests.clear()
        responder.times.clear()
        yield api, identity, responder, factory, snapshot_id


def create_run(flow, key="public-run"):
    api, _, _, _, snapshot_id = flow
    expiry = (
        (datetime.now(UTC) + timedelta(hours=1))
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )
    grants = []
    for endpoint, quota in (("akashi-http", 4), ("akashi-mcp", 1)):
        result = api.post(
            "/api/v1/public-readonly/access-grants",
            headers=AUTH,
            json={
                "snapshot_id": snapshot_id,
                "endpoint_id": endpoint,
                "max_tasks": quota,
                "expires_at": expiry,
                "consent_ref": "explicit-free-readonly-offline-test",
            },
        )
        assert result.status_code == 201, result.text
        grants.append(result.json()["grant"]["grant_id"])
    body = {"snapshot_id": snapshot_id, "review_version": 1, "grant_ids": grants}
    result = api.post(
        "/api/v1/public-readonly/evaluations", headers={**AUTH, "Idempotency-Key": key}, json=body
    )
    assert result.status_code == 202, result.text
    return UUID(result.json()["run_id"]), grants, body


def execute(flow, *, fault_hook=None):
    _, identity, _, factory, _ = flow
    service = ExecutionService(identity.db, identity, client_factory=factory, fault_hook=fault_hook)
    return asyncio.run(Worker(identity.db, {"evaluate": service.execute}).run_once())


@pytest.mark.chain
def test_public_offline_execution_verification_freeze_and_bundle(flow, tmp_path, identity_chain):
    from alembic import command
    from alembic.config import Config
    from reputation_verifier.bundle import verify_bundle

    api, identity, responder, factory, _ = flow
    identity._deployment = identity_chain[0]
    run_id, grants, body = create_run(flow)
    plan = api.get(f"/api/v1/evaluations/{run_id}/plan").json()
    assert len(plan["slots"]) == 5 and plan["template_version"] == "public-readonly@1"
    assert [slot["purpose"] for slot in plan["slots"]] == [
        "functional",
        "availability",
        "functional",
        "functional",
        "functional",
    ]
    assert len(set(slot["task"]["request_id"] for slot in plan["slots"])) == 5
    assert api.post(
        "/api/v1/public-readonly/evaluations",
        headers={**AUTH, "Idempotency-Key": "public-run"},
        json=body,
    ).json()["run_id"] == str(run_id)
    assert execute(flow)
    assert len(responder.requests) == 8
    assert all(b - a >= 0.95 for a, b in zip(responder.times, responder.times[1:]))
    verification = VerificationService(identity.db, identity, client_factory=factory)
    assert asyncio.run(Worker(identity.db, {"verify": verification.verify}).run_once())
    results = verification.results(run_id)
    assert [result.outcome for result in results] == [
        Outcome.PASS,
        Outcome.PASS,
        Outcome.UNKNOWN,
        Outcome.PASS,
        Outcome.PASS,
    ], [
        (
            result.reason_code,
            [(a.rule_id, a.reason_code) for a in result.assertions if a.outcome != Outcome.PASS],
        )
        for result in results
    ]
    assert all(
        result.task_link.executor is None and result.task_link.verified_tx_hash is None
        for result in results
    )
    reporting = ReportService(identity.db, identity, client_factory=factory)
    assert asyncio.run(Worker(identity.db, {"report": reporting.freeze}).run_once())
    report = reporting.for_run(run_id)
    assert (
        report.core.schema_version == "1.6.0" and report.core.scores.evaluation_state == "PARTIAL"
    )
    assert report.core.scores.overall_score_bp is None
    bundle = reporting.export(report.report_id)
    destination = tmp_path / "public-report.zip"
    destination.write_bytes(bundle)
    verified = verify_bundle(str(destination))
    assert verified["offline"] == "PASS" and verified["assessment_comparison"] == "MATCH"
    assert any("not original authenticity" in item for item in verified["limitations"])
    assert all(item["live_chain"]["status"] == "NOT_CHECKED" for item in verified["task_results"])
    assert verified["anchor"]["status"] == "NOT_CHECKED"
    with identity.db.connect() as connection:
        assert len(list(connection.scalars(select(task_links.c.id)))) == 5
        requests = list(
            connection.scalars(
                select(audit_logs.c.body).where(
                    audit_logs.c.action == "public.egress", audit_logs.c.target == run_id
                )
            )
        )
        identity_requests = list(connection.scalars(select(audit_logs.c.body).where(
            audit_logs.c.action == "public.egress", audit_logs.c.body["phase"].astext == "identity"
        )))
    assert len(identity_requests) == 10
    assert len(requests) == len(responder.requests) == 56
    assert all(request["method"] in {"GET", "POST"} for request in requests)
    assert {request["origin"] for request in requests} == {
        "https://anchor.akashi-notari.com",
        "https://mainnet.base.org",
    }
    assert (
        api.get(f"/api/v1/access-grants/{grants[0]}", headers=AUTH).json()["grant"][
            "schema_version"
        ]
        == "public-readonly-grant-v1"
    )
    config = Config(str(ROOT / "alembic.ini"))
    with pytest.raises(RuntimeError, match="Cannot downgrade while public readonly task links exist"):
        command.downgrade(config, "base")
    with identity.db.connect() as connection:
        assert len(list(connection.scalars(select(task_links.c.id)))) == 5
    command.check(config)


@pytest.mark.parametrize("deny", ["revoke", "disabled", "cancel"])
@pytest.mark.chain
def test_public_denial_before_socket_settles_without_queries(flow, deny, identity_chain):
    api, identity, responder, factory, _ = flow
    identity._deployment = identity_chain[0]
    run_id, grants, _ = create_run(flow)
    if deny == "revoke":
        for grant in grants:
            assert (
                api.post(
                    f"/api/v1/access-grants/{grant}/revoke",
                    headers=AUTH,
                    json={"reason": "cancel consent"},
                ).status_code
                == 200
            )
    elif deny == "disabled":
        identity.public_readonly_enabled = False
    else:
        assert (
            api.post(
                f"/api/v1/evaluations/{run_id}/cancel", headers=AUTH, json={"reason": "stop run"}
            ).status_code
            == 200
        )
    assert execute(flow)
    assert responder.requests == []
    observations = api.get(f"/api/v1/evaluations/{run_id}/observations").json()
    assert len(observations) == 5 and all(item["accepted"] is False for item in observations)
    public = PublicReadonlyVerificationService(identity.db, identity, client_factory=factory)
    for observation in observations:
        data = public.inputs(run_id, UUID(observation["slot_id"]))
        assert {packet.record.evidence_id for packet in data.packets} == set(
            data.identity_evidence_refs + data.agent_evidence_refs
        )
        assert data.agent_evidence_refs and data.business_evidence_refs == ()


def test_payment_stops_remaining_run_queries(flow):
    api, _, responder, _, _ = flow
    run_id, _, _ = create_run(flow)
    responder.payment = True
    assert execute(flow)
    assert len(responder.requests) == 1
    observations = api.get(f"/api/v1/evaluations/{run_id}/observations").json()
    assert len(observations) == 5 and all(
        item["reason_code"] == "UNSUPPORTED_PROTOCOL" for item in observations
    )


def test_recovered_send_is_unknown_without_repeating_query(flow):
    api, identity, responder, factory, _ = flow
    run_id, _, _ = create_run(flow)
    queue = JobQueue(identity.db, "crash-recovery")
    lease = queue.claim("evaluate")
    assert lease is not None

    def fault(where):
        if where == "after_send_before_ack":
            raise RuntimeError("simulated public process crash")

    interrupted = ExecutionService(identity.db, identity, client_factory=factory, fault_hook=fault)
    with pytest.raises(RuntimeError, match="simulated public"):
        asyncio.run(interrupted.execute(lease, queue))
    assert len(responder.requests) == 1
    resumed = ExecutionService(identity.db, identity, client_factory=factory)
    asyncio.run(resumed.execute(lease, queue))
    queue.complete(lease)
    assert len(responder.requests) == 8
    observations = api.get(f"/api/v1/evaluations/{run_id}/observations").json()
    assert (
        observations[0]["reason_code"] == "DISPATCH_UNCERTAIN"
        and observations[0]["accepted"] is False
    )
    assert observations[0]["evidence_refs"]
    assert (
        sum(
            request.url.path == "/proof" and "tx" in request.url.params
            for request in responder.requests
        )
        == 2
    )


def test_grant_revocation_after_dns_fences_actual_socket(flow):
    api, identity, responder, factory, _ = flow
    run_id, grants, _ = create_run(flow)
    fired = False

    def guarded_factory(**kwargs):
        original = kwargs["before_request"]

        async def before(*args):
            nonlocal fired
            if not fired:
                fired = True
                for grant in grants:
                    api.post(
                        f"/api/v1/access-grants/{grant}/revoke",
                        headers=AUTH,
                        json={"reason": "revoked at socket boundary"},
                    )
            await original(*args)

        kwargs["before_request"] = before
        return factory(**kwargs)

    service = ExecutionService(identity.db, identity, client_factory=guarded_factory)
    assert asyncio.run(Worker(identity.db, {"evaluate": service.execute}).run_once())
    assert responder.requests == []
    observations = api.get(f"/api/v1/evaluations/{run_id}/observations").json()
    assert all(item["reason_code"] == "ACCESS_NOT_GRANTED" for item in observations)


def test_nullable_executor_is_constrained_not_a_controlled_backdoor(flow):
    _, identity, _, _, _ = flow
    run_id, _, _ = create_run(flow)
    row = identity.db.connect()
    plan = row.scalar(select(runs.c.plan).where(runs.c.id == run_id))
    row.close()
    slot = plan["slots"][0]
    with pytest.raises(IntegrityError), identity.db.begin() as connection:
        connection.execute(
            insert(task_links).values(
                slot_fk=UUID(slot["slot_id"]),
                chain_instance_id=slot["task"]["chain_instance_id"],
                executor=None,
                request_id=slot["task"]["request_id"],
                body={"task_link": {"completion_kind": "execution"}},
            )
        )


def test_stale_lease_at_actual_socket_cannot_dispatch_or_settle(flow):
    _, identity, responder, factory, _ = flow
    run_id, _, _ = create_run(flow)
    queue = JobQueue(identity.db, "stale-public-worker")
    lease = queue.claim("evaluate")
    assert lease is not None

    def stolen_factory(**kwargs):
        original = kwargs["before_request"]

        async def before(*args):
            with identity.db.begin() as connection:
                connection.execute(
                    update(jobs)
                    .where(jobs.c.id == lease.job_id)
                    .values(lease_token=lease.token + 1)
                )
            await original(*args)

        kwargs["before_request"] = before
        return factory(**kwargs)

    service = ExecutionService(identity.db, identity, client_factory=stolen_factory)
    with pytest.raises(LostLease):
        asyncio.run(service.execute(lease, queue))
    assert responder.requests == []
    assert service.evaluations.observations(run_id) == []


def test_durable_request_budget_blocks_all_later_sockets(flow):
    api, identity, responder, _, _ = flow
    run_id, _, _ = create_run(flow)
    with identity.db.begin() as connection:
        connection.execute(
            insert(audit_logs),
            [
                {
                    "actor": "quota-test",
                    "action": "public.egress",
                    "target": run_id,
                    "body": {"origin": "https://mainnet.base.org"},
                }
                for _ in range(64)
            ],
        )
    assert execute(flow)
    assert responder.requests == []
    assert all(
        item["reason_code"] == "ACCESS_NOT_GRANTED"
        for item in api.get(f"/api/v1/evaluations/{run_id}/observations").json()
    )


def test_separate_clients_share_origin_concurrency_and_completion_gap(flow):
    _, identity, responder, _, _ = flow
    run_id, _, _ = create_run(flow)
    with identity.db.connect() as connection:
        row = connection.execute(select(runs).where(runs.c.id == run_id)).mappings().one()
    from reputation_core.models.public_evaluation import PublicReadonlyRunPlan

    slot = PublicReadonlyRunPlan.model_validate(row["plan"]).slots[0]
    active, maximum = 0, 0
    completed = []

    async def transport(request):
        nonlocal active, maximum
        active += 1
        maximum = max(maximum, active)
        await asyncio.sleep(0.2)
        response = responder(request)
        active -= 1
        completed.append(time.monotonic())
        return response

    async def read():
        guard = PublicReadonlyEgress(identity.db, identity, row, slot)
        client = SafeHttpClient.public_readonly(
            enabled=True,
            before_request=guard,
            transport=httpx.MockTransport(transport),
            resolver=lambda _: ["1.1.1.1"],
        )
        try:
            async with guard:
                await client.request(
                    "GET", "https://anchor.akashi-notari.com", "/proof?tx=" + slot.task.query["tx"]
                )
        finally:
            await client.close()

    async def concurrent():
        await asyncio.gather(read(), read())

    asyncio.run(concurrent())
    assert maximum == 1 and len(completed) == 2
    assert responder.times[1] - completed[0] >= 0.95
