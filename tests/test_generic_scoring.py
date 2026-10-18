"""One focused contract check; synthetic samples are not public evaluations."""

from datetime import datetime, timezone
import json
import unittest

from reputation_core import (
    BinaryPrediction, CapabilityCoverage, EvaluationReport, MeasurementPurpose,
    POLICY_VERSION, SERVICE_CONTRACT_POLICY_VERSION, SampleExplanation,
    ScoredSample, Verdict, calculate_scores,
)


class GenericScoringTests(unittest.TestCase):
    def test_generic_scores_partial_evidence_and_capability_binding(self) -> None:
        samples = []
        for purpose, verdicts in (
            (MeasurementPurpose.AVAILABILITY, [Verdict.PASS] * 7 + [Verdict.FAIL] + [Verdict.UNKNOWN] * 2),
            (MeasurementPurpose.FUNCTIONAL, [Verdict.PASS] * 6 + [Verdict.FAIL]),
            (MeasurementPurpose.BEHAVIORAL, [Verdict.PASS] * 5 + [Verdict.FAIL] * 2),
        ):
            samples.extend(ScoredSample(
                sample_id=f"{purpose}-{index}", task_key=f"task-{purpose}-{index}",
                purpose=purpose, verdict=verdict,
                elapsed_ms=5500 if purpose == MeasurementPurpose.AVAILABILITY and verdict == Verdict.PASS else None,
                reason="Synthetic independent verdict; not a schema-only business claim", evidence=[],
            ) for index, verdict in enumerate(verdicts))
        scored = calculate_scores(samples, policy_version=SERVICE_CONTRACT_POLICY_VERSION)
        self.assertEqual(scored.status, "COMPLETE")
        self.assertEqual((scored.availability.value, scored.functional.value, scored.behavioral.value),
                         (80.0, 85.71, 71.43))
        self.assertEqual(scored.overall, 79.71)

        explanations = [SampleExplanation(
            sample=sample, title="Offline contract fixture", input_summary="Fixture input",
            claimed_output="Fixture output", independent_result="Fixture independent judgment", checks=[],
            capability_id=f"operation-{index % 2}" if sample.purpose != MeasurementPurpose.AVAILABILITY else None,
        ) for index, sample in enumerate(samples)]
        capabilities = [CapabilityCoverage(
            capability_id=key, operation=key, description="Synthetic capability", protocol="public-api",
            tested_scope="Only the linked independently judged fixture tasks",
            sample_ids=[item.sample.sample_id for item in explanations if item.capability_id == key],
            findings=[], missing_evidence=[],
        ) for key in ("operation-0", "operation-1")]
        report = EvaluationReport(
            policy_version=SERVICE_CONTRACT_POLICY_VERSION, candidate_key="offline-fixture", name="Offline fixture",
            registration_reference="fixture", generated_at=datetime(2026, 10, 18, tzinfo=timezone.utc),
            scope="Synthetic multi-capability evaluation", scope_exclusions=["No real Agent was evaluated"],
            evaluation_window="Fixture only", approach="Independent fixture judgments, not metadata compliance",
            samples=explanations, source_references=[], limitations=[], capabilities=capabilities,
        )
        self.assertEqual(report.scores, scored)
        payload = report.model_dump(mode="json", exclude={"scores"})
        for change in ("missing-binding", "missing-membership", "duplicate-capability"):
            malformed = json.loads(json.dumps(payload))
            if change == "missing-binding":
                malformed["samples"][10]["capability_id"] = None
            elif change == "missing-membership":
                malformed["capabilities"][0]["sample_ids"].remove(samples[10].sample_id)
            else:
                malformed["capabilities"].append(malformed["capabilities"][0])
            with self.subTest(change=change), self.assertRaises(ValueError):
                EvaluationReport.model_validate_json(json.dumps(malformed))

        for verdict in (Verdict.UNKNOWN, Verdict.NOT_APPLICABLE):
            changed = list(samples)
            changed[16] = samples[16].model_copy(update={"verdict": verdict})
            partial = calculate_scores(changed, policy_version=SERVICE_CONTRACT_POLICY_VERSION)
            self.assertEqual(partial.status, "PARTIAL")
            self.assertIsNone(partial.functional.value)
            self.assertIsNone(partial.overall)
            self.assertEqual(partial.availability.value, 80.0)
        reused = list(samples)
        reused[10] = samples[10].model_copy(update={"task_key": samples[0].task_key})
        with self.assertRaisesRegex(ValueError, "duplicate task_key"):
            calculate_scores(reused, policy_version=SERVICE_CONTRACT_POLICY_VERSION)
        forecast = list(samples)
        forecast[10] = samples[10].model_copy(update={
            "prediction": BinaryPrediction(p_yes=0.75, p_no=0.25, final_outcome="yes"),
        })
        with self.assertRaisesRegex(ValueError, "service-contract-v1 does not accept prediction data"):
            calculate_scores(forecast, policy_version=SERVICE_CONTRACT_POLICY_VERSION)

        # The same fixed legacy scoring fixture remains compatible without the new fields.
        legacy = json.loads(json.dumps(payload))
        legacy["policy_version"] = POLICY_VERSION
        del legacy["capabilities"]
        for sample in legacy["samples"]:
            del sample["capability_id"]
        old_report = EvaluationReport.model_validate_json(json.dumps(legacy))
        self.assertEqual(old_report.capabilities, [])
        self.assertEqual(old_report.scores.overall, 79.71)
        self.assertEqual(old_report.scores.functional.value, 85.71)


if __name__ == "__main__":
    unittest.main()
