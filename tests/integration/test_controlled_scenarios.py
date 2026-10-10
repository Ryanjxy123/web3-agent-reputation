"""Controlled behavior through real PostgreSQL, HTTP Agent, Anvil and bundle replay.

Each run freezes one independently sampled slot. A normal write may be sampled for
behavior instead of functionality; it is never counted in both denominators.
"""

import asyncio
import base64
import socket
from copy import deepcopy
from uuid import UUID

import pytest
from reputation_core.evidence import canonical_bytes
from reputation_core.models import Purpose, RecordVerificationInput
from reputation_platform.application import evaluations as evaluation_module
from reputation_platform.application import verification as verification_module
from reputation_platform.application.execution import ExecutionService
from reputation_platform.application.local_deploy import SetupJournal, contract_abi
from reputation_platform.application.reports import ReportService
from reputation_platform.application.verification import VerificationService
from reputation_platform.infrastructure.db.tables import attempts, dispatch_events, jobs, snapshots
from reputation_platform.worker.main import Worker
from reputation_verifier.bundle import verify_bundle
from sqlalchemy import func, select
from web3 import Web3
from web3.types import RPCEndpoint

from tests.integration.test_execution import prepared, records
from tests.integration.test_formal_evaluation import create_formal, formal_request, scoped_snapshot
from tests.integration.test_identity import AUTH, capture, flow, identity_chain

__all__ = ["prepared", "flow", "identity_chain"]
pytestmark = [pytest.mark.chain, pytest.mark.postgres]


def controlled_run(prepared, monkeypatch, purpose):
    flow, original, grant = prepared
    capabilities: tuple[str, ...] = ("anchor_record",)
    snapshot_id = original["snapshot_id"]
    if purpose == "availability":
        capabilities = ("verify_record", "anchor_record")
        snapshot_id = scoped_snapshot(flow, snapshot_id, capabilities)
    body = formal_request(
        flow,
        snapshot_id,
        1,
        capabilities,
        flow[5].record.address,
        endpoint_id=grant["endpoint_ids"][0],
    )
    real_plan = evaluation_module.RunPlan

    def single_slot(**values):
        if purpose == "behavioral":
            # A single write has no multi-slot pacing offset and its own behavioral purpose.
            selected = next(
                slot
                for slot in values["slots"]
                if slot.capability_id == "anchor_record" and slot.required_class == "normal"
            ).model_copy(update={"purpose": Purpose.BEHAVIORAL})
        else:
            selected = next(slot for slot in values["slots"] if slot.purpose == purpose)
        values["slots"] = (selected,)
        return real_plan(**values)

    with monkeypatch.context() as sampling:
        sampling.setattr(evaluation_module, "RunPlan", single_slot)
        run_id, plan = create_formal(flow, body)
    assert len(plan.slots) == 1
    assert plan.template_version == "capabilities@6"
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
    return flow, run_id, plan, verifier, reports, worker


def advance(scenario, kind):
    flow, run_id, _, _, _, worker = scenario
    assert asyncio.run(worker.run_once())
    with flow[1].db.connect() as connection:
        job = connection.execute(
            select(jobs.c.state, jobs.c.last_error).where(
                jobs.c.run_fk == run_id, jobs.c.kind == kind
            )
        ).one()
    assert job.state == "SUCCEEDED", (kind, job)


