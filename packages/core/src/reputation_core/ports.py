"""Shared dependency-inversion boundaries; implementations live outside core."""
from typing import Protocol

from .models import (
    AccessGrant,
    AgentRef,
    AssertionResult,
    EvidenceRecord,
    ExpectedFacts,
    Observation,
    SnapshotCore,
    TaskEnvelope,
)


class RegistryReader(Protocol):
    def read(self, ref: AgentRef, captured_at: str) -> SnapshotCore: ...


class ProtocolAdapter(Protocol):
    async def execute(self, task: TaskEnvelope, grant: AccessGrant) -> Observation: ...
    async def lookup(self, task: TaskEnvelope, grant: AccessGrant) -> Observation: ...


class EvidenceStore(Protocol):
    def put_redacted(self, data: bytes, metadata: EvidenceRecord) -> EvidenceRecord: ...
    def read(self, ref: EvidenceRecord) -> bytes: ...


class CapabilityTemplate(Protocol):
    def assert_result(self, expected: ExpectedFacts, evidence: bytes) -> tuple[AssertionResult, ...]: ...
