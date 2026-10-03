"""Replayable verification inputs: frozen context and raw JSON-RPC result values."""

from typing import Literal

from pydantic import Field, JsonValue

from .base import Hash32, Model, Timestamp
from .domain import (
    AccessGrant,
    AgentSnapshot,
    AssertionResult,
    CaseSlot,
    ClaimReview,
    ExecutorBinding,
    SnapshotCore,
    TaskLink,
)
from .enums import Outcome, Reason


class RegistryWitness(Model):
    snapshot_core: SnapshotCore
    owner_code: str
    executor_code: str
    read_method: Literal["eth_call_at_block_number"]


class EvmReadEvidence(Model):
    schema_version: Literal["evm-task-evidence-v1"] = "evm-task-evidence-v1"
    candidate_tx_hash: Hash32 | None
    observed_at: Timestamp
    results: dict[str, JsonValue]
    error_reason: Reason | None = None


class RecordVerificationInput(Model):
    schema_version: Literal["record-verification-input-v1"] = "record-verification-input-v1"
    slot: CaseSlot
    snapshot: AgentSnapshot
    review: ClaimReview
    review_version: int = Field(strict=True, ge=1)
    platform_instance_id: Hash32
    binding: ExecutorBinding | None
    grant: AccessGrant | None
    intent_persisted_at: Timestamp
    dispatch_started_at: Timestamp | None
    dispatch_payload_hash: Hash32 | None
    registry_witness: RegistryWitness | None
    execution_reason: Reason | None
    evm: EvmReadEvidence


class RecordVerificationResult(Model):
    assertions: tuple[AssertionResult, ...]
    task_link: TaskLink
    outcome: Outcome
    reason_code: Reason | None
    critical_conflict: bool
