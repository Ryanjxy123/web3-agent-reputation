"""Free public query execution with durable admission and per-socket fencing."""

import asyncio
import hashlib
import json
import time
from datetime import UTC, datetime
from uuid import UUID, uuid4

from reputation_core.evidence import hash_json
from reputation_core.models import DispatchState, EvidenceRecord, Observation, Reason
from reputation_core.models.public_evaluation import PublicReadonlyRunPlan, public_task_payload
from sqlalchemy import func, insert, select, update

from reputation_platform.adapters.akashi import ORIGIN, AkashiReadonlyAdapter, ReadonlyResult
from reputation_platform.adapters.registries.demo import timestamp
from reputation_platform.infrastructure.db.jobs import LostLease, enqueue
from reputation_platform.infrastructure.db.tables import (
    attempts,
    audit_logs,
    case_slots,
    dispatch_events,
    evidence_blobs,
    observations,
    runs,
)
from reputation_platform.infrastructure.network.audited_readonly import EvidencePersistenceError
from reputation_platform.infrastructure.network.safe_http import NetworkPolicyError, SafeHttpClient

from .errors import ApplicationError
from .public_evaluations import PublicReadonlyEvaluationService


def failure_reason(exc):
    if isinstance(exc, ApplicationError):
        if exc.code in {"STALE_SNAPSHOT", "PUBLIC_IDENTITY_UNVERIFIED"}:
            return Reason.IDENTITY_CHANGED
        return (
            Reason(exc.code) if exc.code in Reason._value2member_map_ else Reason.ACCESS_NOT_GRANTED
        )
    return Reason.UNSUPPORTED_PROTOCOL


