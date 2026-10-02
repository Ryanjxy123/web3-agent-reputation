"""Lease heartbeat and bounded recovery, independent of the API process."""

import asyncio
import logging
import socket
from collections.abc import Callable, Coroutine
from contextlib import suppress
from typing import Any
from uuid import uuid4

from sqlalchemy import Connection, Engine, update

from reputation_platform.application.errors import ApplicationError
from reputation_platform.application.execution import ExecutionService
from reputation_platform.application.identity import IdentityService
from reputation_platform.application.reports import ReportService
from reputation_platform.application.verification import VerificationService
from reputation_platform.infrastructure.db.connection import engine
from reputation_platform.infrastructure.db.jobs import JobQueue, Lease, LostLease, mark_run_failed
from reputation_platform.infrastructure.db.tables import jobs

Handler = Callable[[Lease, JobQueue], Coroutine[Any, Any, None]]
LOG = logging.getLogger(__name__)


class Worker:
    def __init__(self, database: Engine, handlers: dict[str, Handler], *, lease_seconds: int = 30):
        self.queue = JobQueue(database, f"{socket.gethostname()}:{uuid4()}", lease_seconds)
        self.handlers = handlers
        self.heartbeat_interval = lease_seconds / 3

    async def _heartbeat(self, lease: Lease) -> None:
        while True:
            await asyncio.sleep(self.heartbeat_interval)
            await asyncio.to_thread(self.queue.heartbeat, lease)

    def _fail(self, lease: Lease, reason: str) -> None:
        def fail(connection: Connection):
            mark_run_failed(connection, lease.run_id)
            connection.execute(
                update(jobs)
                .where(jobs.c.id == lease.job_id)
                .values(state="FAILED", lease_until=None, last_error=reason)
            )

        self.queue.fenced(lease, fail)

    async def run_once(self) -> bool:
        lease = await asyncio.to_thread(self.queue.claim)
        if lease is None:
            return False
        handler = self.handlers.get(lease.kind)
        if handler is None:
            await asyncio.to_thread(self._fail, lease, "UNSUPPORTED_JOB")
            return True
        heartbeat = asyncio.create_task(self._heartbeat(lease))
        work = asyncio.create_task(handler(lease, self.queue))
        try:
            finished, _ = await asyncio.wait({heartbeat, work}, return_when=asyncio.FIRST_COMPLETED)
            if heartbeat in finished:
                heartbeat.result()  # Lost lease cancels outstanding work; no stale completion.
            await work
            await asyncio.to_thread(self.queue.complete, lease)
        except LostLease:
            LOG.warning("Lease lost for job %s; dispatch state must be reconciled.", lease.job_id)
        except ApplicationError as exc:
            with suppress(LostLease):
                if exc.retryable:
                    await asyncio.to_thread(
                        self.queue.retry, lease, exc.code, min(5 * 2 ** (lease.attempt - 1), 60)
                    )
                else:
                    await asyncio.to_thread(self._fail, lease, exc.code)
        except Exception:
            # Do not log response bodies, secrets, or arbitrary exception text.
            LOG.error("Handler failed for job %s; scheduling bounded reconciliation.", lease.job_id)
            with suppress(LostLease):
                await asyncio.to_thread(
                    self.queue.retry,
                    lease,
                    "WORKER_HANDLER_ERROR",
                    min(5 * 2 ** (lease.attempt - 1), 60),
                )
        finally:
            for task in (work, heartbeat):
                task.cancel()
            await asyncio.gather(work, heartbeat, return_exceptions=True)
        return True


async def serve(once: bool = False) -> None:
    database = engine()
    # Only reviewed in-process adapters may register here. No metadata-driven import.
    handlers: dict[str, Handler] = {
        "ingest": IdentityService(database).ingest,
        "evaluate": ExecutionService(database).execute,
        "verify": VerificationService(database).verify,
        "report": ReportService(database).freeze,
    }
    worker = Worker(database, handlers)
    try:
        while True:
            worked = await worker.run_once()
            if once:
                return
            if not worked:
                await asyncio.sleep(1)
    finally:
        database.dispose()
