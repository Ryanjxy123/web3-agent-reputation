"""Real task evidence -> frozen partial report -> deterministic committed ZIP bytes."""

import asyncio
import io
import json
import zipfile
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from uuid import UUID, uuid4

import pytest
from reputation_core.evidence import canonical_bytes, hash_bytes, hash_json, strict_json
from reputation_core.models import Observation, RecordVerificationInput, RunPlan
from reputation_core.reporting import build_report
from reputation_platform.application.errors import ApplicationError
from reputation_platform.application.reports import ReportService
from reputation_platform.infrastructure import evidence_store
from reputation_platform.infrastructure.db.jobs import JobQueue, LostLease, enqueue
from reputation_platform.infrastructure.db.tables import anchor_jobs, jobs, reports, runs, snapshots
from reputation_platform.worker.main import Worker
from reputation_verifier import verify_bundle
from sqlalchemy import func, insert, select, text, update

from tests.integration.test_identity import AUTH
from tests.integration.test_verification import complete, flow, identity_chain, prepared

__all__ = ["flow", "identity_chain", "prepared"]
pytestmark = [pytest.mark.chain, pytest.mark.postgres]


def freeze(prepared):
    flow, _, _ = prepared
    complete(prepared)
    service = ReportService(flow[1].db, flow[1])
    worker = Worker(flow[1].db, {"report": service.freeze})
    assert asyncio.run(worker.run_once())
    with flow[1].db.connect() as connection:
        identifier = connection.execute(select(reports.c.id)).scalar_one()
    return service, service.view(identifier)


@pytest.mark.parametrize("prepared", ["a", "d"], indirect=True)
def test_real_report_recomputes_partial_and_exports_identical_bytes(prepared, tmp_path):
    service, report = freeze(prepared)
    core = report.core
    assert core.scores.evaluation_state == "PARTIAL" and core.scores.overall_score_bp is None
    assert (
        core.raw_statistics["availability"]["decided"]
        == core.raw_statistics["behavior"]["decided"]
        == 0
    )
    assert core.raw_statistics["capabilities"][0]["decided"] == 1
    assert core.raw_statistics["capabilities"][0]["mapping"] is None
    assert core.scores.advice == (
        "NOT_RECOMMENDED" if core.scores.critical_conflict else "INSUFFICIENT_EVIDENCE"
    )
    bundle = service.export(report.report_id)
    assert service.export(report.report_id) == bundle
    bundle_path = tmp_path / "report.zip"
    bundle_path.write_bytes(bundle)
    replayed = verify_bundle(str(bundle_path))
    assert replayed["offline"] == "PASS"
    assert replayed["task_count_comparison"] == "MATCH"
    assert replayed["task_counts"] == core.task_counts.model_dump(mode="json")
    assert replayed["task_results"][0]["outcome"] == core.task_results[0].outcome
    live_replay = verify_bundle(str(bundle_path), task_rpc_url=prepared[0][5].rpc_url)
    assert live_replay["offline"] == "PASS"
    assert live_replay["task_results"][0]["live_chain"]["status"] == "CONFIRMED"
    response = prepared[0][0].get(f"/api/v1/reports/{report.report_id}/bundle")
    assert response.status_code == 200 and response.content == bundle
    api = prepared[0][0]
    with service.db.connect() as connection:
        agent_id = connection.execute(select(snapshots.c.agent_fk).where(
            snapshots.c.id == UUID(prepared[1]["snapshot_id"])
        )).scalar_one()
    history = api.get(f"/api/v1/agents/{agent_id}/reports")
    assert history.status_code == 200 and history.json() == {"items": [report.model_dump(mode="json")], "next_cursor": None}
    assert api.get(f"/api/v1/agents/{agent_id}/reports", params={"cursor": str(uuid4())}).status_code == 404
    assert api.get(f"/api/v1/agents/{uuid4()}/reports").status_code == 404
    receipt = api.get(f"/api/v1/reports/{report.report_id}/anchor")
    assert receipt.status_code == 200 and receipt.json()["status"] == "NOT_REQUESTED"
    packet_id = core.task_results[0].input_evidence_id
    packet = api.get(f"/api/v1/reports/{report.report_id}/evidence/{packet_id}")
    assert packet.status_code == 200 and packet.json()["record"]["evidence_id"] == str(packet_id)
    assert packet.json()["body"]["slot"]["slot_id"] == str(core.task_results[0].slot_id)
    assert api.get(f"/api/v1/reports/{report.report_id}/evidence/{uuid4()}").status_code == 404
    with zipfile.ZipFile(io.BytesIO(bundle)) as archive:
        files = {name: archive.read(name) for name in archive.namelist()}
    assert hash_bytes(files["report_core.json"]) == report.report_hash
    assert hash_bytes(files["evidence_manifest.json"]) == core.evidence_manifest_hash
    assert strict_json(files["anchor_receipt.json"])["status"] == "NOT_REQUESTED"
    by_id = {str(item.evidence_id): item for item in report.manifest.evidence}
    for item in report.manifest.evidence:
        assert (
            hash_bytes(files[item.path]) == item.blob_hash
            and len(files[item.path]) == item.byte_count
        )
    for item in report.manifest.documents:
        assert files[item.path] == files[by_id[str(item.evidence_id)].path]
    committed = {item.path for item in report.manifest.documents} | {
        item.path for item in report.manifest.evidence
    }
    assert set(files) - committed == {
        "report_core.json",
        "evidence_manifest.json",
        "anchor_receipt.json",
        "FORMAT.md",
    }
    policy = strict_json(files["policy.json"])
    assert [
        policy["availability"]["min_samples"],
        policy["consistency"]["min_cases_per_capability"],
        policy["behavior"]["min_accepted_decided_tasks"],
    ] == [20, 10, 10]
    refs = strict_json(files["verification.json"])
    task_ref = refs["tasks"][0]
    evidence = by_id[task_ref["input_evidence_id"]]
    inputs = RecordVerificationInput.model_validate_json(files[evidence.path])
    assert refs["schema_version"] == "task-replay-v1"
    assert task_ref["slot_id"] == str(inputs.slot.slot_id)
    assert core.task_results[0].input_evidence_id == evidence.evidence_id
    assert core.task_counts.model_dump(mode="json")[core.task_results[0].outcome] == 1
    rebuilt = build_report(
        RunPlan.model_validate_json(files["run_plan.json"]),
        inputs,
        evidence.evidence_id,
        tuple(Observation.model_validate(item) for item in strict_json(files["observations.json"])),
        policy,
        evaluated_at=core.evaluated_at,
        code_version=core.code_version,
        manifest_hash=core.evidence_manifest_hash,
        previous_report_hash=core.previous_report_hash,
    )
    assert rebuilt == core and hash_json(rebuilt.model_dump(mode="json")) == report.report_hash
    assert (
        hash_bytes(canonical_bytes(dict(reversed(list(core.model_dump(mode="json").items())))))
        == report.report_hash
    )
    # Private setup material never appears in the evidence or any document alias.
    for key in prepared[0][3].values():
        assert all(
            key.encode() not in data and key.removeprefix("0x").encode() not in data
            for data in files.values()
        )


