"""Source-backed business declarations; extracted claims never execute code."""

from collections.abc import Sequence
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class SourceDocument(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_id: str = Field(min_length=1)
    url: str
    raw_sha256: str
    projection_sha256: str
    text: str = Field(min_length=1)


class ClaimCitation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_id: str = Field(min_length=1)
    quote: str = Field(min_length=1)


class BusinessClaim(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claim_id: str = Field(min_length=1)
    operation: str = Field(min_length=1)
    description: str = Field(min_length=1)
    inputs: list[str]
    outputs: list[str]
    constraints: list[str]
    access: Literal["free", "paid", "auth_required", "unknown"]
    citations: list[ClaimCitation] = Field(min_length=1)


class DeclarationAnalysis(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["declaration-analysis-v1"] = "declaration-analysis-v1"
    claims: list[BusinessClaim]
    gaps: list[str]


def validate_analysis(
    analysis: DeclarationAnalysis, sources: Sequence[SourceDocument],
) -> DeclarationAnalysis:
    """Reject duplicate claims, missing sources and quotations absent from source text."""
    by_id = {}
    for source in sources:
        if not source.text.strip():
            raise ValueError(f"Source text must not be blank: {source.source_id}")
        if source.source_id in by_id:
            raise ValueError(f"Duplicate source_id: {source.source_id}")
        by_id[source.source_id] = source
    claim_ids = set()
    for claim in analysis.claims:
        if claim.claim_id in claim_ids:
            raise ValueError(f"Duplicate claim_id: {claim.claim_id}")
        claim_ids.add(claim.claim_id)
        texts = (claim.claim_id, claim.operation, claim.description,
                 *claim.inputs, *claim.outputs, *claim.constraints)
        if any(not text.strip() for text in texts):
            raise ValueError(f"Claim text must not be blank: {claim.claim_id}")
        if not claim.citations:
            raise ValueError(f"Claim requires at least one citation: {claim.claim_id}")
        for citation in claim.citations:
            if citation.source_id not in by_id:
                raise ValueError(f"Unknown citation source_id: {citation.source_id}")
            if not citation.quote.strip():
                raise ValueError(f"Citation quote must not be blank: {claim.claim_id}")
            if citation.quote not in by_id[citation.source_id].text:
                raise ValueError(f"Citation quote not found in source: {claim.claim_id}")
    return analysis
