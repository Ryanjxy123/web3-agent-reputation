"""Frozen, versioned wire contracts. No implicit clock, random state, or I/O."""

from typing import Literal, Self

from pydantic import UUID4, Field, JsonValue, model_serializer, model_validator

from ..evidence import hash_json
from .base import (
    Address,
    BasisPoints,
    Challenge,
    Count,
    Hash32,
    Model,
    NonzeroAddress,
    SafeText,
    Timestamp,
    UInt256,
    Version,
)
from .enums import AnchorStatus, DispatchState, Outcome, Purpose, Reason, RunStage, RunStatus

Capability = Literal["get_tx_status", "verify_record", "anchor_record"]
Profile = Literal["record-read-v1", "record-write-v1"]
SourceType = Literal["controlled", "public_registry", "replay"]


class AgentRef(Model):
    namespace: Literal["eip155"] = "eip155"
    chain_id: UInt256
    registry_address: NonzeroAddress
    agent_id: UInt256

    @property
    def key_text(self) -> str:
        return f"{self.namespace}:{self.chain_id}:{self.registry_address}:{self.agent_id}"


class Endpoint(Model):
    endpoint_id: Version
    scheme: Literal["http", "https"]
    host: str = Field(pattern=r"^[a-z0-9][a-z0-9.-]{0,252}$")
    port: int = Field(strict=True, ge=1, le=65535)
    path: str = Field(pattern=r"^/[a-zA-Z0-9/_-]*$")
    method: Literal["POST"]
    protocol: Literal["controlled-http-v1"]

    @property
    def origin(self) -> str:
        return f"{self.scheme}://{self.host}:{self.port}"


class ChainIdentity(Model):
    chain_id: UInt256
    genesis_hash: Hash32
    deployment_instance_id: Challenge
    registry_code_hash: Hash32
    instance_hash: Hash32


class SnapshotCore(Model):
    schema_version: Literal["1.0.0"] = "1.0.0"
    agent_ref: AgentRef
    source_type: SourceType
    owner: NonzeroAddress
    declared_executor: Address | None
    agent_uri: SafeText
    registry_revision: Count
    metadata_hash: Hash32
    normalized_metadata: dict[str, JsonValue]
    endpoints: tuple[Endpoint, ...] = Field(min_length=1, max_length=10)
    read_block_number: UInt256
    read_block_hash: Hash32
    captured_at: Timestamp
    registry_chain: ChainIdentity


class AgentSnapshot(Model):
    snapshot_id: UUID4
    core: SnapshotCore
    snapshot_hash: Hash32
    evidence_refs: tuple[UUID4, ...] = ()


class CapabilityClaim(Model):
    source_evidence_id: UUID4
    field_path: SafeText
    quote: SafeText
    start: Count
    end: Count
    polarity: Literal["positive", "negative", "ambiguous"]
    candidate_capability: Capability | None
    extractor_version: Version

    @model_validator(mode="after")
    def span(self) -> Self:
        if self.end < self.start or self.end - self.start != len(self.quote):
            raise ValueError("claim span must use Unicode code points")
        return self


class ClaimReview(Model):
    snapshot_hash: Hash32
    review_version: int = Field(strict=True, ge=1)
    confirmed_claims: tuple[Capability, ...] = Field(min_length=1)
    unsupported_claims: tuple[SafeText, ...] = ()
    mapping_evidence_ids: tuple[UUID4, ...]
    actor: SafeText
    reason: SafeText
    excluded_capabilities: tuple[Capability, ...] = ()

    @model_serializer(mode="wrap")
    def wire(self, handler):
        value = handler(self)
        if not self.excluded_capabilities:
            value.pop("excluded_capabilities", None)
        return value

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


class BindingMessage(Model):
    agent_key_hash: Hash32
    snapshot_hash: Hash32
    executor: NonzeroAddress
    endpoint_hash: Hash32
    execution_chain_id: UInt256
    execution_chain_instance_hash: Hash32
    nonce: Challenge
    issued_at: Count
    deadline: Count

    @model_validator(mode="after")
    def window(self) -> Self:
        if self.deadline <= self.issued_at:
            raise ValueError("binding deadline must follow issue time")
        return self