def check_report(
    scenario,
    tmp_path,
    *,
    outcome,
    reason,
    purpose,
    decided,
    observed,
    mapping,
    critical=False,
    accepted=False,
):
    flow, run_id, plan, verifier, reports, _ = scenario
    result = verifier.result(run_id)
    assert (result.outcome, result.reason_code, result.critical_conflict) == (
        outcome,
        reason,
        critical,
    )
    advance(scenario, "report")
    report = reports.for_run(run_id)
    core = report.core
    assert core.schema_version == "1.5.0"
    assert core.task_results[0].outcome == outcome and core.task_results[0].reason_code == reason
    assert core.task_counts.not_applicable_count == 0
    assert core.task_counts.model_dump(mode="json") == {
        "PASS": int(outcome == "PASS"),
        "FAIL": int(outcome == "FAIL"),
        "UNKNOWN": int(outcome == "UNKNOWN"),
        "NOT_APPLICABLE": 0,
    }
    stats = core.raw_statistics
    assert (stats["availability"]["planned"], stats["availability"]["decided"]) == (
        int(purpose == "availability"),
        decided if purpose == "availability" else 0,
    )
    assert sum(item["planned"] for item in stats["capabilities"]) == int(purpose == "functional")
    assert sum(item["decided"] for item in stats["capabilities"]) == (
        decided if purpose == "functional" else 0
    )
    assert (
        stats["behavior"]["planned"],
        stats["behavior"]["accepted"],
        stats["behavior"]["decided"],
    ) == (
        int(purpose == "behavioral"),
        int(accepted),
        decided if purpose == "behavioral" else 0,
    )
    capability = next(
        item
        for item in stats["capabilities"]
        if item["capability_id"] == plan.slots[0].capability_id
    )
    assert capability["mapping"] == mapping
    dimension = {
        "availability": "availability",
        "functional": "consistency",
        "behavioral": "behavior",
    }[purpose]
    assert core.scores.dimensions[dimension].observed_score_bp == observed
    assert core.scores.dimensions[dimension].score_bp is None
    assert core.scores.evaluation_state == "PARTIAL" and core.scores.overall_score_bp is None
    assert core.scores.sufficiency_bp == 0
    assert core.scores.advice == ("NOT_RECOMMENDED" if critical else "INSUFFICIENT_EVIDENCE")
    assert core.evidence_sufficiency.gate_status == "PARTIAL"
    assert not core.evidence_sufficiency.overall_allowed
    assert core.evidence_sufficiency.task_unknown_bp == (10000 if outcome == "UNKNOWN" else 0)
    assert core.evidence_sufficiency.thresholds["availability_min_samples"] == 20
    assert core.evidence_sufficiency.thresholds["consistency_min_samples_per_capability"] == 10
    assert core.evidence_sufficiency.thresholds["behavior_min_accepted_decided_samples"] == 10
    assert bool(core.risk_assessment.critical_findings) == critical
    assert bool(core.risk_assessment.ordinary_failure_slots) == (outcome == "FAIL" and not critical)
    if critical:
        assert reason in {item.reason_code for item in core.risk_assessment.critical_findings}
    if outcome == "UNKNOWN":
        assert core.risk_assessment.evidence_gap_slots == (plan.slots[0].slot_id,)
    assert flow[0].get(f"/api/v1/evaluations/{run_id}").json()["status"] == "PARTIAL"
    bundle = reports.export(report.report_id)
    assert reports.export(report.report_id) == bundle
    destination = tmp_path / f"{run_id}.zip"
    destination.write_bytes(bundle)
    independent = verify_bundle(str(destination))
    assert independent["offline"] == "PASS"
    assert independent["task_count_comparison"] == "MATCH"
    assert independent["assessment_comparison"] == "MATCH"
    assert independent["task_results"][0]["outcome"] == outcome
    assert independent["task_results"][0]["reason_code"] == reason
    assert independent["evidence_sufficiency"] == core.evidence_sufficiency.model_dump(mode="json")
    assert independent["risk_assessment"] == core.risk_assessment.model_dump(mode="json")
    return report, independent, destination


@pytest.mark.parametrize(
    "prepared,outcome,reason,decided,observed,mapping",
    [
        ({"mode": "normal"}, "PASS", None, 1, 10000, 1),
        ({"mode": "timeout", "delay_seconds": 3.2}, "PASS", None, 1, 8000, 1),
        ({"mode": "intermittent", "failure_every": 1}, "FAIL", "AGENT_SERVICE_ERROR", 1, 0, None),
        ({"mode": "timeout", "delay_seconds": 20}, "UNKNOWN", "SERVICE_TIMEOUT", 0, None, None),
        ({"mode": "unsupported"}, "FAIL", "CAPABILITY_EXPLICITLY_UNSUPPORTED", 1, 10000, 0),
    ],
    indirect=["prepared"],
)
def test_real_service_availability_has_fixed_outcomes_and_never_reuses_functional_denominator(
    prepared, monkeypatch, tmp_path, outcome, reason, decided, observed, mapping
):
    scenario = controlled_run(prepared, monkeypatch, "availability")
    before = scenario[0][4].eth.block_number
    advance(scenario, "evaluate")
    advance(scenario, "verify")
    report, _, _ = check_report(
        scenario,
        tmp_path,
        outcome=outcome,
        reason=reason,
        purpose="availability",
        decided=decided,
        observed=observed,
        mapping=mapping,
    )
    assert scenario[0][4].eth.block_number == before
    assert report.core.raw_statistics["behavior"]["correct"] == 0


