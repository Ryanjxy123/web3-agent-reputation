"""Persist before I/O, fence all writes, reconcile uncertain dispatches by original request."""

import asyncio
import time
from datetime import UTC, datetime
from uuid import uuid4

import httpx
from pydantic import ValidationError
from reputation_core.binding import endpoint_hash, signatures_match
from reputation_core.evidence import hash_json, strict_json
from reputation_core.models import (
    ControlledTaskView,
    DispatchState,
    ExecutorBinding,
    Observation,
    Reason,
    RunPlan,
)
from sqlalchemy import Engine, func, insert, select, update

from reputation_platform.adapters.evm.record import reconcile_record
from reputation_platform.adapters.registries.demo import timestamp
from reputation_platform.infrastructure.db.jobs import JobQueue, Lease
from reputation_platform.infrastructure.db.tables import (
    attempts,
    bindings,
    case_slots,
    dispatch_events,
    observations,
    runs,
    snapshots,
)
from reputation_platform.infrastructure.network.safe_http import NetworkPolicyError, SafeHttpClient

from .errors import ApplicationError
from .evaluations import EvaluationService
from .identity import IdentityService


class ExecutionService:
    def __init__(self, db: Engine, identity: IdentityService | None = None, *, fault_hook=None):
        self.db, self.identity = db, identity or IdentityService(db)
        self.evaluations = EvaluationService(db, self.identity)
        self.fault_hook = fault_hook

    async def execute(self, lease: Lease, queue: JobQueue) -> None:
        if lease.run_id is None:
            raise ApplicationError(422, "RUN_REQUIRED", "Execution requires a frozen run.")
        row = self.evaluations.row(lease.run_id)
        plan = RunPlan.model_validate(row["plan"])
        slot = plan.slots[0]
        if len(plan.slots) != 1:
            raise ApplicationError(
                422, "UNSUPPORTED_SUITE", "M1 execution requires one frozen slot."
            )
        snapshot = self.identity.snapshot(row["snapshot_fk"])
        grant = self.evaluations.grant(slot.grant_id).grant
        endpoint = next(
            item for item in snapshot.core.endpoints if item.endpoint_id == grant.endpoint_ids[0]
        )
        deadline = datetime.fromisoformat(slot.task.deadline)

        def latest(connection):
            return connection.execute(
                select(dispatch_events.c.state)
                .where(dispatch_events.c.slot_fk == slot.slot_id)
                .order_by(dispatch_events.c.created_at.desc(), dispatch_events.c.id.desc())
                .limit(1)
            ).scalar_one()

        with self.db.connect() as connection:
            state = latest(connection)
            previous = (
                connection.execute(
                    select(observations.c.body)
                    .where(observations.c.slot_fk == slot.slot_id)
                    .order_by(observations.c.created_at)
                )
                .scalars()
                .all()
            )
        if state == "SETTLED":
            return
        accepted = any(item["accepted"] for item in previous)
        witness = None
        queue.fenced(
            lease,
            lambda connection: connection.execute(
                update(runs)
                .where(runs.c.id == plan.run_id)
                .values(status="RUNNING", stage="EXECUTING")
            ),
        )

        def event(connection, state, body):
            connection.execute(
                insert(dispatch_events).values(
                    slot_fk=slot.slot_id, state=state, lease_token=lease.token, body=body
                )
            )

        async def persist_record(value, source):
            prepared = await asyncio.to_thread(
                self.identity.evidence.prepare_json,
                value,
                source,
                timestamp(),
                "local-rpc" if source == "record-reconcile" else "controlled-http",
            )
            return await asyncio.to_thread(
                queue.fenced,
                lease,
                lambda connection: self.identity.evidence.register(connection, prepared),
            )

        def settle(reason=None, candidate=None, evidence_refs=(), cancelled=False):
            def commit(connection):
                attempt_no = connection.scalar(
                    select(func.max(attempts.c.attempt_no)).where(
                        attempts.c.slot_fk == slot.slot_id
                    )
                )
                if attempt_no is None:
                    attempt_no = 1
                    connection.execute(
                        insert(attempts).values(
                            slot_fk=slot.slot_id,
                            attempt_no=attempt_no,
                            body={
                                "operation": "not_sent",
                                "started_at": timestamp(),
                                "lease_token": lease.token,
                            },
                        )
                    )
                observation = Observation(
                    observation_id=uuid4(),
                    slot_id=slot.slot_id,
                    attempt_no=attempt_no,
                    dispatch_state=DispatchState.SETTLED,
                    started_at=timestamp(),
                    ended_at=timestamp(),
                    latency_ms=None,
                    error_origin="agent"
                    if reason == Reason.SCHEMA_ERROR
                    else "platform"
                    if reason
                    else None,
                    reason_code=reason,
                    accepted=accepted,
                    candidate_tx_hash=candidate,
                    evidence_refs=evidence_refs,
                    diagnostic_only=attempt_no > 1,
                )
                connection.execute(
                    insert(observations).values(
                        id=observation.observation_id,
                        slot_fk=slot.slot_id,
                        body=observation.model_dump(mode="json"),
                    )
                )
                event(
                    connection,
                    "SETTLED",
                    {
                        "observation_id": str(observation.observation_id),
                        "reason_code": reason,
                        "candidate_tx_hash": candidate,
                    },
                )
                connection.execute(
                    update(runs)
                    .where(runs.c.id == plan.run_id)
                    .values(status="CANCELLED" if cancelled else "PARTIAL", stage="VERIFYING")
                )

            queue.fenced(lease, commit)

        async def reconcile():
            value = await asyncio.to_thread(
                reconcile_record, self.identity.root, self.identity.deployment(), slot
            )
            record = await persist_record(value, "record-reconcile")
            return value, record

        async def preflight():
            observed, config = await asyncio.to_thread(self.identity.current_identity, snapshot)
            with self.db.connect() as connection:
                body = connection.execute(
                    select(bindings.c.body).where(bindings.c.id == slot.expected.binding_id)
                ).scalar_one()
            proof = ExecutorBinding.model_validate(body)
            if (
                proof.status != "VERIFIED"
                or proof.message.deadline < int(datetime.now(UTC).timestamp())
                or proof.message.executor != slot.expected.executor
                or proof.message.endpoint_hash != endpoint_hash(endpoint)
                or config.chain != slot.expected.execution_chain
                or proof.domain_salt != config.platform_instance_id
                or observed["owner_code"] != "0x"
                or observed["executor_code"] != "0x"
                or not signatures_match(proof)
            ):
                raise ApplicationError(
                    409, "BINDING_UNVERIFIED", "Execution binding is no longer valid."
                )
            prepared = await asyncio.to_thread(
                self.identity.evidence.prepare_json,
                observed,
                "pre-dispatch-identity",
                timestamp(),
                "local-rpc",
            )
            return await asyncio.to_thread(
                queue.fenced,
                lease,
                lambda connection: self.identity.evidence.register(connection, prepared),
            )

        async def reserve(method):
            # Run admission serializes Agents. A durable request timestamp enforces pacing across runs/restarts.
            with self.db.connect() as connection:
                agent_id = connection.execute(
                    select(snapshots.c.agent_fk).where(snapshots.c.id == row["snapshot_fk"])
                ).scalar_one()
                last = connection.scalar(
                    select(func.max(attempts.c.created_at))
                    .join(case_slots, attempts.c.slot_fk == case_slots.c.id)
                    .join(runs, case_slots.c.run_fk == runs.c.id)
                    .join(snapshots, runs.c.snapshot_fk == snapshots.c.id)
                    .where(snapshots.c.agent_fk == agent_id)
                )
            if last is not None:
                delay = grant.interval_ms / 1000 - (datetime.now(UTC) - last).total_seconds()
                if delay > 0:
                    await asyncio.sleep(delay)

            def commit(connection):
                current = (
                    connection.execute(
                        select(runs).where(runs.c.id == plan.run_id).with_for_update()
                    )
                    .mappings()
                    .one()
                )
                self.identity.require_current(connection, row["snapshot_fk"])
                permitted = self.evaluations.require_grant(
                    connection, slot.grant_id, snapshot.snapshot_hash, datetime.now(UTC)
                )
                path_template = "/tasks" if method == "POST" else "/tasks/{request_id}"
                if (
                    method not in permitted.methods
                    or path_template not in permitted.paths
                    or endpoint.endpoint_id not in permitted.endpoint_ids
                    or slot.capability_id not in permitted.capabilities
                    or slot.task.chain_instance_id not in permitted.chain_instances
                    or slot.task.target_contract not in permitted.contract_allowlist
                ):
                    raise ApplicationError(
                        409, "ACCESS_NOT_GRANTED", "Request exceeds the frozen grant scope."
                    )
                if method == "POST" and current["cancel_requested"]:
                    raise ApplicationError(
                        409, "CANCELLED_BY_OPERATOR", "Unsent task was cancelled."
                    )
                if method == "POST" and datetime.now(UTC) >= deadline:
                    raise ApplicationError(409, "TIMEOUT", "Task deadline passed before dispatch.")
                attempt_no = (
                    connection.scalar(
                        select(func.max(attempts.c.attempt_no)).where(
                            attempts.c.slot_fk == slot.slot_id
                        )
                    )
                    or 0
                ) + 1
                path = "/tasks" if method == "POST" else "/tasks/" + slot.task.request_id
                connection.execute(
                    insert(attempts).values(
                        slot_fk=slot.slot_id,
                        attempt_no=attempt_no,
                        body={
                            "method": method,
                            "path": path,
                            "started_at": timestamp(),
                            "payload_hash": hash_json(slot.task.model_dump(mode="json")),
                            "lease_token": lease.token,
                        },
                    )
                )
                event(
                    connection,
                    "SENDING" if method == "POST" else "RESOLVING",
                    {
                        "attempt_no": attempt_no,
                        "request_id": slot.task.request_id,
                        "pre_dispatch_evidence": str(witness.evidence_id)
                        if method == "POST" and witness
                        else None,
                    },
                )
                return attempt_no, path

            return await asyncio.to_thread(queue.fenced, lease, commit)

        client = SafeHttpClient(frozenset({endpoint.origin}))
        try:
            if state == "NOT_SENT" and row["cancel_requested"]:
                settle(Reason.CANCELLED_BY_OPERATOR, cancelled=True)
                return
            method = "POST" if state == "NOT_SENT" else "GET"
            if method == "GET":
                queue.fenced(
                    lease,
                    lambda connection: event(
                        connection, "DISPATCH_UNCERTAIN", {"reclaimed_from": state}
                    ),
                )
            while True:
                if datetime.now(UTC) >= deadline:
                    value, record = await reconcile()
                    settle(
                        None if value["candidate_tx_hash"] else Reason.DISPATCH_UNCERTAIN,
                        value["candidate_tx_hash"],
                        (record.evidence_id,),
                    )
                    return
                if method == "POST":
                    witness = await preflight()
                attempt_no, path = await reserve(method)
                started, timer = timestamp(), time.monotonic()
                view = None
                response = None
                payload = None
                reason = None
                try:
                    if method == "POST" and self.fault_hook:
                        self.fault_hook("before_send")
                    response = await client.request(
                        method,
                        endpoint.origin,
                        path,
                        json=slot.task.model_dump(mode="json") if method == "POST" else None,
                        request_id=slot.task.request_id if method == "POST" else None,
                    )
                    if method == "POST" and self.fault_hook:
                        self.fault_hook("after_send_before_ack")
                    payload = strict_json(response.body)
                    if 200 <= response.status < 300:
                        view = ControlledTaskView.model_validate(payload)
                        if (
                            view.request_id != slot.task.request_id
                            or view.status_path != "/tasks/" + slot.task.request_id
                        ):
                            raise ValueError("TASK_HANDLE_MISMATCH")
                    elif not (
                        method == "GET"
                        and response.status == 404
                        and payload == {"accepted": False, "error": {"code": "TASK_NOT_FOUND"}}
                    ):
                        reason = Reason.SCHEMA_ERROR
                except (httpx.HTTPError, TimeoutError):
                    reason = Reason.PLATFORM_NETWORK_ERROR
                except (NetworkPolicyError, ValueError, ValidationError):
                    reason = Reason.SCHEMA_ERROR
                    view = None
                ended = timestamp()
                latency_ms = int((time.monotonic() - timer) * 1000)
                accepted = accepted or view is not None
                candidate = view.result.tx_hash if view and view.result else None
                record = await persist_record(
                    {
                        "method": method,
                        "origin": endpoint.origin,
                        "path": path,
                        "request_id": slot.task.request_id,
                        "http_status": response.status if response else None,
                        "response": payload,
                        "reason_code": reason,
                        "started_at": started,
                        "ended_at": ended,
                    },
                    "agent-task-response",
                )
                observation = Observation(
                    observation_id=uuid4(),
                    slot_id=slot.slot_id,
                    attempt_no=attempt_no,
                    dispatch_state=DispatchState.ACKNOWLEDGED
                    if view
                    else DispatchState.DISPATCH_UNCERTAIN,
                    started_at=started,
                    ended_at=ended,
                    http_status=response.status if response else None,
                    latency_ms=latency_ms,
                    error_origin="platform"
                    if reason == Reason.PLATFORM_NETWORK_ERROR
                    else "agent"
                    if reason
                    else None,
                    reason_code=reason,
                    accepted=view is not None,
                    candidate_tx_hash=candidate,
                    evidence_refs=(record.evidence_id, witness.evidence_id)
                    if method == "POST" and witness
                    else (record.evidence_id,),
                    diagnostic_only=attempt_no > 1,
                )

                def save(connection):
                    connection.execute(
                        insert(observations).values(
                            id=observation.observation_id,
                            slot_fk=slot.slot_id,
                            body=observation.model_dump(mode="json"),
                        )
                    )
                    event(
                        connection,
                        observation.dispatch_state,
                        {"observation_id": str(observation.observation_id)},
                    )

                queue.fenced(lease, save)
                if candidate:
                    settle(candidate=candidate, evidence_refs=(record.evidence_id,))
                    return
                if view is None or view.task_status == "failed":
                    value, chain_record = await reconcile()
                    if value["candidate_tx_hash"]:
                        settle(
                            candidate=value["candidate_tx_hash"],
                            evidence_refs=(record.evidence_id, chain_record.evidence_id),
                        )
                        return
                    known_absent = (
                        method == "GET"
                        and response is not None
                        and response.status == 404
                        and reason is None
                        and not value["exists"]
                    )
                    with self.db.connect() as connection:
                        sends = (
                            connection.scalar(
                                select(func.count())
                                .select_from(attempts)
                                .where(
                                    attempts.c.slot_fk == slot.slot_id,
                                    attempts.c.body["method"].astext == "POST",
                                )
                            )
                            or 0
                        )
                    if known_absent and not accepted and sends < 2:
                        method = "POST"
                        continue
                    if known_absent and sends >= 2:
                        settle(
                            Reason.DISPATCH_UNCERTAIN,
                            evidence_refs=(record.evidence_id, chain_record.evidence_id),
                        )
                        return
                    if reason == Reason.SCHEMA_ERROR or (view and view.task_status == "failed"):
                        settle(
                            reason or Reason.DISPATCH_UNCERTAIN,
                            evidence_refs=(record.evidence_id, chain_record.evidence_id),
                        )
                        return
                method = "GET"
        except ApplicationError as exc:
            # Revocation/cancellation forbids further HTTP writes. Trusted RPC reconciliation remains safe.
            code = {
                "STALE_SNAPSHOT": Reason.IDENTITY_CHANGED,
                "CHAIN_INSTANCE_MISMATCH": Reason.CHAIN_INSTANCE_CHANGED,
            }.get(exc.code)
            try:
                reason = code or Reason(exc.code)
            except ValueError:
                reason = Reason.DISPATCH_UNCERTAIN
            with self.db.connect() as connection:
                sent = connection.scalar(
                    select(func.count())
                    .select_from(attempts)
                    .where(
                        attempts.c.slot_fk == slot.slot_id,
                        attempts.c.body["method"].astext == "POST",
                    )
                )
            if sent:
                try:
                    value, record = await reconcile()
                    if value["candidate_tx_hash"]:
                        settle(
                            candidate=value["candidate_tx_hash"],
                            evidence_refs=(record.evidence_id,),
                        )
                        return
                except ApplicationError:
                    pass
            settle(reason, cancelled=reason == Reason.CANCELLED_BY_OPERATOR and not sent)
        finally:
            await client.close()
