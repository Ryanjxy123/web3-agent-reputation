"""Real HTTP failure responses, unavailable RPC, and explicit capability applicability."""

import asyncio
import base64
import io
import os
import secrets
import socket
import subprocess
import sys
import time
import zipfile
from datetime import UTC, datetime, timedelta
from uuid import UUID

import httpx
import pytest
from reputation_core.evidence import canonical_bytes
from reputation_core.models import EvidenceRecord, RecordVerificationInput
from reputation_core.record_verifier import verify_record
from reputation_platform.application.execution import ExecutionService
from reputation_platform.application.local_deploy import SetupJournal, contract_abi
from reputation_platform.application.reports import ReportService
from reputation_platform.application.verification import VerificationService
from reputation_platform.configuration import controlled_fixture_ports
from reputation_platform.infrastructure.db.tables import attempts, evidence_blobs
from reputation_platform.worker.main import Worker
from reputation_verifier import verify_bundle
from sqlalchemy import func, select
from web3 import Web3

from tests.integration.test_identity import AUTH, capture, flow, identity_chain, signed, verify

__all__ = ["flow", "identity_chain"]
pytestmark = [pytest.mark.chain, pytest.mark.postgres]

FAULT_SERVICE = """
import asyncio
import os
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response
app = FastAPI()
mode = os.environ['FAULT_MODE']
@app.get('/health')
def health(): return {'status': 'ok'}
@app.post('/tasks')
async def task(request: Request):
    body = await request.json()
    if mode == 'timeout':
        await asyncio.sleep(20)
    if mode == 'service': return JSONResponse({'error': {'code': 'INTERNAL'}}, status_code=503)
    if mode == 'forbidden': return JSONResponse({'error': {'code': 'AUTH_REQUIRED'}}, status_code=403)
    if mode == 'rate': return JSONResponse({'error': {'code': 'RATE_LIMIT'}}, status_code=429)
    if mode == 'malformed': return JSONResponse({'accepted': True})
    if mode == 'list': return JSONResponse([1, 2, 3])
    if mode == 'invalid': return Response('{"private_key":"should-not-be-exported", invalid}', media_type='application/json')
    reason = {'failed': 'BUSINESS_REJECTED', 'unsupported': 'UNSUPPORTED_CAPABILITY',
              'spoof_platform': 'PLATFORM_RPC_ERROR'}.get(mode)
    return {'request_id': body['request_id'], 'status_path': '/tasks/' + body['request_id'],
            'task_status': 'failed' if reason else 'succeeded', 'reason_code': reason}
"""


@pytest.fixture
def attribution_prepared(flow, request):
    mode = getattr(request, "param", "failed")
    module = flow[6] / "fault_service.py"
    module.write_text(FAULT_SERVICE, encoding="utf-8")
    port = controlled_fixture_ports()[0]
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "fault_service:app",
            "--app-dir",
            str(flow[6]),
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
            "FAULT_MODE": mode,
        },
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        until = time.monotonic() + 90
        with httpx.Client(trust_env=False, timeout=1) as probe:
            while True:
                assert process.poll() is None
                try:
                    if probe.get(f"http://127.0.0.1:{port}/health").status_code == 200:
                        break
                except httpx.HTTPError:
                    pass
                assert time.monotonic() < until
                time.sleep(0.1)
        _, snapshot, _ = capture(flow)
        reviewed = flow[0].post(
            f"/api/v1/snapshots/{snapshot['snapshot_id']}/claims/confirm",
            headers=AUTH,
            json={
                "confirmed_claims": ["get_tx_status"],
                "reason": "Failure attribution tests",
                "expected_review_version": 0,
            },
        )
        assert reviewed.status_code == 200, reviewed.text
        grant = flow[0].post(
            "/api/v1/access-grants",
            headers=AUTH,
            json={
                "snapshot_id": snapshot["snapshot_id"],
                "endpoint_id": "fixture-a",
                "max_tasks": 1,
                "capabilities": ["get_tx_status"],
                "contract_allowlist": [],
                "expires_at": (datetime.now(UTC) + timedelta(hours=1))
                .isoformat(timespec="milliseconds")
                .replace("+00:00", "Z"),
                "consent_ref": "Explicit fault test authorization",
            },
        )
        assert grant.status_code == 201, grant.text
        body = {
            "snapshot_id": snapshot["snapshot_id"],
            "review_version": 1,
            "profile": "record-read-v1",
            "policy_version": "policy-v1",
            "suite_id": "capabilities-v1",
            "capability_id": "get_tx_status",
            "query_tx_hash": flow[5].record.transaction_hash,
            "grant_ids": [grant.json()["grant"]["grant_id"]],
        }
        yield flow, body, process
    finally:
        if process.poll() is None:
            process.terminate()
        process.wait(timeout=15)


