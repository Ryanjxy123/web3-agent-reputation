"""One real-source replay acceptance; failures never alter retained evidence."""
import hashlib
import json
from pathlib import Path
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'packages/core/src'), str(ROOT / 'services/platform/src'), str(ROOT / 'scripts')]

from reputation_core import Verdict
from reputation_core.reporting import parse_evaluation_report
from reputation_platform.db import Repository
from reputation_platform import shared_report
from reputation_platform.swap_report import SwapEvidence
from public_reports import public_path


class SharedSourceAcceptance(unittest.TestCase):
    def test_real_replay_unknown_behavior_and_source_integrity(self):
        with tempfile.TemporaryDirectory(prefix='shared-source-') as temporary:
            local = ROOT / 'runtime/mangoswap-shared-20261027-v2'
            root = ROOT
            if not (local / 'report.json').is_file():
                root = Path(temporary)
                with tarfile.open(ROOT / 'data/public-reports-single-score-v3.tar.gz', 'r:gz') as archive:
                    for member in archive.getmembers():
                        self.assertTrue(member.isfile())
                        destination = root / public_path(member.name)
                        destination.parent.mkdir(parents=True, exist_ok=True)
                        with archive.extractfile(member) as stream:
                            destination.write_bytes(stream.read())
                local = root / 'runtime/mangoswap-shared-20261027-v2'
            imported = Repository('unused', root)._load_report(local)
            report = imported.report
            self.assertEqual(report.shared_assessment.result.task_count, 31)
            self.assertEqual(report.shared_assessment.result.observation_count, 131)
            self.assertEqual(report.shared_assessment.result.score_status, 'AVAILABLE')
            self.assertEqual(report.shared_assessment.result.declaration_coverage, 'PARTIAL')
            self.assertIsNone(report.scores.overall)
            hashes = {row['path']: row['sha256'] for row in json.loads((local / 'manifest.json').read_bytes())['inputs']}
            origin = json.loads((local / shared_report.ORIGIN).read_bytes())
            parent_path = root / origin['source_report']
            parent_sha = hashlib.sha256(parent_path.read_bytes()).hexdigest()
            parent = parse_evaluation_report(parent_path.read_bytes())
            self.assertEqual(parent.scores.overall, 98.70)

            changed = report.model_copy(deep=True)
            observation = next(row for row in changed.shared_assessment.observations
                               if row.criterion_id == 'asset-display' and row.verdict == Verdict.FAIL)
            observation.verdict = Verdict.PASS
            with self.assertRaisesRegex(ValueError, 'original evidence'):
                shared_report.verify_shared_report_sources(root, changed, hashes)
            changed = report.model_copy(deep=True)
            changed.approach = 'Claim all functions were prospectively verified'
            with self.assertRaisesRegex(ValueError, 'selected scope'):
                shared_report.verify_shared_report_sources(root, changed, hashes)
            forged = report.model_dump(mode='json')
            forged['shared_assessment']['result']['overall']['lower'] -= 1
            with self.assertRaises(ValueError):
                parse_evaluation_report(forged)
            corrupted = dict(hashes)
            corrupted[origin['declarations']] = '0' * 64
            with self.assertRaisesRegex(ValueError, 'source changed'):
                shared_report.verify_shared_report_sources(root, report, corrupted)

            original = shared_report._metadata_tag
            first = next(task.task_key for task in report.shared_assessment.tasks if task.outcome == 'completed')

            def missing_one_metadata(records, request, purpose, send):
                if purpose == 'behavioral' and send and send['requestId'] == first:
                    return None
                return original(records, request, purpose, send)

            with patch.object(shared_report, '_metadata_tag', side_effect=missing_one_metadata):
                _, _, assessment = shared_report._assessment(root, SwapEvidence(root, hashes), origin)
            behavior = [row for row in assessment.observations if row.dimension == 'behavioral']
            self.assertEqual(len(behavior), 7)
            self.assertEqual(sum(row.verdict == Verdict.UNKNOWN for row in behavior), 1)
            self.assertEqual(hashlib.sha256(parent_path.read_bytes()).hexdigest(), parent_sha)


if __name__ == '__main__':
    unittest.main()