class PublicReadonlyEgress:
    """A session advisory lock spans I/O, while lease checks use short transactions."""

    def __init__(self, db, identity, row, slot, *, lease=None, queue=None, phase="agent"):
        self.db, self.identity, self.row, self.slot = db, identity, row, slot
        self.lease, self.queue, self.phase = lease, queue, phase
        self.lock_connection = None
        self.origin = ORIGIN if phase == "agent" else "https://mainnet.base.org"
        self.interval_ms = 1000

    def fenced(self, operation):
        if self.lease is not None and self.queue is not None:
            return self.queue.fenced(self.lease, operation)
        with self.db.begin() as connection:
            return operation(connection)

    def check(self, connection, now):
        if not self.identity.public_readonly_enabled:
            raise ApplicationError(
                409, "PUBLIC_READONLY_DISABLED", "Public readonly access is disabled."
            )
        current = (
            connection.execute(select(runs).where(runs.c.id == self.row["id"]).with_for_update())
            .mappings()
            .one()
        )
        self.identity.require_current(connection, current["snapshot_fk"])
        grant = PublicReadonlyEvaluationService.require_grant(
            connection,
            self.slot.grant_id,
            self.slot.task.snapshot_hash,
            now,
        )
        if current["cancel_requested"]:
            raise ApplicationError(409, "CANCELLED_BY_OPERATOR", "Public query was cancelled.")
        if self.phase == "agent" and now >= datetime.fromisoformat(self.slot.task.deadline):
            raise ApplicationError(409, "TIMEOUT", "Frozen public query deadline expired.")
        if (
            grant.protocol != self.slot.task.protocol
            or grant.endpoint_ids != (self.slot.task.endpoint_id,)
            or grant.chain_instances != (self.slot.task.chain_instance_id,)
        ):
            raise ApplicationError(
                409, "ACCESS_NOT_GRANTED", "Public query exceeds its frozen grant."
            )
        return grant

    async def __aenter__(self):
        key = int.from_bytes(hashlib.sha256(self.origin.encode()).digest()[:8], "big", signed=True)
        lock_connection = await asyncio.to_thread(
            lambda: self.db.connect().execution_options(isolation_level="AUTOCOMMIT")
        )
        self.lock_connection = lock_connection
        try:
            while not await asyncio.to_thread(
                lambda: lock_connection.scalar(select(func.pg_try_advisory_lock(key)))
            ):
                await asyncio.to_thread(self.fenced, lambda c: self.check(c, datetime.now(UTC)))
                await asyncio.sleep(0.1)
        except BaseException:
            await asyncio.to_thread(lock_connection.close)
            self.lock_connection = None
            raise
        self.lock_key = key
        return self

    async def __aexit__(self, *_):
        try:

            def complete(connection):
                self.identity.audit(
                    connection,
                    "local-worker",
                    "public.egress.complete",
                    self.row["id"],
                    {"origin": self.origin, "phase": self.phase},
                )

            try:
                await asyncio.to_thread(self.fenced, complete)
            except LostLease:
                # A stale worker cannot persist completion, so hold the socket lock through the gap.
                await asyncio.sleep(self.interval_ms / 1000)
        finally:
            lock_connection = self.lock_connection
            if lock_connection is not None:
                try:
                    await asyncio.to_thread(
                        lambda: lock_connection.scalar(
                            select(func.pg_advisory_unlock(self.lock_key))
                        )
                    )
                finally:
                    await asyncio.to_thread(lock_connection.close)
                    self.lock_connection = None

    async def __call__(self, method, origin, path, payload):
        def admit(connection):
            now = connection.scalar(select(func.clock_timestamp()))
            grant = self.check(connection, now)
            if origin != self.origin:
                raise ApplicationError(409, "ACCESS_NOT_GRANTED", "Unexpected public origin.")
            if self.phase == "agent":
                expected_path = (
                    "/proof?" + "=".join(next(iter(self.slot.task.query.items())))
                    if self.slot.task.endpoint_id == "akashi-http"
                    else "/mcp"
                )
                if (
                    method not in grant.methods
                    or path != expected_path
                    or (
                        payload
                        and payload.get("method") == "tools/call"
                        and payload.get("params")
                        != {"name": "find_proof", "arguments": self.slot.task.query}
                    )
                ):
                    raise ApplicationError(
                        409, "ACCESS_NOT_GRANTED", "Request exceeds the exact public grant."
                    )
            elif method != "POST" or path != "/":
                raise ApplicationError(
                    409,
                    "ACCESS_NOT_GRANTED",
                    "Independent chain evidence permits only fixed RPC reads.",
                )
            last = connection.scalar(
                select(func.max(audit_logs.c.created_at)).where(
                    audit_logs.c.action.in_(["public.egress", "public.egress.complete"]),
                    audit_logs.c.body["origin"].astext == origin,
                )
            )
            delay = grant.interval_ms / 1000 - (now - last).total_seconds() if last else 0
            if delay > 0:
                return delay
            used = (
                connection.scalar(
                    select(func.count())
                    .select_from(audit_logs)
                    .where(
                        audit_logs.c.action == "public.egress",
                        audit_logs.c.target == self.row["id"],
                    )
                )
                or 0
            )
            if used >= 64:
                raise ApplicationError(
                    409, "ACCESS_NOT_GRANTED", "Finite public request quota is exhausted."
                )
            self.identity.audit(
                connection,
                "local-worker",
                "public.egress",
                self.row["id"],
                {
                    "origin": origin,
                    "method": method,
                    "path": path,
                    "request_json": payload,
                    "slot_id": str(self.slot.slot_id),
                    "phase": self.phase,
                    "request_id": self.slot.task.request_id,
                },
            )
            return 0

        while delay := await asyncio.to_thread(self.fenced, admit):
            await asyncio.sleep(delay)


