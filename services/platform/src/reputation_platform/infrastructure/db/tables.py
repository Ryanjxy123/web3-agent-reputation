"""Relational integrity around immutable versioned JSON documents."""

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID

metadata = MetaData(
    naming_convention={
        "ix": "ix_%(table_name)s_%(column_0_name)s",
        "uq": "uq_%(table_name)s_%(column_0_name)s",
        "ck": "ck_%(table_name)s_%(constraint_name)s",
        "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
        "pk": "pk_%(table_name)s",
    }
)


def table(name: str, *columns):
    return Table(
        name,
        metadata,
        Column(
            "id", UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
        ),
        Column(
            "created_at",
            DateTime(timezone=True),
            nullable=False,
            server_default=text("clock_timestamp()"),
        ),
        *columns,
    )


def fk(name: str, target: str, *, nullable: bool = False):
    return Column(
        name, UUID(as_uuid=True), ForeignKey(target, ondelete="RESTRICT"), nullable=nullable
    )


def body(name: str = "body"):
    return Column(name, JSONB, nullable=False)


agents = table(
    "agents",
    Column("namespace", String(16), nullable=False),
    Column("chain_id", String(78), nullable=False),
    Column("registry_address", String(42), nullable=False),
    Column("agent_id", String(78), nullable=False),
    Column("source_type", String(32), nullable=False),
    UniqueConstraint("namespace", "chain_id", "registry_address", "agent_id"),
    CheckConstraint("namespace = 'eip155'", name="namespace"),
    CheckConstraint(
        "chain_id ~ '^(0|[1-9][0-9]{0,77})$' AND chain_id::numeric < power(2::numeric,256)",
        name="chain_id",
    ),
    CheckConstraint(
        "agent_id ~ '^(0|[1-9][0-9]{0,77})$' AND agent_id::numeric < power(2::numeric,256)",
        name="agent_id",
    ),
    CheckConstraint("registry_address ~ '^0x[0-9a-f]{40}$'", name="registry_address"),
    CheckConstraint("source_type IN ('controlled','public_registry','replay')", name="source_type"),
)
candidates = table(
    "candidates",
    Column("source", Text, nullable=False),
    Column("external_id", Text, nullable=False),
    body(),
    UniqueConstraint("source", "external_id"),
)
snapshots = table(
    "snapshots",
    fk("agent_fk", "agents.id"),
    Column("snapshot_hash", String(66), nullable=False),
    body(),
    UniqueConstraint("agent_fk", "snapshot_hash"),
)
claim_reviews = table(
    "claim_reviews",
    fk("snapshot_fk", "snapshots.id"),
    Column("review_version", Integer, nullable=False),
    body(),
    UniqueConstraint("snapshot_fk", "review_version"),
    CheckConstraint("review_version > 0", name="version"),
)
binding_challenges = table(
    "binding_challenges",
    fk("snapshot_fk", "snapshots.id"),
    Column("nonce", String(66), nullable=False, unique=True),
    Column("deadline", DateTime(timezone=True), nullable=False),
    Column("consumed_at", DateTime(timezone=True)),
    body(),
)
bindings = table(
    "bindings",
    fk("snapshot_fk", "snapshots.id"),
    Column("executor", String(42), nullable=False),
    Column("proof_hash", String(66), nullable=False),
    body(),
    UniqueConstraint("snapshot_fk", "executor", "proof_hash"),
)
binding_events = table("binding_events", fk("binding_fk", "bindings.id"), body())
access_grants = table(
    "access_grants",
    fk("snapshot_fk", "snapshots.id"),
    Column("expires_at", DateTime(timezone=True), nullable=False),
    body(),
)
grant_revocations = table(
    "grant_revocations",
    fk("grant_fk", "access_grants.id"),
    Column("actor", Text, nullable=False),
    Column("reason", Text, nullable=False),
    UniqueConstraint("grant_fk"),
)
runs = table(
    "runs",
    fk("snapshot_fk", "snapshots.id"),
    Column("actor_id", Text, nullable=False),
    Column("idempotency_key", String(200), nullable=False),
    Column("request_payload_hash", String(66), nullable=False),
    body("plan"),
    Column("status", String(24), nullable=False, server_default="QUEUED"),
    Column("stage", String(24), nullable=False, server_default="PLANNING"),
    Column("cancel_requested", Boolean, nullable=False, server_default=text("false")),
    UniqueConstraint("actor_id", "idempotency_key"),
    CheckConstraint(
        "status IN ('QUEUED','RUNNING','PARTIAL','COMPLETED','FAILED','CANCELLED')", name="status"
    ),
)
jobs = table(
    "jobs",
    fk("run_fk", "runs.id", nullable=True),
    Column("kind", String(24), nullable=False),
    Column("dedup_key", Text, nullable=False, unique=True),
    body("payload"),
    Column("state", String(24), nullable=False, server_default="QUEUED"),
    Column(
        "available_at",
        DateTime(timezone=True),
        nullable=False,
        server_default=text("clock_timestamp()"),
    ),
    Column("lease_until", DateTime(timezone=True)),
    Column("lease_token", BigInteger, nullable=False, server_default="0"),
    Column("lease_owner", String(100)),
    Column("attempts", Integer, nullable=False, server_default="0"),
    Column("max_attempts", Integer, nullable=False, server_default="5"),
    Column("last_error", String(100)),
    CheckConstraint(
        "state IN ('QUEUED','LEASED','RETRY_WAIT','SUCCEEDED','FAILED','CANCELLED')", name="state"
    ),
    CheckConstraint("attempts >= 0 AND max_attempts > 0 AND lease_token >= 0", name="attempts"),
)
Index("ix_jobs_runnable", jobs.c.state, jobs.c.available_at, jobs.c.lease_until)
case_slots = table(
    "case_slots",
    fk("run_fk", "runs.id"),
    Column("slot_key", String(100), nullable=False),
    Column("request_id", String(66), nullable=False, unique=True),
    Column("purpose", String(24), nullable=False),
    body(),
    UniqueConstraint("run_fk", "slot_key"),
    CheckConstraint(
        "purpose IN ('availability','functional','behavioral','background')", name="purpose"
    ),
)
attempts = table(
    "attempts",
    fk("slot_fk", "case_slots.id"),
    Column("attempt_no", Integer, nullable=False),
    body(),
    UniqueConstraint("slot_fk", "attempt_no"),
    CheckConstraint("attempt_no > 0", name="number"),
)
dispatch_events = table(
    "dispatch_events",
    fk("slot_fk", "case_slots.id"),
    Column("state", String(32), nullable=False),
    Column("lease_token", BigInteger, nullable=False),
    body(),
)
observations = table("observations", fk("slot_fk", "case_slots.id"), body())
assertions = table("assertions", fk("slot_fk", "case_slots.id"), body())
task_links = table(
    "task_links",
    fk("slot_fk", "case_slots.id"),
    Column("chain_instance_id", String(66), nullable=False),
    Column("executor", String(42), nullable=True),
    Column("request_id", String(66), nullable=False),
    body(),
    UniqueConstraint("chain_instance_id", "executor", "request_id"),
    CheckConstraint(
        "executor IS NOT NULL OR COALESCE(("
        "body->'task_link'->>'completion_kind' = 'readonly-query' AND "
        "body->'task_link'->>'capability_id' = 'verify_record' AND "
        "body->'task_link'->'executor' = 'null'::jsonb AND "
        "body->'task_link'->'candidate_tx_hash' = 'null'::jsonb AND "
        "body->'task_link'->'verified_tx_hash' = 'null'::jsonb AND "
        "body->'task_link'->'log_index' = 'null'::jsonb), false)",
        name="public_readonly_executor",
    ),
)
Index("uq_task_links_public_request", task_links.c.chain_instance_id, task_links.c.request_id,
      unique=True, postgresql_where=task_links.c.executor.is_(None))
