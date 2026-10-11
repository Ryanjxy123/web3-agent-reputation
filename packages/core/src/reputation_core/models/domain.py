"""Frozen, versioned wire contracts. No implicit clock, random state, or I/O."""

from typing import Annotated, Literal, Self, cast

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
from .public_identity import PublicIdentityRead

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
    method: Literal["GET", "POST"]
    protocol: Literal["controlled-http-v1", "akashi-http-readonly-v1", "akashi-mcp-readonly-v1"]

    @model_validator(mode="after")
    def protocol_method(self) -> Self:
        expected = "GET" if self.protocol == "akashi-http-readonly-v1" else "POST"
        if self.method != expected:
            raise ValueError("endpoint method differs from the static protocol")
        return self

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
    public_identity: PublicIdentityRead | None = None

    @model_serializer(mode="wrap")
    def wire(self, handler):
        value = handler(self)
        if self.public_identity is None:
            value.pop("public_identity", None)
        return value


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
    request_overrides: dict[str, JsonValue] | None = None

    @model_serializer(mode="wrap")
    def wire(self, handler):
        value = handler(self)
        if self.applicability_reason is None:
            value.pop("applicability_reason", None)
        if self.request_overrides is None:
            value.pop("request_overrides", None)
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
    suite_id: Literal["m1-smoke-v1", "capabilities-v1", "formal-evaluation-v1"]
    template_version: Literal[
        "anchor_record@1", "capabilities@1", "anchor_record@2", "capabilities@2", "capabilities@3", "capabilities@4", "capabilities@5", "capabilities@6"
    ]
    planning_time: Timestamp
    planning_evidence_refs: tuple[UUID4, ...] = ()
    slots: tuple[CaseSlot, ...] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def frozen_identity(self) -> Self:
        formal = self.suite_id == "formal-evaluation-v1"
        if formal != (self.template_version in {"capabilities@3", "capabilities@4", "capabilities@5", "capabilities@6"}):
            raise ValueError("formal suites require their own assertion template")
        if not formal and any(slot.request_overrides is not None for slot in self.slots):
            raise ValueError("legacy suites cannot contain request overrides")
        if formal and any(
            slot.request_overrides is not None and slot.case_kind != "negative"
            or slot.case_kind == "negative" and slot.purpose != Purpose.FUNCTIONAL
            or slot.purpose == Purpose.AVAILABILITY and slot.capability_id == "anchor_record"
            for slot in self.slots
        ):
            raise ValueError("formal slots require safe availability and functional rejection probes")
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
    rule_version: Literal["1", "2", "3", "4", "5", "6"]
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
    completion_kind: Literal["execution", "rejection"] = "execution"
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
        if self.completion_kind == "rejection":
            if any(value is not None for value in (
                self.candidate_tx_hash, self.verified_tx_hash,
                self.block_number, self.block_hash, self.log_index,
            )):
                raise ValueError("rejection cannot claim a transaction or chain location")
            return self
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
        if self.completion_kind == "execution":
            value.pop("completion_kind", None)
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


class ReportTaskResult(Model):
    slot_id: UUID4
    capability_id: Capability
    outcome: Outcome
    reason_code: Reason | None
    rule_version: Literal["1", "2", "3", "4", "5", "6"]
    input_evidence_id: UUID4

    @model_validator(mode="after")
    def attributed(self) -> Self:
        if (self.outcome == Outcome.PASS) != (self.reason_code is None):
            raise ValueError("only PASS has no task reason")
        return self


class TaskOutcomeCounts(Model):
    pass_count: Count = Field(validation_alias="PASS", serialization_alias="PASS")
    fail_count: Count = Field(validation_alias="FAIL", serialization_alias="FAIL")
    unknown_count: Count = Field(validation_alias="UNKNOWN", serialization_alias="UNKNOWN")
    not_applicable_count: Count = Field(
        validation_alias="NOT_APPLICABLE", serialization_alias="NOT_APPLICABLE"
    )

    @model_serializer(mode="wrap")
    def outcome_keys(self, handler):
        value = handler(self)
        return {
            "PASS": value["pass_count"],
            "FAIL": value["fail_count"],
            "UNKNOWN": value["unknown_count"],
            "NOT_APPLICABLE": value["not_applicable_count"],
        }