@pytest.mark.parametrize("prepared", [{"mode": "unsupported"}], indirect=True)
def test_declared_but_unsupported_capability_is_a_real_functional_failure(
    prepared, monkeypatch, tmp_path
):
    scenario = controlled_run(prepared, monkeypatch, "functional")
    advance(scenario, "evaluate")
    advance(scenario, "verify")
    check_report(
        scenario,
        tmp_path,
        outcome="FAIL",
        reason="CAPABILITY_EXPLICITLY_UNSUPPORTED",
        purpose="functional",
        decided=1,
        observed=0,
        mapping=0,
    )
    assert not records(scenario[0], scenario[2])


@pytest.mark.parametrize(
    "prepared,outcome,reason,critical,observed",
    [
        ("a", "PASS", None, False, 10000),
        ("d", "FAIL", "TASK_ID_MISMATCH", True, 0),
        ({"mode": "wrong_executor", "executor_sample": "d"}, "FAIL", "TX_WRONG_EXECUTOR", True, 0),
    ],
    indirect=["prepared"],
)
def test_successful_receipt_requires_current_task_and_the_bound_executor(
    prepared, monkeypatch, tmp_path, outcome, reason, critical, observed
):
    scenario = controlled_run(prepared, monkeypatch, "behavioral")
    advance(scenario, "evaluate")
    advance(scenario, "verify")
    report, _, _ = check_report(
        scenario,
        tmp_path,
        outcome=outcome,
        reason=reason,
        purpose="behavioral",
        decided=1,
        observed=observed,
        mapping=1,
        critical=critical,
        accepted=True,
    )
    candidate = scenario[3].result(scenario[1]).task_link.candidate_tx_hash
    assert scenario[0][4].eth.get_transaction_receipt(candidate)["status"] == 1
    assert report.core.raw_statistics["behavior"]["correct"] == int(outcome == "PASS")
    if reason == "TX_WRONG_EXECUTOR":
        assert (
            scenario[0][4].eth.get_transaction(candidate)["from"].lower()
            == scenario[0][2]["d"]["executor"]
        )


