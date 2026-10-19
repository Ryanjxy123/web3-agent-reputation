"""One focused regression for prediction credit and retained LP report compatibility."""

import json
from pathlib import Path
import unittest

from pydantic import ValidationError

from reputation_core import (
    BinaryPrediction, EvaluationReport, MeasurementPurpose, PREDICTION_POLICY_VERSION,
    ScoredSample, Verdict, calculate_scores,
)

ROOT = Path(__file__).resolve().parents[1]


class PredictionScoringTests(unittest.TestCase):
    def test_probability_credit_boundaries_and_original_lp_report(self) -> None:
        original = ROOT / "runtime/evaluation-report-20261018T053613Z-fe5237bc/report.json"
        if not original.is_file():
            self.skipTest("NOT_RUN: retained original LP report is required for compatibility verification")
        legacy_payload = json.loads(original.read_bytes())
        original_scores = legacy_payload.pop("scores")
        self.assertNotIn("policy_version", legacy_payload)
        self.assertTrue(all("prediction" not in item["sample"] for item in legacy_payload["samples"]))
        legacy = EvaluationReport.model_validate_json(json.dumps(legacy_payload, ensure_ascii=False))
        self.assertEqual(legacy.scores.model_dump(mode="json"), original_scores)
        self.assertEqual(legacy.scores.overall, 96.67)

        samples = []
        for purpose, count in ((MeasurementPurpose.AVAILABILITY, 10), (MeasurementPurpose.BEHAVIORAL, 7)):
            samples.extend(ScoredSample(
                sample_id=f"{purpose}-{index}", task_key=f"task-{purpose}-{index}",
                purpose=purpose, verdict=Verdict.PASS if index < 5 or count == 10 else Verdict.FAIL,
                elapsed_ms=5500 if count == 10 else None, reason="Offline policy fixture", evidence=[],
            ) for index in range(count))
        forecasts = [(1.0, "yes"), (0.0, "yes"), (0.5, "yes"),
                     (0.8, "yes"), (0.2, "no"), (0.7, "no")]
        expected_credits = [100, 0, 75, 96, 96, 51]
        for index, ((p_yes, final_outcome), expected_credit) in enumerate(zip(forecasts, expected_credits)):
            prediction = BinaryPrediction(p_yes=p_yes, p_no=1.0-p_yes, final_outcome=final_outcome)
            self.assertAlmostEqual(prediction.credit, expected_credit)
            samples.append(ScoredSample(
                sample_id=f"functional-{index}", task_key=f"market-{index}",
                purpose=MeasurementPurpose.FUNCTIONAL,
                verdict=Verdict.PASS if prediction.outcome_probability >= 0.5 else Verdict.FAIL,
                elapsed_ms=None, reason="Offline final binary result fixture", evidence=[], prediction=prediction,
            ))
        samples.append(ScoredSample(
            sample_id="functional-format", task_key="market-format", purpose=MeasurementPurpose.FUNCTIONAL,
            verdict=Verdict.FAIL, elapsed_ms=None, reason="Confirmed malformed output fixture", evidence=[],
        ))
        complete = calculate_scores(samples, policy_version=PREDICTION_POLICY_VERSION)
        self.assertEqual(complete.policy_version, PREDICTION_POLICY_VERSION)
        self.assertEqual(complete.status, "COMPLETE")
        self.assertEqual(complete.functional.value, 59.71)
        self.assertEqual((complete.functional.passed, complete.functional.failed), (4, 3))
        self.assertEqual(complete.availability.value, 90.0)
        self.assertEqual(complete.behavioral.value, 71.43)
        self.assertEqual(complete.overall, 72.31)
        explanations = [legacy.samples[index].model_copy(update={"sample": sample})
                        for index, sample in enumerate(samples)]
        new_report = legacy.model_copy(update={"policy_version": PREDICTION_POLICY_VERSION,
                                               "samples": explanations})
        self.assertEqual(new_report.scores, complete)

        missing = calculate_scores(samples[:-1], policy_version=PREDICTION_POLICY_VERSION)
        self.assertEqual(missing.status, "PARTIAL")
        self.assertIsNone(missing.functional.value)
        self.assertIsNone(missing.overall)
        for verdict in (Verdict.UNKNOWN, Verdict.NOT_APPLICABLE):
            changed = samples[:-1] + [samples[-1].model_copy(update={"verdict": verdict})]
            partial = calculate_scores(changed, policy_version=PREDICTION_POLICY_VERSION)
            self.assertIsNone(partial.functional.value)
            self.assertEqual(partial.functional.failed, 2)
            self.assertIsNone(partial.overall)
        with self.assertRaisesRegex(ValueError, "liquidity-history-v1 does not accept"):
            calculate_scores(samples)
        missing_prediction = samples[:-1] + [samples[-1].model_copy(update={"verdict": Verdict.PASS})]
        with self.assertRaisesRegex(ValueError, "PASS requires validated probabilities"):
            calculate_scores(missing_prediction, policy_version=PREDICTION_POLICY_VERSION)
        reused = samples[:-1] + [samples[-1].model_copy(update={"task_key": samples[0].task_key})]
        with self.assertRaisesRegex(ValueError, "duplicate task_key"):
            calculate_scores(reused, policy_version=PREDICTION_POLICY_VERSION)

        for p_yes, p_no in ((float("nan"), 0.5), (float("inf"), 0.0),
                            (-0.1, 1.1), (1.1, -0.1), (0.5, 0.6), ("0.5", 0.5), (True, 0.0)):
            with self.subTest(p_yes=p_yes, p_no=p_no), self.assertRaises(ValidationError):
                BinaryPrediction(p_yes=p_yes, p_no=p_no, final_outcome="yes")
        neutral = BinaryPrediction(p_yes=0.5, p_no=0.5, final_outcome="yes")
        functional = samples[17].model_dump()
        for update in ({"verdict": Verdict.FAIL, "prediction": neutral},
                       {"verdict": Verdict.UNKNOWN}, {"purpose": MeasurementPurpose.BEHAVIORAL},
                       {"quality_score": 100}):
            with self.subTest(update=update), self.assertRaises(ValidationError):
                ScoredSample.model_validate({**functional, **update})


if __name__ == "__main__":
    unittest.main()
