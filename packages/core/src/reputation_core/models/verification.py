"""Replayable verification inputs: frozen context and raw JSON-RPC result values."""

from typing import Literal, Self

from pydantic import Field, JsonValue, model_serializer, model_validator

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
from .runtime import TaskResult


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
    rule_version: Literal["1", "2", "3", "4", "5", "6"] = "1"
    agent_http: dict[str, JsonValue] | None = None
    initial_agent_http: dict[str, JsonValue] | None = None
    agent_response: JsonValue = None
    agent_result: TaskResult | None = None
    agent_task_status: Literal["accepted", "running", "succeeded", "failed"] | None = None
    evm: EvmReadEvidence

    @model_serializer(mode="wrap")
    def wire(self, handler):
        value = handler(self)
        for name in (
            "agent_http", "initial_agent_http", "agent_response", "agent_result", "agent_task_status"
        ):
            if value.get(name) is None:
                value.pop(name, None)
        if self.rule_version == "1":
            value.pop("rule_version", None)
        return value


class RecordVerificationResult(Model):
    assertions: tuple[AssertionResult, ...]
    task_link: TaskLink
    outcome: Outcome
    reason_code: Reason | None
    critical_conflict: bool

    @model_validator(mode="after")
    def consistent(self) -> Self:
        if self.outcome != self.task_link.match_status:
            raise ValueError("task outcome and link must agree")
        if (self.outcome == Outcome.PASS) != (self.reason_code is None):
            raise ValueError("only PASS has no reason code")
        if self.critical_conflict and not any(
            item.critical and item.outcome == Outcome.FAIL for item in self.assertions
        ):
            raise ValueError("critical conflict requires a failed critical assertion")
        return self
