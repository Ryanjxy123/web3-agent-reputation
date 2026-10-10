"""Operator grants and frozen task plans; no Agent network calls here."""

import secrets
from datetime import UTC, datetime, timedelta
from typing import Literal, cast
from uuid import UUID, uuid4

from pydantic import JsonValue
from reputation_core.binding import endpoint_hash, signatures_match
from reputation_core.evidence import hash_bytes, hash_json, strict_json
from reputation_core.models import (
    AcceptedEvaluation,
    AccessGrant,
    AccessGrantCreate,
    CaseSlot,
    ClaimReview,
    EvaluationCreate,
    EvaluationRun,
    ExecutorBinding,
    ExpectedFacts,
    GrantView,
    Observation,
    Outcome,
    Purpose,
    Reason,
    RunPlan,
    TaskEnvelope,
)
from requests.exceptions import RequestException
from sqlalchemy import Connection, Engine, func, insert, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from web3 import Web3
from web3.exceptions import Web3Exception

from reputation_platform.infrastructure.db.jobs import IdempotencyConflict, persist_plan
from reputation_platform.infrastructure.db.tables import (
    access_grants,
    assertions,
    bindings,
    case_slots,
    claim_reviews,
    grant_revocations,
    observations,
    reports,
    runs,
    snapshots,
)

from .errors import ApplicationError
from .identity import IdentityService
from .local_deploy import local_web3


def utc_text(value: datetime) -> str:
    return value.isoformat(timespec="milliseconds").replace("+00:00", "Z")


