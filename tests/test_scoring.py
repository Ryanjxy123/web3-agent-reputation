"""Critical pilot scoring boundaries; fixtures are not real evaluation results."""

import unittest

from reputation_core import MeasurementPurpose, ScoredSample, Verdict, calculate_scores


class ScoringTests(unittest.TestCase):
    def test_weights_unknown_evidence_and_disjoint_tasks(self) -> None:
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
                reason="Offline policy fixture", evidence=[],
            ) for index, verdict in enumerate(verdicts))
        complete = calculate_scores(samples)
        self.assertEqual(complete.status, "COMPLETE")
        self.assertEqual(complete.availability.value, 80.0)
        self.assertEqual(complete.availability.p95_ms, 5500)
        self.assertEqual(complete.availability.observed, 10)
        self.assertEqual(complete.availability.unknown, 2)
        self.assertEqual(complete.functional.value, 85.71)
        self.assertEqual(complete.behavioral.value, 71.43)
        self.assertEqual(complete.overall, 79.71)

        # Missing planned slots cannot disappear merely because eight are decisive.
        missing_slots = calculate_scores(samples[:8] + samples[10:])
        self.assertIsNone(missing_slots.availability.value)
        self.assertIsNone(missing_slots.overall)
        self.assertEqual(missing_slots.status, "PARTIAL")

        partial_samples = list(samples)
        functional_failure_index = 16
        partial_samples[functional_failure_index] = samples[functional_failure_index].model_copy(
            update={"verdict": Verdict.UNKNOWN}
        )
        partial = calculate_scores(partial_samples)
        self.assertEqual(partial.status, "PARTIAL")
        self.assertIsNone(partial.functional.value)
        self.assertEqual(partial.functional.passed, 6)
        self.assertEqual(partial.functional.failed, 0)
        self.assertEqual(partial.functional.unknown, 1)
        self.assertEqual(partial.availability.value, complete.availability.value)
        self.assertIsNone(partial.overall)

        reused_task = list(samples)
        reused_task[10] = samples[10].model_copy(update={"task_key": samples[0].task_key})
        with self.assertRaisesRegex(ValueError, "duplicate task_key"):
            calculate_scores(reused_task)
