"""Real Agent writes survive a recovered platform RPC log contradiction as UNKNOWN."""

import asyncio
from copy import deepcopy

import pytest
from reputation_core.models import RecordVerificationInput
from reputation_core.record_verifier import verify_record
from reputation_platform.application import evaluations as evaluation_module
from reputation_platform.application import reports as report_module
from reputation_platform.application import verification as verification_module
from reputation_platform.application.execution import ExecutionService
from reputation_platform.application.local_deploy import contract_abi
from reputation_platform.application.reports import ReportService
from reputation_platform.application.verification import VerificationService
from reputation_platform.infrastructure.db.tables import jobs, reports
from reputation_platform.worker.main import Worker
from reputation_verifier.bundle import verify_bundle
from sqlalchemy import func, select
from web3 import Web3

from tests.integration.test_execution import prepared
from tests.integration.test_formal_evaluation import create_formal, formal_request
from tests.integration.test_identity import flow, identity_chain

__all__ = ["prepared", "flow", "identity_chain"]
pytestmark = [pytest.mark.chain, pytest.mark.postgres]


@pytest.fixture
def single_write(prepared, monkeypatch):
    flow, original, _ = prepared
    body = formal_request(
        flow, original["snapshot_id"], 1, ("anchor_record",), flow[5].record.address
    )
    real_plan = evaluation_module.RunPlan

    def one_behavioral_slot(**values):
        values["slots"] = (
            next(slot for slot in values["slots"] if slot.purpose == "behavioral"),
        )
        return real_plan(**values)

    # Preserve real planning and intent persistence; a partial plan needs no full sample window.
    with monkeypatch.context() as scoped:
        scoped.setattr(evaluation_module, "RunPlan", one_behavioral_slot)
        run_id, plan = create_formal(flow, body)
    assert len(plan.slots) == 1 and plan.template_version == "capabilities@6"
    contract = flow[4].eth.contract(
        address=Web3.to_checksum_address(flow[5].record.address),
        abi=contract_abi(flow[1].root, "DemoRecordRegistry"),
    )
    foreign_tx = contract.events.RecordAnchored().get_logs(from_block=0)[0]["transactionHash"].to_0x_hex()
    verifier = VerificationService(flow[1].db, flow[1])
    service = ReportService(flow[1].db, flow[1])
    worker = Worker(flow[1].db, {
        "evaluate": ExecutionService(flow[1].db, flow[1]).execute,
        "verify": verifier.verify,
        "report": service.freeze,
    })
    assert asyncio.run(worker.run_once())
    with flow[1].db.connect() as connection:
        assert connection.scalar(select(jobs.c.state).where(
            jobs.c.run_fk == run_id, jobs.c.kind == "evaluate"
        )) == "SUCCEEDED"
    return flow, run_id, plan, verifier, service, worker, foreign_tx


@pytest.mark.parametrize("fault_stage", ["verify", "report", "logs_shape"])
def test_rpc_log_location_fault_preserves_unknown_but_cannot_invalidate_a_decided_report(
    single_write, monkeypatch, tmp_path, fault_stage
):
    flow, run_id, plan, verifier, service, worker, foreign_tx = single_write
    injection_stage = "report" if fault_stage == "report" else "verify"
    historical_reason = "PLATFORM_RPC_ERROR" if fault_stage == "logs_shape" else "EVIDENCE_INCONSISTENT"
    module = verification_module if injection_stage == "verify" else report_module
    collect = module.collect_task
    faulted_candidates = []

    def inconsistent_log(*args, **kwargs):
        evidence = collect(*args, **kwargs)
        assert evidence.error_reason is None
        results = deepcopy(evidence.results)
        assert results["receipt"]["status"] == "0x1"
        assert results["receipt"]["logs"][0]["transactionHash"] == evidence.candidate_tx_hash
        assert evidence.candidate_tx_hash != foreign_tx
        if fault_stage == "logs_shape":
            results["receipt"]["logs"][0]["topics"][0] = None
        else:
            results["receipt"]["logs"][0]["transactionHash"] = foreign_tx
        faulted_candidates.append(evidence.candidate_tx_hash)
        return evidence.model_copy(update={"results": results})

    for kind in ("verify", "report"):
        with monkeypatch.context() as fault:
            if kind == injection_stage:
                fault.setattr(module, "collect_task", inconsistent_log)
            assert asyncio.run(worker.run_once())
        with flow[1].db.connect() as connection:
            job = connection.execute(select(jobs.c.state, jobs.c.last_error).where(
                jobs.c.run_fk == run_id, jobs.c.kind == kind
            )).one()
        if kind == "report" and fault_stage == "report":
            assert job.state == "FAILED" and job.last_error == "STALE_EVIDENCE"
        else:
            assert job.state == "SUCCEEDED", (kind, job)
        if kind == "verify":
            result = verifier.result(run_id)
            assert result.outcome == ("UNKNOWN" if injection_stage == "verify" else "PASS")
            assert result.reason_code == (historical_reason if injection_stage == "verify" else None)
            assert not result.critical_conflict
            receipt = flow[4].eth.get_transaction_receipt(result.task_link.candidate_tx_hash)
            assert receipt["status"] == 1
            assert receipt["logs"][0]["transactionHash"].to_0x_hex() == result.task_link.candidate_tx_hash
    assert len(faulted_candidates) == 1
    if fault_stage == "report":
        with flow[1].db.connect() as connection:
            assert connection.scalar(select(func.count()).select_from(reports)) == 0
        return

    report = service.for_run(run_id)
    assert report.core.schema_version == "1.5.0"
    assert report.core.task_counts.unknown_count == 1 and report.core.task_counts.fail_count == 0
    assert report.core.task_results[0].reason_code == historical_reason
    assert report.core.scores.overall_score_bp is None and not report.core.scores.critical_conflict
    assert report.core.raw_statistics["behavior"]["decided"] == 0
    assert not report.core.risk_assessment.critical_findings
    assert not report.core.risk_assessment.ordinary_failure_slots
    assert report.core.risk_assessment.evidence_gap_slots == (plan.slots[0].slot_id,)
    original = next(item for item in report.manifest.evidence if item.source == "record-verification-input")
    frozen = next(item for item in report.manifest.evidence if item.source == "report-freeze-verification-input")
    original_input = RecordVerificationInput.model_validate_json(service.read_evidence(original))
    frozen_input = RecordVerificationInput.model_validate_json(service.read_evidence(frozen))
    assert verify_record(original_input, (original.evidence_id,)).outcome == "UNKNOWN"
    assert verify_record(frozen_input, (original.evidence_id,)).outcome == "PASS"
    destination = tmp_path / "rpc-log-unknown.zip"
    bundle = service.export(report.report_id)
    assert service.export(report.report_id) == bundle
    destination.write_bytes(bundle)
    independent = verify_bundle(str(destination), task_rpc_url=flow[5].rpc_url)
    assert independent["offline"] == "PASS" and independent["task_count_comparison"] == "MATCH"
    assert independent["assessment_comparison"] == "MATCH"
    assert independent["task_results"][0]["outcome"] == "UNKNOWN"
    assert independent["task_results"][0]["reason_code"] == historical_reason
    assert independent["task_results"][0]["live_chain"]["status"] == "RESOLVED"
    assert independent["task_results"][0]["live_chain"]["outcome"] == "PASS"
    assert independent["evidence_sufficiency"] == report.core.evidence_sufficiency.model_dump(mode="json")
    assert independent["risk_assessment"] == report.core.risk_assessment.model_dump(mode="json")
