"""Shared local application contracts; persistence and execution live outside core."""

from datetime import datetime
import re
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field

from reputation_core.admission import CandidateRecord
from reputation_core.scoring import ScoringOutcome


def normalize_reference(value: str) -> str | None:
    """Parse supported public identifiers without fetching a submitted URL."""
    value = value.strip()
    match = re.fullmatch(r"(?:eip155:)?([0-9]+):(0x[0-9a-fA-F]{40}):([0-9]+)", value)
    if match:
        return f"eip155:{int(match[1])}:{match[2].lower()}:{int(match[3])}"
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError:
        return None
    if parsed.scheme != "https" or parsed.hostname not in {"8004scan.io", "www.8004scan.io"} or parsed.query or parsed.fragment:
        return None
    chains = {"bsc": 56, "ethereum": 1, "base": 8453, "mantle": 5000,
              "gnosis": 100, "polygon": 137, "celo": 42220, "arbitrum": 42161,
              "avalanche": 43114, "optimism": 10}
    match = re.fullmatch(r"/agents/(" + "|".join(chains) + r")/([0-9]+)/?", parsed.path)
    if match and not parsed.username and not parsed.password and port in (None, 443):
        chain = chains[match[1]]
        return f"eip155:{chain}:0x8004a169fb4a3325136eb29fa0ceb6d2e539a432:{int(match[2])}"
    return None


class EvaluationSubmission(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reference: str = Field(min_length=1)


class ReportSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    candidate_key: str
    generated_at: datetime
    scope: str
    scores: ScoringOutcome


class AgentProfile(BaseModel):
    """Source-backed business context, separate from a report and its scores."""

    model_config = ConfigDict(extra="forbid")

    business_summary: str
    ecosystem: str
    role: Literal["asset-execution", "chain-query", "research-delivery", "unverified"]
    registration_chain_id: int | None
    execution_chain_ids: list[int]
    capabilities: list[str]
    execution_accounts: list[str]
    evidence_status: Literal["verified", "declared", "unverified"]
    sources: list[str]
    boundary: str


class AgentSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str
    name: str
    registration_reference: str
    description: str
    report_count: int
    latest_report: ReportSummary | None
    profile: AgentProfile | None = None
    complete_report_count: int = 0


class AgentDetail(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agent: AgentSummary
    reports: list[ReportSummary]
    candidate: CandidateRecord | None


class EvaluationJob(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    reference: str
    status: Literal["QUEUED", "RUNNING", "COMPLETE", "NEEDS_INFO", "UNSUPPORTED", "FAILED"]
    stage: Literal["QUEUED", "COLLECTING", "VERIFYING", "REPORTING", "DONE"]
    message: str
    candidate_key: str | None
    report_id: str | None
    created_at: datetime
    updated_at: datetime


class HealthStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["ok"]
    database: Literal["ready"]