evidence_blobs = table(
    "evidence_blobs",
    Column("blob_hash", String(66), nullable=False, unique=True),
    Column("path", Text, nullable=False, unique=True),
    Column("byte_count", BigInteger, nullable=False),
    body(),
    CheckConstraint("byte_count >= 0", name="byte_count"),
    CheckConstraint("blob_hash ~ '^0x[0-9a-f]{64}$'", name="hash"),
    CheckConstraint("path = 'blobs/' || substring(blob_hash from 3) || '.bin'", name="path"),
)
reports = table(
    "reports",
    fk("run_fk", "runs.id"),
    Column("revision", Integer, nullable=False),
    Column("report_hash", String(66), nullable=False, unique=True),
    Column("previous_report_hash", String(66), nullable=False),
    body("core"),
    body("manifest"),
    UniqueConstraint("run_fk", "revision"),
    CheckConstraint("revision > 0", name="revision"),
)
evidence_manifest_items = table(
    "evidence_manifest_items",
    fk("report_fk", "reports.id"),
    fk("evidence_fk", "evidence_blobs.id"),
    body(),
    UniqueConstraint("report_fk", "evidence_fk"),
)
anchor_jobs = table(
    "anchor_jobs",
    fk("report_fk", "reports.id"),
    Column("chain_instance", String(66), nullable=False),
    Column("contract", String(42), nullable=False),
    Column("publisher", String(42), nullable=False),
    Column("report_hash", String(66), nullable=False),
    Column("state", String(24), nullable=False, server_default="QUEUED"),
    Column("nonce", BigInteger),
    Column("signed_tx_hash", String(66)),
    Column("signed_transaction", Text),  # Restricted outbox: NEVER exported.
    UniqueConstraint("chain_instance", "contract", "publisher", "report_hash"),
)
anchor_receipts = table("anchor_receipts", fk("anchor_job_fk", "anchor_jobs.id"), body())
signer_nonces = table(
    "signer_nonces",
    Column("chain_instance", String(66), nullable=False),
    Column("address", String(42), nullable=False),
    Column("next_nonce", BigInteger, nullable=False),
    UniqueConstraint("chain_instance", "address"),
    CheckConstraint("next_nonce >= 0", name="nonce"),
)
audit_logs = table(
    "audit_logs",
    Column("actor", Text, nullable=False),
    Column("action", Text, nullable=False),
    Column("target", UUID(as_uuid=True)),
    body(),
)
verification_jobs = table("verification_jobs", Column("status", String(24), nullable=False), body())

APPEND_ONLY = (
    "agents",
    "candidates",
    "snapshots",
    "claim_reviews",
    "bindings",
    "binding_events",
    "access_grants",
    "grant_revocations",
    "case_slots",
    "attempts",
    "dispatch_events",
    "observations",
    "assertions",
    "task_links",
    "evidence_blobs",
    "reports",
    "evidence_manifest_items",
    "anchor_receipts",
    "audit_logs",
)
