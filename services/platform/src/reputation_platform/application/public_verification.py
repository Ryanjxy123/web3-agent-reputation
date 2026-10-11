"""Packet-complete public inputs and independently audited fixed Base reads."""

import asyncio
from uuid import UUID

from reputation_core.evidence import strict_json
from reputation_core.models import AgentSnapshot, ClaimReview, EvidenceRecord, Observation
from reputation_core.models.public_evaluation import (
    EvidencePacket,
    PublicReadonlyGrant,
    PublicReadonlyRunPlan,
    PublicReadonlyVerificationInput,
)
from reputation_core.public_identity import associate_readonly_identity
from sqlalchemy import insert, select, update

from reputation_platform.adapters.akashi import ORIGIN
from reputation_platform.adapters.akashi_evidence import PROTOCOL, collect_public_task
from reputation_platform.adapters.registries.demo import timestamp
from reputation_platform.infrastructure.db.jobs import enqueue
from reputation_platform.infrastructure.db.tables import (
    access_grants,
    assertions,
    attempts,
    case_slots,
    claim_reviews,
    dispatch_events,
    evidence_blobs,
    observations,
    runs,
    snapshots,
    task_links,
)
from reputation_platform.infrastructure.network.safe_http import NetworkPolicyError, SafeHttpClient

from .errors import ApplicationError
from .evaluations import utc_text
from .public_execution import PublicReadonlyEgress, failure_reason


