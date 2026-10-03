"""Freeze immutable partial reports; export only hash-checked committed evidence."""

import asyncio
import io
import os
import re
import subprocess
import zipfile
from uuid import UUID, uuid4

from reputation_core.binding import agent_key_hash
from reputation_core.evidence import canonical_bytes, hash_json, strict_json
from reputation_core.models import (
    AcceptedJob,
    AnchorReceipt,
    AnchorStatus,
    EvidenceManifest,
    EvidenceRecord,
    ManifestDocument,
    Observation,
    PublicationContext,
    RecordVerificationInput,
    ReportView,
    RunPlan,
)
from reputation_core.record_verifier import verify_record
from reputation_core.reporting import build_report
from sqlalchemy import Engine, insert, select, text, update
from web3 import Web3

from reputation_platform.adapters.evm.collector import collect_task
from reputation_platform.adapters.registries.demo import timestamp
from reputation_platform.infrastructure.db.jobs import JobQueue, Lease, enqueue
from reputation_platform.infrastructure.db.tables import (
    anchor_jobs,
    anchor_receipts,
    case_slots,
    evidence_blobs,
    evidence_manifest_items,
    observations,
    reports,
    runs,
)

from .errors import ApplicationError
from .identity import IdentityService
from .local_deploy import contract_abi, local_web3, verify_deployment
from .verification import VerificationService

FORMAT = b"Web3 Agent Reputation evidence bundle v1. Local Anvil demonstration.\nVerify committed bytes and recompute rules before interpreting scores.\nOffline consistency is not chain verification. Anchor receipt is outside the report hash.\n"