class ExecutorBinding(Model):
    binding_id: UUID4
    message: BindingMessage
    owner: NonzeroAddress
    owner_signature: str = Field(pattern=r"^0x[0-9a-f]{130}$")
    executor_signature: str = Field(pattern=r"^0x[0-9a-f]{130}$")
    domain_chain_id: UInt256
    domain_registry: NonzeroAddress
    domain_salt: Challenge
    status: Literal["VERIFIED", "UNKNOWN"]
    reason_code: Reason | None
    verification_evidence: tuple[UUID4, ...]

    @model_validator(mode="after")
    def unknown_reason(self) -> Self:
        if self.status == "UNKNOWN" and self.reason_code is None:
            raise ValueError("unknown binding requires reason")
        return self


class AccessGrant(Model):
    grant_id: UUID4
    snapshot_hash: Hash32
    endpoint_ids: tuple[Version, ...] = Field(min_length=1)
    capabilities: tuple[Capability, ...] = Field(min_length=1)
    methods: tuple[Literal["POST", "GET"], ...] = Field(min_length=1)
    paths: tuple[Literal["/tasks", "/tasks/{request_id}", "/health", "/capabilities"], ...]
    chain_instances: tuple[Hash32, ...] = Field(min_length=1)
    contract_allowlist: tuple[NonzeroAddress, ...]
    max_tasks: int = Field(strict=True, ge=1, le=100)
    concurrency: Literal[1] = 1
    interval_ms: int = Field(strict=True, ge=1000)
    expires_at: Timestamp
    operator: SafeText
    consent_ref: SafeText


class TaskEnvelope(Model):
    protocol: Literal["controlled-http-v1"] = "controlled-http-v1"
    request_id: Challenge
    capability_id: Capability = "anchor_record"
    snapshot_hash: Hash32
    chain_id: UInt256
    chain_instance_id: Hash32
    target_contract: NonzeroAddress | None = None
    record_hash: Challenge | None = None
    query_tx_hash: Hash32 | None = None
    record_executor: NonzeroAddress | None = None
    record_request_id: Challenge | None = None
    read_block_number: UInt256 | None = None
    read_block_hash: Hash32 | None = None
    deadline: Timestamp

    @model_serializer(mode="wrap")
    def wire(self, handler):
        value = handler(self)
        if self.capability_id == "anchor_record":
            for name in (
                "query_tx_hash",
                "record_executor",
                "record_request_id",
                "read_block_number",
                "read_block_hash",
            ):
                value.pop(name, None)
        return value

    @model_validator(mode="after")
    def capability_inputs(self) -> Self:
        if self.capability_id == "anchor_record":
            if self.target_contract is None or self.record_hash is None:
                raise ValueError("anchor_record requires target_contract and record_hash")
            if any(
                value is not None
                for value in (
                    self.query_tx_hash,
                    self.record_executor,
                    self.record_request_id,
                    self.read_block_number,
                    self.read_block_hash,
                )
            ):
                raise ValueError("anchor_record cannot contain query inputs")
        else:
            if self.read_block_number is None or self.read_block_hash is None:
                raise ValueError("read capabilities require a frozen block")
            if self.capability_id == "get_tx_status":
                if self.query_tx_hash is None or any(
                    value is not None
                    for value in (
                        self.target_contract,
                        self.record_hash,
                        self.record_executor,
                        self.record_request_id,
                    )
                ):
                    raise ValueError("get_tx_status requires only a transaction query")
            elif (
                self.target_contract is None
                or self.record_executor is None
                or self.record_request_id is None
                or self.record_hash is None
                or self.query_tx_hash is not None
            ):
                raise ValueError(
                    "verify_record requires target, executor, request and expected hash"
                )
        return self


