"""Public observations of actual execution, separate from a reputation score."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

from reputation_core.admission import Verdict
from reputation_core.application import AgentProfile
from reputation_core.chain_view import ChainAction
from reputation_core.reporting import ReportFinding


class ChainDimensionEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    purpose: Literal["availability", "functional", "behavioral"]
    verdict: Verdict
    observed: int
    summary: str
    missing_evidence: list[str]


class AgentChainEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["chain-execution-evidence-v1"] = "chain-execution-evidence-v1"
    candidate_key: str
    registration_reference: str
    generated_at: datetime
    title: str
    profile: AgentProfile
    actions: list[ChainAction]
    checks: list[ReportFinding]
    dimensions: list[ChainDimensionEvidence]
    selection: str
    window_summary: str
    sources: list[str]
    limitations: list[str]
