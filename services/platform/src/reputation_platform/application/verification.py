"""Collect immutable verification inputs, invoke pure rules, append fenced results."""

import asyncio
from datetime import UTC, datetime
from typing import Literal, cast
from uuid import UUID

from reputation_core.evidence import strict_json
from reputation_core.models import (
    AccessGrant,
    AgentSnapshot,
    ClaimReview,
    ControlledTaskView,
    EvidenceRecord,
    EvmReadEvidence,
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
from reputation_platform.infrastructure.db.jobs import JobQueue, Lease, enqueue
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

    def inputs(self, run_id: UUID, slot_id: UUID | None = None) -> RecordVerificationInput:
        with self.db.connect() as connection:
            row = connection.execute(select(runs).where(runs.c.id == run_id)).mappings().one()
            plan = RunPlan.model_validate(row["plan"])
            if slot_id is None and len(plan.slots) != 1:
                raise ApplicationError(
                    409, "MULTIPLE_TASK_INPUTS", "Select a slot for this multi-task run."
                )
            slot = next(
                (item for item in plan.slots if slot_id is None or item.slot_id == slot_id), None
            )
            if slot is None:
                raise ApplicationError(404, "NOT_FOUND", "Task slot does not exist in the run.")
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
            binding_body = (
                connection.execute(
                    select(bindings.c.body).where(bindings.c.id == slot.expected.binding_id)
                ).scalar_one_or_none()
                if slot.expected.binding_id
                else None
            )
            binding = ExecutorBinding.model_validate(binding_body) if binding_body else None
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
            response_records = [
                EvidenceRecord.model_validate(body)
                for body in connection.execute(
                    select(evidence_blobs.c.body).where(evidence_blobs.c.id.in_(last.evidence_refs))
                ).scalars()
                if body["source"] == "agent-task-response"
            ]
            initial_body = connection.execute(
                select(observations.c.body)
                .where(
                    observations.c.slot_fk == slot.slot_id,
                    observations.c.body["attempt_no"].astext == "1",
                    observations.c.body["dispatch_state"].astext != "SETTLED",
                )
                .order_by(observations.c.created_at)
                .limit(1)
            ).scalar_one_or_none()
        witness = None
        if witness_record is not None:
            try:
                witness = RegistryWitness.model_validate_json(
                    self.identity.evidence.read(witness_record)
                )
            except (OSError, ValueError):
                pass  # Missing/corrupt witness is an explicit UNKNOWN attribution gap.
        deployment = self.identity.deployment()
        agent_view = None
        agent_response = None
        agent_http = None
        initial_agent_http = None
        for record in sorted(
            response_records, key=lambda item: (item.observed_at, str(item.evidence_id))
        ):
            try:
                raw = strict_json(self.identity.evidence.read(record))
                response_body = raw["response"]
                endpoint = next(
                    item
                    for item in snapshot.core.endpoints
                    if item.endpoint_id == grant.endpoint_ids[0]
                )
                if (
                    raw["request_id"] == slot.task.request_id
                    and raw["origin"] == endpoint.origin
                    and raw["path"]
                    == ("/tasks" if raw["method"] == "POST" else "/tasks/" + slot.task.request_id)
                    and raw["method"] in {"POST", "GET"}
                ):
                    if (
                        initial_body
                        and str(record.evidence_id) in initial_body["evidence_refs"]
                        and raw["method"] == "POST"
                    ):
                        initial_agent_http = raw
                    agent_http = raw
                    agent_response = response_body
                    agent_view = None
                    if raw["http_status"] is not None and 200 <= raw["http_status"] < 300:
                        try:
                            candidate_view = ControlledTaskView.model_validate(response_body)
                            if (
                                candidate_view.request_id == slot.task.request_id
                                and candidate_view.status_path == "/tasks/" + slot.task.request_id
                            ):
                                agent_view = candidate_view
                        except (ValueError, TypeError):
                            pass
            except (OSError, ValueError, KeyError, TypeError):
                pass
        evm = (
            EvmReadEvidence(
                candidate_tx_hash=None,
                observed_at=utc_text(datetime.now(UTC)),
                results={},
            )
            if slot.applicability_reason is not None
            else collect_task(
                deployment,
                slot,
                last.candidate_tx_hash,
                witness.snapshot_core.read_block_number if witness else None,
            )
        )
        if plan.template_version in {"capabilities@3", "capabilities@4", "capabilities@5"} and slot.case_kind == "negative":
            evm = evm.model_copy(update={"candidate_tx_hash": None})
        return RecordVerificationInput(
            rule_version=cast(Literal["1", "2", "3", "4", "5"], plan.template_version.rsplit("@", 1)[1]),
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
            agent_http=agent_http,
            initial_agent_http=initial_agent_http
            if plan.template_version in {"capabilities@3", "capabilities@4", "capabilities@5"}
            else None,
            agent_response=agent_response,
            agent_result=agent_view.result if agent_view else None,
            agent_task_status=agent_view.task_status if agent_view else None,
            evm=evm,
        )

    async def verify(self, lease: Lease, queue: JobQueue) -> None:
        if lease.run_id is None:
            raise ApplicationError(422, "RUN_REQUIRED", "Verification requires a frozen run.")
        run_id = lease.run_id
        def context():
            with self.db.connect() as connection:
                plan = RunPlan.model_validate(
                    connection.execute(select(runs.c.plan).where(runs.c.id == run_id)).scalar_one()
                )
                settled = set(
                    connection.execute(
                        select(observations.c.slot_fk)
                        .join(case_slots, observations.c.slot_fk == case_slots.c.id)
                        .where(
                            case_slots.c.run_fk == run_id,
                            observations.c.body["dispatch_state"].astext == "SETTLED",
                        )
                    ).scalars()
                )
                return plan, settled
        plan, settled = await asyncio.to_thread(context)
        if settled != {slot.slot_id for slot in plan.slots}:
            raise ApplicationError(
                409, "NOT_SETTLED", "Every planned task must settle before verification.", True
            )
        for slot in plan.slots:
            await self.verify_slot(lease, queue, slot.slot_id, len(plan.slots))

    async def verify_slot(self, lease: Lease, queue: JobQueue, slot_id: UUID, planned: int) -> None:
        run_id = lease.run_id
        assert run_id is not None
        def already_verified():
            with self.db.connect() as connection:
                return connection.execute(
                    select(task_links.c.id).where(task_links.c.slot_fk == slot_id)
                ).first() is not None
        if await asyncio.to_thread(already_verified):
            return
        inputs = await asyncio.to_thread(self.inputs, run_id, slot_id)
        prepared = await asyncio.to_thread(
            self.identity.evidence.prepare_json,
            inputs.model_dump(mode="json"),
            "record-verification-input",
            inputs.evm.observed_at,
            "platform-and-local-rpc",
        )

        def save(connection):
            connection.execute(select(runs.c.id).where(runs.c.id == run_id).with_for_update()).one()
            if connection.execute(
                select(task_links.c.id).where(task_links.c.slot_fk == slot_id)
            ).first():
                return
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
            verified = (
                connection.execute(
                    select(task_links.c.slot_fk)
                    .join(case_slots, task_links.c.slot_fk == case_slots.c.id)
                    .where(case_slots.c.run_fk == run_id)
                )
                .scalars()
                .all()
            )
            if len(set(verified)) == planned:
                connection.execute(update(runs).where(runs.c.id == run_id).values(stage="SCORING"))
                enqueue(connection, "report", f"report:{run_id}", {"run_id": str(run_id)}, run_id)
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

    def results(self, run_id: UUID) -> tuple[RecordVerificationResult, ...]:
        with self.db.connect() as connection:
            plan_body = connection.execute(
                select(runs.c.plan).where(runs.c.id == run_id)
            ).scalar_one_or_none()
            rows = connection.execute(
                select(task_links.c.slot_fk, task_links.c.body)
                .join(case_slots, task_links.c.slot_fk == case_slots.c.id)
                .where(case_slots.c.run_fk == run_id)
            ).all()
        if plan_body is None or len(rows) != len(plan_body["slots"]):
            raise ApplicationError(
                404, "NOT_VERIFIED", "Independent verification is not available yet."
            )
        by_slot = {slot_id: RecordVerificationResult.model_validate(body) for slot_id, body in rows}
        return tuple(by_slot[UUID(slot["slot_id"])] for slot in plan_body["slots"])

    def result(self, run_id: UUID) -> RecordVerificationResult:
        results = self.results(run_id)
        if len(results) != 1:
            raise ApplicationError(
                409, "MULTIPLE_TASK_RESULTS", "This run contains multiple task results."
            )
        return results[0]
