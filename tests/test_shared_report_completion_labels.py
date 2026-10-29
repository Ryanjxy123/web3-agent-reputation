"""One display-only combination; synthetic checks are not business observations."""
from datetime import datetime, timezone
import base64
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from reputation_core.reporting import EvaluationReport
from reputation_core.scoring import POINT_POLICY_VERSION
from reputation_core.shared_scoring import SharedAssessment
from reputation_platform.evaluation_report import render_evaluation_report
from reputation_platform import cow_swap_report
from reputation_platform.swap_report import SwapEvidence

ROOT = Path(__file__).resolve().parents[1]


class SharedCompletionLabels(unittest.TestCase):
    def test_completed_diagnostics_simulations_fulfillment_and_refund(self):
        cases, tasks, observations = [], [], []
        examples = [
            ('warning-check', [('functional', 'safe-rejection', 'PASS', 'valid')], '检查已完成'),
            ('planned-only', [('behavioral', 'onchain-fulfillment', 'UNKNOWN', 'valid')], '检查已完成'),
            ('simulation-only', [('functional', 'execution-effect', 'PASS', 'valid')], '检查已完成'),
            ('canonical-swap', [('behavioral', 'onchain-fulfillment', 'PASS', 'valid')], '已成交'),
            ('invalid-measurement', [('behavioral', 'onchain-fulfillment', 'PASS', 'invalid')], '检查已完成'),
            ('legacy-execution', [('behavioral', 'execution-effect', 'PASS', 'valid')], '已成交'),
            ('principal-refund', [('functional', 'exact-principal-refund', 'PASS', 'valid'),
                                  ('behavioral', 'onchain-fulfillment', 'PASS', 'valid')], '已撤销退款'),
            ('native-swap', [('functional', 'native-input', 'PASS', 'valid'),
                             ('behavioral', 'onchain-fulfillment', 'PASS', 'valid')], '已成交'),
            ('native-format-only', [('functional', 'native-input', 'PASS', 'valid')], '检查已完成'),
        ]
        for key, checks, _ in examples:
            tasks.append({'task_key': key, 'capability_id': 'trading', 'input_summary': key,
                'outcome': 'completed', 'attribution': 'unknown', 'observed_at': None, 'evidence': ['controlled-display-input']})
            for dimension, criterion, verdict, validity in checks:
                case_id = key + ':' + criterion
                cases.append({'case_id': case_id, 'capability_id': 'trading', 'dimension': dimension,
                    'declaration_group_id': 'diagnostics' if dimension == 'functional' else None,
                    'title': case_id, 'criterion_ids': [criterion], 'task_keys': [key],
                    'normal_execution': dimension == 'behavioral', 'required_decisive': 1})
                observations.append({'task_key': key, 'case_id': case_id, 'criterion_id': criterion,
                    'dimension': dimension, 'verdict': verdict, 'reason': 'Controlled rendering boundary.',
                    'evidence': ['controlled-display-input'], 'measurement_validity': validity, 'elapsed_ms': None})
        assessment = SharedAssessment.model_validate_json(json.dumps({
            'schema_version': 'shared-task-assessment-v3', 'capabilities': [{'capability_id': 'trading',
                'title': 'Trading', 'selected': True, 'write_operation': True, 'declaration_groups': [{
                    'group_id': 'diagnostics', 'title': 'Diagnostics', 'selected': True,
                    'source_references': ['controlled-display-input']}]}],
            'cases': cases, 'tasks': tasks, 'observations': observations}))
        report = EvaluationReport(policy_version=POINT_POLICY_VERSION, candidate_key='controlled-display',
            name='Controlled display', registration_reference='mcp-registry:example.test/service@1.0.0',
            generated_at=datetime(2026, 10, 29, tzinfo=timezone.utc), scope='Rendering only',
            scope_exclusions=[], evaluation_window='Controlled input', approach='Display verification', samples=[],
            source_references=['controlled-display-input'], limitations=[], shared_assessment=assessment)
        before = report.model_dump(mode='json')
        html = render_evaluation_report(report)
        for index, (key, _, label) in enumerate(examples, 1):
            self.assertIn(f'<summary>任务{index} · {key}</summary><p>真实结局：{label}</p>', html)
        self.assertEqual(html.count('真实结局：已成交'), 3)
        self.assertEqual(html.count('真实结局：已撤销退款'), 1)
        self.assertEqual(report.model_dump(mode='json'), before)
        # Existing real C24 remains a completed diagnostic; the frozen draft
        # scope is retained as evidence but is not the calibrated report label.
        fixture = json.loads((ROOT / 'tests/fixtures/cow_declared_diagnostics_case.json').read_bytes())
        with tempfile.TemporaryDirectory(prefix='cow-display-offline-') as temporary:
            root = Path(temporary)
            for row in fixture['files']:
                raw = base64.b64decode(row['base64'], validate=True)
                self.assertEqual(hashlib.sha256(raw).hexdigest(), row['sha256'])
                path = root / row['path']
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(raw)
            note = root / cow_swap_report.ADR
            note.parent.mkdir(parents=True, exist_ok=True)
            note.write_bytes((ROOT / cow_swap_report.ADR).read_bytes())
            plan_raw = (root / fixture['plan_path']).read_bytes()
            plan = json.loads(plan_raw)
            self.assertIn('DRAFT', plan['scope'])
            for contract in [None, fixture['measurement_contract']]:
                source = cow_swap_report.collect_cow_originals(root, fixture['plan_path'], fixture['items'],
                    measurement_contract=contract)
                hashes = {row['path']: row['sha256'] for row in source['sources']}
                hashes[cow_swap_report.ADR] = hashlib.sha256(note.read_bytes()).hexdigest()
                cow = cow_swap_report.replay_cow_swap_sources(root, SwapEvidence(root, hashes), source, report.generated_at)
                if contract is None:
                    self.assertEqual(cow.scope, plan['scope'])
                else:
                    self.assertNotIn('DRAFT', cow.scope)
                    self.assertIn('链ID 8453', cow.scope)
                    rendered = render_evaluation_report(cow)
                    self.assertIn('真实结局：检查已完成', rendered)
                    self.assertNotIn('真实结局：已成交', rendered)
                    task = next(task for task in cow.shared_assessment.tasks
                                if task.task_key == plan['tasks'][23]['task_key'])
                    self.assertEqual(task.outcome, 'completed')
            self.assertEqual((root / fixture['plan_path']).read_bytes(), plan_raw)


if __name__ == '__main__':
    unittest.main()
