"""User-facing explanations over evidence-derived scores, without I/O."""

from datetime import datetime
import json
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, computed_field, model_validator

from reputation_core.admission import MeasurementPurpose, Verdict
from reputation_core.scoring import (
    POLICY_VERSION, SERVICE_POLICY_VERSIONS, SHARED_POLICY_VERSION, SHARED_POLICY_VERSIONS, SWAP_POLICY_VERSIONS, PolicyVersion,
    ScoredSample, ScoringOutcome, calculate_scores,
)
from reputation_core.shared_scoring import SharedAssessment, shared_legacy_scores


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
    shared_assessment: SharedAssessment | None = None

    @model_validator(mode="after")
    def bind_service_contract_capabilities(self) -> Self:
        if self.policy_version in SHARED_POLICY_VERSIONS:
            if self.shared_assessment is None:
                raise ValueError('shared policy requires a structured shared assessment')
            expected_schema = 'shared-task-assessment-v' + self.policy_version.rsplit('-v', 1)[1]
            if self.shared_assessment.schema_version != expected_schema:
                raise ValueError('shared policy and assessment schema versions differ')
            return self
        if self.shared_assessment is not None:
            raise ValueError('shared assessment is only valid under its versioned policy')
        if self.policy_version not in (*SERVICE_POLICY_VERSIONS, *SWAP_POLICY_VERSIONS):
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
        if self.policy_version in SHARED_POLICY_VERSIONS:
            return shared_legacy_scores(self.shared_assessment)
        return calculate_scores([explanation.sample for explanation in self.samples], policy_version=self.policy_version)


def parse_evaluation_report(value: dict | str | bytes) -> EvaluationReport:
    """Round-trip published computed fields without trusting supplied scores."""
    data = json.loads(value) if isinstance(value, (str, bytes)) else dict(value)
    supplied_scores = data.pop('scores', None)
    supplied_shared = None
    if data.get('shared_assessment') is not None:
        shared = dict(data['shared_assessment'])
        supplied_shared = shared.pop('result', None)
        data['shared_assessment'] = shared
    report = EvaluationReport.model_validate_json(json.dumps(data, ensure_ascii=False))
    if supplied_scores is not None and supplied_scores != report.scores.model_dump(mode='json'):
        raise ValueError('supplied scores differ from deterministic evaluation')
    if supplied_shared is not None and supplied_shared != report.shared_assessment.result.model_dump(mode='json'):
        raise ValueError('supplied shared result differs from deterministic evaluation')
    return report
