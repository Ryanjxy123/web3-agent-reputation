"""Deterministic scores for frozen liquidity and binary prediction policies."""

from math import ceil, isfinite
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, model_validator

from reputation_core.admission import MeasurementPurpose, Verdict
from reputation_core.prediction import BinaryPrediction

POLICY_VERSION = "liquidity-history-v1"
PREDICTION_POLICY_VERSION = "prediction-history-v1"
PolicyVersion = Literal["liquidity-history-v1", "prediction-history-v1"]
DIMENSION_WEIGHTS = {
    MeasurementPurpose.AVAILABILITY: 0.30,
    MeasurementPurpose.FUNCTIONAL: 0.40,
    MeasurementPurpose.BEHAVIORAL: 0.30,
}
PLANNED_SAMPLES = {
    MeasurementPurpose.AVAILABILITY: 10,
    MeasurementPurpose.FUNCTIONAL: 7,
    MeasurementPurpose.BEHAVIORAL: 7,
}
MIN_DECISIVE_SAMPLES = {
    MeasurementPurpose.AVAILABILITY: 8,
    MeasurementPurpose.FUNCTIONAL: 7,
    MeasurementPurpose.BEHAVIORAL: 7,
}
AVAILABILITY_SUCCESS_WEIGHT = 0.80
AVAILABILITY_LATENCY_WEIGHT = 0.20
LATENCY_FULL_SCORE_MS = 1000.0
LATENCY_ZERO_SCORE_MS = 10000.0


class ScoredSample(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sample_id: str
    task_key: str
    purpose: MeasurementPurpose
    verdict: Verdict
    elapsed_ms: float | None
    reason: str
    evidence: list[str]
    prediction: BinaryPrediction | None = None

    @model_validator(mode="after")
    def validate_prediction(self) -> Self:
        if self.prediction is not None:
            if self.purpose != MeasurementPurpose.FUNCTIONAL or self.verdict not in (Verdict.PASS, Verdict.FAIL):
                raise ValueError("prediction data requires a decisive functional sample")
            expected = Verdict.PASS if self.prediction.outcome_probability >= 0.5 else Verdict.FAIL
            if self.verdict != expected:
                raise ValueError("functional verdict disagrees with the final-outcome probability")
        return self


class DimensionScore(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: float | None
    planned: int
    observed: int
    passed: int
    failed: int
    unknown: int
    not_applicable: int
    p95_ms: float | None


class ScoringOutcome(BaseModel):
    model_config = ConfigDict(extra="forbid")

    policy_version: PolicyVersion = POLICY_VERSION
    availability: DimensionScore
    functional: DimensionScore
    behavioral: DimensionScore
    overall: float | None
    status: Literal["COMPLETE", "PARTIAL", "NOT_EVALUATED"]


def _dimension_score(purpose: MeasurementPurpose, samples: list[ScoredSample],
                     policy_version: PolicyVersion) -> DimensionScore:
    passed = sum(sample.verdict == Verdict.PASS for sample in samples)
    failed = sum(sample.verdict == Verdict.FAIL for sample in samples)
    decisive = passed + failed
    value, p95 = None, None
    if purpose == MeasurementPurpose.AVAILABILITY:
        timings = sorted(sample.elapsed_ms for sample in samples if sample.verdict == Verdict.PASS)
        if timings:
            p95 = timings[ceil(0.95 * len(timings)) - 1]
    if len(samples) == PLANNED_SAMPLES[purpose] and decisive >= MIN_DECISIVE_SAMPLES[purpose]:
        success_rate = passed / decisive
        if purpose == MeasurementPurpose.AVAILABILITY:
            latency_ratio = 0.0 if p95 is None else max(0.0, min(
                1.0, (LATENCY_ZERO_SCORE_MS - p95) / (LATENCY_ZERO_SCORE_MS - LATENCY_FULL_SCORE_MS)
            ))
            value = 100 * (AVAILABILITY_SUCCESS_WEIGHT * success_rate
                           + AVAILABILITY_LATENCY_WEIGHT * latency_ratio)
        elif purpose == MeasurementPurpose.FUNCTIONAL and policy_version == PREDICTION_POLICY_VERSION:
            value = sum(sample.prediction.credit if sample.prediction is not None else 0.0
                        for sample in samples) / decisive
        else:
            value = 100 * success_rate
    return DimensionScore(
        value=round(value, 2) if value is not None else None,
        planned=PLANNED_SAMPLES[purpose], observed=len(samples), passed=passed, failed=failed,
        unknown=sum(sample.verdict == Verdict.UNKNOWN for sample in samples),
        not_applicable=sum(sample.verdict == Verdict.NOT_APPLICABLE for sample in samples),
        p95_ms=p95,
    )


def calculate_scores(samples: list[ScoredSample], *, policy_version: PolicyVersion = POLICY_VERSION) -> ScoringOutcome:
    """Score disjoint measurement tasks; unknown evidence never becomes a zero."""
    if policy_version not in (POLICY_VERSION, PREDICTION_POLICY_VERSION):
        raise ValueError("unsupported scoring policy")
    grouped = {purpose: [] for purpose in DIMENSION_WEIGHTS}
    sample_ids, task_keys = set(), set()
    for sample in samples:
        sample.validate_prediction()
        if sample.prediction is not None and policy_version == POLICY_VERSION:
            raise ValueError("liquidity-history-v1 does not accept prediction data")
        if (policy_version == PREDICTION_POLICY_VERSION
                and sample.purpose == MeasurementPurpose.FUNCTIONAL
                and sample.verdict == Verdict.PASS and sample.prediction is None):
            raise ValueError("prediction functional PASS requires validated probabilities and a final outcome")
        if sample.purpose == MeasurementPurpose.BACKGROUND:
            raise ValueError("background evidence cannot be a scored sample")
        if sample.sample_id in sample_ids:
            raise ValueError("duplicate sample_id")
        if sample.task_key in task_keys:
            raise ValueError("duplicate task_key: a task cannot enter multiple scoring denominators")
        sample_ids.add(sample.sample_id)
        task_keys.add(sample.task_key)
        if sample.purpose == MeasurementPurpose.AVAILABILITY and sample.verdict == Verdict.PASS:
            if sample.elapsed_ms is None or not isfinite(sample.elapsed_ms) or sample.elapsed_ms < 0:
                raise ValueError("availability PASS requires finite, nonnegative elapsed_ms")
        grouped[sample.purpose].append(sample)
        if len(grouped[sample.purpose]) > PLANNED_SAMPLES[sample.purpose]:
            raise ValueError(f"sample count exceeds the plan for {sample.purpose}")
    dimensions = {purpose: _dimension_score(purpose, group, policy_version) for purpose, group in grouped.items()}
    complete = all(dimension.value is not None for dimension in dimensions.values())
    overall = round(sum(dimensions[purpose].value * weight
                        for purpose, weight in DIMENSION_WEIGHTS.items()), 2) if complete else None
    return ScoringOutcome(
        policy_version=policy_version,
        availability=dimensions[MeasurementPurpose.AVAILABILITY],
        functional=dimensions[MeasurementPurpose.FUNCTIONAL],
        behavioral=dimensions[MeasurementPurpose.BEHAVIORAL], overall=overall,
        status="COMPLETE" if complete else "PARTIAL" if samples else "NOT_EVALUATED",
    )