class EvaluationService:
    def __init__(self, db: Engine, identity: IdentityService | None = None):
        self.db, self.identity = db, identity or IdentityService(db)

    def create_grant(self, request: AccessGrantCreate, actor: str) -> GrantView:
        snapshot = self.identity.snapshot(request.snapshot_id)
        config = self.identity.deployment()
        if (
            snapshot.core.source_type != "controlled"
            or snapshot.core.registry_chain != config.chain
        ):
            raise ApplicationError(
                409, "ACCESS_NOT_GRANTED", "M1 grants require the configured controlled chain."
            )
        if request.endpoint_id not in {
            endpoint.endpoint_id for endpoint in snapshot.core.endpoints
        }:
            raise ApplicationError(422, "ACCESS_NOT_GRANTED", "Endpoint is not in the snapshot.")
        expiry = datetime.fromisoformat(request.expires_at)
        if not datetime.now(UTC) < expiry <= datetime.now(UTC) + timedelta(hours=24):
            raise ApplicationError(
                422, "ACCESS_NOT_GRANTED", "Local grants must expire within 24 hours."
            )
        grant = AccessGrant(
            grant_id=uuid4(),
            snapshot_hash=snapshot.snapshot_hash,
            endpoint_ids=(request.endpoint_id,),
            capabilities=request.capabilities,
            methods=("POST", "GET"),
            paths=("/tasks", "/tasks/{request_id}"),
            chain_instances=(config.chain.instance_hash,),
            contract_allowlist=request.contract_allowlist
            if request.contract_allowlist is not None
            else ()
            if request.capabilities == ("get_tx_status",)
            else (config.record.address,),
            max_tasks=request.max_tasks,
            interval_ms=request.interval_ms,
            expires_at=request.expires_at,
            operator=actor,
            consent_ref=request.consent_ref,
        )
        with self.db.begin() as connection:
            self.identity.require_current(connection, request.snapshot_id)
            connection.execute(
                insert(access_grants).values(
                    id=grant.grant_id,
                    snapshot_fk=request.snapshot_id,
                    expires_at=expiry,
                    body=grant.model_dump(mode="json"),
                )
            )
            self.identity.audit(
                connection,
                actor,
                "grant.create",
                grant.grant_id,
                {"snapshot_id": str(request.snapshot_id)},
            )
        return GrantView(grant=grant, revoked=False)

    def grant(self, grant_id: UUID) -> GrantView:
        with self.db.connect() as connection:
            row = connection.execute(
                select(access_grants.c.body).where(access_grants.c.id == grant_id)
            ).scalar_one_or_none()
            revoked = connection.execute(
                select(grant_revocations.c.id).where(grant_revocations.c.grant_fk == grant_id)
            ).first()
        if row is None:
            raise ApplicationError(404, "NOT_FOUND", "Grant does not exist.")
        return GrantView(grant=AccessGrant.model_validate(row), revoked=revoked is not None)

    def revoke(self, grant_id: UUID, reason: str, actor: str) -> GrantView:
        self.grant(grant_id)
        with self.db.begin() as connection:
            connection.execute(
                select(access_grants.c.id).where(access_grants.c.id == grant_id).with_for_update()
            ).one()
            connection.execute(
                pg_insert(grant_revocations)
                .values(grant_fk=grant_id, actor=actor, reason=reason)
                .on_conflict_do_nothing(index_elements=["grant_fk"])
            )
            self.identity.audit(connection, actor, "grant.revoke", grant_id, {"reason": reason})
        return self.grant(grant_id)

    @staticmethod
    def require_grant(
        connection: Connection, grant_id: UUID, snapshot_hash: str, now: datetime
    ) -> AccessGrant:
        row = (
            connection.execute(
                select(access_grants).where(access_grants.c.id == grant_id).with_for_update()
            )
            .mappings()
            .first()
        )
        revoked = connection.execute(
            select(grant_revocations.c.id).where(grant_revocations.c.grant_fk == grant_id)
        ).first()
        if row is None or revoked is not None or row["expires_at"] <= now:
            raise ApplicationError(
                409, "ACCESS_NOT_GRANTED", "Grant is absent, revoked or expired."
            )
        grant = AccessGrant.model_validate(row["body"])
        if grant.snapshot_hash != snapshot_hash:
            raise ApplicationError(
                409, "ACCESS_NOT_GRANTED", "Grant belongs to a different snapshot."
            )
        return grant

    @staticmethod
    def existing(connection: Connection, actor: str, key: str, payload_hash: str):
        row = (
            connection.execute(
                select(runs).where(runs.c.actor_id == actor, runs.c.idempotency_key == key)
            )
            .mappings()
            .first()
        )
        if row is not None and row["request_payload_hash"] != payload_hash:
            raise ApplicationError(
                409,
                "IDEMPOTENCY_CONFLICT",
                "Idempotency key was already used with different inputs.",
            )
        return row

    @staticmethod
    def accepted(row) -> AcceptedEvaluation:
        return AcceptedEvaluation(
            run_id=row["id"], status=row["status"], status_url=f"/api/v1/evaluations/{row['id']}"
        )

    def create(self, request: EvaluationCreate, key: str, actor: str) -> AcceptedEvaluation:
        if (
            not 1 <= len(key) <= 200
            or not key.isascii()
            or any(ord(char) < 33 or ord(char) > 126 for char in key)
        ):
            raise ApplicationError(
                422,
                "IDEMPOTENCY_KEY_REQUIRED",
                "Use a nonempty printable Idempotency-Key of at most 200 characters.",
            )
        payload_hash = hash_json(request.model_dump(mode="json"))
        with self.db.connect() as connection:
            existing = self.existing(connection, actor, key, payload_hash)
        if existing is not None:
            return self.accepted(existing)
        formal = request.suite_id == "formal-evaluation-v1"
        writing = (
            request.profile == "record-write-v1"
            if formal
            else request.capability_id == "anchor_record"
        )
        if (
            len(request.grant_ids) != 1
            or (writing and request.profile != "record-write-v1")
            or (request.suite_id == "m1-smoke-v1" and not writing)
        ):
            raise ApplicationError(
                422,
                "UNSUPPORTED_PROFILE",
                "Runs require one explicit local grant; writes require a write profile.",
            )
        snapshot = self.identity.snapshot(request.snapshot_id)
        observation, config = self.identity.current_identity(snapshot)
        target = (
            (request.target_contract or config.record.address)
            if formal or request.capability_id != "get_tx_status"
            else None
        )
        target_code = None
        if target is not None:
            try:
                web3 = local_web3(config.rpc_url)
                code = web3.eth.get_code(
                    Web3.to_checksum_address(target),
                    int(observation["snapshot_core"]["read_block_number"]),
                )
            except (RequestException, Web3Exception, OSError, ValueError):
                raise ApplicationError(
                    503,
                    "PLATFORM_RPC_ERROR",
                    "Task target code could not be independently read.",
                    True,
                ) from None
            if not code:
                raise ApplicationError(
                    422, "TARGET_NOT_ALLOWED", "A task target must be a deployed contract."
                )
            target_code = hash_bytes(bytes(code))
        planning_evidence = self.identity.evidence.prepare_json(
            observation,
            "planning-registry-read",
            observation["snapshot_core"]["captured_at"],
            "local-rpc",
        )
        now = datetime.now(UTC)
        deadline = now + timedelta(seconds=60)
        with self.db.begin() as connection:
            self.identity.require_current(connection, request.snapshot_id)
            existing = self.existing(connection, actor, key, payload_hash)
            if existing is not None:
                return self.accepted(existing)
            agent_id = connection.execute(
                select(snapshots.c.agent_fk).where(snapshots.c.id == request.snapshot_id)
            ).scalar_one()
            busy = connection.execute(
                select(runs.c.id)
                .join(snapshots, snapshots.c.id == runs.c.snapshot_fk)
                .where(snapshots.c.agent_fk == agent_id, runs.c.status.in_(["QUEUED", "RUNNING"]))
                .limit(1)
            ).first()
            if busy:
                raise ApplicationError(409, "AGENT_BUSY", "This Agent already has an active run.")
            review_body = connection.execute(
                select(claim_reviews.c.body)
                .where(claim_reviews.c.snapshot_fk == request.snapshot_id)
                .order_by(claim_reviews.c.review_version.desc())
                .limit(1)
            ).scalar_one_or_none()
            if review_body is None:
                raise ApplicationError(
                    409, "MAPPING_UNCONFIRMED", "Capability mapping is not confirmed."
                )
            review = ClaimReview.model_validate(review_body)
            excluded = not formal and request.capability_id in review.excluded_capabilities
            if excluded and request.suite_id == "m1-smoke-v1":
                raise ApplicationError(
                    422,
                    "UNSUPPORTED_PROFILE",
                    "The M1 smoke suite requires a declared anchor_record capability.",
                )
            if review.review_version != request.review_version or (
                not formal and request.capability_id not in review.confirmed_claims and not excluded
            ):
                raise ApplicationError(
                    409, "REVIEW_CONFLICT", "The current confirmed mapping differs."
                )
            grant = self.require_grant(
                connection, request.grant_ids[0], snapshot.snapshot_hash, now
            )
            policy = strict_json(
                (self.identity.root / "configs/policies/policy-v1.json").read_bytes()
            )
            capabilities = review.confirmed_claims if formal else (request.capability_id,)
            if formal and ("anchor_record" in capabilities) != writing:
                raise ApplicationError(
                    422, "UNSUPPORTED_PROFILE", "The profile must cover all confirmed capabilities."
                )
            specifications = [(request.capability_id, Purpose.FUNCTIONAL, "normal")]
            if formal:
                specifications = []
                readonly = next(
                    (cap for cap in ("verify_record", "get_tx_status") if cap in capabilities), None
                )
                if readonly:
                    specifications.extend(
                        (readonly, Purpose.AVAILABILITY, "normal")
                        for _ in range(policy["availability"]["min_samples"])
                    )
                for capability in capabilities:
                    classes = {
                        "get_tx_status": ("success",) * 3
                        + ("revert",) * 2
                        + ("pending",) * 2
                        + ("not_found", "invalid_format", "unsupported_chain"),
                        "verify_record": ("match",) * 4
                        + ("not_found",) * 2
                        + ("hash_mismatch",) * 2
                        + ("invalid_format", "forbidden_contract"),
                        "anchor_record": ("normal",) * 7
                        + ("expired_deadline", "forbidden_contract", "unsupported_chain"),
                    }[capability]
                    specifications.extend(
                        (capability, Purpose.FUNCTIONAL, case) for case in classes
                    )
                if writing:
                    specifications.extend(
                        ("anchor_record", Purpose.BEHAVIORAL, "normal")
                        for _ in range(policy["behavior"]["min_accepted_decided_tasks"])
                    )
                # Each slot reserves an initial send and two status/recovery requests.
                deadline += timedelta(
                    milliseconds=(len(specifications) - 1) * 3 * grant.interval_ms
                )
            if not set(capabilities).issubset(grant.capabilities) or (
                any(cap != "get_tx_status" for cap in capabilities)
                and target not in grant.contract_allowlist
            ):
                raise ApplicationError(
                    409,
                    "ACCESS_NOT_GRANTED",
                    "Task exceeds the explicit capability or contract grant.",
                )
            if datetime.fromisoformat(grant.expires_at) < deadline:
                raise ApplicationError(
                    409, "ACCESS_NOT_GRANTED", "Grant must cover the complete frozen task window."
                )
            reserved = connection.scalar(
                select(func.count())
                .select_from(case_slots)
                .where(case_slots.c.body["grant_id"].astext == str(grant.grant_id))
            )
            if (reserved or 0) + len(specifications) > grant.max_tasks:
                raise ApplicationError(
                    409, "GRANT_QUOTA_EXHAUSTED", "Grant task quota has already been reserved."
                )
            endpoint = next(
                item
                for item in snapshot.core.endpoints
                if item.endpoint_id == grant.endpoint_ids[0]
            )
            proof_bodies = connection.execute(
                select(bindings.c.body)
                .where(bindings.c.snapshot_fk == request.snapshot_id)
                .order_by(bindings.c.created_at.desc())
            ).scalars()
            proof = next(
                (
                    candidate
                    for body in proof_bodies
                    if (candidate := ExecutorBinding.model_validate(body)).status == "VERIFIED"
                    and candidate.message.endpoint_hash == endpoint_hash(endpoint)
                    and datetime.fromtimestamp(candidate.message.deadline, UTC) >= deadline
                    and candidate.domain_salt == config.platform_instance_id
                    and candidate.domain_chain_id == config.chain.chain_id
                    and candidate.domain_registry == config.registry.address
                    and signatures_match(candidate)
                ),
                None,
            )
            if (
                writing
                and not excluded
                and (
                    proof is None
                    or observation["owner_code"] != "0x"
                    or observation["executor_code"] != "0x"
                )
            ):
                raise ApplicationError(
                    409,
                    "BINDING_UNVERIFIED",
                    "A current dual-signed EOA binding must cover this task window.",
                )
            slots = []
            for index, (capability, purpose, required_class) in enumerate(specifications, start=1):
                slot_writes = capability == "anchor_record"
                slot_deadline = (
                    now + timedelta(seconds=60, milliseconds=(index - 1) * 3 * grant.interval_ms)
                    if formal
                    else deadline
                )
                query_hash = (
                    (request.transaction_cases or {}).get(
                        cast(Literal["success", "revert", "pending"], required_class)
                    )
                    if formal
                    else request.query_tx_hash
                )
                record_source = (
                    formal
                    and required_class in {"match", "hash_mismatch"}
                    and request.record_request_id is not None
                )
                record_hash = (
                    request.record_hash
                    if record_source
                    else "0x" + secrets.token_hex(32)
                    if formal and capability == "verify_record"
                    else request.record_hash
                )
                if required_class == "hash_mismatch" and record_source:
                    record_hash = "0x" + secrets.token_hex(32)
                synthetic: dict[str, JsonValue] | None = (
                    {"kind": "synthetic-credential-v1", "challenge": "0x" + secrets.token_hex(32)}
                    if slot_writes
                    else None
                )
                task = TaskEnvelope(
                    capability_id=capability,
                    request_id="0x" + secrets.token_hex(32),
                    snapshot_hash=snapshot.snapshot_hash,
                    chain_id=config.chain.chain_id,
                    chain_instance_id=config.chain.instance_hash,
                    target_contract=None if capability == "get_tx_status" else target,
                    record_hash=hash_json(synthetic)
                    if slot_writes
                    else record_hash
                    if capability == "verify_record"
                    else None,
                    query_tx_hash=query_hash or "0x" + secrets.token_hex(32)
                    if capability == "get_tx_status"
                    else None,
                    record_executor=request.record_executor
                    if record_source
                    else snapshot.core.owner
                    if formal and capability == "verify_record"
                    else request.record_executor
                    if capability == "verify_record"
                    else None,
                    record_request_id=request.record_request_id
                    if record_source
                    else "0x" + secrets.token_hex(32)
                    if formal and capability == "verify_record"
                    else request.record_request_id
                    if capability == "verify_record"
                    else None,
                    read_block_number=None
                    if slot_writes
                    else observation["snapshot_core"]["read_block_number"],
                    read_block_hash=None
                    if slot_writes
                    else observation["snapshot_core"]["read_block_hash"],
                    deadline=utc_text(slot_deadline),
                )
                facts = ExpectedFacts(
                    agent_ref=snapshot.core.agent_ref,
                    snapshot_hash=snapshot.snapshot_hash,
                    execution_chain=config.chain,
                    executor=proof.message.executor
                    if slot_writes and proof
                    else task.record_executor or snapshot.core.owner,
                    target_contract=task.target_contract,
                    target_code_hash=target_code if task.target_contract else None,
                    request_id=task.request_id,
                    record_hash=task.record_hash,
                    binding_id=proof.binding_id if slot_writes and proof and not excluded else None,
                    window_start=utc_text(now),
                    deadline=task.deadline,
                    pre_dispatch_block=observation["snapshot_core"]["read_block_number"],
                    pre_dispatch_block_hash=observation["snapshot_core"]["read_block_hash"],
                    confirmation_depth=config.confirmation_depth,
                )
                slot = CaseSlot(
                    slot_id=uuid4(),
                    slot_key=f"{capability}-{index}",
                    capability_id=capability,
                    purpose=purpose,
                    case_kind="negative"
                    if formal
                    and required_class
                    in {
                        "invalid_format",
                        "forbidden_contract",
                        "unsupported_chain",
                        "expired_deadline",
                    }
                    else "positive",
                    required_class=required_class,
                    expected_outcome=Outcome.NOT_APPLICABLE if excluded else Outcome.PASS,
                    task=task,
                    expected=facts,
                    grant_id=grant.grant_id,
                    synthetic_input=synthetic,
                    applicability_reason=Reason.CAPABILITY_NOT_DECLARED if excluded else None,
                    request_overrides={
                        "target_contract": next(
                            (
                                address
                                for address in (config.anchor.address, config.registry.address)
                                if address not in grant.contract_allowlist
                            ),
                            "0x" + secrets.token_hex(20),
                        )
                    }
                    if formal and required_class == "forbidden_contract"
                    else None,
                )
                slots.append(slot)
            evidence = self.identity.evidence.register(connection, planning_evidence)
            plan = RunPlan(
                run_id=uuid4(),
                snapshot_hash=snapshot.snapshot_hash,
                review_version=review.review_version,
                policy_version="policy-v1",
                policy_hash=hash_json(policy),
                profile=request.profile,
                confirmed_capabilities=review.confirmed_claims if excluded else capabilities,
                suite_id=request.suite_id,
                template_version="capabilities@5"
                if formal
                else "anchor_record@2"
                if request.suite_id == "m1-smoke-v1"
                else "capabilities@2",
                planning_time=utc_text(now),
                planning_evidence_refs=(evidence.evidence_id,),
                slots=tuple(slots),
            )
            try:
                persist_plan(connection, request.snapshot_id, actor, key, payload_hash, plan)
            except IdempotencyConflict:
                raise ApplicationError(
                    409,
                    "IDEMPOTENCY_CONFLICT",
                    "Idempotency key was already used with different inputs.",
                ) from None
            self.identity.audit(
                connection, actor, "evaluation.create", plan.run_id, {"request_hash": payload_hash}
            )
        return AcceptedEvaluation(
            run_id=plan.run_id, status_url=f"/api/v1/evaluations/{plan.run_id}"
        )

    def row(self, run_id: UUID):
        with self.db.connect() as connection:
            row = connection.execute(select(runs).where(runs.c.id == run_id)).mappings().first()
        if row is None:
            raise ApplicationError(404, "NOT_FOUND", "Evaluation does not exist.")
        return row

    def view(self, run_id: UUID) -> EvaluationRun:
        row = self.row(run_id)
        with self.db.connect() as connection:
            report_id = connection.execute(
                select(reports.c.id)
                .where(reports.c.run_fk == run_id)
                .order_by(reports.c.revision.desc())
                .limit(1)
            ).scalar_one_or_none()
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
            outcomes: dict[UUID, list[str]] = {}
            for slot_id, body in connection.execute(
                select(assertions.c.slot_fk, assertions.c.body)
                .join(case_slots, assertions.c.slot_fk == case_slots.c.id)
                .where(case_slots.c.run_fk == run_id)
            ):
                outcomes.setdefault(slot_id, []).append(body["outcome"])
            unknown = sum(
                not outcomes.get(slot_id)
                or ("FAIL" not in outcomes[slot_id] and "UNKNOWN" in outcomes[slot_id])
                for slot_id in settled
            )
        return EvaluationRun(
            run_id=run_id,
            status=row["status"],
            stage=row["stage"],
            planned=len(row["plan"]["slots"]),
            settled=len(settled),
            unknown=unknown,
            latest_report_id=report_id,
            cancel_requested=row["cancel_requested"],
        )

    def cancel(self, run_id: UUID, reason: str, actor: str) -> EvaluationRun:
        self.row(run_id)
        with self.db.begin() as connection:
            connection.execute(
                update(runs).where(runs.c.id == run_id).values(cancel_requested=True)
            )
            self.identity.audit(connection, actor, "evaluation.cancel", run_id, {"reason": reason})
        return self.view(run_id)

    def observations(self, run_id: UUID) -> list[Observation]:
        self.row(run_id)
        with self.db.connect() as connection:
            return [
                Observation.model_validate(body)
                for body in connection.execute(
                    select(observations.c.body)
                    .join(case_slots, observations.c.slot_fk == case_slots.c.id)
                    .where(case_slots.c.run_fk == run_id)
                    .order_by(observations.c.created_at)
                ).scalars()
            ]