@pytest.mark.parametrize(
    "change,reason",
    [
        ("version", "IDENTITY_CHANGED"),
        ("executor_code", "BINDING_UNVERIFIED"),
        ("revoke", "ACCESS_NOT_GRANTED"),
    ],
)
def test_identity_and_authorization_changes_stop_dispatch_and_are_evidence_gaps(
    prepared, monkeypatch, tmp_path, change, reason
):
    scenario = controlled_run(prepared, monkeypatch, "behavioral")
    flow, run_id, plan, _, _, _ = scenario
    if change == "version":
        registry = flow[4].eth.contract(
            address=Web3.to_checksum_address(flow[5].registry.address),
            abi=contract_abi(flow[1].root, "DemoAgentRegistry"),
        )
        metadata = {
            **flow[2]["a"]["metadata"],
            "description": "Controlled service version v2; declaration changed",
        }
        uri = "data:application/json;base64," + base64.b64encode(canonical_bytes(metadata)).decode()
        SetupJournal(flow[6] / "version-change.sqlite3", flow[4]).transact(
            "set-version",
            flow[3]["owner-a"],
            registry.functions.setAgentURI(int(flow[2]["a"]["agent_ref"]["agent_id"]), uri),
        )
    elif change == "executor_code":
        reply = flow[4].provider.make_request(
            RPCEndpoint("anvil_setCode"), [flow[2]["a"]["executor"], "0x60006000f3"]
        )
        assert "error" not in reply
    else:
        response = flow[0].post(
            f"/api/v1/access-grants/{plan.slots[0].grant_id}/revoke",
            headers=AUTH,
            json={"reason": "Controlled authorization withdrawal"},
        )
        assert response.status_code == 200, response.text
    advance(scenario, "evaluate")
    advance(scenario, "verify")
    report, _, _ = check_report(
        scenario,
        tmp_path,
        outcome="UNKNOWN",
        reason=reason,
        purpose="behavioral",
        decided=0,
        observed=None,
        mapping=None,
    )
    with flow[1].db.connect() as connection:
        # Settlement records a not_sent attempt even when preflight forbids all HTTP dispatch.
        reserved = (
            connection.execute(
                select(attempts.c.body).where(attempts.c.slot_fk == plan.slots[0].slot_id)
            )
            .scalars()
            .all()
        )
        assert len(reserved) == 1 and reserved[0]["operation"] == "not_sent"
        assert (
            connection.scalar(
                select(func.count())
                .select_from(dispatch_events)
                .where(
                    dispatch_events.c.slot_fk == plan.slots[0].slot_id,
                    dispatch_events.c.state.in_(("SENDING", "RESOLVING")),
                )
            )
            == 0
        )
    saved = next(
        item for item in report.manifest.evidence if item.source == "record-verification-input"
    )
    inputs = RecordVerificationInput.model_validate_json(scenario[4].read_evidence(saved))
    assert inputs.dispatch_started_at is None
    assert inputs.agent_http is None and inputs.initial_agent_http is None
    assert not records(flow, plan)
    if change == "version":
        with flow[1].db.connect() as connection:
            agent_id = connection.execute(
                select(snapshots.c.agent_fk).where(
                    snapshots.c.id == UUID(prepared[1]["snapshot_id"])
                )
            ).scalar_one()
        _, current, _ = capture(flow, agent_id=str(agent_id))
        assert current["snapshot_hash"] != plan.snapshot_hash
        assert current["core"]["normalized_metadata"]["description"] == metadata["description"]
        assert current["core"]["registry_revision"] > 1
        assert flow[0].get(f"/api/v1/snapshots/{current['snapshot_id']}/bindings").json() == []