def test_two_report_jobs_freeze_one_immutable_revision(prepared):
    _, inputs, _ = complete(prepared)
    identity = prepared[0][1]
    service = ReportService(identity.db, identity)
    with identity.db.begin() as connection:
        run_id = connection.execute(select(runs.c.id)).scalar_one()
        enqueue(connection, "report", f"duplicate-test:{uuid4()}", {"run_id": str(run_id)}, run_id)
    workers = [Worker(identity.db, {"report": service.freeze}) for _ in range(2)]
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert all(pool.map(lambda worker: asyncio.run(worker.run_once()), workers))
    with identity.db.connect() as connection:
        assert connection.scalar(select(func.count()).select_from(reports)) == 1
        assert (
            connection.scalar(
                select(func.count())
                .select_from(jobs)
                .where(jobs.c.kind == "report", jobs.c.state == "SUCCEEDED")
            )
            == 2
        )
    report = service.for_run(run_id)
    assert report.core.snapshot_hash == inputs.snapshot.snapshot_hash


def test_export_refuses_changed_or_missing_committed_bytes(prepared):
    service, report = freeze(prepared)
    item = report.manifest.evidence[0]
    path = service.identity.evidence.root / item.path
    original = path.read_bytes()
    try:
        path.write_bytes(original + b" ")
        response = prepared[0][0].get(f"/api/v1/reports/{report.report_id}/evidence/{item.evidence_id}")
        assert response.status_code == 409 and response.json()["error"]["code"] == "CONTENT_HASH_MISMATCH"
        with pytest.raises(ApplicationError) as failure:
            service.export(report.report_id)
        assert failure.value.code == "CONTENT_HASH_MISMATCH"
        path.unlink()
        response = prepared[0][0].get(f"/api/v1/reports/{report.report_id}/evidence/{item.evidence_id}")
        assert response.status_code == 409 and response.json()["error"]["code"] == "MISSING_EVIDENCE"
        with pytest.raises(ApplicationError) as failure:
            service.export(report.report_id)
        assert failure.value.code == "MISSING_EVIDENCE"
    finally:
        path.write_bytes(original)