def execute_attribution(prepared, *, fault_hook=None, rpc_url=None):
    flow, body, _ = prepared
    response = flow[0].post(
        "/api/v1/evaluations", headers={**AUTH, "Idempotency-Key": secrets.token_hex(16)}, json=body
    )
    assert response.status_code == 202, response.text
    run_id = UUID(response.json()["run_id"])
    if rpc_url is not None:
        flow[1]._deployment = flow[5].model_copy(update={"rpc_url": rpc_url})
    service = ExecutionService(flow[1].db, flow[1], fault_hook=fault_hook)
    verifier = VerificationService(flow[1].db, flow[1])
    worker = Worker(flow[1].db, {"evaluate": service.execute, "verify": verifier.verify})
    assert asyncio.run(worker.run_once()) and asyncio.run(worker.run_once())
    result = verifier.result(run_id)
    identifier = result.assertions[0].evidence_refs[0]
    with flow[1].db.connect() as connection:
        record = EvidenceRecord.model_validate(
            connection.execute(
                select(evidence_blobs.c.body).where(evidence_blobs.c.id == identifier)
            ).scalar_one()
        )
    inputs = RecordVerificationInput.model_validate_json(flow[1].evidence.read(record))
    assert inputs.rule_version == "2" and verify_record(inputs, (identifier,)) == result
    return run_id, result, inputs


def freeze_and_export(flow, run_id):
    reports = ReportService(flow[1].db, flow[1])
    assert asyncio.run(Worker(flow[1].db, {"report": reports.freeze}).run_once())
    report = reports.for_run(run_id)
    bundle = reports.export(report.report_id)
    with zipfile.ZipFile(io.BytesIO(bundle)) as archive:
        core = archive.read("report_core.json")
    path = flow[6] / f"report-{report.report_id}.zip"
    path.write_bytes(bundle)
    replayed = verify_bundle(str(path))
    assert replayed["offline"] == "PASS"
    assert replayed["task_counts"] == report.core.task_counts.model_dump(mode="json")
    assert replayed["task_results"][0]["outcome"] == report.core.task_results[0].outcome
    assert replayed["task_results"][0]["reason_code"] == report.core.task_results[0].reason_code
    return report, core, bundle


@pytest.mark.parametrize(
    "attribution_prepared,outcome,reason",
    [
        ("service", "FAIL", "AGENT_SERVICE_ERROR"),
        ("malformed", "FAIL", "SCHEMA_ERROR"),
        ("list", "FAIL", "SCHEMA_ERROR"),
        ("no_result", "FAIL", "SCHEMA_ERROR"),
        ("failed", "FAIL", "AGENT_TASK_FAILED"),
        ("unsupported", "FAIL", "CAPABILITY_EXPLICITLY_UNSUPPORTED"),
        ("spoof_platform", "FAIL", "AGENT_TASK_FAILED"),
        ("invalid", "UNKNOWN", "PLATFORM_NETWORK_ERROR"),
        ("forbidden", "UNKNOWN", "ACCESS_NOT_GRANTED"),
        ("rate", "UNKNOWN", "RATE_LIMIT_UNATTRIBUTED"),
        ("timeout", "UNKNOWN", "SERVICE_TIMEOUT"),
    ],
    indirect=["attribution_prepared"],
)
def test_http_failure_reasons_are_evidence_driven(attribution_prepared, outcome, reason):
    _, result, inputs = execute_attribution(attribution_prepared)
    assert result.outcome == outcome and result.reason_code == reason, [
        (a.rule_id, a.outcome, a.reason_code) for a in result.assertions
    ]
    assert inputs.agent_http is not None
    if outcome == "FAIL":
        assert inputs.agent_http["response"] is not None
    for path in attribution_prepared[0][1].evidence.root.rglob("*.bin"):
        assert b"should-not-be-exported" not in path.read_bytes()


def test_unavailable_agent_transport_is_unknown(attribution_prepared):
    attribution_prepared[2].terminate()
    attribution_prepared[2].wait(timeout=15)
    _, result, inputs = execute_attribution(attribution_prepared)
    assert result.outcome == "UNKNOWN" and result.reason_code == "PLATFORM_NETWORK_ERROR"
    assert inputs.agent_http["http_status"] is None