class PublicReadonlyExecutionService:
    def __init__(self, db, identity, *, client_factory=None, fault_hook=None):
        self.db, self.identity, self.client_factory, self.fault_hook = (
            db,
            identity,
            client_factory,
            fault_hook,
        )

    async def execute(self, lease, queue, row):
        plan = PublicReadonlyRunPlan.model_validate(row["plan"])
        guard = PublicReadonlyEgress(
            self.db, self.identity, row, plan.slots[0], lease=lease, queue=queue
        )
        with self.db.connect() as connection:
            bodies = list(
                connection.scalars(
                    select(observations.c.body)
                    .join(case_slots)
                    .where(case_slots.c.run_fk == plan.run_id)
                )
            )
        stopped = any(body["reason_code"] == "UNSUPPORTED_PROTOCOL" for body in bodies)
        from .evaluations import EvaluationService

        grants = [
            EvaluationService(self.db, self.identity).grant(slot.grant_id).grant
            for slot in plan.slots
        ]
        interval = max(grant.interval_ms for grant in grants)
        guard.interval_ms = interval
        factory = self.client_factory or SafeHttpClient.public_readonly
        client = factory(
            enabled=True, before_request=guard, business_reads=False, interval_ms=interval
        )

        async def register_record(record):
            def commit(connection):
                saved = self.identity.evidence.register(connection, record)
                previous = connection.execute(
                    select(dispatch_events.c.body)
                    .where(
                        dispatch_events.c.slot_fk == guard.slot.slot_id,
                        dispatch_events.c.state == "SENDING",
                    )
                    .order_by(dispatch_events.c.created_at.desc(), dispatch_events.c.id.desc())
                    .limit(1)
                ).scalar_one()
                refs = list(
                    dict.fromkeys((*previous.get("evidence_refs", ()), str(saved.evidence_id)))
                )
                connection.execute(
                    insert(dispatch_events).values(
                        slot_fk=guard.slot.slot_id,
                        state="SENDING",
                        lease_token=lease.token,
                        body={
                            "request_id": guard.slot.task.request_id,
                            "attempt_no": 1,
                            "evidence_refs": refs,
                        },
                    )
                )
                return saved

            return await asyncio.to_thread(queue.fenced, lease, commit)

        adapters = {
            protocol: AkashiReadonlyAdapter(
                protocol, client, self.identity.evidence, register_record
            )
            for protocol in {slot.task.protocol for slot in plan.slots}
        }
        try:
            async with guard:
                for slot in plan.slots:
                    guard.slot = slot
                    stopped = (
                        await self.execute_slot(
                            lease, queue, row, plan, slot, adapters[slot.task.protocol], stopped
                        )
                        or stopped
                    )
        finally:
            await client.close()

    async def execute_slot(self, lease, queue, row, plan, slot, adapter, stopped):
        def reserve(connection):
            current = (
                connection.execute(select(runs).where(runs.c.id == plan.run_id).with_for_update())
                .mappings()
                .one()
            )
            state = connection.scalar(
                select(dispatch_events.c.state)
                .where(dispatch_events.c.slot_fk == slot.slot_id)
                .order_by(dispatch_events.c.created_at.desc(), dispatch_events.c.id.desc())
                .limit(1)
            )
            if state == "SETTLED":
                return state, None
            started = timestamp()
            if state != "NOT_SENT":
                return state, started
            reason = (
                Reason.UNSUPPORTED_PROTOCOL
                if stopped
                else Reason.CANCELLED_BY_OPERATOR
                if current["cancel_requested"]
                else None
            )
            try:
                PublicReadonlyEgress(self.db, self.identity, row, slot).check(
                    connection, datetime.now(UTC)
                )
            except ApplicationError as exc:
                reason = reason or failure_reason(exc)
            if reason is None:
                connection.execute(
                    insert(attempts).values(
                        slot_fk=slot.slot_id,
                        attempt_no=1,
                        body={
                            "method": "GET" if slot.task.endpoint_id == "akashi-http" else "POST",
                            "path": "/proof" if slot.task.endpoint_id == "akashi-http" else "/mcp",
                            "started_at": started,
                            "payload_hash": hash_json(public_task_payload(slot)),
                            "lease_token": lease.token,
                        },
                    )
                )
                connection.execute(
                    insert(dispatch_events).values(
                        slot_fk=slot.slot_id,
                        state="SENDING",
                        lease_token=lease.token,
                        body={"request_id": slot.task.request_id, "attempt_no": 1},
                    )
                )
                connection.execute(
                    update(runs)
                    .where(runs.c.id == plan.run_id)
                    .values(status="RUNNING", stage="EXECUTING")
                )
            return state, reason or started

        state, reserved = await asyncio.to_thread(queue.fenced, lease, reserve)
        if state == "SETTLED":
            return stopped
        records: list[EvidenceRecord] = []
        if state != "NOT_SENT" or isinstance(reserved, Reason):
            reason = reserved if isinstance(reserved, Reason) else Reason.DISPATCH_UNCERTAIN
            with self.db.connect() as connection:
                sending = connection.execute(
                    select(dispatch_events.c.body)
                    .where(
                        dispatch_events.c.slot_fk == slot.slot_id,
                        dispatch_events.c.state == "SENDING",
                    )
                    .order_by(dispatch_events.c.created_at.desc(), dispatch_events.c.id.desc())
                    .limit(1)
                ).scalar_one_or_none()
            retained_refs = tuple(UUID(value) for value in (sending or {}).get("evidence_refs", ()))
            with self.db.connect() as connection:
                by_id = {
                    record.evidence_id: record
                    for body in connection.scalars(
                        select(evidence_blobs.c.body).where(evidence_blobs.c.id.in_(retained_refs))
                    )
                    if (record := EvidenceRecord.model_validate(body))
                }
            retained = tuple(by_id[ref] for ref in retained_refs)
            retained_status = None
            for record in retained:
                try:
                    value = self.identity.evidence.read(record)
                    body = json.loads(value)
                    response = body.get("response") if isinstance(body, dict) else None
                    if isinstance(response, dict) and isinstance(response.get("status"), int):
                        retained_status = response["status"]
                except (OSError, ValueError, TypeError):
                    continue
            with self.db.connect() as connection:
                attempt_started = connection.scalar(
                    select(attempts.c.body["started_at"].astext)
                    .where(attempts.c.slot_fk == slot.slot_id, attempts.c.attempt_no == 1)
                    .limit(1)
                )
            ended = timestamp()
            observation = Observation(
                observation_id=uuid4(),
                slot_id=slot.slot_id,
                attempt_no=1,
                dispatch_state=DispatchState.SETTLED,
                started_at=attempt_started or timestamp(),
                ended_at=ended,
                # A crashed sender has no trustworthy end-to-end latency measurement.
                latency_ms=None,
                http_status=retained_status,
                error_origin="platform",
                reason_code=reason,
                accepted=False,
                candidate_tx_hash=None,
                evidence_refs=retained_refs,
                diagnostic_only=False,
            )
            result = ReadonlyResult(observation, None, retained)
        else:
            timer = time.monotonic()
            try:
                if self.fault_hook:
                    self.fault_hook("before_send")
                result = await adapter.query(slot.task.query, slot.slot_id, records=records)
            except (ApplicationError, NetworkPolicyError) as exc:
                reason = failure_reason(exc)
                result = ReadonlyResult(
                    Observation(
                        observation_id=uuid4(),
                        slot_id=slot.slot_id,
                        attempt_no=1,
                        dispatch_state=DispatchState.SETTLED,
                        started_at=reserved,
                        ended_at=timestamp(),
                        latency_ms=round((time.monotonic() - timer) * 1000),
                        error_origin="platform",
                        reason_code=reason,
                        accepted=False,
                        candidate_tx_hash=None,
                        evidence_refs=(),
                        diagnostic_only=False,
                    ),
                    None,
                    tuple(records),
                )
            except EvidencePersistenceError:
                raise
        # Register every intent/response before acknowledging the request; a crash after
        # the socket can then recover UNKNOWN while retaining the exact original packets.
        registered = await asyncio.to_thread(
            queue.fenced, lease, lambda c: result.registered(c, self.identity.evidence)
        )
        if self.fault_hook and state == "NOT_SENT" and not isinstance(reserved, Reason):
            self.fault_hook("after_send_before_ack")
        observation = registered.observation
        prepared = await asyncio.to_thread(
            self.identity.evidence.prepare_json,
            observation.model_dump(mode="json"),
            "public-readonly-observation",
            observation.ended_at,
            "public-http",
        )

        def settle(connection):
            record = self.identity.evidence.register(connection, prepared)
            if not connection.scalar(
                select(func.count()).select_from(attempts).where(attempts.c.slot_fk == slot.slot_id)
            ):
                connection.execute(
                    insert(attempts).values(
                        slot_fk=slot.slot_id,
                        attempt_no=1,
                        body={
                            "operation": "not_sent",
                            "started_at": observation.started_at,
                            "lease_token": lease.token,
                        },
                    )
                )
            connection.execute(
                insert(observations).values(
                    id=observation.observation_id,
                    slot_fk=slot.slot_id,
                    body=observation.model_dump(mode="json"),
                )
            )
            connection.execute(
                insert(dispatch_events).values(
                    slot_fk=slot.slot_id,
                    state="SETTLED",
                    lease_token=lease.token,
                    body={
                        "observation_id": str(observation.observation_id),
                        "observation_evidence_id": str(record.evidence_id),
                        "reason_code": observation.reason_code,
                    },
                )
            )
            settled = set(
                connection.scalars(
                    select(observations.c.slot_fk)
                    .join(case_slots)
                    .where(
                        case_slots.c.run_fk == plan.run_id,
                        observations.c.body["dispatch_state"].astext == "SETTLED",
                    )
                )
            )
            if settled == {item.slot_id for item in plan.slots}:
                enqueue(
                    connection,
                    "verify",
                    f"verify:{plan.run_id}",
                    {"run_id": str(plan.run_id)},
                    plan.run_id,
                )
                cancelled = connection.scalar(
                    select(runs.c.cancel_requested).where(runs.c.id == plan.run_id)
                )
                connection.execute(
                    update(runs)
                    .where(runs.c.id == plan.run_id)
                    .values(status="CANCELLED" if cancelled else "PARTIAL", stage="VERIFYING")
                )

        await asyncio.to_thread(queue.fenced, lease, settle)
        return (
            observation.reason_code == Reason.UNSUPPORTED_PROTOCOL
            or adapter.client.public_stop_reason is not None
        )
