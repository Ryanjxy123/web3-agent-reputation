"""Immutable snapshots, reviewed claims and single-use dual-signature local bindings."""

import asyncio
import os
import secrets
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

from reputation_core.binding import agent_key_hash, endpoint_hash, signatures_match, typed_data
from reputation_core.evidence import hash_json
from reputation_core.models import (
    AcceptedJob,
    AgentRef,
    AgentSnapshot,
    AgentView,
    BindingChallengeRequest,
    BindingChallengeView,
    BindingMessage,
    BindingVerifyRequest,
    ClaimReview,
    ClaimsConfirm,
    ExecutorBinding,
    LocalDeployment,
    Reason,
    RefreshRequest,
)
from sqlalchemy import Connection, Engine, insert, select, update

from reputation_platform.adapters.registries.demo import DemoRegistryReader
from reputation_platform.infrastructure.db.connection import repo_root
from reputation_platform.infrastructure.db.jobs import JobQueue, Lease, enqueue
from reputation_platform.infrastructure.db.tables import (
    agents,
    audit_logs,
    binding_challenges,
    bindings,
    claim_reviews,
    jobs,
    snapshots,
)
from reputation_platform.infrastructure.evidence_store import EvidenceStore

from .errors import ApplicationError


class IdentityService:
    def __init__(
        self,
        database: Engine,
        deployment: LocalDeployment | None = None,
        evidence_root: Path | None = None,
    ):
        self.db, self._deployment = database, deployment
        self.root = repo_root()
        self.evidence = EvidenceStore(
            evidence_root or Path(os.environ.get("EVIDENCE_ROOT", self.root / "runtime/evidence"))
        )

    def deployment(self) -> LocalDeployment:
        if self._deployment is not None:
            return self._deployment
        path = Path(
            os.environ.get("LOCAL_CHAIN_CONFIG", self.root / "runtime/local-chain/deployment.json")
        )
        try:
            return LocalDeployment.model_validate_json(path.read_bytes())
        except (OSError, ValueError):
            raise ApplicationError(
                503,
                "LOCAL_CHAIN_NOT_CONFIGURED",
                "Trusted local deployment configuration is required.",
            ) from None

    def source_type(self, ref: AgentRef) -> str:
        try:
            config = self.deployment()
        except ApplicationError:
            return "public_registry"
        return (
            "controlled"
            if ref.chain_id == config.chain.chain_id
            and ref.registry_address == config.registry.address
            else "public_registry"
        )

    @staticmethod
    def latest(connection: Connection, agent_id: UUID):
        return (
            connection.execute(
                select(snapshots)
                .where(snapshots.c.agent_fk == agent_id)
                .order_by(snapshots.c.created_at.desc(), snapshots.c.id.desc())
                .limit(1)
            )
            .mappings()
            .first()
        )

    def agent(self, agent_id: UUID) -> AgentView:
        with self.db.connect() as connection:
            row = (
                connection.execute(select(agents).where(agents.c.id == agent_id)).mappings().first()
            )
            current = self.latest(connection, agent_id)
        if row is None:
            raise ApplicationError(404, "NOT_FOUND", "Agent does not exist.")
        return AgentView(
            id=row["id"],
            agent_ref=AgentRef(
                **{
                    key: row[key]
                    for key in ("namespace", "chain_id", "registry_address", "agent_id")
                }
            ),
            source_type=row["source_type"],
            status="SNAPSHOT_CAPTURED" if current else "UNVERIFIED",
            current_snapshot_id=current["id"] if current else None,
        )

    def refresh(self, agent_id: UUID, request: RefreshRequest, actor: str) -> AcceptedJob:
        self.agent(agent_id)
        with self.db.begin() as connection:
            current = self.latest(connection, agent_id)
            if request.expected_snapshot_hash is not None and (
                current is None or current["snapshot_hash"] != request.expected_snapshot_hash
            ):
                raise ApplicationError(
                    409, "SNAPSHOT_CONFLICT", "Current snapshot differs from the expected version."
                )
            job_id = enqueue(
                connection,
                "ingest",
                f"ingest:{uuid4()}",
                {
                    "agent_id": str(agent_id),
                    "actor": actor,
                    "expected_snapshot_hash": current["snapshot_hash"] if current else None,
                },
            )
        return AcceptedJob(job_id=job_id, status_url=f"/api/v1/jobs/{job_id}")

    async def ingest(self, lease: Lease, queue: JobQueue) -> None:
        await asyncio.to_thread(self._ingest, lease, queue)

    def _ingest(self, lease: Lease, queue: JobQueue) -> None:
        # A commit-before-complete crash reclaims the saved result, never another snapshot.
        with self.db.connect() as connection:
            payload = connection.execute(
                select(jobs.c.payload).where(jobs.c.id == lease.job_id)
            ).scalar_one()
        if payload.get("snapshot_id"):
            return
        agent = self.agent(UUID(payload["agent_id"]))
        core, observation = DemoRegistryReader(self.root, self.deployment()).read(agent.agent_ref)
        record = self.evidence.prepare_json(
            observation, "demo-registry", core.captured_at, "local-rpc"
        )

        def save(connection: Connection):
            connection.execute(
                select(agents.c.id).where(agents.c.id == agent.id).with_for_update()
            ).one()
            current = self.latest(connection, agent.id)
            if (current["snapshot_hash"] if current else None) != payload["expected_snapshot_hash"]:
                raise ApplicationError(409, "SNAPSHOT_CONFLICT", "Another refresh committed first.")
            evidence = self.evidence.register(connection, record)
            snapshot = AgentSnapshot(
                snapshot_id=uuid4(),
                core=core,
                snapshot_hash=hash_json(core.model_dump(mode="json")),
                evidence_refs=(evidence.evidence_id,),
            )
            connection.execute(
                insert(snapshots).values(
                    id=snapshot.snapshot_id,
                    agent_fk=agent.id,
                    snapshot_hash=snapshot.snapshot_hash,
                    body=snapshot.model_dump(mode="json"),
                )
            )
            connection.execute(
                update(jobs)
                .where(jobs.c.id == lease.job_id)
                .values(payload={**payload, "snapshot_id": str(snapshot.snapshot_id)})
            )
            self.audit(
                connection,
                payload["actor"],
                "snapshot.capture",
                snapshot.snapshot_id,
                {"job_id": str(lease.job_id), "snapshot_hash": snapshot.snapshot_hash},
            )

        queue.fenced(lease, save)

    def snapshot(self, snapshot_id: UUID) -> AgentSnapshot:
        with self.db.connect() as connection:
            body = connection.execute(
                select(snapshots.c.body).where(snapshots.c.id == snapshot_id)
            ).scalar_one_or_none()
        if body is None:
            raise ApplicationError(404, "NOT_FOUND", "Snapshot does not exist.")
        return AgentSnapshot.model_validate(body)

    def require_current(self, connection: Connection, snapshot_id: UUID) -> None:
        agent_id = connection.execute(
            select(snapshots.c.agent_fk).where(snapshots.c.id == snapshot_id)
        ).scalar_one()
        connection.execute(
            select(agents.c.id).where(agents.c.id == agent_id).with_for_update()
        ).one()
        if self.latest(connection, agent_id)["id"] != snapshot_id:
            raise ApplicationError(
                409, "STALE_SNAPSHOT", "Refresh invalidated this snapshot for new operations."
            )

    @staticmethod
    def audit(connection: Connection, actor: str, action: str, target: UUID, body: dict) -> None:
        connection.execute(
            insert(audit_logs).values(actor=actor, action=action, target=target, body=body)
        )

    def confirm(self, snapshot_id: UUID, request: ClaimsConfirm, actor: str) -> ClaimReview:
        snapshot = self.snapshot(snapshot_id)
        claims = snapshot.core.normalized_metadata["capabilities"]
        if (
            request.confirmed_claims != ("anchor_record",)
            or not isinstance(claims, list)
            or "anchor_record" not in claims
        ):
            raise ApplicationError(
                422, "UNSUPPORTED_CLAIM", "M1 confirms only a declared anchor_record capability."
            )
        with self.db.begin() as connection:
            self.require_current(connection, snapshot_id)
            version = (
                connection.execute(
                    select(claim_reviews.c.review_version)
                    .where(claim_reviews.c.snapshot_fk == snapshot_id)
                    .order_by(claim_reviews.c.review_version.desc())
                    .limit(1)
                ).scalar_one_or_none()
                or 0
            )
            if version != request.expected_review_version:
                raise ApplicationError(409, "REVIEW_CONFLICT", "Claim review version changed.")
            review = ClaimReview(
                snapshot_hash=snapshot.snapshot_hash,
                review_version=version + 1,
                confirmed_claims=request.confirmed_claims,
                unsupported_claims=request.unsupported_claims,
                mapping_evidence_ids=snapshot.evidence_refs,
                actor=actor,
                reason=request.reason,
            )
            connection.execute(
                insert(claim_reviews).values(
                    snapshot_fk=snapshot_id,
                    review_version=review.review_version,
                    body=review.model_dump(mode="json"),
                )
            )
            self.audit(
                connection,
                actor,
                "claims.confirm",
                snapshot_id,
                {"review_version": review.review_version},
            )
        return review

    def current_identity(self, snapshot: AgentSnapshot) -> tuple[dict, LocalDeployment]:
        config = self.deployment()
        core, observation = DemoRegistryReader(self.root, config).read(snapshot.core.agent_ref)
        excluded = {"captured_at", "read_block_number", "read_block_hash"}
        if core.model_dump(exclude=excluded) != snapshot.core.model_dump(exclude=excluded):
            raise ApplicationError(
                409,
                "IDENTITY_CHANGED",
                "Registry identity changed; capture and review a new snapshot.",
            )
        return observation, config

    def challenge(
        self, snapshot_id: UUID, request: BindingChallengeRequest, actor: str
    ) -> BindingChallengeView:
        snapshot = self.snapshot(snapshot_id)
        endpoint = next(
            (item for item in snapshot.core.endpoints if item.endpoint_id == request.endpoint_id),
            None,
        )
        if endpoint is None or request.executor != snapshot.core.declared_executor:
            raise ApplicationError(
                409, "BINDING_CONTEXT_MISMATCH", "Executor or endpoint differs from the snapshot."
            )
        _, config = self.current_identity(snapshot)
        now = int(datetime.now(UTC).timestamp())
        message = BindingMessage(
            agent_key_hash=agent_key_hash(snapshot.core.agent_ref),
            snapshot_hash=snapshot.snapshot_hash,
            executor=request.executor,
            endpoint_hash=endpoint_hash(endpoint),
            execution_chain_id=config.chain.chain_id,
            execution_chain_instance_hash=config.chain.instance_hash,
            nonce="0x" + secrets.token_hex(32),
            issued_at=now,
            deadline=now + 300,
        )
        challenge_id = uuid4()
        domain = (config.chain.chain_id, config.registry.address, config.platform_instance_id)
        view = BindingChallengeView(
            challenge_id=challenge_id,
            message=message,
            owner_typed_data=typed_data(message, *domain, 1),
            executor_typed_data=typed_data(message, *domain, 2),
        )
        with self.db.begin() as connection:
            self.require_current(connection, snapshot_id)
            review = connection.execute(
                select(claim_reviews.c.id)
                .where(claim_reviews.c.snapshot_fk == snapshot_id)
                .limit(1)
            ).first()
            if review is None:
                raise ApplicationError(
                    409, "CLAIMS_UNCONFIRMED", "Confirm the snapshot capability first."
                )
            connection.execute(
                insert(binding_challenges).values(
                    id=challenge_id,
                    snapshot_fk=snapshot_id,
                    nonce=message.nonce,
                    deadline=datetime.fromtimestamp(message.deadline, UTC),
                    body=view.model_dump(mode="json"),
                )
            )
            self.audit(
                connection,
                actor,
                "binding.challenge",
                snapshot_id,
                {"challenge_id": str(challenge_id)},
            )
        return view

    def verify(
        self, snapshot_id: UUID, request: BindingVerifyRequest, actor: str
    ) -> ExecutorBinding:
        snapshot = self.snapshot(snapshot_id)
        with self.db.connect() as connection:
            row = (
                connection.execute(
                    select(binding_challenges).where(
                        binding_challenges.c.id == request.challenge_id
                    )
                )
                .mappings()
                .first()
            )
        self.check_challenge(row, snapshot_id)
        assert row is not None
        challenge = BindingChallengeView.model_validate(row["body"])
        observation, config = self.current_identity(snapshot)
        domain = challenge.owner_typed_data["domain"]
        if (
            domain
            != typed_data(
                challenge.message,
                config.chain.chain_id,
                config.registry.address,
                config.platform_instance_id,
                1,
            )["domain"]
        ):
            raise ApplicationError(
                409, "BINDING_CONTEXT_MISMATCH", "Binding domain configuration changed."
            )
        supported = observation["owner_code"] == "0x" and observation["executor_code"] == "0x"
        proof = ExecutorBinding(
            binding_id=uuid4(),
            message=challenge.message,
            owner=snapshot.core.owner,
            owner_signature=request.owner_signature,
            executor_signature=request.executor_signature,
            domain_chain_id=config.chain.chain_id,
            domain_registry=config.registry.address,
            domain_salt=config.platform_instance_id,
            status="VERIFIED" if supported else "UNKNOWN",
            reason_code=None if supported else Reason.BINDING_UNVERIFIED,
            verification_evidence=(),
        )
        if supported and not signatures_match(proof):
            raise ApplicationError(
                422,
                "SIGNATURE_INVALID",
                "Both role-specific signatures must match the captured identity.",
            )
        record = self.evidence.prepare_json(
            observation,
            "binding-registry-read",
            observation["snapshot_core"]["captured_at"],
            "local-rpc",
        )
        with self.db.begin() as connection:
            self.require_current(connection, snapshot_id)
            locked = (
                connection.execute(
                    select(binding_challenges)
                    .where(binding_challenges.c.id == request.challenge_id)
                    .with_for_update()
                )
                .mappings()
                .one()
            )
            self.check_challenge(locked, snapshot_id)
            evidence = self.evidence.register(connection, record)
            proof = proof.model_copy(
                update={"verification_evidence": (*snapshot.evidence_refs, evidence.evidence_id)}
            )
            connection.execute(
                update(binding_challenges)
                .where(binding_challenges.c.id == request.challenge_id)
                .values(consumed_at=datetime.now(UTC))
            )
            connection.execute(
                insert(bindings).values(
                    id=proof.binding_id,
                    snapshot_fk=snapshot_id,
                    executor=proof.message.executor,
                    proof_hash=hash_json(proof.model_dump(mode="json")),
                    body=proof.model_dump(mode="json"),
                )
            )
            self.audit(
                connection,
                actor,
                "binding.verify",
                proof.binding_id,
                {"status": proof.status, "challenge_id": str(request.challenge_id)},
            )
        return proof

    @staticmethod
    def check_challenge(row, snapshot_id: UUID) -> None:
        if row is None or row["snapshot_fk"] != snapshot_id:
            raise ApplicationError(
                409, "BINDING_CONTEXT_MISMATCH", "Challenge does not belong to this snapshot."
            )
        if row["consumed_at"] is not None:
            raise ApplicationError(409, "NONCE_CONSUMED", "Challenge was already consumed.")
        if row["deadline"] <= datetime.now(UTC):
            raise ApplicationError(409, "NONCE_EXPIRED", "Challenge expired.")

    def proofs(self, snapshot_id: UUID) -> list[ExecutorBinding]:
        self.snapshot(snapshot_id)
        with self.db.connect() as connection:
            return [
                ExecutorBinding.model_validate(body)
                for body in connection.execute(
                    select(bindings.c.body)
                    .where(bindings.c.snapshot_fk == snapshot_id)
                    .order_by(bindings.c.created_at)
                ).scalars()
            ]
