"""Immutable bundle index; document aliases point to the same committed CAS bytes."""

from typing import Literal, Self

from pydantic import UUID4, Field, model_validator

from .base import Count, Hash32, Model, NonzeroAddress, UInt256
from .domain import ChainIdentity, EvidenceRecord, ReportCore


class PublicationContext(Model):
    trusted_chain_key: Literal["local-demo"] = "local-demo"
    chain: ChainIdentity
    contract: NonzeroAddress
    publisher: NonzeroAddress
    confirmation_depth: int = Field(strict=True, ge=1, le=100)
    previous_report_hash: Hash32
    head_sequence: Count
    head_block_number: UInt256
    head_block_hash: Hash32
    platform_instance_id: Hash32


class ManifestDocument(Model):
    path: str = Field(
        pattern=r"^(?:[a-z][a-z0-9_-]*\.json|schemas/[A-Za-z][A-Za-z0-9]*\.schema\.json)$"
    )
    evidence_id: UUID4

    @model_validator(mode="after")
    def no_cycle(self) -> Self:
        if self.path in {"report_core.json", "evidence_manifest.json", "anchor_receipt.json"}:
            raise ValueError("report, manifest and receipt cannot enter the evidence manifest")
        return self


class EvidenceManifest(Model):
    schema_version: Literal["evidence-manifest-v1"] = "evidence-manifest-v1"
    publication: PublicationContext
    documents: tuple[ManifestDocument, ...]
    evidence: tuple[EvidenceRecord, ...]

    @model_validator(mode="after")
    def ordered_unique(self) -> Self:
        paths = [item.path for item in self.documents]
        identifiers = [str(item.evidence_id) for item in self.evidence]
        if paths != sorted(set(paths)) or identifiers != sorted(set(identifiers)):
            raise ValueError("manifest entries must be unique and canonically ordered")
        if len({item.path for item in self.evidence}) != len(self.evidence):
            raise ValueError("duplicate evidence content")
        if any(str(item.evidence_id) not in identifiers for item in self.documents):
            raise ValueError("document does not reference committed evidence")
        return self


class ReportView(Model):
    report_id: UUID4
    report_hash: Hash32
    core: ReportCore
    manifest: EvidenceManifest
