"""Public process health from database heartbeats, separate from Agent evidence."""

from datetime import datetime, timedelta, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict

HEARTBEAT_MAX_AGE_SECONDS = 90
WorkerMode = Literal['public-off', 'scoped', 'online']


class WorkerStatus(BaseModel):
    model_config = ConfigDict(extra='forbid')

    state: Literal['public-off', 'scoped', 'online', 'stopped', 'unavailable']
    last_seen_at: datetime | None = None
    scope_reference: str | None = None


class RuntimeStatus(BaseModel):
    model_config = ConfigDict(extra='forbid')

    api: Literal['ok'] = 'ok'
    database: Literal['ready', 'unavailable']
    queued: int | None
    running: int | None
    worker: WorkerStatus
    observed_at: datetime


def worker_status(row: dict | None, now: datetime) -> WorkerStatus:
    if row is None:
        return WorkerStatus(state='unavailable')
    state = 'stopped' if row['stopped'] else row['mode']
    if not row['stopped'] and not timedelta(0) <= now - row['last_seen_at'] <= timedelta(seconds=HEARTBEAT_MAX_AGE_SECONDS):
        state = 'unavailable'
    return WorkerStatus(state=state, last_seen_at=row['last_seen_at'], scope_reference=row['scope_reference'])


def unavailable_runtime() -> RuntimeStatus:
    return RuntimeStatus(database='unavailable', queued=None, running=None,
                         worker=WorkerStatus(state='unavailable'), observed_at=datetime.now(timezone.utc))
