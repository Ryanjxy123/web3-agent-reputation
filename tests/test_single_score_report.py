"""One acceptance for known-judgment points and retained real-source history."""
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import sys
import tarfile
import tempfile
import unittest

from reputation_core import Verdict, parse_evaluation_report
from reputation_core.point_scoring import calculate_point_assessment
from reputation_core.shared_scoring import SharedAssessment, shared_legacy_scores
from reputation_platform.db import Repository
from reputation_platform.shared_report import verify_shared_report_sources

ROOT = Path(__file__).resolve().parents[1]


class SingleScoreAcceptance(unittest.TestCase):
    def test_known_judgments_real_sources_and_immutable_history(self):
        data = {'schema_version': 'shared-task-assessment-v3', 'capabilities': [
            {'capability_id': 'swap', 'title': 'Synthetic swap fixture', 'selected': True,
             'write_operation': True, 'declaration_groups': [{'group_id': 'binding',
              'title': 'Binding', 'selected': True, 'source_references': ['synthetic-declaration']}]}],
            'tasks': [], 'cases': [], 'observations': []}
        for number, outcome in enumerate(('completed', 'failed', 'completed', 'unknown'), 1):
            data['tasks'].append({'task_key': f'task-{number}', 'capability_id': 'swap',
                'input_summary': 'Synthetic rule fixture, not a real Agent experiment.',
                'outcome': outcome, 'attribution': 'unknown', 'observed_at': None, 'evidence': ['fixture']})
        for dimension in ('availability', 'functional', 'behavioral'):
            data['cases'].append({'case_id': dimension, 'capability_id': 'swap', 'dimension': dimension,
                'declaration_group_id': 'binding' if dimension == 'functional' else None,
                'title': dimension, 'criterion_ids': ['criterion'],
                'task_keys': [task['task_key'] for task in data['tasks']],
                'normal_execution': dimension == 'behavioral', 'required_decisive': 1})
            for number, verdict in enumerate(('PASS', 'FAIL', 'PASS', 'UNKNOWN'), 1):
                data['observations'].append({'task_key': f'task-{number}', 'case_id': dimension,
                    'dimension': dimension, 'criterion_id': 'criterion', 'verdict': verdict,
                    'measurement_validity': 'valid', 'elapsed_ms': None,
                    'reason': 'Synthetic boundary observation.', 'evidence': ['fixture']})

        def model(value):
            return SharedAssessment.model_validate_json(json.dumps(value))

        current = model(data)
        point = calculate_point_assessment(current)
        self.assertEqual(current.result, point)
        self.assertEqual(point.overall.model_dump(), {'lower': 66.67, 'upper': 66.67})
        self.assertEqual(shared_legacy_scores(current).overall, 66.67)
        self.assertEqual(point.functional.counts.unknown, 1)
        legacy_data = deepcopy(data)
        legacy_data['schema_version'] = 'shared-task-assessment-v2'
        legacy = model(legacy_data)
        before = legacy.model_dump(mode='json')
        self.assertEqual(legacy.result.overall.model_dump(), {'lower': 50, 'upper': 75})
        self.assertNotIn(point.overall.lower, (legacy.result.overall.lower, legacy.result.overall.upper))
        for validity, verdict in (('valid', 'NOT_APPLICABLE'), ('invalid', 'PASS')):
            omitted = deepcopy(data)
            for row in omitted['observations']:
                if row['task_key'] == 'task-4':
                    row.update(measurement_validity=validity, verdict=verdict)
            self.assertEqual(model(omitted).result.overall.lower, 66.67)
        missing = deepcopy(data)
        missing['observations'] = [row for row in missing['observations'] if row['dimension'] != 'availability']
        self.assertIsNone(model(missing).result.availability.interval)
        self.assertIsNone(model(missing).result.overall)
        insufficient = deepcopy(data)
        insufficient['cases'][-1]['required_decisive'] = 4
        self.assertIsNone(model(insufficient).result.behavioral.interval)
        self.assertIsNone(model(insufficient).result.overall)
        readonly = deepcopy(data)
        readonly['capabilities'][0]['write_operation'] = False
        readonly['cases'][-1]['normal_execution'] = False
        self.assertIsNone(model(readonly).result.behavioral.interval)
        self.assertIsNone(model(readonly).result.overall)
        critical = deepcopy(data)
        next(row for row in critical['observations'] if row['verdict'] == 'FAIL')['critical'] = True
        self.assertEqual(model(critical).result.risk_status, 'MAJOR_VIOLATION')
        self.assertEqual(legacy.model_dump(mode='json'), before)
        partial_capability = deepcopy(data)
        partial_capability['capabilities'].append({**deepcopy(data['capabilities'][0]), 'capability_id': 'management'})
        partial_capability['tasks'].append({**data['tasks'][0], 'task_key': 'management-task', 'capability_id': 'management'})
        for case in data['cases']:
            ident = 'management:' + case['case_id']
            partial_capability['cases'].append({**deepcopy(case), 'case_id': ident,
                'capability_id': 'management', 'task_keys': ['management-task']})
            if case['dimension'] != 'availability':
                row = next(row for row in data['observations'] if row['case_id'] == case['case_id'])
                partial_capability['observations'].append({**row, 'case_id': ident, 'task_key': 'management-task'})
        partial_result = model(partial_capability).result
        self.assertIsNone(partial_result.capabilities[1].availability.interval)
        self.assertEqual(partial_result.availability.interval.lower, 66.67)

        with tempfile.TemporaryDirectory(prefix='single-score-source-') as temporary:
            root = ROOT
            directory = root / os.environ.get('SINGLE_SCORE_REPORT', 'runtime/mangoswap-single-score-20261027-v1')
            if not (directory / 'report.json').is_file():
                sys.path.insert(0, str(ROOT / 'scripts'))
                from public_reports import INDEX, public_path
                root = Path(temporary)
                archive_path = ROOT / os.environ.get('SINGLE_SCORE_ARCHIVE', 'data/public-reports-single-score-v3.tar.gz')
                self.assertTrue(archive_path.is_file(), 'Real single-score report package is required')
                index = None
                with tarfile.open(archive_path, 'r:gz') as archive:
                    for member in archive.getmembers():
                        self.assertTrue(member.isfile())
                        name = public_path(member.name)
                        destination = root / name
                        destination.parent.mkdir(parents=True, exist_ok=True)
                        with archive.extractfile(member) as stream:
                            raw = stream.read()
                        destination.write_bytes(raw)
                        if INDEX.fullmatch(name):
                            index = json.loads(raw)
                self.assertIsNotNone(index)
                self.assertEqual(len(index['reports']), 1)
                directory = root / index['reports'][0]['directory']
            report = Repository('unused', root)._load_report(directory).report
            self.assertEqual(report.policy_version, 'transaction-agent-evidence-v3')
            assessment = report.shared_assessment
            self.assertEqual(assessment.schema_version, 'shared-task-assessment-v3')
            self.assertEqual(assessment.result.score_status, 'AVAILABLE')
            self.assertEqual(assessment.result.task_count, 34)
            self.assertEqual(len({task.task_key for task in assessment.tasks}), 34)
            self.assertEqual(len(assessment.result.selected_capabilities), 3)
            self.assertEqual(assessment.result.behavioral.counts.passed, 10)
            self.assertEqual(report.scores.availability.value, 100)
            self.assertEqual(assessment.result.availability.counts.unknown, 3)
            self.assertEqual(assessment.result.availability.counts.not_run, 3)
            self.assertEqual(sum(cap.selected and cap.availability.interval is None
                                 for cap in assessment.result.capabilities), 2)
            self.assertGreater(assessment.result.functional.counts.failed, 0)
            self.assertLess(report.scores.functional.value, 100)
            result = assessment.result
            for value in [result.overall, *(getattr(result, dim).interval
                          for dim in ('availability', 'functional', 'behavioral'))]:
                self.assertIsNotNone(value)
                self.assertEqual(value.lower, value.upper)
            self.assertEqual(report.scores.overall, assessment.result.overall.lower)

            manifest = json.loads((directory / 'manifest.json').read_bytes())
            hashes = {row['path']: row['sha256'] for row in manifest['inputs']}
            historical = []
            for name in hashes:
                if name.endswith('/report.json'):
                    supplied = json.loads((root / name).read_bytes())
                    if supplied.get('policy_version') == 'transaction-agent-evidence-v2':
                        historical.append(root / name)
            self.assertEqual(len(historical), 1, 'Bundle must retain the preceding formal interval report')
            old_path = historical[0]
            old_raw = old_path.read_bytes()
            old_sha = hashlib.sha256(old_raw).hexdigest()
            old = parse_evaluation_report(old_raw)
            self.assertEqual(old.shared_assessment.result.task_count, 34)
            self.assertNotEqual(old.shared_assessment.result.overall.lower, old.shared_assessment.result.overall.upper)
            self.assertNotIn(report.scores.overall,
                (old.shared_assessment.result.overall.lower, old.shared_assessment.result.overall.upper))
            self.assertEqual({task.task_key for task in old.shared_assessment.tasks},
                             {task.task_key for task in assessment.tasks})
            changed = report.model_copy(deep=True)
            failure = next(row for row in changed.shared_assessment.observations
                           if row.dimension == 'functional' and row.verdict == Verdict.FAIL)
            failure.verdict = Verdict.PASS
            with self.assertRaises(ValueError):
                verify_shared_report_sources(root, changed, hashes)
            self.assertEqual(hashlib.sha256(old_path.read_bytes()).hexdigest(), old_sha)


if __name__ == '__main__':
    unittest.main()