class ReportService:
    def __init__(self, db: Engine, identity: IdentityService | None = None):
        self.db, self.identity = db, identity or IdentityService(db)

    def read_evidence(self, record: EvidenceRecord) -> bytes:
        try:
            return self.identity.evidence.read(record)
        except OSError:
            raise ApplicationError(
                409, "MISSING_EVIDENCE", "A committed evidence file is missing."
            ) from None
        except ValueError:
            raise ApplicationError(
                409, "CONTENT_HASH_MISMATCH", "Committed evidence bytes changed."
            ) from None

    def request(self, run_id: UUID, actor: str) -> AcceptedJob:
        VerificationService(self.db, self.identity).result(run_id)
        with self.db.begin() as connection:
            identifier = enqueue(
                connection, "report", f"report:{run_id}", {"run_id": str(run_id)}, run_id
            )
            self.identity.audit(
                connection, actor, "report.request", run_id, {"job_id": str(identifier)}
            )
        return AcceptedJob(job_id=identifier, status_url=f"/api/v1/jobs/{identifier}")

    def view(self, report_id: UUID) -> ReportView:
        with self.db.connect() as connection:
            row = (
                connection.execute(select(reports).where(reports.c.id == report_id))
                .mappings()
                .first()
            )
        if row is None:
            raise ApplicationError(404, "REPORT_NOT_FOUND", "Report is not available.")
        result = ReportView(
            report_id=report_id,
            report_hash=row["report_hash"],
            core=row["core"],
            manifest=row["manifest"],
        )
        if result.report_hash != hash_json(
            result.core.model_dump(mode="json")
        ) or result.core.evidence_manifest_hash != hash_json(
            result.manifest.model_dump(mode="json")
        ):
            raise ApplicationError(
                409, "CONTENT_HASH_MISMATCH", "Frozen report integrity check failed."
            )
        return result

    def for_run(self, run_id: UUID) -> ReportView:
        with self.db.connect() as connection:
            identifier = connection.execute(
                select(reports.c.id)
                .where(reports.c.run_fk == run_id)
                .order_by(reports.c.revision.desc())
                .limit(1)
            ).scalar_one_or_none()
        if identifier is None:
            raise ApplicationError(404, "REPORT_NOT_FOUND", "Report is not available.")
        return self.view(identifier)

    def prepare(self, run_id: UUID):
        result = VerificationService(self.db, self.identity).result(run_id)
        evidence_id = result.assertions[0].evidence_refs[0]
        with self.db.connect() as connection:
            plan = RunPlan.model_validate(
                connection.execute(select(runs.c.plan).where(runs.c.id == run_id)).scalar_one()
            )
            record = EvidenceRecord.model_validate(
                connection.execute(
                    select(evidence_blobs.c.body).where(evidence_blobs.c.id == evidence_id)
                ).scalar_one()
            )
            observed = tuple(
                Observation.model_validate(body)
                for body in connection.execute(
                    select(observations.c.body)
                    .join(case_slots, observations.c.slot_fk == case_slots.c.id)
                    .where(case_slots.c.run_fk == run_id)
                    .order_by(observations.c.id)
                ).scalars()
            )
        inputs = RecordVerificationInput.model_validate_json(self.read_evidence(record))
        if verify_record(inputs, (evidence_id,)) != result:
            raise ApplicationError(
                409, "ASSERTION_REPLAY_MISMATCH", "Stored assertions differ from evidence replay."
            )
        deployment = self.identity.deployment()
        fresh = inputs.model_copy(
            update={
                "evm": collect_task(
                    deployment,
                    inputs.slot,
                    inputs.evm.candidate_tx_hash,
                    inputs.registry_witness.snapshot_core.read_block_number
                    if inputs.registry_witness
                    else None,
                )
            }
        )
        rechecked = verify_record(fresh, (evidence_id,))
        if fresh.evm.error_reason:
            retryable = fresh.evm.error_reason == "PLATFORM_RPC_ERROR"
            raise ApplicationError(
                503 if retryable else 409,
                fresh.evm.error_reason,
                "Trusted chain context is unavailable or changed before report freeze.",
                retryable=retryable,
            )
        if [(item.rule_id, item.outcome, item.reason_code) for item in rechecked.assertions] != [
            (item.rule_id, item.outcome, item.reason_code) for item in result.assertions
        ] or rechecked.task_link != result.task_link:
            raise ApplicationError(
                409,
                "STALE_EVIDENCE",
                "Chain evidence changed before report freeze; run a new evaluation.",
            )
        web3 = local_web3(deployment.rpc_url)
        verify_deployment(web3, deployment, self.identity.root)
        head = web3.eth.get_block("latest")
        contract = web3.eth.contract(
            address=Web3.to_checksum_address(deployment.anchor.address),
            abi=contract_abi(self.identity.root, "EvaluationAnchor"),
        )
        previous, sequence = contract.functions.head(
            Web3.to_checksum_address(deployment.evaluator),
            agent_key_hash(inputs.slot.expected.agent_ref),
        ).call(block_identifier=head["number"])
        publication = PublicationContext(
            chain=deployment.chain,
            contract=deployment.anchor.address,
            publisher=deployment.evaluator,
            confirmation_depth=deployment.confirmation_depth,
            previous_report_hash="0x" + bytes(previous).hex(),
            head_sequence=sequence,
            head_block_number=str(head["number"]),
            head_block_hash=head["hash"].to_0x_hex(),
            platform_instance_id=deployment.platform_instance_id,
        )
        now = timestamp()
        freeze_record = self.identity.evidence.prepare_json(
            fresh.model_dump(mode="json"),
            "report-freeze-verification-input",
            now,
            "platform-and-local-rpc",
        )
        with self.db.begin() as connection:
            freeze_record = self.identity.evidence.register(connection, freeze_record)
        policy = strict_json((self.identity.root / "configs/policies/policy-v1.json").read_bytes())
        refs = {
            evidence_id,
            freeze_record.evidence_id,
            *plan.planning_evidence_refs,
            *inputs.snapshot.evidence_refs,
            *inputs.review.mapping_evidence_ids,
            *[ref for item in observed for ref in item.evidence_refs],
        }
        if inputs.binding:
            refs.update(inputs.binding.verification_evidence)
        with self.db.connect() as connection:
            evidence = [
                EvidenceRecord.model_validate(body)
                for body in connection.execute(
                    select(evidence_blobs.c.body).where(evidence_blobs.c.id.in_(refs))
                ).scalars()
            ]
        if {item.evidence_id for item in evidence} != refs:
            raise ApplicationError(409, "MISSING_EVIDENCE", "Report evidence is incomplete.")
        for item in evidence:
            self.read_evidence(item)
        documents = {
            "policy.json": policy,
            "snapshot_core.json": inputs.snapshot.core.model_dump(mode="json"),
            "run_plan.json": plan.model_dump(mode="json"),
            "claims_review.json": inputs.review.model_dump(mode="json"),
            "bindings.json": [inputs.binding.model_dump(mode="json")] if inputs.binding else [],
            "access_grants.json": [inputs.grant.model_dump(mode="json")] if inputs.grant else [],
            "observations.json": [item.model_dump(mode="json") for item in observed],
            "assertions.json": [
                item.model_dump(mode="json")
                for item in sorted(result.assertions, key=lambda item: str(item.assertion_id))
            ],
            "verification.json": {
                "input_evidence_id": str(evidence_id),
                "freeze_evidence_id": str(freeze_record.evidence_id),
            },
        }
        for path in sorted(
            (self.identity.root / "packages/schemas/generated").glob("*.schema.json")
        ):
            documents[f"schemas/{path.name}"] = strict_json(path.read_bytes())
        prepared = {
            path: self.identity.evidence.prepare_json(
                value, f"report-document:{path}", now, "frozen-report"
            )
            for path, value in documents.items()
        }
        code_version = os.environ.get("CODE_VERSION")
        if code_version is None:
            code_version = subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=self.identity.root, text=True
            ).strip()
            if subprocess.check_output(["git", "status", "--porcelain"], cwd=self.identity.root):
                code_version += "-dirty"
        if not re.fullmatch(r"[0-9a-f]{40}(?:-dirty)?", code_version):
            raise ApplicationError(
                503, "CODE_VERSION_REQUIRED", "A concrete source commit is required."
            )
        return (
            plan,
            inputs,
            evidence_id,
            observed,
            policy,
            publication,
            now,
            code_version,
            evidence,
            prepared,
        )

    async def freeze(self, lease: Lease, queue: JobQueue) -> None:
        if lease.run_id is None:
            raise ApplicationError(422, "RUN_REQUIRED", "Report requires a frozen run.")
        with self.db.connect() as connection:
            if connection.execute(
                select(reports.c.id).where(reports.c.run_fk == lease.run_id)
            ).first():
                return
        (
            plan,
            inputs,
            evidence_id,
            observed,
            policy,
            publication,
            now,
            version,
            evidence,
            prepared,
        ) = await asyncio.to_thread(self.prepare, lease.run_id)
        key = agent_key_hash(inputs.slot.expected.agent_ref)
        lock = int(
            hash_json(
                [key, publication.chain.instance_hash, publication.publisher, publication.contract]
            )[2:18],
            16,
        )
        if lock >= 2**63:
            lock -= 2**64

        def save(connection):
            connection.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": lock})
            if connection.execute(
                select(reports.c.id).where(reports.c.run_fk == plan.run_id)
            ).first():
                return
            previous = connection.execute(
                select(reports.c.report_hash)
                .where(
                    reports.c.core["agent_key_hash"].astext == key,
                    reports.c.manifest["publication"]["chain"]["instance_hash"].astext
                    == publication.chain.instance_hash,
                    reports.c.manifest["publication"]["publisher"].astext == publication.publisher,
                    reports.c.manifest["publication"]["contract"].astext == publication.contract,
                )
                .order_by(reports.c.created_at.desc())
                .limit(1)
            ).scalar_one_or_none()
            if previous is not None and previous != publication.previous_report_hash:
                raise ApplicationError(
                    409,
                    "PREVIOUS_REPORT_UNPUBLISHED",
                    "Publish the previous frozen report before freezing another for this agent.",
                )
            records = {item.evidence_id: item for item in evidence}
            aliases = []
            for path, item in sorted(prepared.items()):
                registered = self.identity.evidence.register(connection, item)
                records[registered.evidence_id] = registered
                aliases.append(ManifestDocument(path=path, evidence_id=registered.evidence_id))
            manifest = EvidenceManifest(
                publication=publication,
                documents=tuple(aliases),
                evidence=tuple(sorted(records.values(), key=lambda item: str(item.evidence_id))),
            )
            core = build_report(
                plan,
                inputs,
                evidence_id,
                observed,
                policy,
                evaluated_at=now,
                code_version=version,
                manifest_hash=hash_json(manifest.model_dump(mode="json")),
                previous_report_hash=publication.previous_report_hash,
            )
            report_id = uuid4()
            connection.execute(
                insert(reports).values(
                    id=report_id,
                    run_fk=plan.run_id,
                    revision=1,
                    report_hash=hash_json(core.model_dump(mode="json")),
                    previous_report_hash=core.previous_report_hash,
                    core=core.model_dump(mode="json"),
                    manifest=manifest.model_dump(mode="json"),
                )
            )
            connection.execute(
                insert(evidence_manifest_items),
                [
                    {
                        "report_fk": report_id,
                        "evidence_fk": item.evidence_id,
                        "body": item.model_dump(mode="json"),
                    }
                    for item in manifest.evidence
                ],
            )
            connection.execute(update(runs).where(runs.c.id == plan.run_id).values(stage="DONE"))
            self.identity.audit(
                connection,
                "local-worker",
                "report.freeze",
                report_id,
                {
                    "run_id": str(plan.run_id),
                    "report_hash": hash_json(core.model_dump(mode="json")),
                },
            )

        await asyncio.to_thread(queue.fenced, lease, save)

    def export(self, report_id: UUID) -> bytes:
        report = self.view(report_id)
        files = {
            "report_core.json": canonical_bytes(report.core.model_dump(mode="json")),
            "evidence_manifest.json": canonical_bytes(report.manifest.model_dump(mode="json")),
            "FORMAT.md": FORMAT,
        }
        by_id = {}
        for record in report.manifest.evidence:
            data = self.read_evidence(record)
            files[record.path], by_id[record.evidence_id] = data, data
        for document in report.manifest.documents:
            files[document.path] = by_id[document.evidence_id]
        context = report.manifest.publication
        with self.db.connect() as connection:
            body = connection.execute(
                select(anchor_receipts.c.body)
                .join(anchor_jobs, anchor_receipts.c.anchor_job_fk == anchor_jobs.c.id)
                .where(anchor_jobs.c.report_fk == report_id)
                .order_by(anchor_receipts.c.created_at.desc())
                .limit(1)
            ).scalar_one_or_none()
        receipt = (
            AnchorReceipt.model_validate(body)
            if body
            else AnchorReceipt(
                report_hash=report.report_hash,
                status=AnchorStatus.NOT_REQUESTED,
                trusted_chain_key="local-demo",
                chain_instance_id=context.chain.instance_hash,
                contract=context.contract,
                publisher=context.publisher,
                tx_hash=None,
                sequence=None,
                block_number=None,
                block_hash=None,
                confirmations=0,
            )
        )
        files["anchor_receipt.json"] = canonical_bytes(receipt.model_dump(mode="json"))
        if sum(len(value) for value in files.values()) > 64 * 1024 * 1024:
            raise ApplicationError(
                413, "BUNDLE_TOO_LARGE", "Evidence bundle exceeds the export limit."
            )
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for path, data in sorted(files.items()):
                info = zipfile.ZipInfo(path, date_time=(1980, 1, 1, 0, 0, 0))
                info.compress_type, info.create_system, info.external_attr = (
                    zipfile.ZIP_DEFLATED,
                    3,
                    0o100644 << 16,
                )
                archive.writestr(info, data)
        return output.getvalue()
