"""API input/output contracts; callers cannot supply scores, RPC URLs or clocks."""

from typing import Literal, Self

from pydantic import UUID4, Field, JsonValue, model_serializer, model_validator

from .base import Challenge, Hash32, Model, NonzeroAddress, SafeText, Timestamp
from .domain import AccessGrant, AgentRef, BindingMessage, Capability, Profile, SourceType
from .enums import JobStatus, RunStatus
from .public_identity import PublicIdentityRead


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
    public_identity: PublicIdentityRead | None = None


class ClaimsConfirm(Model):
    confirmed_claims: tuple[Capability, ...] = Field(min_length=1)
    unsupported_claims: tuple[SafeText, ...] = ()
    reason: SafeText
    expected_review_version: int = Field(strict=True, ge=0)
    excluded_capabilities: tuple[Capability, ...] = ()

    @model_validator(mode="after")
    def unique_claims(self) -> Self:
        if len(set(self.confirmed_claims)) != len(self.confirmed_claims):
            raise ValueError("duplicate confirmed capability")
        if len(set(self.excluded_capabilities)) != len(self.excluded_capabilities) or (
            set(self.confirmed_claims) & set(self.excluded_capabilities)
        ):
            raise ValueError(
                "excluded capabilities must be unique and disjoint from confirmed claims"
            )
        return self


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
    suite_id: Literal["m1-smoke-v1", "capabilities-v1", "formal-evaluation-v1"]
    capability_id: Capability = "anchor_record"
    query_tx_hash: Hash32 | None = None
    target_contract: NonzeroAddress | None = None
    record_executor: NonzeroAddress | None = None
    record_request_id: Challenge | None = None
    record_hash: Challenge | None = None
    transaction_cases: dict[Literal["success", "revert", "pending"], Hash32] | None = None

    @model_serializer(mode="wrap")
    def wire(self, handler):
        value = handler(self)
        if self.transaction_cases is None:
            value.pop("transaction_cases", None)
        if self.suite_id == "m1-smoke-v1" and self.capability_id == "anchor_record":
            value.pop("capability_id", None)
            for name in (
                "query_tx_hash",
                "target_contract",
                "record_executor",
                "record_request_id",
                "record_hash",
            ):
                if value.get(name) is None:
                    value.pop(name, None)
        return value

    @model_validator(mode="after")
    def capability_inputs(self) -> Self:
        if self.suite_id == "formal-evaluation-v1":
            if (
                self.query_tx_hash is not None
                or len(
                    {
                        value is None
                        for value in (
                            self.record_executor,
                            self.record_request_id,
                            self.record_hash,
                        )
                    }
                )
                != 1
            ):
                raise ValueError(
                    "formal evaluation requires complete record source parameters and transaction_cases"
                )
            return self
        if self.transaction_cases is not None:
            raise ValueError("transaction_cases are only accepted by formal evaluation")
        if (self.capability_id == "anchor_record") != (self.profile == "record-write-v1"):
            raise ValueError(
                "single-capability runs require the corresponding read or write profile"
            )
        if self.capability_id == "get_tx_status":
            if self.query_tx_hash is None or any(
                value is not None
                for value in (
                    self.target_contract,
                    self.record_executor,
                    self.record_request_id,
                    self.record_hash,
                )
            ):
                raise ValueError("get_tx_status requires only query_tx_hash")
        elif self.capability_id == "verify_record":
            if (
                any(
                    value is None
                    for value in (self.record_executor, self.record_request_id, self.record_hash)
                )
                or self.query_tx_hash is not None
            ):
                raise ValueError("verify_record requires executor, request and expected hash")
        elif any(
            value is not None
            for value in (
                self.query_tx_hash,
                self.record_executor,
                self.record_request_id,
                self.record_hash,
            )
        ):
            raise ValueError("anchor_record uses a fresh synthetic record")
        if self.suite_id == "m1-smoke-v1" and self.capability_id != "anchor_record":
            raise ValueError("m1-smoke-v1 only supports anchor_record")
        return self


class AccessGrantCreate(Model):
    snapshot_id: UUID4
    endpoint_id: str = Field(min_length=1, max_length=100)
    max_tasks: int = Field(strict=True, ge=1, le=100)
    interval_ms: int = Field(strict=True, ge=1000, le=60000, default=1000)
    expires_at: Timestamp
    consent_ref: SafeText
    capabilities: tuple[Capability, ...] = Field(default=("anchor_record",), min_length=1)
    contract_allowlist: tuple[NonzeroAddress, ...] | None = None

    @model_validator(mode="after")
    def unique_scope(self) -> Self:
        if len(set(self.capabilities)) != len(self.capabilities):
            raise ValueError("duplicate granted capability")
        if self.contract_allowlist is not None and (
            len(set(self.contract_allowlist)) != len(self.contract_allowlist)
            or (
                not self.contract_allowlist and any(c != "get_tx_status" for c in self.capabilities)
            )
        ):
            raise ValueError("record capabilities require a unique nonempty contract allowlist")
        return self


class GrantView(Model):
    grant: AccessGrant
    revoked: bool


class ReasonRequest(Model):
    reason: SafeText


class AcceptedEvaluation(Model):
    run_id: UUID4
    status: RunStatus = RunStatus.QUEUED
    status_url: str


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
