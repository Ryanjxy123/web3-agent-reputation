"""User-facing explanations over evidence-derived scores, without I/O."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, computed_field

from reputation_core.admission import Verdict
from reputation_core.scoring import ScoredSample, ScoringOutcome, calculate_scores


class ReportFinding(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    label: str
    verdict: Verdict
    explanation: str


class SampleExplanation(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    sample: ScoredSample
    observed_at: datetime | None = None
    title: str
    input_summary: str
    claimed_output: str
    independent_result: str
    checks: list[ReportFinding]


class EvaluationReport(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    schema_version: Literal["evaluation-report-v1"] = "evaluation-report-v1"
    candidate_key: str
    name: str
    registration_reference: str
    generated_at: datetime
    scope: str
    scope_exclusions: list[str]
    evaluation_window: str
    approach: str
    samples: list[SampleExplanation]
    source_references: list[str]
    limitations: list[str]

    @computed_field
    @property
    def scores(self) -> ScoringOutcome:
        return calculate_scores([explanation.sample for explanation in self.samples])
