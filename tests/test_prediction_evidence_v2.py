"""One affected regression: continuous credit, authenticated root bytes, legacy replay."""

from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

from reputation_core import EvaluationReport, MeasurementPurpose, Verdict, calculate_scores
from reputation_platform.prediction_auto import verify_auto_prediction_report
from reputation_platform.prediction_evidence import EvidenceStore
from reputation_platform.prediction_report import RetainedEvidence


ROOT = Path(__file__).resolve().parents[1]


class PredictionEvidenceV2Tests(unittest.TestCase):
    def test_evidence_version_preserves_scores_and_authentication(self):
        legacy_run = ROOT / 'runtime/evaluation-report-20261018T130748Z-45152bd3'
        payload = json.loads((legacy_run / 'report.json').read_bytes())
        retained_scores = payload.pop('scores')
        report = EvaluationReport.model_validate_json(json.dumps(payload, ensure_ascii=False))
        manifest = json.loads((legacy_run / 'manifest.json').read_bytes())
        self.assertEqual(verify_auto_prediction_report(ROOT, report,
            {item['path']: item['sha256'] for item in manifest['inputs']}), report.registration_reference)
        self.assertEqual(report.scores.model_dump(mode='json'), retained_scores)
        samples = [item.sample for item in report.samples]
        expanded = calculate_scores(samples, policy_version='prediction-history-v2').model_dump(mode='json')
        previous = report.scores.model_dump(mode='json')
        previous['policy_version'] = 'prediction-history-v2'
        self.assertEqual(expanded, previous)
        self.assertNotEqual(expanded['functional']['value'], 100)
        functional = next(item for item in samples if item.purpose == MeasurementPurpose.FUNCTIONAL)
        broken = functional.model_copy(update={'verdict': Verdict.PASS, 'prediction': None})
        with self.assertRaisesRegex(ValueError, 'PASS requires validated probabilities'):
            calculate_scores([broken], policy_version='prediction-history-v2')

        research = ROOT / 'runtime/input-layout-research-20261018T133653Z-b20ec01e'
        findings = json.loads((research / 'findings.json').read_bytes())['findings']
        with tempfile.TemporaryDirectory(prefix='v2-content-check-', dir=ROOT / 'runtime') as directory:
            store = EvidenceStore(Path(directory), [research], root=ROOT)
            try:
                for case in findings:
                    content = store.ipfs('request-content', case['digest'], 'metadata.json', root_layout=True)
                    actual = RetainedEvidence(ROOT).content(content, case['digest'], 'metadata.json')
                    self.assertEqual(actual, json.loads((ROOT / case['input_file']['path']).read_bytes()))
                    forged = deepcopy(content)
                    forged['payload']['tool'] = 'forged-tool'
                    with self.assertRaisesRegex(ValueError, 'retained JSON'):
                        RetainedEvidence(ROOT).content(forged, case['digest'], 'metadata.json')
                self.assertEqual(store.sent, 0)
            finally:
                store.close()


if __name__ == '__main__':
    unittest.main()
