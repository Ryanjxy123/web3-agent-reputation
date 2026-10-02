"""Offline reference tests. No test here attests to live platform behavior."""

import copy
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "packages/core/src"))
from reputation_core.scoring_reference import (  # noqa: E402
    evaluate_from_stats,
)


class PolicyReferenceTests(unittest.TestCase):
    def setUp(self):
        self.policy = json.loads(
            (ROOT / "configs/policies/policy-v1.json").read_text(encoding="utf-8")
        )
        self.golden = json.loads(
            (ROOT / "fixtures/datasets/scoring-golden-v1.json").read_text(encoding="utf-8")
        )
        self.data = copy.deepcopy(self.golden["input"])

    def run_score(self):
        return evaluate_from_stats(self.data, self.policy)

    def test_prd_golden(self):
        r = self.run_score()
        e = self.golden["expected"]
        for name in ("availability", "consistency", "behavior"):
            self.assertEqual(r["dimensions"][name]["score_bp"], e[name + "_bp"])
        for name in ("overall_score_bp", "sufficiency_bp", "advice"):
            self.assertEqual(r[name], e[name])

    def test_no_mutation(self):
        before = copy.deepcopy(self.data)
        self.run_score()
        self.assertEqual(before, self.data)

    def test_deterministic(self):
        self.assertEqual(self.run_score(), self.run_score())

    def test_zero_availability_is_unknown_not_zero(self):
        self.data["availability"].update(
            decided=0, responded=0, within_latency=0, oldest_age_seconds=None
        )
        r = self.run_score()
        self.assertIsNone(r["overall_score_bp"])
        self.assertEqual(r["dimensions"]["availability"]["state"], "UNKNOWN")

    def test_one_success_no_complete_score(self):
        self.data["availability"].update(decided=1, responded=1, within_latency=1)
        r = self.run_score()
        self.assertIsNone(r["overall_score_bp"])
        self.assertEqual(r["dimensions"]["availability"]["observed_score_bp"], 10000)
        self.assertIsNone(r["dimensions"]["availability"]["score_bp"])

    def test_unknown_stays_in_coverage_denominator(self):
        self.data["availability"]["planned"] = 30
        r = self.run_score()
        self.assertEqual(r["dimensions"]["availability"]["coverage_bp"], 6667)
        self.assertIsNone(r["overall_score_bp"])

    def test_coverage_exact_boundary(self):
        self.data["availability"]["planned"] = 25
        r = self.run_score()
        self.assertEqual(r["dimensions"]["availability"]["coverage_bp"], 8000)
        self.assertIsNotNone(r["overall_score_bp"])

    def test_actual_all_fail_is_zero(self):
        self.data["availability"].update(responded=0, within_latency=0)
        r = self.run_score()
        self.assertEqual(r["dimensions"]["availability"]["score_bp"], 0)

    def test_readonly_no_transaction_penalty(self):
        self.data["profile"] = "record-read-v1"
        self.data["behavior"] = None
        self.data["capabilities"] = self.data["capabilities"][:2]
        self.data["attribution_verified"] = False
        r = self.run_score()
        self.assertEqual(r["overall_score_bp"], 9270)
        self.assertEqual(r["dimensions"]["behavior"]["state"], "NOT_APPLICABLE")

    def test_readonly_with_write_claim_rejected(self):
        self.data["profile"] = "record-read-v1"
        self.data["behavior"] = None
        with self.assertRaises(ValueError):
            self.run_score()

    def test_readonly_with_behavior_rejected(self):
        self.data["profile"] = "record-read-v1"
        self.data["capabilities"] = self.data["capabilities"][:2]
        with self.assertRaises(ValueError):
            self.run_score()

    def test_binding_unverified(self):
        self.data["attribution_verified"] = False
        r = self.run_score()
        self.assertIsNone(r["overall_score_bp"])
        self.assertEqual(r["dimensions"]["behavior"]["state"], "UNKNOWN")
        self.assertIsNone(r["dimensions"]["behavior"]["observed_score_bp"])

    def test_mapping_unknown_not_zero(self):
        self.data["capabilities"][0]["mapping"] = None
        r = self.run_score()
        self.assertIsNone(r["dimensions"]["consistency"]["score_bp"])
        self.assertIsNone(r["overall_score_bp"])

    def test_mapping_conflict_is_decided(self):
        self.data["capabilities"][0]["mapping"] = 0
        r = self.run_score()
        self.assertEqual(r["dimensions"]["consistency"]["state"], "COMPLETE")
        self.assertLess(r["dimensions"]["consistency"]["score_bp"], 9200)

    def test_insufficient_function_samples(self):
        self.data["capabilities"][0].update(decided=9, passed=9)
        self.assertIsNone(self.run_score()["overall_score_bp"])

    def test_missing_required_class(self):
        self.data["capabilities"][0]["required_classes_decided"] = False
        self.assertIsNone(self.run_score()["overall_score_bp"])

    def test_uncovered_claim_not_silently_dropped(self):
        self.data["uncovered_claim_count"] = 1
        r = self.run_score()
        self.assertIsNone(r["overall_score_bp"])
        self.assertEqual(r["sufficiency_bp"], 0)

    def test_no_capabilities(self):
        self.data["capabilities"] = []
        self.assertIsNone(self.run_score()["overall_score_bp"])

    def test_unaccepted_tasks_not_behavior_denominator(self):
        self.data["behavior"].update(accepted=0, decided=0, correct=0, oldest_age_seconds=None)
        r = self.run_score()
        self.assertIsNone(r["dimensions"]["behavior"]["score_bp"])

    def test_expired_evidence_no_full_score(self):
        self.data["availability"]["oldest_age_seconds"] = 86400
        r = self.run_score()
        self.assertEqual(r["sufficiency_bp"], 0)
        self.assertIsNone(r["overall_score_bp"])

    def test_freshness_exact_threshold(self):
        self.data["availability"]["oldest_age_seconds"] = 34560
        self.assertEqual(self.run_score()["sufficiency_bp"], 6000)
        self.assertIsNotNone(self.run_score()["overall_score_bp"])

    def test_threshold_uses_exact_value_not_rounded_q(self):
        self.data["availability"]["oldest_age_seconds"] = 34561
        r = self.run_score()
        self.assertEqual(r["sufficiency_bp"], 6000)
        self.assertIsNone(r["overall_score_bp"])

    def test_critical_conflict_veto(self):
        self.data["critical_conflict"] = True
        self.assertEqual(self.run_score()["advice"], "NOT_RECOMMENDED")

    def test_critical_warning_survives_partial_result(self):
        self.data["critical_conflict"] = True
        self.data["availability"].update(decided=1, responded=1, within_latency=1)
        r = self.run_score()
        self.assertEqual(r["evaluation_state"], "PARTIAL")
        self.assertEqual(r["advice"], "NOT_RECOMMENDED")

    def test_no_sufficient_data_no_recommendation(self):
        self.data["availability"].update(decided=1, responded=1, within_latency=1)
        self.assertEqual(self.run_score()["advice"], "INSUFFICIENT_EVIDENCE")

    def test_high_dimensions_recommend_with_scope(self):
        self.data["behavior"]["correct"] = 10
        self.assertEqual(self.run_score()["advice"], "RECOMMENDED_WITHIN_SCOPE")

    def test_negative_count_rejected(self):
        self.data["availability"]["decided"] = -1
        with self.assertRaises(ValueError):
            self.run_score()

    def test_bool_count_rejected(self):
        self.data["availability"]["decided"] = True
        with self.assertRaises(ValueError):
            self.run_score()

    def test_float_count_rejected(self):
        self.data["availability"]["decided"] = 20.0
        with self.assertRaises(ValueError):
            self.run_score()

    def test_inconsistent_counts_rejected(self):
        self.data["availability"]["within_latency"] = 21
        with self.assertRaises(ValueError):
            self.run_score()

    def test_invalid_behavior_counts_rejected(self):
        self.data["behavior"]["correct"] = 11
        with self.assertRaises(ValueError):
            self.run_score()

    def test_negative_age_rejected(self):
        self.data["availability"]["oldest_age_seconds"] = -1
        with self.assertRaises(ValueError):
            self.run_score()

    def test_missing_age_for_evidence_rejected(self):
        self.data["availability"]["oldest_age_seconds"] = None
        with self.assertRaises(ValueError):
            self.run_score()

    def test_duplicate_capabilities_rejected(self):
        self.data["capabilities"].append(copy.deepcopy(self.data["capabilities"][0]))
        with self.assertRaises(ValueError):
            self.run_score()

    def test_unknown_policy_rejected(self):
        self.policy["policy_version"] = "unreviewed-v9"
        with self.assertRaises(ValueError):
            self.run_score()

    def test_invalid_weights_rejected(self):
        self.policy["profiles"]["record-write-v1"]["weights_bp"]["availability"] = 9000
        with self.assertRaises(ValueError):
            self.run_score()


if __name__ == "__main__":
    unittest.main(verbosity=2)
