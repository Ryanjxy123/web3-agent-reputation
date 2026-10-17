import unittest

from pydantic import ValidationError

from reputation_core import (
    AdmissionCheck,
    CandidateAdmission,
    CandidateRecord,
    CheckCode,
    Verdict,
    assess_candidate,
)


class CandidateAdmissionTests(unittest.TestCase):
    def candidate_data(self) -> dict:
        return {
            "key": "fixture-agent",
            "name": "Admission test fixture",
            "registration_reference": "https://example.test/fixture-agent",
            "source_urls": ["https://example.test/fixture-agent"],
            "checks": [
                AdmissionCheck(
                    code=code,
                    status=Verdict.PASS,
                    explanation="Controlled unit-test evidence.",
                    evidence=[f"fixture://evidence/{code.value}"],
                )
                for code in CheckCode
            ],
            "next_actions": [],
        }

    def test_all_six_pass_allows_full_scoring(self) -> None:
        admission = assess_candidate(CandidateRecord(**self.candidate_data()))

        self.assertTrue(admission.ready_for_full_score)
        self.assertTrue(admission.model_dump()["ready_for_full_score"])

    def test_incomplete_or_duplicate_checks_cannot_admit(self) -> None:
        for status in (Verdict.FAIL, Verdict.UNKNOWN, Verdict.NOT_APPLICABLE):
            with self.subTest(status=status):
                data = self.candidate_data()
                data["checks"][0].status = status
                admission = assess_candidate(CandidateRecord(**data))
                self.assertFalse(admission.ready_for_full_score)

        for invalid_kind in ("missing", "duplicate", "supplied_readiness"):
            with self.subTest(invalid_kind=invalid_kind):
                data = self.candidate_data()
                if invalid_kind == "missing":
                    data["checks"].pop()
                elif invalid_kind == "duplicate":
                    data["checks"][-1] = data["checks"][0]
                else:
                    data["ready_for_full_score"] = True
                with self.assertRaises(ValidationError):
                    CandidateAdmission(**data)
