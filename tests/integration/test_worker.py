import asyncio

import pytest
from reputation_platform.infrastructure.db.jobs import enqueue
from reputation_platform.infrastructure.db.tables import jobs
from reputation_platform.worker.main import Worker
from sqlalchemy import select, update

pytestmark = pytest.mark.postgres


async def test_worker_keeps_lease_alive_during_slow_io(db):
    with db.begin() as connection:
        enqueue(connection, "test", "heartbeat", {})

    async def handler(lease, queue):
        await asyncio.sleep(1.3)
        queue.fenced(lease, lambda conn: None)

    worker = Worker(db, {"test": handler}, lease_seconds=1)
    assert await worker.run_once()
    with db.connect() as connection:
        assert connection.execute(select(jobs.c.state)).scalar_one() == "SUCCEEDED"


async def test_worker_failure_is_retryable_not_silent_success(db):
    with db.begin() as connection:
        enqueue(connection, "test", "failure", {})

    async def handler(lease, queue):
        raise RuntimeError("simulated crash")

    await Worker(db, {"test": handler}).run_once()
    with db.connect() as connection:
        row = connection.execute(select(jobs)).mappings().one()
        assert row["state"] == "RETRY_WAIT"
        assert row["last_error"] == "WORKER_HANDLER_ERROR"
        assert row["attempts"] == 1


async def test_worker_cancels_after_fencing_loss(db):
    with db.begin() as connection:
        enqueue(connection, "test", "fenced", {})
    cancelled = asyncio.Event()

    async def handler(lease, queue):
        with db.begin() as connection:
            connection.execute(
                update(jobs).where(jobs.c.id == lease.job_id).values(lease_token=lease.token + 1)
            )
        try:
            await asyncio.sleep(10)
        finally:
            cancelled.set()

    await Worker(db, {"test": handler}, lease_seconds=1).run_once()
    assert cancelled.is_set()
    with db.connect() as connection:
        assert connection.execute(select(jobs.c.state)).scalar_one() != "SUCCEEDED"
