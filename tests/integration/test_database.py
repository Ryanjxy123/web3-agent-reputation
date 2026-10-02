from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from reputation_core.models import RunPlan
from reputation_platform.infrastructure.db.connection import repo_root
from reputation_platform.infrastructure.db.jobs import (
    IdempotencyConflict,
    JobQueue,
    LostLease,
    enqueue,
    persist_plan,
)
from reputation_platform.infrastructure.db.tables import (
    agents,
    audit_logs,
    case_slots,
    jobs,
    metadata,
    reports,
    runs,
    snapshots,
)
from sqlalchemy import func, inspect, select, text, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import DBAPIError, IntegrityError

from tests.factories import HASH, ZERO, plan_data

pytestmark = pytest.mark.postgres


def snapshot(db):
    with db.begin() as connection:
        agent = connection.execute(
            insert(agents)
            .values(
                namespace="eip155",
                chain_id="31337",
                registry_address="0x" + "ab" * 20,
                agent_id=str(2**255 + 1),
                source_type="controlled",
            )
            .returning(agents.c.id)
        ).scalar_one()
        return connection.execute(
            insert(snapshots)
            .values(agent_fk=agent, snapshot_hash=HASH, body={"synthetic_example": True})
            .returning(snapshots.c.id)
        ).scalar_one()


def test_real_migration_roundtrip_and_schema(db):
    assert set(metadata.tables).issubset(inspect(db).get_table_names())
    with db.connect() as connection:
        assert connection.execute(text("SHOW timezone")).scalar_one() == "UTC"
        version = connection.execute(text("SELECT version()")).scalar_one()
        assert "PostgreSQL" in version
    config = Config(str(repo_root() / "alembic.ini"))
    command.check(config)
    command.downgrade(config, "base")
    assert inspect(db).get_table_names() == ["alembic_version"]
    command.upgrade(config, "head")
    assert "case_slots" in inspect(db).get_table_names()


def test_duplicate_identity_foreign_keys_and_rollback(db):
    snapshot(db)
    with pytest.raises(IntegrityError), db.begin() as connection:
        connection.execute(
            insert(agents).values(
                namespace="eip155",
                chain_id="31337",
                registry_address="0x" + "ab" * 20,
                agent_id=str(2**255 + 1),
                source_type="controlled",
            )
        )
    with pytest.raises(IntegrityError), db.begin() as connection:
        connection.execute(insert(snapshots).values(agent_fk=uuid4(), snapshot_hash=HASH, body={}))
    with pytest.raises(RuntimeError), db.begin() as connection:
        connection.execute(insert(audit_logs).values(actor="test", action="rollback", body={}))
        raise RuntimeError("rollback")
    with db.connect() as connection:
        assert connection.execute(select(func.count()).select_from(audit_logs)).scalar_one() == 0


def test_immutable_snapshots_reports_and_run_plan(db):
    sid = snapshot(db)
    plan = RunPlan(**plan_data())
    run_id, _ = persist_plan(db, sid, "operator", "immutability", HASH, plan)
    with db.begin() as connection:
        report_id = connection.execute(
            insert(reports)
            .values(
                run_fk=run_id,
                revision=1,
                report_hash=HASH,
                previous_report_hash=ZERO,
                core={"synthetic_example": True},
                manifest={},
            )
            .returning(reports.c.id)
        ).scalar_one()
    for statement in (
        update(snapshots).where(snapshots.c.id == sid).values(body={"changed": True}),
        update(reports).where(reports.c.id == report_id).values(core={"changed": True}),
        snapshots.delete().where(snapshots.c.id == sid),
        update(runs).where(runs.c.id == run_id).values(plan={"changed": True}),
    ):
        with pytest.raises(DBAPIError), db.begin() as connection:
            connection.execute(statement)
    with db.begin() as connection:
        connection.execute(update(runs).where(runs.c.id == run_id).values(status="RUNNING"))


