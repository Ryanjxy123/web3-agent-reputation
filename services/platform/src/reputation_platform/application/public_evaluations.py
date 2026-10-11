"""Explicit consent and five frozen queries for the fixed free public adapter."""

import secrets
from datetime import UTC, datetime, timedelta
from typing import Literal
from uuid import uuid4

from reputation_core.evidence import hash_json, strict_json
from reputation_core.models import AcceptedEvaluation, ClaimReview, Outcome, Purpose
from reputation_core.models.public_evaluation import (
    KNOWN_TX,
    PublicReadonlyCaseSlot,
    PublicReadonlyEvaluationCreate,
    PublicReadonlyExpectedFacts,
    PublicReadonlyGrant,
    PublicReadonlyGrantCreate,
    PublicReadonlyGrantView,
    PublicReadonlyRunPlan,
    PublicReadonlyTask,
)
from reputation_core.models.public_identity import PublicReadonlyProtocol
from sqlalchemy import func, insert, select

from reputation_platform.infrastructure.db.jobs import persist_plan
from reputation_platform.infrastructure.db.tables import (
    access_grants,
    case_slots,
    claim_reviews,
    grant_revocations,
    runs,
    snapshots,
)

from .errors import ApplicationError
from .evaluations import EvaluationService, utc_text


