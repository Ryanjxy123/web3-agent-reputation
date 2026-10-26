"""User-facing explanations over evidence-derived scores, without I/O."""

from datetime import datetime
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, computed_field, model_validator

from reputation_core.admission import MeasurementPurpose, Verdict
from reputation_core.scoring import (
    POLICY_VERSION, SERVICE_POLICY_VERSIONS, SWAP_POLICY_VERSION, PolicyVersion,
    ScoredSample, ScoringOutcome, calculate_scores,
)


class ReportFinding(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    label: str
    verdict: Verdict
    explanation: str


class CapabilityCoverage(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    capability_id: str
    operation: str
    description: str
    protocol: str
    tested_scope: str
    sample_ids: list[str]
    findings: list[ReportFinding]
    missing_evidence: list[str]
    capability_type: str | None = None
    checker_id: str | None = None
    checker_version: str | None = None


class SampleExplanation(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    sample: ScoredSample
    observed_at: datetime | None = None
    title: str
    input_summary: str
    claimed_output: str
    independent_result: str
    checks: list[ReportFinding]
    capability_id: str | None = None


class EvaluationReport(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    schema_version: Literal["evaluation-report-v1"] = "evaluation-report-v1"
    policy_version: PolicyVersion = POLICY_VERSION
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
    capabilities: list[CapabilityCoverage] = []

    @model_validator(mode="after")
    def bind_service_contract_capabilities(self) -> Self:
        if self.policy_version not in (*SERVICE_POLICY_VERSIONS, SWAP_POLICY_VERSION):
            return self
        capabilities = {item.capability_id: item for item in self.capabilities}
        if len(capabilities) != len(self.capabilities):
            raise ValueError("duplicate capability_id")
        samples = {item.sample.sample_id: item for item in self.samples}
        for capability in self.capabilities:
            if len(set(capability.sample_ids)) != len(capability.sample_ids):
                raise ValueError("duplicate capability sample_id")
            for sample_id in capability.sample_ids:
                sample = samples.get(sample_id)
                if sample is None or sample.capability_id != capability.capability_id:
                    raise ValueError("capability references a missing or differently bound sample")
        for sample in self.samples:
            required = sample.sample.purpose in (MeasurementPurpose.FUNCTIONAL, MeasurementPurpose.BEHAVIORAL)
            if required or sample.capability_id is not None:
                capability = capabilities.get(sample.capability_id)
                if capability is None or sample.sample.sample_id not in capability.sample_ids:
                    raise ValueError("service-contract sample requires a matching capability binding")
        return self

    @computed_field
    @property
    def scores(self) -> ScoringOutcome:
        return calculate_scores([explanation.sample for explanation in self.samples], policy_version=self.policy_version)
