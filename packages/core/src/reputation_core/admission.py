"""Deterministic candidate admission types and rules."""

from datetime import datetime
from enum import StrEnum
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, computed_field, model_validator


class Verdict(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    UNKNOWN = "UNKNOWN"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class MeasurementPurpose(StrEnum):
    AVAILABILITY = "availability"
    FUNCTIONAL = "functional"
    BEHAVIORAL = "behavioral"
    BACKGROUND = "background"


class CheckCode(StrEnum):
    REGISTRATION = "registration"
    FUNCTIONAL_DECLARATION = "functional_declaration"
    SERVICE_INTERFACE = "service_interface"
    INDEPENDENT_ORACLE = "independent_oracle"
    EXECUTION_BINDING = "execution_binding"
    EXECUTION_HISTORY = "execution_history"


class AdmissionCheck(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: CheckCode
    status: Verdict
    explanation: str
    evidence: list[str]


class CandidateRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str
    name: str
    registration_reference: str
    source_urls: list[str]
    checks: list[AdmissionCheck]
    next_actions: list[str]

    @model_validator(mode="after")
    def require_all_checks_once(self) -> Self:
        codes = [check.code for check in self.checks]
        if len(codes) != len(CheckCode) or set(codes) != set(CheckCode):
            raise ValueError("checks must contain each CheckCode exactly once")
        return self


class CandidateAdmission(CandidateRecord):
    @computed_field
    @property
    def ready_for_full_score(self) -> bool:
        return all(check.status == Verdict.PASS for check in self.checks)


def assess_candidate(candidate: CandidateRecord) -> CandidateAdmission:
    """Return admission readiness derived from the six required checks."""
    return CandidateAdmission.model_validate(candidate, from_attributes=True)


class AdmissionReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["candidate-admission-v1"] = "candidate-admission-v1"
    assessed_at: datetime
    candidates: list[CandidateAdmission]


class ProbeObservation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_key: str
    purpose: MeasurementPurpose
    url: str
    method: str
    request_json: str | None
    observed_at: datetime
    http_status: int | None
    elapsed_ms: float
    outcome: Verdict
    error_kind: str | None
    response_file: str | None
    response_sha256: str | None
    body_complete: bool