@pytest.mark.parametrize(
    "fault,reason",
    [
        ("connection", "PLATFORM_RPC_ERROR"),
        ("rpc_timeout", "PLATFORM_RPC_ERROR"),
        ("wrong_chain", "CHAIN_INSTANCE_CHANGED"),
        ("invalid_receipt", "PLATFORM_RPC_ERROR"),
    ],
)
def test_recovered_rpc_fault_keeps_frozen_unknown_and_independent_live_resolution(
    prepared, monkeypatch, tmp_path, fault, reason
):
    scenario = controlled_run(prepared, monkeypatch, "behavioral")
    flow, run_id, plan, verifier, reports, _ = scenario
    advance(scenario, "evaluate")
    deployment = flow[1].deployment()
    collect = verification_module.collect_task

    def faulted_evidence(*args, **kwargs):
        evidence = collect(*args, **kwargs)
        changed = deepcopy(evidence.model_dump(mode="json")["results"])
        assert evidence.error_reason is None and changed["receipt"]["status"] == "0x1"
        if fault == "wrong_chain":
            changed["chain_id"] = "0x1"
        else:
            changed["receipt"]["status"] = "0x2"
        return evidence.model_copy(update={"results": changed})

    with monkeypatch.context() as injection:
        if fault in {"connection", "rpc_timeout"}:
            # Real RPC refusal or read timeout; Agent already wrote on healthy Anvil.
            with socket.socket() as refused:
                refused.bind(("127.0.0.1", 0))
                if fault == "rpc_timeout":
                    refused.listen(16)
                flow[1]._deployment = deployment.model_copy(
                    update={"rpc_url": f"http://127.0.0.1:{refused.getsockname()[1]}"}
                )
                try:
                    advance(scenario, "verify")
                    if fault == "rpc_timeout":
                        refused.settimeout(1)
                        with refused.accept()[0] as captured:
                            captured.settimeout(1)
                            request = captured.recv(65536)
                            assert request.startswith(b"POST ") and b"eth_chainId" in request
                finally:
                    flow[1]._deployment = deployment
        else:
            # Controlled platform observation faults over real RPC evidence, never fake Agent tasks.
            injection.setattr(verification_module, "collect_task", faulted_evidence)
            advance(scenario, "verify")
    historical = verifier.result(run_id)
    assert historical.task_link.candidate_tx_hash is not None
    report, _, destination = check_report(
        scenario,
        tmp_path,
        outcome="UNKNOWN",
        reason=reason,
        purpose="behavioral",
        decided=0,
        observed=None,
        mapping=1,
        accepted=True,
    )
    assert len(records(flow, plan)) == 1
    original = next(
        item for item in report.manifest.evidence if item.source == "record-verification-input"
    )
    frozen = next(
        item
        for item in report.manifest.evidence
        if item.source == "report-freeze-verification-input"
    )
    saved = RecordVerificationInput.model_validate_json(reports.read_evidence(original))
    recovered = RecordVerificationInput.model_validate_json(reports.read_evidence(frozen))
    assert saved.evm.candidate_tx_hash == recovered.evm.candidate_tx_hash
    live = verify_bundle(str(destination), task_rpc_url=flow[5].rpc_url)
    assert live["offline"] == "PASS"
    assert live["task_results"][0]["outcome"] == "UNKNOWN"
    assert live["task_results"][0]["live_chain"]["status"] == "RESOLVED"
    assert live["task_results"][0]["live_chain"]["outcome"] == "PASS"


def test_recovered_record_query_rpc_fault_preserves_http_availability(
    prepared, monkeypatch, tmp_path
):
    scenario = controlled_run(prepared, monkeypatch, "availability")
    flow, _, plan, _, reports, _ = scenario
    before = flow[4].eth.block_number
    advance(scenario, "evaluate")
    collect = verification_module.collect_task

    def invalid_call(*args, **kwargs):
        evidence = collect(*args, **kwargs)
        changed = deepcopy(evidence.model_dump(mode="json")["results"])
        assert evidence.error_reason is None and len(changed["record_call"]) == 130
        changed["record_call"] = "0x1234"
        return evidence.model_copy(update={"results": changed})

    with monkeypatch.context() as injection:
        injection.setattr(verification_module, "collect_task", invalid_call)
        advance(scenario, "verify")
    report, _, destination = check_report(
        scenario,
        tmp_path,
        outcome="UNKNOWN",
        reason="PLATFORM_RPC_ERROR",
        purpose="availability",
        decided=1,
        observed=10000,
        mapping=1,
    )
    assert flow[4].eth.block_number == before
    assert report.core.raw_statistics["capabilities"][0]["decided"] == 0
    assert (
        report.core.evidence_sufficiency.dimensions["availability"]["unknown_or_unresolved_bp"] == 0
    )
    original = next(
        item for item in report.manifest.evidence if item.source == "record-verification-input"
    )
    frozen = next(
        item
        for item in report.manifest.evidence
        if item.source == "report-freeze-verification-input"
    )
    saved = RecordVerificationInput.model_validate_json(reports.read_evidence(original))
    recovered = RecordVerificationInput.model_validate_json(reports.read_evidence(frozen))
    assert saved.evm.results["record_call"] == "0x1234"
    assert recovered.evm.results["record_call"] != saved.evm.results["record_call"]
    assert not records(flow, plan)
    live = verify_bundle(str(destination), task_rpc_url=flow[5].rpc_url)
    assert live["offline"] == "PASS" and live["assessment_comparison"] == "MATCH"
    assert live["task_results"][0]["outcome"] == "UNKNOWN"
    assert live["task_results"][0]["live_chain"]["status"] == "RESOLVED"
    assert live["task_results"][0]["live_chain"]["outcome"] == "PASS"