class ExpectedFacts(Model):
    agent_ref: AgentRef
    snapshot_hash: Hash32
    execution_chain: ChainIdentity
    executor: NonzeroAddress
    target_contract: NonzeroAddress | None
    target_code_hash: Hash32 | None = None
    request_id: Challenge
    record_hash: Challenge | None
    binding_id: UUID4 | None
    window_start: Timestamp
    deadline: Timestamp
    pre_dispatch_block: UInt256
    pre_dispatch_block_hash: Hash32
    confirmation_depth: int = Field(strict=True, ge=1, le=100)

    @model_validator(mode="after")
    def window(self) -> Self:
        if self.deadline <= self.window_start:
            raise ValueError("task deadline must follow window start")
        return self


class CaseSlot(Model):
    slot_id: UUID4
    slot_key: Version
    capability_id: Capability
    purpose: Purpose
    case_kind: Literal["positive", "negative"]
    required_class: Version
    expected_outcome: Outcome
    task: TaskEnvelope
    expected: ExpectedFacts
    grant_id: UUID4
    synthetic_input: dict[str, JsonValue] | None = None
    applicability_reason: Literal[Reason.CAPABILITY_NOT_DECLARED] | None = None

    @model_serializer(mode="wrap")
    def wire(self, handler):
        value = handler(self)
        if self.applicability_reason is None:
            value.pop("applicability_reason", None)
        return value

    @model_validator(mode="after")
    def linked(self) -> Self:
        if self.capability_id != self.task.capability_id:
            raise ValueError("slot capability differs from task")
        expected = self.expected
        task = self.task
        checks = (
            task.request_id == expected.request_id,
            task.record_hash == expected.record_hash,
            task.snapshot_hash == expected.snapshot_hash,
            task.target_contract == expected.target_contract,
            task.chain_id == expected.execution_chain.chain_id,
            task.chain_instance_id == expected.execution_chain.instance_hash,
            task.deadline == expected.deadline,
        )
        if not all(checks):
            raise ValueError("task and independently expected facts differ")
        if (
            task.capability_id == "anchor_record"
            and expected.binding_id is None
            and self.applicability_reason is None
        ):
            raise ValueError("write tasks require an executor binding")
        if task.capability_id == "verify_record" and task.record_executor != expected.executor:
            raise ValueError("record query executor differs from independently expected executor")
        if task.capability_id != "anchor_record" and (
            task.read_block_number != expected.pre_dispatch_block
            or task.read_block_hash != expected.pre_dispatch_block_hash
        ):
            raise ValueError("query block differs from independently expected block")
        if self.synthetic_input is not None and hash_json(self.synthetic_input) != task.record_hash:
            raise ValueError("synthetic input hash differs from frozen task")
        return self


class RunPlan(Model):
    schema_version: Literal["1.0.0"] = "1.0.0"
    run_id: UUID4
    snapshot_hash: Hash32
    review_version: int = Field(strict=True, ge=1)
    policy_version: Literal["policy-v1"]
    policy_hash: Hash32
    profile: Profile
    confirmed_capabilities: tuple[Capability, ...]
    suite_id: Literal["m1-smoke-v1", "capabilities-v1"]
    template_version: Literal[
        "anchor_record@1", "capabilities@1", "anchor_record@2", "capabilities@2"
    ]
    planning_time: Timestamp
    planning_evidence_refs: tuple[UUID4, ...] = ()
    slots: tuple[CaseSlot, ...] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def frozen_identity(self) -> Self:
        if self.profile == "record-read-v1" and (
            "anchor_record" in self.confirmed_capabilities
            or any(
                s.capability_id == "anchor_record" or s.purpose == Purpose.BEHAVIORAL
                for s in self.slots
            )
        ):
            raise ValueError("read-only profile cannot contain writes or behavior slots")
        if any(s.task.snapshot_hash != self.snapshot_hash for s in self.slots):
            raise ValueError("slot snapshot differs from frozen run")
        for field in ("slot_id", "slot_key"):
            if len({getattr(s, field) for s in self.slots}) != len(self.slots):
                raise ValueError(f"duplicate {field}")
        if len({s.task.request_id for s in self.slots}) != len(self.slots):
            raise ValueError("request_id cannot be reused across slots")
        return self