def test_unavailable_platform_rpc_is_unknown_before_dispatch(attribution_prepared):
    flow = attribution_prepared[0]
    with socket.socket() as unavailable:
        unavailable.bind(("127.0.0.1", 0))
        try:
            run_id, result, inputs = execute_attribution(
                attribution_prepared,
                rpc_url=f"http://127.0.0.1:{unavailable.getsockname()[1]}",
            )
        finally:
            flow[1]._deployment = flow[5]
    assert result.outcome == "UNKNOWN" and result.reason_code == "PLATFORM_RPC_ERROR"
    assert inputs.agent_http is None and inputs.evm.error_reason == "PLATFORM_RPC_ERROR"
    with flow[1].db.connect() as connection:
        assert (
            connection.scalar(
                select(func.count())
                .select_from(attempts)
                .where(attempts.c.body["method"].astext == "POST")
            )
            == 0
        )
    report, core, bundle = freeze_and_export(flow, run_id)
    assert {item.rule_id: item.outcome for item in report.core.assertions} == {
        item.rule_id: item.outcome for item in result.assertions
    }
    assert b'"outcome":"UNKNOWN"' in core and bundle


@pytest.mark.parametrize("attribution_prepared", ["service", "invalid"], indirect=True)
def test_fail_and_unknown_are_frozen_and_exported(attribution_prepared):
    flow = attribution_prepared[0]
    run_id, result, _ = execute_attribution(attribution_prepared)
    report, core, bundle = freeze_and_export(flow, run_id)
    assert {item.rule_id: item.outcome for item in report.core.assertions} == {
        item.rule_id: item.outcome for item in result.assertions
    }
    assert f'"outcome":"{result.outcome}"'.encode() in core
    assert bundle


@pytest.mark.parametrize("attribution_prepared", ["service"], indirect=True)
def test_agent_failure_survives_reconciliation_rpc_failure(attribution_prepared):
    flow, read_body, process = attribution_prepared
    snapshot_id = read_body["snapshot_id"]
    reviewed = flow[0].post(
        f"/api/v1/snapshots/{snapshot_id}/claims/confirm",
        headers=AUTH,
        json={
            "confirmed_claims": ["anchor_record"],
            "reason": "Check write failure evidence",
            "expected_review_version": 1,
        },
    )
    assert reviewed.status_code == 200, reviewed.text
    issued = flow[0].post(
        f"/api/v1/snapshots/{snapshot_id}/bindings/challenge",
        headers=AUTH,
        json={
            "executor": flow[2]["a"]["executor"],
            "endpoint_id": "fixture-a",
            "execution_chain_key": "local-demo",
        },
    )
    assert issued.status_code == 200, issued.text
    bound = verify(flow, {"snapshot_id": snapshot_id}, signed(flow, issued.json()))
    assert bound.status_code == 200, bound.text
    grant = flow[0].post(
        "/api/v1/access-grants",
        headers=AUTH,
        json={
            "snapshot_id": snapshot_id,
            "endpoint_id": "fixture-a",
            "max_tasks": 1,
            "capabilities": ["anchor_record"],
            "expires_at": (datetime.now(UTC) + timedelta(hours=1))
            .isoformat(timespec="milliseconds")
            .replace("+00:00", "Z"),
            "consent_ref": "Explicit write failure test authorization",
        },
    )
    assert grant.status_code == 201, grant.text
    prepared = (
        flow,
        {
            "snapshot_id": snapshot_id,
            "review_version": 2,
            "profile": "record-write-v1",
            "policy_version": "policy-v1",
            "suite_id": "capabilities-v1",
            "capability_id": "anchor_record",
            "grant_ids": [grant.json()["grant"]["grant_id"]],
        },
        process,
    )
    with socket.socket() as unavailable:
        unavailable.bind(("127.0.0.1", 0))

        def rpc_fails_after_http(stage):
            if stage == "after_send_before_ack":
                flow[1]._deployment = flow[5].model_copy(
                    update={"rpc_url": f"http://127.0.0.1:{unavailable.getsockname()[1]}"}
                )

        try:
            _, result, inputs = execute_attribution(prepared, fault_hook=rpc_fails_after_http)
        finally:
            flow[1]._deployment = flow[5]
    assert result.outcome == "FAIL" and result.reason_code == "AGENT_SERVICE_ERROR"
    assert inputs.agent_http["http_status"] == 503
    assert inputs.agent_response == {"error": {"code": "INTERNAL"}}
    assert inputs.evm.error_reason == "PLATFORM_RPC_ERROR"
    assert any(assertion.outcome == "UNKNOWN" for assertion in result.assertions)