class EvidenceSufficiency(Model):
    thresholds: dict[str, JsonValue]
    dimensions: dict[str, JsonValue]
    capabilities: tuple[dict[str, JsonValue], ...]
    unknown_or_unresolved_bp: BasisPoints
    task_unknown_bp: BasisPoints
    sufficiency_bp: BasisPoints
    exact_gates: dict[str, Annotated[bool, Field(strict=True)]]
    uncovered_claims: tuple[str, ...] = ()
    missing_evidence: tuple[SafeText, ...] = ()
    gate_status: Literal["PASS", "PARTIAL"]
    overall_allowed: bool = Field(strict=True)


class CriticalRisk(Model):
    slot_id: UUID4
    assertion_id: UUID4
    rule_id: Version
    reason_code: Reason
    evidence_refs: tuple[UUID4, ...] = Field(min_length=1)


class RiskAssessment(Model):
    conclusion: Literal["CONFIRMED_CRITICAL_CONFLICT", "NO_CONFIRMED_CRITICAL_CONFLICT"]
    critical_findings: tuple[CriticalRisk, ...] = ()
    ordinary_failure_slots: tuple[UUID4, ...] = ()
    evidence_gap_slots: tuple[UUID4, ...] = ()


class ReportCore(Model):
    schema_version: Literal["1.0.0", "1.1.0", "1.2.0", "1.3.0", "1.4.0", "1.5.0"] = "1.0.0"
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
    task_results: tuple[ReportTaskResult, ...] = ()
    task_counts: TaskOutcomeCounts | None = None
    scoring_rule_version: Literal["three-dimensional-v1"] | None = None
    assessment_rule_version: Literal["evidence-assessment-v1"] | None = None
    task_success_rate_bp: BasisPoints | None = None
    evidence_sufficiency: EvidenceSufficiency | None = None
    risk_assessment: RiskAssessment | None = None
    evidence_manifest_hash: Hash32
    previous_report_hash: Hash32
    limitations: tuple[SafeText, ...] = Field(min_length=1)

    @model_serializer(mode="wrap")
    def compatible_wire(self, handler):
        value = handler(self)
        if self.schema_version == "1.0.0":
            value.pop("task_results", None)
            value.pop("task_counts", None)
        if self.schema_version not in {"1.2.0", "1.3.0", "1.4.0", "1.5.0"}:
            value.pop("scoring_rule_version", None)
        if self.schema_version not in {"1.3.0", "1.4.0", "1.5.0"}:
            value.pop("assessment_rule_version", None)
            value.pop("evidence_sufficiency", None)
            value.pop("risk_assessment", None)
        if self.schema_version not in {"1.2.0", "1.3.0", "1.4.0", "1.5.0"}:
            value.pop("task_success_rate_bp", None)
        return value

    @model_validator(mode="after")
    def consistent(self) -> Self:
        if not self.observation_start <= self.observation_end <= self.evaluated_at:
            raise ValueError("invalid report observation window")
        if self.profile != self.scores.profile or self.policy_version != self.scores.policy_version:
            raise ValueError("report and scores disagree")
        if (self.schema_version in {"1.2.0", "1.3.0", "1.4.0", "1.5.0"}) != (self.scoring_rule_version is not None):
            raise ValueError("formal report requires an explicit scoring rule version")
        if self.schema_version not in {"1.2.0", "1.3.0", "1.4.0", "1.5.0"} and self.task_success_rate_bp is not None:
            raise ValueError("legacy report cannot carry formal task success rate")
        assessment_fields = (
            self.assessment_rule_version, self.evidence_sufficiency, self.risk_assessment
        )
        if (
            self.schema_version in {"1.3.0", "1.4.0", "1.5.0"} and any(value is None for value in assessment_fields)
            or self.schema_version not in {"1.3.0", "1.4.0", "1.5.0"} and any(value is not None for value in assessment_fields)
        ):
            raise ValueError("formal assessment fields require report schema 1.3.0, 1.4.0 or 1.5.0")
        if self.schema_version == "1.0.0":
            if self.task_results or self.task_counts is not None:
                raise ValueError("legacy report cannot carry task replay summaries")
            return self
        if not self.task_results or self.task_counts is None:
            raise ValueError("task replay report requires results and counts")
        if len({item.slot_id for item in self.task_results}) != len(self.task_results):
            raise ValueError("duplicate task result slot")
        expected = {outcome: 0 for outcome in Outcome}
        for result in self.task_results:
            expected[result.outcome] += 1
        if self.task_counts.model_dump(mode="json") != {
            outcome.value: count for outcome, count in expected.items()
        }:
            raise ValueError("task result counts disagree")
        versions = {item.slot_id: item.rule_version for item in self.task_results}
        if self.schema_version in {"1.2.0", "1.3.0", "1.4.0", "1.5.0"}:
            expected_rule = {"1.2.0": "3", "1.3.0": "4", "1.4.0": "5", "1.5.0": "6"}[self.schema_version]
            if any(version != expected_rule for version in versions.values()):
                raise ValueError(f"formal report requires task rule version {expected_rule}")
            decided = expected[Outcome.PASS] + expected[Outcome.FAIL]
            success_rate = (
                (2 * expected[Outcome.PASS] * 10_000 + decided) // (2 * decided)
                if decided else None
            )
            if self.task_success_rate_bp != success_rate:
                raise ValueError("formal task success rate disagrees with task results")
        if any(
            assertion.slot_id not in versions
            or assertion.rule_version != versions[assertion.slot_id]
            for assertion in self.assertions
        ):
            raise ValueError("task assertion rules do not match reported slots")
        if self.schema_version in {"1.3.0", "1.4.0", "1.5.0"}:
            assert self.evidence_sufficiency is not None and self.risk_assessment is not None
            sufficient = self.evidence_sufficiency
            if (
                sufficient.overall_allowed != (self.scores.overall_score_bp is not None)
                or sufficient.gate_status != ("PASS" if sufficient.overall_allowed else "PARTIAL")
                or sufficient.sufficiency_bp != self.scores.sufficiency_bp
            ):
                raise ValueError("sufficiency gates and scores disagree")
            expected_risks = tuple(
                CriticalRisk(
                    slot_id=assertion.slot_id, assertion_id=assertion.assertion_id,
                    rule_id=assertion.rule_id, reason_code=cast(Reason, assertion.reason_code),
                    evidence_refs=assertion.evidence_refs,
                )
                for assertion in sorted(self.assertions, key=lambda item: str(item.assertion_id))
                if assertion.critical and assertion.outcome == Outcome.FAIL
            )
            critical_slots = {item.slot_id for item in expected_risks}
            evidence_gap_slots = {item.slot_id for item in self.assertions if item.outcome == Outcome.UNKNOWN}
            risk = self.risk_assessment
            if (
                risk.critical_findings != expected_risks
                or bool(expected_risks) != self.scores.critical_conflict
                or risk.conclusion != (
                    "CONFIRMED_CRITICAL_CONFLICT" if expected_risks else "NO_CONFIRMED_CRITICAL_CONFLICT"
                )
                or risk.ordinary_failure_slots != tuple(
                    item.slot_id for item in self.task_results
                    if item.outcome == Outcome.FAIL and item.slot_id not in critical_slots
                )
                or risk.evidence_gap_slots != tuple(
                    item.slot_id for item in self.task_results if item.slot_id in evidence_gap_slots
                )
            ):
                raise ValueError("risk assessment and task assertions disagree")
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
