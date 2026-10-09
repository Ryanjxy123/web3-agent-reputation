"""Short PostgreSQL leases with fencing; network work never runs inside these transactions."""

from collections.abc import Callable
from contextlib import nullcontext
from dataclasses import dataclass
from datetime import timedelta
from typing import Any, TypeVar
from uuid import UUID, uuid4

from reputation_core.case_templates import mutated_payload
from reputation_core.evidence import hash_json
from reputation_core.models import RunPlan
from sqlalchemy import Connection, Engine, and_, func, or_, select, update
from sqlalchemy.dialects.postgresql import insert

from .tables import case_slots, dispatch_events, jobs, runs

T = TypeVar("T")


class LostLease(RuntimeError):
    pass


class IdempotencyConflict(ValueError):
    pass


def mark_run_failed(connection: Connection, run_id: UUID | None) -> None:
    if run_id is not None:
        connection.execute(
            update(runs)
            .where(runs.c.id == run_id, runs.c.status.in_(["QUEUED", "RUNNING"]))
            .values(status="FAILED", stage="VERIFYING")
        )


@dataclass(frozen=True)
class Lease:
    job_id: UUID
    token: int
    kind: str
    run_id: UUID | None
    payload: dict[str, Any]
    attempt: int


def enqueue(
    connection: Connection,
    kind: str,
    dedup_key: str,
    payload: dict[str, Any],
    run_id: UUID | None = None,
) -> UUID:
    candidate = uuid4()
    result = connection.execute(
        insert(jobs)
        .values(id=candidate, kind=kind, dedup_key=dedup_key, payload=payload, run_fk=run_id)
        .on_conflict_do_nothing(index_elements=["dedup_key"])
        .returning(jobs.c.id)
    ).scalar_one_or_none()
    if result is not None:
        return result
    existing = (
        connection.execute(select(jobs).where(jobs.c.dedup_key == dedup_key)).mappings().one()
    )
    if existing["kind"] != kind or existing["payload"] != payload or existing["run_fk"] != run_id:
        raise IdempotencyConflict("job key was already used with different inputs")
    return existing["id"]


def persist_plan(
    db: Engine | Connection,
    snapshot_id: UUID,
    actor: str,
    idempotency_key: str,
    payload_hash: str,
    plan: RunPlan,
) -> tuple[UUID, bool]:
    with db.begin() if isinstance(db, Engine) else nullcontext(db) as connection:
        inserted = connection.execute(
            insert(runs)
            .values(
                id=plan.run_id,
                snapshot_fk=snapshot_id,
                actor_id=actor,
                idempotency_key=idempotency_key,
                request_payload_hash=payload_hash,
                plan=plan.model_dump(mode="json"),
            )
            .on_conflict_do_nothing(index_elements=["actor_id", "idempotency_key"])
            .returning(runs.c.id)
        ).scalar_one_or_none()
        if inserted is None:
            existing = (
                connection.execute(
                    select(runs).where(
                        runs.c.actor_id == actor, runs.c.idempotency_key == idempotency_key
                    )
                )
                .mappings()
                .one()
            )
            if existing["request_payload_hash"] != payload_hash:
                raise IdempotencyConflict("run key was already used with different inputs")
            return existing["id"], False
        for slot in plan.slots:
            connection.execute(
                insert(case_slots).values(
                    id=slot.slot_id,
                    run_fk=plan.run_id,
                    slot_key=slot.slot_key,
                    request_id=slot.task.request_id,
                    purpose=slot.purpose.value,
                    body=slot.model_dump(mode="json"),
                )
            )
            connection.execute(
                insert(dispatch_events).values(
                    slot_fk=slot.slot_id,
                    state="NOT_SENT",
                    lease_token=0,
                    body={
                        "request_id": slot.task.request_id,
                        "payload_hash": hash_json(
                            mutated_payload(slot)
                            if plan.template_version == "capabilities@3"
                            else slot.task.model_dump(mode="json")
                        ),
                    },
                )
            )
        enqueue(
            connection,
            "evaluate",
            f"evaluate:{plan.run_id}",
            {"run_id": str(plan.run_id)},
            plan.run_id,
        )
    return plan.run_id, True