class PublicReadonlyVerificationService:
    def __init__(self, db, identity, *, client_factory=None):
        self.db, self.identity, self.client_factory = db, identity, client_factory

    def packet(self, record):
        return EvidencePacket(record=record, body=strict_json(self.identity.evidence.read(record)))

    def inputs(self, run_id: UUID, slot_id: UUID | None = None):
        with self.db.connect() as connection:
            row = connection.execute(select(runs).where(runs.c.id == run_id)).mappings().one()
            plan = PublicReadonlyRunPlan.model_validate(row["plan"])
            if slot_id is None and len(plan.slots) != 1:
                raise ApplicationError(409, "MULTIPLE_TASK_INPUTS", "Select a public query slot.")
            slot = next(
                (slot for slot in plan.slots if slot_id is None or slot.slot_id == slot_id), None
            )
            if slot is None:
                raise ApplicationError(404, "NOT_FOUND", "Public query slot does not exist.")
            snapshot = AgentSnapshot.model_validate(
                connection.scalar(
                    select(snapshots.c.body).where(snapshots.c.id == row["snapshot_fk"])
                )
            )
            review = ClaimReview.model_validate(
                connection.scalar(
                    select(claim_reviews.c.body).where(
                        claim_reviews.c.snapshot_fk == row["snapshot_fk"],
                        claim_reviews.c.review_version == plan.review_version,
                    )
                )
            )
            grant = PublicReadonlyGrant.model_validate(
                connection.scalar(
                    select(access_grants.c.body).where(access_grants.c.id == slot.grant_id)
                )
            )
            intent_at = connection.scalar(
                select(case_slots.c.created_at).where(case_slots.c.id == slot.slot_id)
            )
            dispatch = connection.scalar(
                select(attempts.c.body)
                .where(
                    attempts.c.slot_fk == slot.slot_id,
                    attempts.c.body["method"].astext.in_(["GET", "POST"]),
                )
                .order_by(attempts.c.attempt_no)
                .limit(1)
            )
            last = Observation.model_validate(
                connection.scalar(
                    select(observations.c.body)
                    .where(
                        observations.c.slot_fk == slot.slot_id,
                        observations.c.body["dispatch_state"].astext == "SETTLED",
                    )
                    .order_by(observations.c.created_at.desc())
                    .limit(1)
                )
            )
            event = connection.scalar(
                select(dispatch_events.c.body)
                .where(
                    dispatch_events.c.slot_fk == slot.slot_id, dispatch_events.c.state == "SETTLED"
                )
                .order_by(dispatch_events.c.created_at.desc(), dispatch_events.c.id.desc())
                .limit(1)
            )
            agent_refs = (*last.evidence_refs, UUID(event["observation_evidence_id"]))
            refs = tuple(dict.fromkeys((*snapshot.evidence_refs, *agent_refs)))
            by_id = {
                record.evidence_id: record
                for body in connection.scalars(
                    select(evidence_blobs.c.body).where(evidence_blobs.c.id.in_(refs))
                )
                if (record := EvidenceRecord.model_validate(body))
            }
        packets = tuple(self.packet(by_id[ref]) for ref in refs)
        metadata_raw = openapi_raw = None
        for packet in packets:
            value = packet.body
            if (
                isinstance(value, dict)
                and value.get("origin") == ORIGIN
                and isinstance(value.get("response"), dict)
            ):
                raw = value["response"].get("raw_body_utf8")
                if isinstance(raw, str):
                    if value.get("path") == "/openapi.json":
                        openapi_raw = raw.encode()
                    elif value.get("path") == "/.well-known/agent-registration.json":
                        metadata_raw = raw.encode()
        association = associate_readonly_identity(
            snapshot,
            ORIGIN + ("/proof" if slot.task.endpoint_id == "akashi-http" else "/mcp"),
            slot.task.protocol,
            openapi_raw=openapi_raw,
            metadata_raw=metadata_raw,
        )
        return PublicReadonlyVerificationInput(
            slot=slot,
            snapshot=snapshot,
            review=review,
            review_version=plan.review_version,
            platform_instance_id=self.identity.deployment().platform_instance_id,
            grant=grant,
            intent_persisted_at=utc_text(intent_at),
            dispatch_started_at=dispatch["started_at"] if dispatch else None,
            dispatch_payload_hash=dispatch["payload_hash"] if dispatch else None,
            execution_reason=last.reason_code,
            observed_at=timestamp(),
            association=association,
            packets=packets,
            identity_evidence_refs=snapshot.evidence_refs,
            agent_evidence_refs=agent_refs,
            business_evidence_refs=(),
        )

    async def fresh_input(self, data, *, lease=None, queue=None):
        if "tx" not in data.slot.task.query or data.execution_reason is not None:
            return data.model_copy(update={"observed_at": timestamp()})
        with self.db.connect() as connection:
            row = (
                connection.execute(
                    select(runs)
                    .join(case_slots, case_slots.c.run_fk == runs.c.id)
                    .where(case_slots.c.id == data.slot.slot_id)
                )
                .mappings()
                .one()
            )
        phase = "freeze" if lease is not None and lease.kind == "report" else "verify"
        guard = PublicReadonlyEgress(
            self.db, self.identity, row, data.slot, lease=lease, queue=queue, phase=phase
        )
        interval = data.grant.interval_ms if data.grant else 1000
        guard.interval_ms = interval
        client = (self.client_factory or SafeHttpClient.public_readonly)(
            enabled=True,
            before_request=guard,
            business_reads=True,
            interval_ms=interval,
        )
        records: list[EvidenceRecord] = []

        async def register_record(record):
            if lease is None or queue is None:
                with self.db.begin() as connection:
                    return self.identity.evidence.register(connection, record)
            return await asyncio.to_thread(
                queue.fenced,
                lease,
                lambda connection: self.identity.evidence.register(connection, record),
            )

        try:
            async with guard:
                await collect_public_task(
                    client,
                    self.identity.evidence,
                    data.slot,
                    records=records,
                    register_record=register_record,
                )
        except (ApplicationError, NetworkPolicyError) as exc:
            records.append(
                await asyncio.to_thread(
                    self.identity.evidence.prepare_json,
                    {
                        "protocol": PROTOCOL,
                        "capability_id": "verify_record",
                        "query": data.slot.task.query,
                        "read_block_number": data.slot.task.read_block_number,
                        "read_block_hash": data.slot.task.read_block_hash,
                        "reason_code": failure_reason(exc),
                    },
                    "public-business-collection-error",
                    timestamp(),
                    "public-http",
                )
            )
        finally:
            await client.close()

        def register(connection):
            return tuple(self.identity.evidence.register(connection, record) for record in records)

        saved = await asyncio.to_thread(guard.fenced, register)
        retained = tuple(
            packet
            for packet in data.packets
            if packet.record.evidence_id not in data.business_evidence_refs
        )
        return data.model_copy(
            update={
                "observed_at": timestamp(),
                "packets": (*retained, *(self.packet(record) for record in saved)),
                "business_evidence_refs": tuple(record.evidence_id for record in saved),
            }
        )

    async def verify(self, lease, queue):
        from reputation_core.public_verifier import verify_public_readonly

        run_id = lease.run_id
        assert run_id is not None
        with self.db.connect() as connection:
            plan = PublicReadonlyRunPlan.model_validate(
                connection.scalar(select(runs.c.plan).where(runs.c.id == run_id))
            )
            settled = set(
                connection.scalars(
                    select(observations.c.slot_fk)
                    .join(case_slots)
                    .where(
                        case_slots.c.run_fk == run_id,
                        observations.c.body["dispatch_state"].astext == "SETTLED",
                    )
                )
            )
        if settled != {slot.slot_id for slot in plan.slots}:
            raise ApplicationError(
                409, "NOT_SETTLED", "Every public query must settle before verification.", True
            )
        for slot in plan.slots:
            with self.db.connect() as connection:
                done = connection.execute(
                    select(task_links.c.id).where(task_links.c.slot_fk == slot.slot_id)
                ).first()
            if done:
                continue
            data = await asyncio.to_thread(self.inputs, run_id, slot.slot_id)
            data = await self.fresh_input(data, lease=lease, queue=queue)
            prepared = await asyncio.to_thread(
                self.identity.evidence.prepare_json,
                data.model_dump(mode="json"),
                "public-readonly-verification-input",
                data.observed_at,
                "platform-and-public-rpc",
            )
            result = verify_public_readonly(data, (prepared.evidence_id,))

            def save(connection):
                connection.execute(
                    select(runs.c.id).where(runs.c.id == run_id).with_for_update()
                ).one()
                if connection.execute(
                    select(task_links.c.id).where(task_links.c.slot_fk == slot.slot_id)
                ).first():
                    return
                record = self.identity.evidence.register(connection, prepared)
                committed = (
                    result
                    if record.evidence_id == prepared.evidence_id
                    else verify_public_readonly(data, (record.evidence_id,))
                )
                for assertion in committed.assertions:
                    connection.execute(
                        insert(assertions).values(
                            id=assertion.assertion_id,
                            slot_fk=slot.slot_id,
                            body=assertion.model_dump(mode="json"),
                        )
                    )
                connection.execute(
                    insert(task_links).values(
                        slot_fk=slot.slot_id,
                        chain_instance_id=slot.task.chain_instance_id,
                        executor=None,
                        request_id=slot.task.request_id,
                        body=committed.model_dump(mode="json"),
                    )
                )
                verified = set(
                    connection.scalars(
                        select(task_links.c.slot_fk)
                        .join(case_slots)
                        .where(case_slots.c.run_fk == run_id)
                    )
                )
                if verified == {item.slot_id for item in plan.slots}:
                    connection.execute(
                        update(runs).where(runs.c.id == run_id).values(stage="SCORING")
                    )
                    enqueue(
                        connection, "report", f"report:{run_id}", {"run_id": str(run_id)}, run_id
                    )
                self.identity.audit(
                    connection,
                    "local-worker",
                    "public.evaluation.verify",
                    run_id,
                    {
                        "outcome": committed.outcome,
                        "reason_code": committed.reason_code,
                        "evidence_id": str(record.evidence_id),
                    },
                )

            await asyncio.to_thread(queue.fenced, lease, save)
