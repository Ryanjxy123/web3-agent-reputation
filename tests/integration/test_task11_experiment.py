"""Capture actual single-slot controlled experiments without changing platform rules."""
import base64
import hashlib
import json
import os
import platform
import socket
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path

import pytest
from reputation_core.evidence import canonical_bytes
from reputation_core.models import RecordVerificationInput
from reputation_platform.application.execution import ExecutionService
from reputation_platform.application.local_deploy import SetupJournal, contract_abi
from reputation_platform.application.reports import ReportService
from reputation_platform.application.verification import VerificationService
from reputation_platform.infrastructure.db.tables import attempts, observations
from reputation_platform.infrastructure.network.safe_http import SafeHttpClient
from reputation_platform.worker.main import Worker
from reputation_verifier.bundle import verify_bundle
from sqlalchemy import select, text
from web3 import HTTPProvider, Web3
from web3.types import RPCEndpoint

from tests.integration.test_controlled_scenarios import advance, controlled_run
from tests.integration.test_execution import create, prepared
from tests.integration.test_formal_evaluation import formal_request, scoped_snapshot
from tests.integration.test_identity import AUTH, flow, identity_chain

__all__ = ["prepared", "flow", "identity_chain"]
ROOT = Path(__file__).resolve().parents[2]
PLAN = json.loads((ROOT / "fixtures/experiments/task11_cases.json").read_text(encoding="utf-8"))
REPETITIONS = int(os.environ.get("TASK11_REPETITIONS", "1"))
pytestmark = [pytest.mark.chain, pytest.mark.postgres]


@pytest.fixture
def experiment_prepared(flow, request, monkeypatch):
    # Reuse the real fixture lifecycle; only this case selects an experiment-only Agent factory.
    original_popen = subprocess.Popen

    def launch(command, *args, **kwargs):
        if isinstance(request.param, dict) and request.param.get("hash_mismatch"):
            command = ["tests.integration.task11_hash_agent:create_app"
                       if item == "fixture_agents.service:create_app" else item for item in command]
        return original_popen(command, *args, **kwargs)

    generator = prepared.__wrapped__(flow, request)
    try:
        with monkeypatch.context() as startup:
            startup.setattr(subprocess, "Popen", launch)
            value = next(generator)
        yield value
    finally:
        generator.close()


def undeclared_run(prepared):
    flow, original, _ = prepared
    snapshot_id = scoped_snapshot(flow, original["snapshot_id"], ("verify_record",))
    review = flow[0].post(
        f"/api/v1/snapshots/{snapshot_id}/claims/confirm", headers=AUTH,
        json={"confirmed_claims": ["verify_record"], "excluded_capabilities": ["get_tx_status"],
              "reason": "Ground Truth declaration omits transaction-status capability",
              "expected_review_version": 1},
    )
    assert review.status_code == 200, review.text
    body = formal_request(flow, snapshot_id, 2, ("get_tx_status",), flow[5].record.address)
    for field in ("target_contract", "record_executor", "record_request_id", "record_hash"):
        body.pop(field)
    transaction = flow[4].eth.get_block("latest", full_transactions=True)["transactions"][0]
    body.update(suite_id="capabilities-v1", capability_id="get_tx_status", query_tx_hash=transaction["hash"].to_0x_hex())
    run_id, plan = create((flow, body, None), body=body)
    verifier = VerificationService(flow[1].db, flow[1])
    reports = ReportService(flow[1].db, flow[1])
    worker = Worker(flow[1].db, {"evaluate": ExecutionService(flow[1].db, flow[1]).execute,
                               "verify": verifier.verify, "report": reports.freeze})
    return flow, run_id, plan, verifier, reports, worker


def change_identity(scenario, change):
    flow, _, _, _, _, _ = scenario
    if change == "binding":
        reply = flow[4].provider.make_request(
            RPCEndpoint("anvil_setCode"), [flow[2]["a"]["executor"], "0x60006000f3"]
        )
        assert "error" not in reply
    elif change == "version":
        registry = flow[4].eth.contract(
            address=Web3.to_checksum_address(flow[5].registry.address),
            abi=contract_abi(flow[1].root, "DemoAgentRegistry"),
        )
        metadata = {**flow[2]["a"]["metadata"], "description": "Task 11 version changed"}
        uri = "data:application/json;base64," + base64.b64encode(canonical_bytes(metadata)).decode()
        SetupJournal(flow[6] / "task11-version.sqlite3", flow[4]).transact(
            "version-change", flow[3]["owner-a"],
            registry.functions.setAgentURI(int(flow[2]["a"]["agent_ref"]["agent_id"]), uri),
        )


