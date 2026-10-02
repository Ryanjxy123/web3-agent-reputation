"""Collect immutable verification inputs, invoke pure rules, append fenced results."""

import asyncio
from uuid import UUID

from reputation_core.models import (
    AccessGrant,
    AgentSnapshot,
    ClaimReview,
    EvidenceRecord,
    ExecutorBinding,
    Observation,
    RecordVerificationInput,
    RecordVerificationResult,
    RegistryWitness,
    RunPlan,
)
from reputation_core.record_verifier import verify_record
from sqlalchemy import Engine, insert, select, update

from reputation_platform.adapters.evm.collector import collect_task
from reputation_platform.infrastructure.db.jobs import JobQueue, Lease
from reputation_platform.infrastructure.db.tables import (
    access_grants,
    assertions,
    attempts,
    bindings,
    case_slots,
    claim_reviews,
    dispatch_events,
    evidence_blobs,
    observations,
    runs,
    snapshots,
    task_links,
)

from .errors import ApplicationError
from .evaluations import utc_text
from .identity import IdentityService


class VerificationService:
    def __init__(self, db: Engine, identity: IdentityService | None = None):
        self.db, self.identity = db, identity or IdentityService(db)

    def inputs(self, run_id: UUID) -> RecordVerificationInput:
        with self.db.connect() as connection:
            row = connection.execute(select(runs).where(runs.c.id == run_id)).mappings().one()
            plan = RunPlan.model_validate(row["plan"])
            slot = plan.slots[0]
            snapshot = AgentSnapshot.model_validate(
                connection.execute(
                    select(snapshots.c.body).where(snapshots.c.id == row["snapshot_fk"])
                ).scalar_one()
            )
            review = ClaimReview.model_validate(
                connection.execute(
                    select(claim_reviews.c.body).where(
                        claim_reviews.c.snapshot_fk == row["snapshot_fk"],
                        claim_reviews.c.review_version == plan.review_version,
                    )
                ).scalar_one()
            )
            binding = ExecutorBinding.model_validate(
                connection.execute(
                    select(bindings.c.body).where(bindings.c.id == slot.expected.binding_id)
                ).scalar_one()
            )
            grant = AccessGrant.model_validate(
                connection.execute(
                    select(access_grants.c.body).where(access_grants.c.id == slot.grant_id)
                ).scalar_one()
            )
            intent_at = connection.execute(
                select(case_slots.c.created_at).where(case_slots.c.id == slot.slot_id)
            ).scalar_one()
            dispatch = connection.execute(
                select(attempts.c.body)
                .where(
                    attempts.c.slot_fk == slot.slot_id, attempts.c.body["method"].astext == "POST"
                )
                .order_by(attempts.c.attempt_no)
                .limit(1)
            ).scalar_one_or_none()
            last = Observation.model_validate(
                connection.execute(
                    select(observations.c.body)
                    .where(
                        observations.c.slot_fk == slot.slot_id,
                        observations.c.body["dispatch_state"].astext == "SETTLED",
                    )
                    .order_by(observations.c.created_at.desc())
                    .limit(1)
                ).scalar_one()
            )
            event = connection.execute(
                select(dispatch_events.c.body)
                .where(
                    dispatch_events.c.slot_fk == slot.slot_id, dispatch_events.c.state == "SENDING"
                )
                .order_by(dispatch_events.c.created_at)
                .limit(1)
            ).scalar_one_or_none()
            witness_record = None
            if event and event.get("pre_dispatch_evidence"):
                body = connection.execute(
                    select(evidence_blobs.c.body).where(
                        evidence_blobs.c.id == UUID(event["pre_dispatch_evidence"])
                    )
                ).scalar_one_or_none()
                witness_record = EvidenceRecord.model_validate(body) if body else None
        witness = None
        if witness_record is not None:
            try:
                witness = RegistryWitness.model_validate_json(
                    self.identity.evidence.read(witness_record)
                )
            except (OSError, ValueError):
                pass  # Missing/corrupt witness is an explicit UNKNOWN attribution gap.
        deployment = self.identity.deployment()
        evm = collect_task(
            deployment,
            slot,
            last.candidate_tx_hash,
            witness.snapshot_core.read_block_number if witness else None,
        )
        return RecordVerificationInput(
            slot=slot,
            snapshot=snapshot,
            review=review,
            review_version=plan.review_version,
            platform_instance_id=deployment.platform_instance_id,
            binding=binding,
            grant=grant,
            intent_persisted_at=utc_text(intent_at),
            dispatch_started_at=dispatch["started_at"] if dispatch else None,
            dispatch_payload_hash=dispatch["payload_hash"] if dispatch else None,
            registry_witness=witness,
            execution_reason=last.reason_code,
            evm=evm,
        )

    async def verify(self, lease: Lease, queue: JobQueue) -> None:
        if lease.run_id is None:
            raise ApplicationError(422, "RUN_REQUIRED", "Verification requires a frozen run.")
        run_id = lease.run_id
        with self.db.connect() as connection:
            exists = connection.execute(
                select(task_links.c.id)
                .join(case_slots, task_links.c.slot_fk == case_slots.c.id)
                .where(case_slots.c.run_fk == lease.run_id)
            ).first()
        if exists:
            return
        inputs = await asyncio.to_thread(self.inputs, lease.run_id)
        prepared = await asyncio.to_thread(
            self.identity.evidence.prepare_json,
            inputs.model_dump(mode="json"),
            "record-verification-input",
            inputs.evm.observed_at,
            "platform-and-local-rpc",
        )

        def save(connection):
            record = self.identity.evidence.register(connection, prepared)
            result = verify_record(inputs, (record.evidence_id,))
            for assertion in result.assertions:
                connection.execute(
                    insert(assertions).values(
                        id=assertion.assertion_id,
                        slot_fk=inputs.slot.slot_id,
                        body=assertion.model_dump(mode="json"),
                    )
                )
            connection.execute(
                insert(task_links).values(
                    slot_fk=inputs.slot.slot_id,
                    chain_instance_id=inputs.slot.task.chain_instance_id,
                    executor=inputs.slot.expected.executor,
                    request_id=inputs.slot.task.request_id,
                    body=result.model_dump(mode="json"),
                )
            )
            connection.execute(
                update(runs).where(runs.c.id == lease.run_id).values(stage="SCORING")
            )
            self.identity.audit(
                connection,
                "local-worker",
                "evaluation.verify",
                run_id,
                {
                    "outcome": result.outcome,
                    "reason_code": result.reason_code,
                    "evidence_id": str(record.evidence_id),
                },
            )

        await asyncio.to_thread(queue.fenced, lease, save)

    def result(self, run_id: UUID) -> RecordVerificationResult:
        with self.db.connect() as connection:
            body = connection.execute(
                select(task_links.c.body)
                .join(case_slots, task_links.c.slot_fk == case_slots.c.id)
                .where(case_slots.c.run_fk == run_id)
            ).scalar_one_or_none()
        if body is None:
            raise ApplicationError(
                404, "NOT_VERIFIED", "Independent verification is not available yet."
            )
        return RecordVerificationResult.model_validate(body)