@pytest.mark.parametrize("location", ["cas_url", "cas_escaped_url", "cas_secret_field", "manifest_source"])
def test_historical_sensitive_report_evidence_and_bundle_are_restricted(prepared, monkeypatch, location):
    service, report = freeze(prepared)
    api = prepared[0][0]
    safe_bundle = service.export(report.report_id)
    secret = "HISTORICAL_REPORT_SYNTHETIC_CREDENTIAL_ONLY"
    url = f"https://audit-user:{secret}@example.com/legacy"
    if location == "cas_url":
        content = {"nested": [{"example": url}]}
    elif location == "cas_escaped_url":
        content = {"response": {"raw_body_utf8": json.dumps({"example": url}).replace("/", r"\/")}}
    elif location == "cas_secret_field":
        content = {"token": secret}
    else:
        content = {"note": "historical safe CAS with sensitive record metadata"}
    # Only this synthetic append simulates the pre-fix collector; original CAS stays intact.
    with monkeypatch.context() as legacy:
        legacy.setattr(evidence_store, "redact", lambda value: value)
        extra = service.identity.evidence.prepare_json(
            content, url if location == "manifest_source" else "legacy-synthetic",
            report.core.evaluated_at, "test",
        )
    original_bytes = service.identity.evidence.read(extra)
    with service.db.begin() as connection:
        extra = service.identity.evidence.register(connection, extra)
        manifest = report.manifest.model_copy(update={"evidence": tuple(sorted(
            (*report.manifest.evidence, extra), key=lambda item: str(item.evidence_id),
        ))})
        core = report.core.model_copy(update={
            "evidence_manifest_hash": hash_json(manifest.model_dump(mode="json")),
        })
        identifier = uuid4()
        report_body = core.model_dump(mode="json")
        manifest_body = manifest.model_dump(mode="json")
        digest = hash_json(report_body)
        connection.execute(insert(reports).values(
            id=identifier, run_fk=report.core.run_id, revision=2,
            report_hash=digest, previous_report_hash=core.previous_report_hash,
            core=report_body, manifest=manifest_body,
        ))
    packet_path = f"/api/v1/reports/{identifier}/evidence/{extra.evidence_id}"
    for path in (packet_path, f"/api/v1/reports/{identifier}/bundle"):
        response = api.get(path)
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "HISTORICAL_EVIDENCE_RESTRICTED"
        assert secret not in response.text
    with pytest.raises(ApplicationError) as failure:
        service.export(identifier)
    assert failure.value.code == "HISTORICAL_EVIDENCE_RESTRICTED"
    if location == "manifest_source":
        with service.db.connect() as connection:
            agent_id = connection.execute(select(snapshots.c.agent_fk).where(
                snapshots.c.id == UUID(prepared[1]["snapshot_id"]),
            )).scalar_one()
        for path in (f"/api/v1/reports/{identifier}", f"/api/v1/agents/{agent_id}/reports"):
            response = api.get(path)
            assert response.status_code == 403
            assert response.json()["error"]["code"] == "HISTORICAL_EVIDENCE_RESTRICTED"
            assert secret not in response.text
    assert service.identity.evidence.read(extra) == original_bytes
    assert hash_bytes(original_bytes) == extra.blob_hash
    assert service.view(identifier).report_hash == digest
    with service.db.connect() as connection:
        stored = connection.execute(select(reports.c.core, reports.c.manifest).where(
            reports.c.id == identifier,
        )).one()
    assert stored.core == report_body and stored.manifest == manifest_body
    assert service.export(report.report_id) == safe_bundle
    safe = api.get(f"/api/v1/reports/{report.report_id}/bundle")
    assert safe.status_code == 200 and safe.content == safe_bundle


def test_pending_and_failed_anchor_receipts_show_safe_outbox_state(prepared, tmp_path):
    service, report = freeze(prepared)
    api = prepared[0][0]
    path = f"/api/v1/reports/{report.report_id}/anchor"
    assert api.get(path).json()["status"] == "NOT_REQUESTED"
    assert api.post(path, headers=AUTH).status_code == 202
    assert api.get(path).json()["status"] == "QUEUED"
    transaction_hash = "0x" + "ab" * 32
    for state in ("SIGNED", "BROADCAST", "FAILED"):
        with service.db.begin() as connection:
            connection.execute(update(anchor_jobs).where(anchor_jobs.c.report_fk == report.report_id).values(
                state=state, signed_tx_hash=transaction_hash, signed_transaction="must-not-export-signed-bytes",
            ))
        response = api.get(path)
        assert response.status_code == 200
        receipt = response.json()
        assert receipt["status"] == state and receipt["tx_hash"] == transaction_hash
        assert receipt["block_number"] is None and receipt["confirmations"] == 0
        assert "must-not-export-signed-bytes" not in response.text
        bundle = service.export(report.report_id)
        with zipfile.ZipFile(io.BytesIO(bundle)) as archive:
            assert strict_json(archive.read("anchor_receipt.json")) == receipt
            assert hash_bytes(archive.read("report_core.json")) == report.report_hash
            assert all(b"must-not-export-signed-bytes" not in archive.read(name) for name in archive.namelist())
        bundle_path = tmp_path / f"{state}.zip"
        bundle_path.write_bytes(bundle)
        assert verify_bundle(bundle_path)["status"] == "PASS"


