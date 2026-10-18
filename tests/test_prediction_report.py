"""One necessary evidence-binding check over a retained background pilot, never formal sampling."""

from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'packages/core/src'), str(ROOT / 'services/platform/src')]
from reputation_core import Verdict
from reputation_platform.prediction_evidence import PredictionProfile
from reputation_platform.prediction_report import RetainedEvidence, explain_task, load_selection


class PredictionReportEvidenceTest(unittest.TestCase):
    def test_actual_pilot_recomputed_and_tampered_copies_rejected(self):
        source = ROOT / 'runtime/prediction-history-20261018T070519Z-78e8864d/bundle.json'
        plan = ROOT / 'runtime/plan-selection-20261018T070307Z-fd317e93'
        if not source.is_file() or not plan.is_dir():
            self.skipTest('Retained real pilot evidence is not installed')
        bundle = json.loads(source.read_bytes())
        profile = PredictionProfile(**bundle['profile'])
        evidence = RetainedEvidence(ROOT)
        evidence.snapshot_header = evidence.rpc(bundle['identity']['header'])['value']
        _, descriptor = load_selection(evidence, plan, profile)
        # The pilot remains excluded from production; this copy exercises one functional unit only.
        task = deepcopy(bundle['tasks'][0])
        task['purpose'] = 'functional'
        task['settlement_verification']['verdict'] = 'FAIL'
        task['chain_verification']['verdict'] = 'FAIL'
        result, _ = explain_task(evidence, task, profile, descriptor, {})
        self.assertEqual(result.sample.verdict, Verdict.PASS, result.sample.reason)
        self.assertAlmostEqual(result.sample.prediction.credit, 96.0)
        self.assertIn('不是预测准确率', result.independent_result)
        forged = deepcopy(task)
        forged['output']['payload']['result'] = '{"p_yes":1.0,"p_no":0.0}'
        result, _ = explain_task(evidence, forged, profile, descriptor, {})
        self.assertEqual(result.sample.verdict, Verdict.UNKNOWN)
        self.assertIsNone(result.sample.prediction)
        forged = deepcopy(task)
        forged['chain_evidence']['delivery']['proofs']['receipt']['value']['status'] = '0x0'
        result, _ = explain_task(evidence, forged, profile, descriptor, {})
        self.assertEqual(result.sample.verdict, Verdict.UNKNOWN)
        with self.assertRaises(ValueError):
            evidence.remember('runtime/platform-config/database-url.txt')


if __name__ == '__main__':
    unittest.main()