class EvaluationRun(Model):
    run_id: UUID4
    status: RunStatus
    stage: RunStage
    planned: Count
    settled: Count
    unknown: Count
    latest_report_id: UUID4 | None
    cancel_requested: bool = False

    @model_validator(mode="after")
    def counts(self) -> Self:
        if not self.unknown <= self.settled <= self.planned:
            raise ValueError("invalid progress counts")
        return self


class Observation(Model):
    observation_id: UUID4
    slot_id: UUID4
    attempt_no: int = Field(strict=True, ge=1)
    dispatch_state: DispatchState
    started_at: Timestamp
    ended_at: Timestamp | None
    http_status: int | None = Field(default=None, strict=True, ge=100, le=599)
    latency_ms: Count | None
    error_origin: Literal["platform", "agent", "unknown"] | None
    reason_code: Reason | None
    accepted: bool = Field(strict=True)
    candidate_tx_hash: Hash32 | None
    evidence_refs: tuple[UUID4, ...]
    diagnostic_only: bool = Field(strict=True)


class AssertionResult(Model):
    assertion_id: UUID4
    slot_id: UUID4
    rule_id: Version
    rule_version: Literal["1", "2"]
    outcome: Outcome
    reason_code: Reason | None
    expected: JsonValue
    observed: JsonValue
    evidence_refs: tuple[UUID4, ...]
    critical: bool = Field(strict=True)

    @model_validator(mode="after")
    def attributed(self) -> Self:
        if self.outcome != Outcome.PASS and self.reason_code is None:
            raise ValueError("non-PASS outcomes require a reason code")
        if self.outcome == Outcome.PASS and self.reason_code is not None:
            raise ValueError("PASS cannot contain a failure reason")
        if self.outcome in (Outcome.PASS, Outcome.FAIL) and not self.evidence_refs:
            raise ValueError("decided assertion requires evidence")
        return self


class TaskLink(Model):
    capability_id: Capability = "anchor_record"
    request_id: Challenge
    candidate_tx_hash: Hash32 | None
    verified_tx_hash: Hash32 | None
    executor: NonzeroAddress
    block_number: UInt256 | None
    block_hash: Hash32 | None
    log_index: Count | None
    match_status: Outcome

    @model_validator(mode="after")
    def verified(self) -> Self:
        if self.verified_tx_hash is not None and (
            self.verified_tx_hash != self.candidate_tx_hash
            or self.block_number is None
            or self.block_hash is None
        ):
            raise ValueError("verified transaction must identify its candidate and real block")
        if self.capability_id == "verify_record" and self.verified_tx_hash is not None:
            raise ValueError("record lookup cannot claim a verified transaction")
        if (
            self.capability_id == "verify_record"
            and self.match_status == Outcome.PASS
            and (self.block_number is None or self.block_hash is None)
        ):
            raise ValueError("record lookup PASS requires the frozen query block")
        if (
            self.match_status == Outcome.PASS
            and self.capability_id == "anchor_record"
            and (
                self.verified_tx_hash is None
                or self.verified_tx_hash != self.candidate_tx_hash
                or self.block_number is None
                or self.block_hash is None
                or self.log_index is None
            )
        ):
            raise ValueError("PASS link requires a fully located candidate transaction")
        if self.match_status != Outcome.PASS and self.verified_tx_hash is not None:
            raise ValueError("unverified link cannot claim a verified transaction")
        return self

    @model_serializer(mode="wrap")
    def wire(self, handler):
        value = handler(self)
        if self.capability_id == "anchor_record":
            value.pop("capability_id", None)
        return value


class EvidenceRecord(Model):
    evidence_id: UUID4
    path: str = Field(pattern=r"^blobs/[0-9a-f]{64}\.bin$")
    blob_hash: Hash32
    byte_count: Count
    media_type: Literal["application/json", "application/octet-stream", "text/plain"]
    source: SafeText
    observed_at: Timestamp
    collector_version: Version
    redaction_profile: Literal["credentials-v1"]
    trust_group: SafeText

    @model_validator(mode="after")
    def content_address(self) -> Self:
        if self.path != f"blobs/{self.blob_hash[2:]}.bin":
            raise ValueError("evidence path must match stored content hash")
        return self


