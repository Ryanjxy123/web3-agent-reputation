"""Explicit frozen public query contracts; no executor or write authorization."""

import re
from typing import Literal, Self

from pydantic import UUID4, Field, JsonValue, model_validator

from ..evidence import canonical_bytes, hash_bytes
from .base import Challenge, Hash32, Model, NonzeroAddress, SafeText, Timestamp, UInt256, Version
from .domain import AgentRef, AgentSnapshot, ChainIdentity, ClaimReview, EvidenceRecord
from .enums import Outcome, Purpose, Reason
from .public_identity import PublicReadonlyProtocol, ReadonlyIdentityAssociation

KNOWN_TX = "0xd01d3e019906321b7d410538aebb696dec806df1099756ec85ac7b2da91df7fc"


class PublicReadonlyTask(Model):
    protocol: PublicReadonlyProtocol
    request_id: Challenge
    capability_id: Literal["verify_record"] = "verify_record"
    snapshot_hash: Hash32
    chain_id: Literal["8453"] = "8453"
    chain_instance_id: Hash32
    endpoint_id: Literal["akashi-http", "akashi-mcp"]
    query: dict[str, str]
    read_block_number: UInt256
    read_block_hash: Hash32
    deadline: Timestamp

    @model_validator(mode="after")
    def safe_query(self) -> Self:
        endpoint = "akashi-http" if self.protocol == "akashi-http-readonly-v1" else "akashi-mcp"
        if self.endpoint_id != endpoint or set(self.query) not in ({"tx"}, {"hash"}):
            raise ValueError("public task requires its exact static endpoint and one query")
        value = next(iter(self.query.values()))
        if ("tx" in self.query and value != KNOWN_TX
                or "hash" in self.query and value != "not-a-sha256"
                and re.fullmatch(r"(?:0x)?[0-9a-f]{64}", value) is None):
            raise ValueError("unsupported public query")
        if self.protocol == "akashi-mcp-readonly-v1" and self.query != {"tx": KNOWN_TX}:
            raise ValueError("public MCP only permits the known transaction")
        return self


class PublicReadonlyExpectedFacts(Model):
    agent_ref: AgentRef
    snapshot_hash: Hash32
    execution_chain: ChainIdentity
    request_id: Challenge
    window_start: Timestamp
    deadline: Timestamp
    pre_dispatch_block: UInt256
    pre_dispatch_block_hash: Hash32
    confirmation_depth: Literal[12] = 12
    protocol: PublicReadonlyProtocol
    endpoint_id: Literal["akashi-http", "akashi-mcp"]
    query: dict[str, str]

    @model_validator(mode="after")
    def window(self) -> Self:
        if self.deadline <= self.window_start:
            raise ValueError("task deadline must follow window start")
        return self


class PublicReadonlyCaseSlot(Model):
    slot_id: UUID4
    slot_key: Version
    capability_id: Literal["verify_record"] = "verify_record"
    purpose: Purpose
    case_kind: Literal["positive", "negative"]
    required_class: Literal["match", "not_found", "invalid_format"]
    expected_outcome: Outcome
    task: PublicReadonlyTask
    expected: PublicReadonlyExpectedFacts
    grant_id: UUID4

    @model_validator(mode="after")
    def linked(self) -> Self:
        task, facts = self.task, self.expected
        if self.purpose not in {Purpose.AVAILABILITY, Purpose.FUNCTIONAL, Purpose.BACKGROUND}:
            raise ValueError("public queries cannot contain behavioral slots")
        if not all((task.request_id == facts.request_id,
                    task.snapshot_hash == facts.snapshot_hash,
                    task.chain_id == facts.execution_chain.chain_id,
                    task.chain_instance_id == facts.execution_chain.instance_hash,
                    task.deadline == facts.deadline,
                    task.read_block_number == facts.pre_dispatch_block,
                    task.read_block_hash == facts.pre_dispatch_block_hash,
                    task.protocol == facts.protocol, task.endpoint_id == facts.endpoint_id,
                    task.query == facts.query)):
            raise ValueError("public task and independent expected facts differ")
        invalid = task.query == {"hash": "not-a-sha256"}
        if invalid != (self.case_kind == "negative") or invalid != (self.required_class == "invalid_format"):
            raise ValueError("public negative probe must be the fixed invalid hash")
        if invalid and (self.purpose != Purpose.FUNCTIONAL or self.expected_outcome != Outcome.PASS):
            raise ValueError("invalid input is a safe functional rejection probe")
        if not invalid and self.required_class != ("match" if "tx" in task.query else "not_found"):
            raise ValueError("public query class differs from frozen input")
        return self


class PublicReadonlyRunPlan(Model):
    schema_version: Literal["public-readonly-plan-v1"] = "public-readonly-plan-v1"
    run_id: UUID4
    snapshot_hash: Hash32
    review_version: int = Field(strict=True, ge=1)
    policy_version: Literal["policy-v1"] = "policy-v1"
    policy_hash: Hash32
    profile: Literal["record-read-v1"] = "record-read-v1"
    confirmed_capabilities: tuple[Literal["verify_record"], ...] = ("verify_record",)
    suite_id: Literal["public-readonly-v1"] = "public-readonly-v1"
    template_version: Literal["public-readonly@1"] = "public-readonly@1"
    planning_time: Timestamp
    planning_evidence_refs: tuple[UUID4, ...] = ()
    slots: tuple[PublicReadonlyCaseSlot, ...] = Field(min_length=1, max_length=5)

    @model_validator(mode="after")
    def frozen(self) -> Self:
        if self.confirmed_capabilities != ("verify_record",):
            raise ValueError("public plan supports only verify_record")
        for name in ("slot_id", "slot_key"):
            if len({getattr(slot, name) for slot in self.slots}) != len(self.slots):
                raise ValueError("duplicate public slot")
        if len({slot.task.request_id for slot in self.slots}) != len(self.slots):
            raise ValueError("duplicate public correlation challenge")
        first = self.slots[0].expected
        if any(slot.task.snapshot_hash != self.snapshot_hash
               or slot.expected.execution_chain != first.execution_chain
               or slot.expected.agent_ref != first.agent_ref
               or slot.task.read_block_number != first.pre_dispatch_block
               or slot.task.read_block_hash != first.pre_dispatch_block_hash
               or slot.expected.window_start < self.planning_time for slot in self.slots):
            raise ValueError("public plan has inconsistent frozen identity or time")
        return self