def test_evidence_endpoint_rejects_an_existing_member_of_another_report(prepared):
    service, report = freeze(prepared)
    extra = service.identity.evidence.prepare_json({"note": "only in the other report", "token": "must-be-redacted"}, "foreign-report-test", report.core.evaluated_at, "test")
    with service.db.begin() as connection:
        extra = service.identity.evidence.register(connection, extra)
        manifest = report.manifest.model_copy(update={"evidence": tuple(sorted(
            (*report.manifest.evidence, extra), key=lambda item: str(item.evidence_id)
        ))})
        core = report.core.model_copy(update={"evidence_manifest_hash": hash_json(manifest.model_dump(mode="json"))})
        other_report_id = uuid4()
        connection.execute(insert(reports).values(
            id=other_report_id, run_fk=report.core.run_id, revision=2,
            report_hash=hash_json(core.model_dump(mode="json")), previous_report_hash=core.previous_report_hash,
            core=core.model_dump(mode="json"), manifest=manifest.model_dump(mode="json"),
        ))
    api = prepared[0][0]
    allowed = api.get(f"/api/v1/reports/{other_report_id}/evidence/{extra.evidence_id}")
    assert allowed.status_code == 200 and allowed.json()["body"]["token"] == "[REDACTED]"
    denied = api.get(f"/api/v1/reports/{report.report_id}/evidence/{extra.evidence_id}")
    assert denied.status_code == 404 and denied.json()["error"]["code"] == "NOT_FOUND"
    assert "only in the other report" not in denied.text


def test_report_commit_before_job_ack_is_recovered_without_new_revision(prepared):
    complete(prepared)
    identity = prepared[0][1]
    service = ReportService(identity.db, identity)
    old = JobQueue(identity.db, "old-report-worker")
    lease = old.claim()
    assert lease and lease.kind == "report"
    asyncio.run(service.freeze(lease, old))
    first = service.for_run(lease.run_id)
    with identity.db.begin() as connection:
        connection.execute(
            update(jobs)
            .where(jobs.c.id == lease.job_id)
            .values(lease_until=func.clock_timestamp() - text("interval '1 second'"))
        )
    newer = JobQueue(identity.db, "new-report-worker")
    resumed = newer.claim()
    assert resumed and resumed.job_id == lease.job_id and resumed.token != lease.token
    asyncio.run(service.freeze(resumed, newer))
    newer.complete(resumed)
    with pytest.raises(LostLease):
        old.complete(lease)
    assert service.for_run(lease.run_id) == first
    with identity.db.connect() as connection:
        assert connection.scalar(select(func.count()).select_from(reports)) == 1


def test_slow_report_replay_does_not_hold_the_fenced_job_row(prepared, monkeypatch):
    """A real heartbeat must renew while pure report replay remains blocked."""
    complete(prepared)
    identity = prepared[0][1]
    service = ReportService(identity.db, identity)
    from reputation_platform.application import reports as report_module

    original = report_module.build_report
    replay_entered, renewed_during_replay = Event(), Event()
    worker = Worker(identity.db, {"report": service.freeze})
    worker.heartbeat_interval = 0.05
    heartbeat = worker.queue.heartbeat

    def renew(lease):
        during_replay = replay_entered.is_set()
        heartbeat(lease)
        if during_replay:
            renewed_during_replay.set()

    def slow_replay(*args, **kwargs):
        replay_entered.set()
        assert renewed_during_replay.wait(10), "heartbeat blocked during report replay"
        return original(*args, **kwargs)

    monkeypatch.setattr(worker.queue, "heartbeat", renew)
    monkeypatch.setattr(report_module, "build_report", slow_replay)
    assert asyncio.run(worker.run_once())
    assert renewed_during_replay.is_set()
    with identity.db.connect() as connection:
        assert connection.scalar(select(jobs.c.state).where(jobs.c.kind == "report")) == "SUCCEEDED"
        assert connection.scalar(select(func.count()).select_from(reports)) == 1