class PublicReadonlyEvaluationService:
    def __init__(self, db, identity):
        self.db, self.identity = db, identity

    def require_enabled(self):
        if not self.identity.public_readonly_enabled:
            raise ApplicationError(
                409, "PUBLIC_READONLY_DISABLED", "Public readonly access is disabled."
            )

    def association(self, snapshot_id, protocol):
        self.require_enabled()
        snapshot = self.identity.snapshot(snapshot_id)
        association = self.identity.readonly_association(snapshot_id, protocol)
        if (
            snapshot.public_identity is None
            or association.registration_outcome != Outcome.PASS
            or association.endpoint_outcome != Outcome.PASS
        ):
            raise ApplicationError(
                409,
                "PUBLIC_IDENTITY_UNVERIFIED",
                "Public registration and endpoint must be verified.",
            )
        return snapshot

    @staticmethod
    def require_grant(connection, grant_id, snapshot_hash, now):
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
        if (
            row is None
            or revoked
            or row["expires_at"] <= now
            or row["body"].get("schema_version") != "public-readonly-grant-v1"
        ):
            raise ApplicationError(
                409, "ACCESS_NOT_GRANTED", "Public grant is absent, revoked or expired."
            )
        grant = PublicReadonlyGrant.model_validate(row["body"])
        if grant.snapshot_hash != snapshot_hash:
            raise ApplicationError(
                409, "ACCESS_NOT_GRANTED", "Grant belongs to a different snapshot."
            )
        return grant

    def create_grant(self, request: PublicReadonlyGrantCreate, actor: str):
        protocol: PublicReadonlyProtocol = (
            "akashi-http-readonly-v1"
            if request.endpoint_id == "akashi-http"
            else "akashi-mcp-readonly-v1"
        )
        snapshot = self.association(request.snapshot_id, protocol)
        expiry, now = datetime.fromisoformat(request.expires_at), datetime.now(UTC)
        if not now < expiry <= now + timedelta(hours=24):
            raise ApplicationError(
                422, "ACCESS_NOT_GRANTED", "Public grants must expire within 24 hours."
            )
        grant = PublicReadonlyGrant(
            protocol=protocol,
            grant_id=uuid4(),
            snapshot_hash=snapshot.snapshot_hash,
            endpoint_ids=(request.endpoint_id,),
            methods=("GET",) if request.endpoint_id == "akashi-http" else ("POST",),
            paths=("/proof",) if request.endpoint_id == "akashi-http" else ("/mcp",),
            chain_instances=(snapshot.core.registry_chain.instance_hash,),
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
                "public.grant.create",
                grant.grant_id,
                {"snapshot_id": str(request.snapshot_id)},
            )
        return PublicReadonlyGrantView(grant=grant, revoked=False)

    def create(self, request: PublicReadonlyEvaluationCreate, key: str, actor: str):
        if (
            not 1 <= len(key) <= 200
            or not key.isascii()
            or any(ord(char) < 33 or ord(char) > 126 for char in key)
        ):
            raise ApplicationError(
                422,
                "IDEMPOTENCY_KEY_REQUIRED",
                "Use a printable Idempotency-Key of at most 200 characters.",
            )
        payload_hash = hash_json(request.model_dump(mode="json"))
        with self.db.connect() as connection:
            existing = EvaluationService.existing(connection, actor, key, payload_hash)
        if existing is not None:
            return EvaluationService.accepted(existing)
        snapshot = self.association(request.snapshot_id, "akashi-http-readonly-v1")
        self.association(request.snapshot_id, "akashi-mcp-readonly-v1")
        now = datetime.now(UTC)
        with self.db.begin() as connection:
            self.identity.require_current(connection, request.snapshot_id)
            existing = EvaluationService.existing(connection, actor, key, payload_hash)
            if existing is not None:
                return EvaluationService.accepted(existing)
            agent_id = connection.scalar(
                select(snapshots.c.agent_fk).where(snapshots.c.id == request.snapshot_id)
            )
            if connection.execute(
                select(runs.c.id)
                .join(snapshots, snapshots.c.id == runs.c.snapshot_fk)
                .where(snapshots.c.agent_fk == agent_id, runs.c.status.in_(["QUEUED", "RUNNING"]))
                .limit(1)
            ).first():
                raise ApplicationError(409, "AGENT_BUSY", "This Agent already has an active run.")
            body = connection.scalar(
                select(claim_reviews.c.body)
                .where(claim_reviews.c.snapshot_fk == request.snapshot_id)
                .order_by(claim_reviews.c.review_version.desc())
                .limit(1)
            )
            if body is None:
                raise ApplicationError(
                    409, "MAPPING_UNCONFIRMED", "Capability mapping is not confirmed."
                )
            review = ClaimReview.model_validate(body)
            if review.review_version != request.review_version or review.confirmed_claims != (
                "verify_record",
            ):
                raise ApplicationError(
                    409,
                    "REVIEW_CONFLICT",
                    "The current confirmed mapping must contain only verify_record.",
                )
            grants = [
                self.require_grant(connection, gid, snapshot.snapshot_hash, now)
                for gid in sorted(request.grant_ids, key=str)
            ]
            by_endpoint = {grant.endpoint_ids[0]: grant for grant in grants}
            if set(by_endpoint) != {"akashi-http", "akashi-mcp"}:
                raise ApplicationError(
                    409, "ACCESS_NOT_GRANTED", "Separate HTTP and MCP consent is required."
                )
            # The window covers finite MCP negotiation and independent reads without retries.
            deadline = now + timedelta(
                seconds=120 + 64 * (20 + max(g.interval_ms for g in grants) / 1000)
            )
            for endpoint, required in (("akashi-http", 4), ("akashi-mcp", 1)):
                grant = by_endpoint[endpoint]
                reserved = (
                    connection.scalar(
                        select(func.count())
                        .select_from(case_slots)
                        .where(case_slots.c.body["grant_id"].astext == str(grant.grant_id))
                    )
                    or 0
                )
                if reserved + required > grant.max_tasks:
                    raise ApplicationError(
                        409, "GRANT_QUOTA_EXHAUSTED", "Public task quota has already been reserved."
                    )
                if datetime.fromisoformat(grant.expires_at) < deadline or grant.chain_instances != (
                    snapshot.core.registry_chain.instance_hash,
                ):
                    raise ApplicationError(
                        409,
                        "ACCESS_NOT_GRANTED",
                        "Grant must cover the frozen chain and complete query window.",
                    )
            specs: tuple[
                tuple[
                    Literal["akashi-http", "akashi-mcp"],
                    Purpose,
                    dict[str, str],
                    Literal["match", "not_found", "invalid_format"],
                ],
                ...,
            ] = (
                ("akashi-http", Purpose.FUNCTIONAL, {"tx": KNOWN_TX}, "match"),
                ("akashi-http", Purpose.AVAILABILITY, {"tx": KNOWN_TX}, "match"),
                ("akashi-http", Purpose.FUNCTIONAL, {"hash": secrets.token_hex(32)}, "not_found"),
                ("akashi-http", Purpose.FUNCTIONAL, {"hash": "not-a-sha256"}, "invalid_format"),
                ("akashi-mcp", Purpose.FUNCTIONAL, {"tx": KNOWN_TX}, "match"),
            )
            slots = []
            for index, (endpoint, purpose, query, case) in enumerate(specs, 1):
                grant, challenge = by_endpoint[endpoint], "0x" + secrets.token_hex(32)
                task = PublicReadonlyTask(
                    protocol=grant.protocol,
                    request_id=challenge,
                    snapshot_hash=snapshot.snapshot_hash,
                    chain_instance_id=snapshot.core.registry_chain.instance_hash,
                    endpoint_id=endpoint,
                    query=query,
                    read_block_number=snapshot.core.read_block_number,
                    read_block_hash=snapshot.core.read_block_hash,
                    deadline=utc_text(deadline),
                )
                facts = PublicReadonlyExpectedFacts(
                    agent_ref=snapshot.core.agent_ref,
                    snapshot_hash=snapshot.snapshot_hash,
                    execution_chain=snapshot.core.registry_chain,
                    request_id=challenge,
                    window_start=utc_text(now),
                    deadline=task.deadline,
                    pre_dispatch_block=task.read_block_number,
                    pre_dispatch_block_hash=task.read_block_hash,
                    protocol=task.protocol,
                    endpoint_id=endpoint,
                    query=query,
                )
                slots.append(
                    PublicReadonlyCaseSlot(
                        slot_id=uuid4(),
                        slot_key=f"public-query-{index}",
                        purpose=purpose,
                        case_kind="negative" if case == "invalid_format" else "positive",
                        required_class=case,
                        expected_outcome=Outcome.UNKNOWN if case == "not_found" else Outcome.PASS,
                        task=task,
                        expected=facts,
                        grant_id=grant.grant_id,
                    )
                )
            policy = strict_json(
                (self.identity.root / "configs/policies/policy-v1.json").read_bytes()
            )
            plan = PublicReadonlyRunPlan(
                run_id=uuid4(),
                snapshot_hash=snapshot.snapshot_hash,
                review_version=review.review_version,
                policy_hash=hash_json(policy),
                planning_time=utc_text(now),
                slots=tuple(slots),
            )
            persist_plan(connection, request.snapshot_id, actor, key, payload_hash, plan)
            self.identity.audit(
                connection,
                actor,
                "public.evaluation.create",
                plan.run_id,
                {"request_hash": payload_hash},
            )
        return AcceptedEvaluation(
            run_id=plan.run_id, status_url=f"/api/v1/evaluations/{plan.run_id}"
        )