class PublicReadonlyGrant(Model):
    schema_version: Literal["public-readonly-grant-v1"] = "public-readonly-grant-v1"
    protocol: PublicReadonlyProtocol
    grant_id: UUID4
    snapshot_hash: Hash32
    endpoint_ids: tuple[Literal["akashi-http", "akashi-mcp"], ...]
    capabilities: tuple[Literal["verify_record"], ...] = ("verify_record",)
    methods: tuple[Literal["GET", "POST"], ...]
    paths: tuple[Literal["/proof", "/mcp"], ...]
    chain_instances: tuple[Hash32, ...] = Field(min_length=1, max_length=1)
    contract_allowlist: tuple[NonzeroAddress, ...] = ()
    max_tasks: int = Field(strict=True, ge=1, le=5)
    concurrency: Literal[1] = 1
    interval_ms: int = Field(strict=True, ge=1000, le=60000, default=1000)
    expires_at: Timestamp
    operator: SafeText
    consent_ref: SafeText

    @model_validator(mode="after")
    def exact_scope(self) -> Self:
        http = self.protocol == "akashi-http-readonly-v1"
        if (self.endpoint_ids != (("akashi-http",) if http else ("akashi-mcp",))
                or self.methods != (("GET",) if http else ("POST",))
                or self.paths != (("/proof",) if http else ("/mcp",))
                or self.capabilities != ("verify_record",) or self.contract_allowlist):
            raise ValueError("public grant requires exact static readonly scope")
        return self


class PublicReadonlyGrantCreate(Model):
    snapshot_id: UUID4
    endpoint_id: Literal["akashi-http", "akashi-mcp"]
    max_tasks: int = Field(strict=True, ge=1, le=5)
    interval_ms: int = Field(strict=True, ge=1000, le=60000, default=1000)
    expires_at: Timestamp
    consent_ref: SafeText


class PublicReadonlyGrantView(Model):
    grant: PublicReadonlyGrant
    revoked: bool


class PublicReadonlyEvaluationCreate(Model):
    snapshot_id: UUID4
    review_version: int = Field(strict=True, ge=1)
    profile: Literal["record-read-v1"] = "record-read-v1"
    policy_version: Literal["policy-v1"] = "policy-v1"
    grant_ids: tuple[UUID4, ...] = Field(min_length=2, max_length=2)
    suite_id: Literal["public-readonly-v1"] = "public-readonly-v1"
    capability_id: Literal["verify_record"] = "verify_record"

    @model_validator(mode="after")
    def unique(self) -> Self:
        if len(set(self.grant_ids)) != 2:
            raise ValueError("HTTP and MCP grants must be distinct")
        return self


class EvidencePacket(Model):
    record: EvidenceRecord
    body: JsonValue

    @model_validator(mode="after")
    def committed(self) -> Self:
        raw = canonical_bytes(self.body)
        if self.record.blob_hash != hash_bytes(raw) or self.record.byte_count != len(raw):
            raise ValueError("evidence packet differs from canonical CAS bytes")
        return self


class PublicReadonlyVerificationInput(Model):
    schema_version: Literal["public-readonly-verification-input-v1"] = "public-readonly-verification-input-v1"
    rule_version: Literal["7"] = "7"
    slot: PublicReadonlyCaseSlot
    snapshot: AgentSnapshot
    review: ClaimReview
    review_version: int = Field(strict=True, ge=1)
    platform_instance_id: Hash32
    grant: PublicReadonlyGrant | None
    intent_persisted_at: Timestamp
    dispatch_started_at: Timestamp | None
    dispatch_payload_hash: Hash32 | None
    execution_reason: Reason | None
    observed_at: Timestamp
    association: ReadonlyIdentityAssociation
    packets: tuple[EvidencePacket, ...] = Field(max_length=100)
    identity_evidence_refs: tuple[UUID4, ...]
    agent_evidence_refs: tuple[UUID4, ...]
    business_evidence_refs: tuple[UUID4, ...]

    @model_validator(mode="after")
    def unique_packets(self) -> Self:
        identifiers = [packet.record.evidence_id for packet in self.packets]
        if len(set(identifiers)) != len(identifiers):
            raise ValueError("duplicate public evidence packet")
        for refs in (self.identity_evidence_refs, self.agent_evidence_refs, self.business_evidence_refs):
            if len(set(refs)) != len(refs):
                raise ValueError("duplicate public evidence reference")
        all_refs = (*self.identity_evidence_refs, *self.agent_evidence_refs, *self.business_evidence_refs)
        if len(set(all_refs)) != len(all_refs) or set(all_refs) != set(identifiers):
            raise ValueError("public evidence roles must exactly cover distinct packets")
        return self


def public_task_payload(slot: PublicReadonlyCaseSlot) -> dict[str, JsonValue]:
    """Frozen platform intent, distinct from the exact external query wire."""
    return slot.task.model_dump(mode="json")