def test_run_idempotency_is_atomic_and_preserves_original_challenge(db):
    sid = snapshot(db)
    plan = RunPlan(**plan_data())
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(lambda _: persist_plan(db, sid, "operator", "same-key", HASH, plan), range(2))
        )
    assert {result[0] for result in results} == {plan.run_id}
    assert sum(result[1] for result in results) == 1
    with pytest.raises(IdempotencyConflict):
        persist_plan(db, sid, "operator", "same-key", ZERO, plan)
    with db.connect() as connection:
        assert connection.execute(select(func.count()).select_from(runs)).scalar_one() == 1
        assert connection.execute(select(func.count()).select_from(case_slots)).scalar_one() == 1
        assert (
            connection.execute(select(case_slots.c.request_id)).scalar_one()
            == plan.slots[0].task.request_id
        )


def test_two_workers_claim_distinct_jobs_and_skip_locked(db):
    with db.begin() as connection:
        ids = [enqueue(connection, "test", f"job:{i}", {"i": i}) for i in range(3)]
    with db.begin() as locked:
        locked.execute(select(jobs.c.id).where(jobs.c.id == ids[0]).with_for_update()).one()
        with ThreadPoolExecutor(max_workers=2) as pool:
            leases = list(pool.map(lambda owner: JobQueue(db, owner).claim("test"), ["a", "b"]))
        assert all(leases)
        assert {lease.job_id for lease in leases} == set(ids[1:])


def test_expired_lease_fences_old_worker_and_recovers_same_payload(db):
    with db.begin() as connection:
        enqueue(connection, "test", "recover", {"request_id": HASH})
    old = JobQueue(db, "old")
    new = JobQueue(db, "new")
    first = old.claim("test")
    with db.begin() as connection:
        connection.execute(
            update(jobs)
            .where(jobs.c.id == first.job_id)
            .values(lease_until=func.clock_timestamp() - timedelta(seconds=1))
        )
    second = new.claim("test")
    assert second.job_id == first.job_id and second.token > first.token
    assert second.payload == first.payload
    for action in (
        lambda: old.heartbeat(first),
        lambda: old.complete(first),
        lambda: old.fenced(
            first,
            lambda conn: conn.execute(
                insert(audit_logs).values(actor="old", action="stale", body={})
            ),
        ),
    ):
        with pytest.raises(LostLease):
            action()
    new.heartbeat(second)
    new.complete(
        second,
        lambda conn: conn.execute(
            insert(audit_logs).values(actor="new", action="settled", body={})
        ),
    )
    with db.connect() as connection:
        assert connection.execute(select(audit_logs.c.actor)).scalars().all() == ["new"]
        assert connection.execute(select(jobs.c.state)).scalar_one() == "SUCCEEDED"


def test_retry_is_same_job_and_has_attempt_limit(db):
    with db.begin() as connection:
        jid = enqueue(connection, "test", "retry", {})
        connection.execute(update(jobs).where(jobs.c.id == jid).values(max_attempts=2))
    queue = JobQueue(db, "worker")
    first = queue.claim()
    queue.retry(first, "PLATFORM_RPC_ERROR", 0)
    second = queue.claim()
    assert second.job_id == first.job_id and second.attempt == 2
    queue.retry(second, "PLATFORM_RPC_ERROR", 0)
    assert queue.claim() is None
    with db.connect() as connection:
        row = connection.execute(select(jobs)).mappings().one()
        assert row["state"] == "FAILED" and row["last_error"] == "MAX_ATTEMPTS"


def test_business_write_and_job_completion_rollback_together(db):
    with db.begin() as connection:
        enqueue(connection, "test", "atomic", {})
    queue = JobQueue(db, "worker")
    lease = queue.claim()

    def failing(connection):
        connection.execute(insert(audit_logs).values(actor="worker", action="partial", body={}))
        raise RuntimeError("crash")

    with pytest.raises(RuntimeError):
        queue.complete(lease, failing)
    with db.connect() as connection:
        assert connection.execute(select(func.count()).select_from(audit_logs)).scalar_one() == 0
        assert connection.execute(select(jobs.c.state)).scalar_one() == "LEASED"
