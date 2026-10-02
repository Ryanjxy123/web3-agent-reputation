"""API input/output contracts; callers cannot supply scores, RPC URLs or clocks."""
from typing import Literal

from pydantic import UUID4, Field, JsonValue

from .base import Hash32, Model, NonzeroAddress, SafeText
from .domain import AgentRef, BindingMessage, Capability, Profile, SourceType
from .enums import JobStatus


class AgentCreate(Model):
    agent_ref: AgentRef


class AgentView(Model):
    id: UUID4
    agent_ref: AgentRef
    source_type: SourceType
    status: Literal["UNVERIFIED", "SNAPSHOT_CAPTURED"] = "UNVERIFIED"
    current_snapshot_id: UUID4 | None = None


class JobView(Model):
    id: UUID4
    state: JobStatus
    reason_code: str | None = None
    snapshot_id: UUID4 | None = None


class ClaimsConfirm(Model):
    confirmed_claims: tuple[Capability, ...] = Field(min_length=1)
    unsupported_claims: tuple[SafeText, ...] = ()
    reason: SafeText
    expected_review_version: int = Field(strict=True, ge=0)


class BindingChallengeRequest(Model):
    executor: NonzeroAddress
    endpoint_id: str = Field(min_length=1, max_length=100)
    execution_chain_key: Literal["local-demo"]


class BindingVerifyRequest(Model):
    challenge_id: UUID4
    owner_signature: str = Field(pattern=r"^0x[0-9a-f]{130}$")
    executor_signature: str = Field(pattern=r"^0x[0-9a-f]{130}$")


class BindingChallengeView(Model):
    challenge_id: UUID4
    message: BindingMessage
    owner_typed_data: dict[str, JsonValue]
    executor_typed_data: dict[str, JsonValue]
    scope: Literal["local-demo-eoa-only"] = "local-demo-eoa-only"


class EvaluationCreate(Model):
    snapshot_id: UUID4
    review_version: int = Field(strict=True, ge=1)
    profile: Profile
    policy_version: Literal["policy-v1"]
    grant_ids: tuple[UUID4, ...] = Field(min_length=1, max_length=10)
    suite_id: Literal["m1-smoke-v1"]


class RefreshRequest(Model):
    expected_snapshot_hash: Hash32 | None = None


class AcceptedJob(Model):
    job_id: UUID4
    status: Literal["QUEUED"] = "QUEUED"
    status_url: str = Field(pattern=r"^/api/v1/[a-z/-]+[0-9a-f-]+$")


class ErrorDetail(Model):
    code: str = Field(min_length=1, max_length=100)
    message: SafeText
    request_id: UUID4
    retryable: bool = Field(strict=True)


class ApiError(Model):
    error: ErrorDetail