def test_explicitly_absent_capability_is_not_applicable_and_never_dispatched(flow, monkeypatch):
    metadata = {**flow[2]["a"]["metadata"], "capabilities": ["get_tx_status"]}
    registry = flow[4].eth.contract(
        address=Web3.to_checksum_address(flow[5].registry.address),
        abi=contract_abi(flow[1].root, "DemoAgentRegistry"),
    )
    uri = "data:application/json;base64," + base64.b64encode(canonical_bytes(metadata)).decode(
        "ascii"
    )
    SetupJournal(flow[6] / "read-only-registration.sqlite3", flow[4]).transact(
        "restrict",
        flow[3]["owner-a"],
        registry.functions.setAgentURI(int(flow[2]["a"]["agent_ref"]["agent_id"]), uri),
    )
    _, snapshot, _ = capture(flow)
    reviewed = flow[0].post(
        f"/api/v1/snapshots/{snapshot['snapshot_id']}/claims/confirm",
        headers=AUTH,
        json={
            "confirmed_claims": ["get_tx_status"],
            "excluded_capabilities": ["anchor_record"],
            "reason": "Declared read-only scope",
            "expected_review_version": 0,
        },
    )
    assert reviewed.status_code == 200, reviewed.text
    grant = flow[0].post(
        "/api/v1/access-grants",
        headers=AUTH,
        json={
            "snapshot_id": snapshot["snapshot_id"],
            "endpoint_id": "fixture-a",
            "max_tasks": 1,
            "capabilities": ["anchor_record"],
            "expires_at": (datetime.now(UTC) + timedelta(hours=1))
            .isoformat(timespec="milliseconds")
            .replace("+00:00", "Z"),
            "consent_ref": "Applicability assessment, no HTTP dispatch",
        },
    )
    assert grant.status_code == 201, grant.text
    smoke = {
        "snapshot_id": snapshot["snapshot_id"],
        "review_version": 1,
        "profile": "record-write-v1",
        "policy_version": "policy-v1",
        "suite_id": "m1-smoke-v1",
        "capability_id": "anchor_record",
        "grant_ids": [grant.json()["grant"]["grant_id"]],
    }
    rejected = flow[0].post(
        "/api/v1/evaluations",
        headers={**AUTH, "Idempotency-Key": secrets.token_hex(16)},
        json=smoke,
    )
    assert rejected.status_code == 422
    assert rejected.json()["error"]["code"] == "UNSUPPORTED_PROFILE"
    prepared = (
        flow,
        {
            "snapshot_id": snapshot["snapshot_id"],
            "review_version": 1,
            "profile": "record-write-v1",
            "policy_version": "policy-v1",
            "suite_id": "capabilities-v1",
            "capability_id": "anchor_record",
            "grant_ids": [grant.json()["grant"]["grant_id"]],
        },
        None,
    )
    run_id, result, inputs = execute_attribution(prepared)
    assert result.outcome == "NOT_APPLICABLE" and result.reason_code == "CAPABILITY_NOT_DECLARED"
    assert inputs.binding is None and inputs.agent_http is None
    with flow[1].db.connect() as connection:
        sent = connection.scalar(
            select(func.count())
            .select_from(attempts)
            .where(attempts.c.body["method"].astext == "POST")
        )
    assert sent == 0

    def unexpected_collection(*args, **kwargs):
        raise AssertionError("not-applicable tasks do not need business RPC collection")

    monkeypatch.setattr(
        "reputation_platform.application.reports.collect_task", unexpected_collection
    )
    report, core, bundle = freeze_and_export(flow, run_id)
    assert {item.rule_id: item.outcome for item in report.core.assertions} == {
        item.rule_id: item.outcome for item in result.assertions
    }
    assert b'"outcome":"NOT_APPLICABLE"' in core and bundle


def test_declared_capability_cannot_be_excluded_after_failure(flow):
    _, snapshot, _ = capture(flow)
    response = flow[0].post(
        f"/api/v1/snapshots/{snapshot['snapshot_id']}/claims/confirm",
        headers=AUTH,
        json={
            "confirmed_claims": ["get_tx_status"],
            "excluded_capabilities": ["anchor_record"],
            "reason": "Cannot exclude declared support",
            "expected_review_version": 0,
        },
    )
    assert response.status_code == 422 and response.json()["error"]["code"] == "UNSUPPORTED_CLAIM"