@pytest.mark.parametrize(
    "experiment_prepared,case,repetition",
    [(case["prepared"], case, repeat)
     for repeat in range(REPETITIONS) for case in PLAN["cases"]],
    indirect=["experiment_prepared"],
    ids=[f"{case['case_id']}-{repeat}" for repeat in range(REPETITIONS) for case in PLAN["cases"]],
)
def test_capture_real_task11_case(experiment_prepared, monkeypatch, tmp_path, case, repetition):
    scenario = (undeclared_run(experiment_prepared) if case["purpose"] == "undeclared"
                else controlled_run(experiment_prepared, monkeypatch, case["purpose"]))
    flow, run_id, plan, verifier, reports, _ = scenario
    change_identity(scenario, case["change"])
    rpc_trace = []
    http_trace = []
    stage = ["evaluate"]
    make_request = HTTPProvider.make_request
    http_request = SafeHttpClient.request

    def counted_request(provider, method, params):
        # Count the real provider operation, including attempted refused connections.
        rpc_trace.append({"stage": stage[0], "method": str(method)})
        return make_request(provider, method, params)

    async def counted_http(client, method, origin, path, **kwargs):
        http_trace.append({"stage": stage[0], "method": method})
        return await http_request(client, method, origin, path, **kwargs)

    timings = {}
    with monkeypatch.context() as instrumentation:
        instrumentation.setattr(HTTPProvider, "make_request", counted_request)
        instrumentation.setattr(SafeHttpClient, "request", counted_http)
        for kind in ("evaluate", "verify", "report"):
            stage[0] = kind
            started = time.perf_counter_ns()
            if kind == "verify" and case["change"] == "rpc":
                original = flow[1].deployment()
                with socket.socket() as refused:
                    refused.bind(("127.0.0.1", 0))
                    flow[1]._deployment = original.model_copy(update={
                        "rpc_url": f"http://127.0.0.1:{refused.getsockname()[1]}"
                    })
                    try:
                        advance(scenario, kind)
                    finally:
                        flow[1]._deployment = original
            else:
                advance(scenario, kind)
            timings[f"{kind}_ms"] = (time.perf_counter_ns() - started) / 1_000_000
    result = verifier.result(run_id)
    report = reports.for_run(run_id)
    with flow[1].db.connect() as connection:
        attempt_rows = connection.execute(select(attempts.c.body).where(
            attempts.c.slot_fk == plan.slots[0].slot_id
        ).order_by(attempts.c.attempt_no)).scalars().all()
        observation_rows = connection.execute(select(observations.c.body).where(
            observations.c.slot_fk == plan.slots[0].slot_id
        )).scalars().all()
        postgres_version = connection.execute(text("SELECT version()" )).scalar_one()
    output = Path(os.environ.get("TASK11_OUTPUT", str(tmp_path)))
    destination = output / "captures" / f"{case['case_id']}-{repetition}"
    destination.mkdir(parents=True, exist_ok=False)
    input_record = next(item for item in report.manifest.evidence
                        if item.source == "record-verification-input")
    input_bytes = reports.read_evidence(input_record)
    inputs = RecordVerificationInput.model_validate_json(input_bytes)
    (destination / "input.json").write_bytes(input_bytes)
    bundle_bytes = reports.export(report.report_id)
    bundle_path = destination / "bundle.zip"
    bundle_path.write_bytes(bundle_bytes)
    independent = verify_bundle(str(bundle_path))
    (destination / "verifier.json").write_bytes(canonical_bytes(independent))
    trace = {
        "schema_version": "task11-capture-v1", "case_id": case["case_id"],
        "repetition": repetition, "ground_truth": case["ground_truth"],
        "task_type": "write" if inputs.slot.capability_id == "anchor_record" else "read",
        "captured_at": datetime.now(UTC).isoformat(), "python": platform.python_version(),
        "postgres_server": postgres_version,
        "commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "run_id": str(run_id), "plan": plan.model_dump(mode="json"),
        "chain": flow[5].chain.model_dump(mode="json"),
        "report_schema_version": report.core.schema_version,
        "worker_outcome": str(result.outcome), "worker_reason": result.reason_code,
        "worker_critical_risk": result.critical_conflict,
        "plan_sha256": os.environ.get("TASK11_PLAN_SHA256", hashlib.sha256((ROOT / "fixtures/experiments/task11_cases.json").read_bytes()).hexdigest()),
        "source_manifest_sha256": os.environ.get("TASK11_SOURCE_SHA256"),
        "measurements": {**timings, "rpc_attempts": len(rpc_trace),
                         "external_attempts": len(http_trace), "persisted_attempt_count": len(attempt_rows)},
        "http_trace": http_trace,
        "rpc_trace": rpc_trace, "attempts": attempt_rows, "observations": observation_rows,
        "input_sha256": hashlib.sha256(input_bytes).hexdigest(),
        "input_evidence_id": str(input_record.evidence_id),
        "bundle_sha256": hashlib.sha256(bundle_bytes).hexdigest(),
    }
    (destination / "trace.json").write_bytes(canonical_bytes(trace))
    # Save failed captures as evidence too; never turn expectations into observations.
    assert (str(result.outcome), result.reason_code, result.critical_conflict) == (
        case["ground_truth"]["outcome"], case["ground_truth"]["reason"], case["ground_truth"]["critical_risk"]
    )
    expected_assessment = ("NOT_AVAILABLE_LEGACY_REPORT"
                           if case["purpose"] == "undeclared" else "MATCH")
    assert report.core.schema_version == ("1.1.0" if case["purpose"] == "undeclared" else "1.5.0")
    assert independent["offline"] == "PASS"
    assert independent["assessment_comparison"] == expected_assessment
    assert report.core.scores.overall_score_bp is None