class JobQueue:
    def __init__(self, db: Engine, owner: str, lease_seconds: int = 30):
        if not 1 <= lease_seconds <= 300:
            raise ValueError("lease seconds out of range")
        self.db, self.owner, self.duration = db, owner, timedelta(seconds=lease_seconds)

    def claim(self, kind: str | None = None) -> Lease | None:
        now = func.clock_timestamp()
        ready = or_(
            and_(jobs.c.state.in_(["QUEUED", "RETRY_WAIT"]), jobs.c.available_at <= now),
            and_(jobs.c.state == "LEASED", jobs.c.lease_until <= now),
        )
        with self.db.begin() as connection:
            # Short claim-only mutex makes the initial global dispatch limit atomic across workers.
            connection.execute(select(func.pg_advisory_xact_lock(0x574152000001)))
            exhausted = (
                connection.execute(
                    update(jobs)
                    .where(ready, jobs.c.attempts >= jobs.c.max_attempts)
                    .values(state="FAILED", lease_until=None, last_error="MAX_ATTEMPTS")
                    .returning(jobs.c.run_fk)
                )
                .scalars()
                .all()
            )
            for run_id in exhausted:
                mark_run_failed(connection, run_id)
            query = select(jobs).where(ready, jobs.c.attempts < jobs.c.max_attempts)
            active_dispatches = (
                connection.scalar(
                    select(func.count())
                    .select_from(jobs)
                    .where(
                        jobs.c.kind == "evaluate",
                        jobs.c.state == "LEASED",
                        jobs.c.lease_until > now,
                    )
                )
                or 0
            )
            if active_dispatches >= 2:
                query = query.where(jobs.c.kind != "evaluate")
            if kind:
                query = query.where(jobs.c.kind == kind)
            row = (
                connection.execute(
                    query.order_by(jobs.c.available_at, jobs.c.id)
                    .with_for_update(skip_locked=True)
                    .limit(1)
                )
                .mappings()
                .first()
            )
            if row is None:
                return None
            token = row["lease_token"] + 1
            connection.execute(
                update(jobs)
                .where(jobs.c.id == row["id"])
                .values(
                    state="LEASED",
                    lease_owner=self.owner,
                    lease_token=token,
                    lease_until=now + self.duration,
                    attempts=row["attempts"] + 1,
                )
            )
            return Lease(
                row["id"], token, row["kind"], row["run_fk"], row["payload"], row["attempts"] + 1
            )

    def _owned(self, lease: Lease):
        return and_(
            jobs.c.id == lease.job_id,
            jobs.c.lease_token == lease.token,
            jobs.c.lease_owner == self.owner,
            jobs.c.state == "LEASED",
            jobs.c.lease_until > func.clock_timestamp(),
        )

    def heartbeat(self, lease: Lease) -> None:
        with self.db.begin() as connection:
            result = connection.execute(
                update(jobs)
                .where(self._owned(lease))
                .values(lease_until=func.clock_timestamp() + self.duration)
            )
            if result.rowcount != 1:
                raise LostLease("worker no longer owns this lease")

    def fenced(self, lease: Lease, operation: Callable[[Connection], T]) -> T:
        """Atomically check ownership, lock, and persist business progress."""
        with self.db.begin() as connection:
            row = connection.execute(
                select(jobs.c.id).where(self._owned(lease)).with_for_update()
            ).first()
            if row is None:
                raise LostLease("stale worker cannot persist progress")
            return operation(connection)

    def complete(self, lease: Lease, operation: Callable[[Connection], Any] | None = None) -> None:
        def finish(connection: Connection):
            if operation:
                operation(connection)
            connection.execute(
                update(jobs)
                .where(jobs.c.id == lease.job_id)
                .values(state="SUCCEEDED", lease_until=None, last_error=None)
            )

        self.fenced(lease, finish)

    def retry(self, lease: Lease, reason_code: str, delay_seconds: int = 5) -> None:
        if not 0 <= delay_seconds <= 3600:
            raise ValueError("invalid retry delay")

        def reschedule(connection: Connection):
            connection.execute(
                update(jobs)
                .where(jobs.c.id == lease.job_id)
                .values(
                    state="RETRY_WAIT",
                    lease_until=None,
                    last_error=reason_code,
                    available_at=func.clock_timestamp() + timedelta(seconds=delay_seconds),
                )
            )

        self.fenced(lease, reschedule)
