"""Freeze immutable reports; export only hash-checked committed evidence."""

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
from reputation_core.models.public_evaluation import (
    PublicReadonlyRunPlan,
    PublicReadonlyVerificationInput,
)
from reputation_core.record_verifier import preserve_rpc_unknown, verify_record
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
    def __init__(self, db: Engine, identity: IdentityService | None = None, *, client_factory=None):
        self.db, self.identity = db, identity or IdentityService(db)
        self.client_factory = client_factory

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
        VerificationService(self.db, self.identity).results(run_id)
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

    def prepare(self, run_id: UUID, lease: Lease | None = None, queue: JobQueue | None = None):
        results = VerificationService(self.db, self.identity).results(run_id)
        evidence_ids = tuple(result.assertions[0].evidence_refs[0] for result in results)
        with self.db.connect() as connection:
            plan_body = connection.execute(
                select(runs.c.plan).where(runs.c.id == run_id)
            ).scalar_one()
            records = {
                item.evidence_id: item
                for item in (
                    EvidenceRecord.model_validate(body)
                    for body in connection.execute(
                        select(evidence_blobs.c.body).where(evidence_blobs.c.id.in_(evidence_ids))
                    ).scalars()
                )
            }
            observed = tuple(
                Observation.model_validate(body)
                for body in connection.execute(
                    select(observations.c.body)
                    .join(case_slots, observations.c.slot_fk == case_slots.c.id)
                    .where(case_slots.c.run_fk == run_id)
                    .order_by(observations.c.id)
                ).scalars()
            )
        if plan_body.get("suite_id") == "public-readonly-v1":
            from .public_reports import refresh_public_inputs

            public_plan = PublicReadonlyRunPlan.model_validate(plan_body)
            public_inputs = tuple(
                PublicReadonlyVerificationInput.model_validate_json(
                    self.read_evidence(records[evidence_id])
                )
                for evidence_id in evidence_ids
            )
            observed_by_slot = {item.slot_id: item for item in observed}
            if len(observed_by_slot) != len(observed) or set(observed_by_slot) != {
                slot.slot_id for slot in public_plan.slots
            }:
                raise ApplicationError(409, "EVIDENCE_INCONSISTENT", "Public observations are incomplete.")
            public_observed = tuple(observed_by_slot[slot.slot_id] for slot in public_plan.slots)
            fresh_public = asyncio.run(
                refresh_public_inputs(self, public_inputs, results, evidence_ids, lease, queue)
            )
            return self._prepare_documents(
                public_plan, public_inputs, results, evidence_ids, public_observed,
                self.identity.deployment(), fresh_public,
            )
        plan = RunPlan.model_validate(plan_body)
        all_inputs = tuple(
            RecordVerificationInput.model_validate_json(self.read_evidence(records[evidence_id]))
            for evidence_id in evidence_ids
        )
        deployment = self.identity.deployment()
        refreshed = []
        for inputs, result, evidence_id in zip(all_inputs, results, evidence_ids, strict=True):
            if verify_record(inputs, (evidence_id,)) != result:
                raise ApplicationError(
                    409,
                    "ASSERTION_REPLAY_MISMATCH",
                    "Stored assertions differ from evidence replay.",
                )
            historical_rpc_unknown = preserve_rpc_unknown(inputs, result)
            fresh = (
                inputs
                if inputs.slot.applicability_reason is not None
                else inputs.model_copy(
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
            )
            if plan.template_version in {"capabilities@3", "capabilities@4", "capabilities@5", "capabilities@6"} and inputs.slot.case_kind == "negative":
                fresh = fresh.model_copy(
                    update={"evm": fresh.evm.model_copy(update={"candidate_tx_hash": None})}
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
            if not historical_rpc_unknown and (
                [(item.rule_id, item.outcome, item.reason_code) for item in rechecked.assertions]
                != [(item.rule_id, item.outcome, item.reason_code) for item in result.assertions]
                or rechecked.task_link != result.task_link
            ):
                raise ApplicationError(
                    409,
                    "STALE_EVIDENCE",
                    "Chain evidence changed before report freeze; run a new evaluation.",
                )
            refreshed.append(fresh)
        return self._prepare_documents(
            plan, all_inputs, results, evidence_ids, observed, deployment, tuple(refreshed)
        )

    def _prepare_documents(
        self, plan, all_inputs, results, evidence_ids, observed, deployment, refreshed,
    ):
        public = isinstance(plan, PublicReadonlyRunPlan)
        inputs = all_inputs[0]
        if public and deployment.chain.chain_id != "31337":
            raise ApplicationError(409, "CHAIN_INSTANCE_MISMATCH", "Publication requires local Anvil.")
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
        frozen = tuple(
            self.identity.evidence.prepare_json(
                fresh.model_dump(mode="json"),
                "report-freeze-public-readonly-input" if public
                else "report-freeze-verification-input",
                now,
                "platform-and-public-rpc" if public else "platform-and-local-rpc",
            )
            for fresh in refreshed
        )
        with self.db.begin() as connection:
            frozen = tuple(self.identity.evidence.register(connection, item) for item in frozen)
        policy = strict_json((self.identity.root / "configs/policies/policy-v1.json").read_bytes())
        refs = {
            *evidence_ids,
            *(item.evidence_id for item in frozen),
            *plan.planning_evidence_refs,
            *inputs.snapshot.evidence_refs,
            *inputs.review.mapping_evidence_ids,
            *[ref for item in observed for ref in item.evidence_refs],
        }
        for verification_input in all_inputs:
            if public:
                refs.update(packet.record.evidence_id for packet in verification_input.packets)
            elif verification_input.binding:
                refs.update(verification_input.binding.verification_evidence)
        if public:
            for verification_input in refreshed:
                refs.update(packet.record.evidence_id for packet in verification_input.packets)
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
        if public:
            from .public_reports import check_public_packets

            by_id = {item.evidence_id: item for item in evidence}
            for verification_input in (*all_inputs, *refreshed):
                check_public_packets(verification_input, by_id, self.read_evidence)
        task_index = []
        for inputs, evidence_id, freeze_record in zip(
            all_inputs, evidence_ids, frozen, strict=True
        ):
            entry = {
                "slot_id": str(inputs.slot.slot_id),
                "input_evidence_id": str(evidence_id),
                "freeze_evidence_id": str(freeze_record.evidence_id),
            }
            if public:
                task_index.append(entry)
                continue
            for field, envelope in (
                ("agent_http_evidence_id", inputs.agent_http),
                (
                    "initial_http_evidence_id",
                    inputs.initial_agent_http if inputs.rule_version in {"3", "4", "5", "6"} else None,
                ),
            ):
                if envelope is None or inputs.rule_version == "1":
                    continue
                match = None
                for item in evidence:
                    if item.source != "agent-task-response":
                        continue
                    try:
                        if strict_json(self.read_evidence(item)) == envelope:
                            match = item
                            break
                    except (UnicodeError, ValueError):
                        continue
                if match is None:
                    raise ApplicationError(
                        409,
                        "MISSING_EVIDENCE",
                        "Frozen Agent HTTP envelope has no matching raw response evidence.",
                    )
                entry[field] = str(match.evidence_id)
            task_index.append(entry)
        verification_index = (
            {
                "schema_version": "public-readonly-replay-v1" if public else "task-replay-v1",
                "tasks": task_index,
            }
            if public or all_inputs[0].rule_version in {"2", "3", "4", "5", "6"}
            else {
                "input_evidence_id": str(evidence_ids[0]),
                "freeze_evidence_id": str(frozen[0].evidence_id),
            }
        )
        inputs = all_inputs[0]
        documents = {
            "policy.json": policy,
            "snapshot_core.json": inputs.snapshot.core.model_dump(mode="json"),
            "run_plan.json": plan.model_dump(mode="json"),
            "claims_review.json": inputs.review.model_dump(mode="json"),
            "bindings.json": list(
                {
                    str(item.binding.binding_id): item.binding.model_dump(mode="json")
                    for item in all_inputs
                    if not public and item.binding
                }.values()
            ),
            "access_grants.json": list(
                {
                    str(item.grant.grant_id): item.grant.model_dump(mode="json")
                    for item in all_inputs
                    if item.grant
                }.values()
            ),
            "observations.json": [item.model_dump(mode="json") for item in observed],
            "assertions.json": [
                item.model_dump(mode="json")
                for item in sorted(
                    (assertion for result in results for assertion in result.assertions),
                    key=lambda item: str(item.assertion_id),
                )
            ],
            "verification.json": verification_index,
        }
        if public:
            documents["public_snapshot.json"] = inputs.snapshot.model_dump(mode="json")
            documents["readonly_associations.json"] = list({
                item.association.protocol: item.association.model_dump(mode="json")
                for item in all_inputs
            }.values())
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
            all_inputs if public or plan.suite_id == "formal-evaluation-v1" else all_inputs[0],
            evidence_ids if public or plan.suite_id == "formal-evaluation-v1" else evidence_ids[0],
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
        def already_reported():
            with self.db.connect() as connection:
                return connection.execute(
                    select(reports.c.id).where(reports.c.run_fk == lease.run_id)
                ).first() is not None
        if await asyncio.to_thread(already_reported):
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
        ) = await asyncio.to_thread(self.prepare, lease.run_id, lease, queue)
        key = agent_key_hash(
            (inputs[0] if isinstance(inputs, tuple) else inputs).slot.expected.agent_ref
        )
        lock = int(
            hash_json(
                [key, publication.chain.instance_hash, publication.publisher, publication.contract]
            )[2:18],
            16,
        )
        if lock >= 2**63:
            lock -= 2**64

        def assemble():
            records = {item.evidence_id: item for item in evidence}
            aliases = []
            for path, item in sorted(prepared.items()):
                with self.db.begin() as connection:
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
                report_schema_version="1.2.0" if plan.template_version == "capabilities@3"
                else "1.3.0" if plan.template_version == "capabilities@4" else None,
            )
            body = core.model_dump(mode="json")
            return manifest, body, hash_json(body)

        manifest, core_body, report_hash = await asyncio.to_thread(assemble)
        manifest_body = manifest.model_dump(mode="json")
        manifest_items = [
            {"evidence_fk": item.evidence_id, "body": item.model_dump(mode="json")}
            for item in manifest.evidence
        ]

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
            report_id = uuid4()
            connection.execute(
                insert(reports).values(
                    id=report_id,
                    run_fk=plan.run_id,
                    revision=1,
                    report_hash=report_hash,
                    previous_report_hash=publication.previous_report_hash,
                    core=core_body,
                    manifest=manifest_body,
                )
            )
            connection.execute(
                insert(evidence_manifest_items),
                [{"report_fk": report_id, **item} for item in manifest_items],
            )
            connection.execute(
                update(runs).where(runs.c.id == plan.run_id).values(
                    stage="DONE",
                    **({"status": "COMPLETED"} if plan.template_version in {"capabilities@5", "capabilities@6"}
                       and core_body["scores"]["evaluation_state"] == "COMPLETE" else {}),
                )
            )
            self.identity.audit(
                connection,
                "local-worker",
                "report.freeze",
                report_id,
                {
                    "run_id": str(plan.run_id),
                    "report_hash": report_hash,
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