class ScoreDimension(Model):
    state: Literal["COMPLETE", "PARTIAL", "UNKNOWN", "NOT_APPLICABLE"]
    score_bp: BasisPoints | None
    observed_score_bp: BasisPoints | None
    coverage_bp: BasisPoints | None
    sample_bp: BasisPoints | None
    freshness_bp: BasisPoints | None
    sufficiency_bp: BasisPoints | None
    reason_codes: tuple[str, ...]
    capabilities: tuple[dict[str, JsonValue], ...] | None = None

    @model_validator(mode="after")
    def score_state(self) -> Self:
        if self.state == "COMPLETE" and self.score_bp is None:
            raise ValueError("complete dimension must have a score")
        if self.state != "COMPLETE" and self.score_bp is not None:
            raise ValueError("incomplete dimension cannot have a formal score")
        return self


class ScoreResult(Model):
    policy_version: Literal["policy-v1"]
    profile: Profile
    evaluation_state: Literal["COMPLETE", "PARTIAL"]
    dimensions: dict[Literal["availability", "consistency", "behavior"], ScoreDimension]
    overall_score_bp: BasisPoints | None
    sufficiency_bp: BasisPoints
    advice: Literal[
        "NOT_RECOMMENDED",
        "INSUFFICIENT_EVIDENCE",
        "RECOMMENDED_WITHIN_SCOPE",
        "LIMITED_OR_MANUAL_REVIEW",
    ]
    critical_conflict: bool = Field(strict=True)
    limitations: tuple[SafeText, ...]

    @model_validator(mode="after")
    def partial(self) -> Self:
        if set(self.dimensions) != {"availability", "consistency", "behavior"}:
            raise ValueError("all three dimension states are required")
        if self.evaluation_state == "PARTIAL" and self.overall_score_bp is not None:
            raise ValueError("partial evaluation has no overall score")
        if self.evaluation_state == "COMPLETE" and self.overall_score_bp is None:
            raise ValueError("complete evaluation requires an overall score")
        return self


class ReportCore(Model):
    schema_version: Literal["1.0.0"] = "1.0.0"
    agent_ref: AgentRef
    agent_key_hash: Hash32
    snapshot_hash: Hash32
    run_id: UUID4
    profile: Profile
    observation_start: Timestamp
    observation_end: Timestamp
    evaluated_at: Timestamp
    policy_version: Literal["policy-v1"]
    policy_hash: Hash32
    code_version: str = Field(pattern=r"^[0-9a-f]{40}(?:-dirty)?$")
    raw_statistics: dict[str, JsonValue]
    scores: ScoreResult
    assertions: tuple[AssertionResult, ...]
    evidence_manifest_hash: Hash32
    previous_report_hash: Hash32
    limitations: tuple[SafeText, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def consistent(self) -> Self:
        if not self.observation_start <= self.observation_end <= self.evaluated_at:
            raise ValueError("invalid report observation window")
        if self.profile != self.scores.profile or self.policy_version != self.scores.policy_version:
            raise ValueError("report and scores disagree")
        return self


class AnchorReceipt(Model):
    report_hash: Hash32
    status: AnchorStatus
    trusted_chain_key: Version
    chain_instance_id: Hash32
    contract: NonzeroAddress
    publisher: NonzeroAddress
    tx_hash: Hash32 | None
    sequence: Count | None
    block_number: UInt256 | None
    block_hash: Hash32 | None
    confirmations: Count

    @model_validator(mode="after")
    def confirmed(self) -> Self:
        if self.status == AnchorStatus.CONFIRMED and (
            self.tx_hash is None
            or self.sequence is None
            or self.sequence == 0
            or self.block_number is None
            or self.block_hash is None
            or self.confirmations < 1
        ):
            raise ValueError(
                "confirmed anchor requires real transaction location and confirmations"
            )
        return self


# Stable published aliases for the names used in the project brief.
AgentKey = AgentRef
EvaluationReport = ReportCore
