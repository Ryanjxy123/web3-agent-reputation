"""One acceptance for versioned uncertainty and the real multicapability report."""
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
from reputation_core.scoring import MULTICAP_POLICY_VERSION, SHARED_POLICY_VERSION
from reputation_core.shared_scoring import SharedAssessment, shared_legacy_scores
from reputation_platform.db import Repository
from reputation_platform.shared_report import verify_shared_report_sources

ROOT = Path(__file__).resolve().parents[1]


class FormalLifecycleAcceptance(unittest.TestCase):
    def test_versioned_availability_and_real_lifecycle_sources(self):
        # Synthetic rule fixture: the second capability has F/B facts, no A observation.
        fixture = {'schema_version': 'shared-task-assessment-v2', 'capabilities': [],
                   'cases': [], 'tasks': [], 'observations': []}
        for number in (1, 2):
            capability, key = f'capability-{number}', f'task-{number}'
            fixture['capabilities'].append({'capability_id': capability, 'title': capability,
                'selected': True, 'write_operation': True, 'declaration_groups': [
                    {'group_id': 'binding', 'title': 'Binding', 'selected': True,
                     'source_references': ['synthetic-declaration']}]})
            fixture['tasks'].append({'task_key': key, 'capability_id': capability,
                'input_summary': 'Synthetic fixture, not an Agent experiment.',
                'outcome': 'completed', 'attribution': 'operator', 'observed_at': None,
                'evidence': ['synthetic-evidence']})
            for dimension in ('availability', 'functional', 'behavioral'):
                case = {'case_id': f'{capability}:{dimension}', 'capability_id': capability,
                    'dimension': dimension, 'declaration_group_id': 'binding' if dimension == 'functional' else None,
                    'title': dimension, 'criterion_ids': ['criterion'], 'task_keys': [key],
                    'normal_execution': dimension == 'behavioral', 'required_decisive': 1}
                fixture['cases'].append(case)
                if number == 2 and dimension == 'availability':
                    continue
                fixture['observations'].append({'task_key': key, 'case_id': case['case_id'],
                    'criterion_id': 'criterion', 'dimension': dimension, 'verdict': 'PASS',
                    'reason': 'Synthetic boundary observation.', 'evidence': ['synthetic-evidence'],
                    'measurement_validity': 'valid', 'elapsed_ms': None})

        def model(data):
            return SharedAssessment.model_validate_json(json.dumps(data))

        current = model(fixture)
        self.assertEqual(current.result.score_status, 'AVAILABLE')
        self.assertEqual(current.result.availability.interval.model_dump(), {'lower': 50, 'upper': 100})
        self.assertEqual(current.result.overall.model_dump(), {'lower': 85, 'upper': 100})
        self.assertIsNone(shared_legacy_scores(current).availability.value)
        self.assertIsNone(shared_legacy_scores(current).overall)
        unobserved = current.result.capabilities[1].availability
        self.assertEqual(unobserved.interval.model_dump(), {'lower': 0, 'upper': 100})
        self.assertEqual((unobserved.counts.observed, unobserved.counts.not_run), (0, 1))
        for dimension in ('availability', 'functional', 'behavioral'):
            missing = deepcopy(fixture)
            missing['observations'] = [row for row in missing['observations']
                if not (row['dimension'] == dimension and (dimension == 'availability' or row['task_key'] == 'task-2'))]
            result = model(missing).result
            self.assertEqual(result.score_status, 'INSUFFICIENT')
            self.assertIsNone(getattr(result, dimension).interval)
            self.assertIsNone(result.overall)
        legacy = deepcopy(fixture)
        legacy['schema_version'] = 'shared-task-assessment-v1'
        self.assertEqual(model(legacy).result.score_status, 'INSUFFICIENT')
        self.assertIsNone(model(legacy).result.overall)

        with tempfile.TemporaryDirectory(prefix='formal-lifecycle-source-') as temporary:
            root = ROOT
            relative = os.environ.get('FORMAL_LIFECYCLE_REPORT', 'runtime/mangoswap-formal-multicap-20261027-v1')
            directory = root / relative
            if not (directory / 'report.json').is_file():
                # CI restores the exact published bytes; it never fabricates a lifecycle task.
                sys.path.insert(0, str(ROOT / 'scripts'))
                from public_reports import INDEX, public_path
                root = Path(temporary)
                archive_path = ROOT / os.environ.get('FORMAL_LIFECYCLE_ARCHIVE', 'data/public-reports-multicap-v2.tar.gz')
                self.assertTrue(archive_path.is_file(), 'Real multicapability package is required')
                with tarfile.open(archive_path, 'r:gz') as archive:
                    index = None
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
            self.assertEqual(report.policy_version, MULTICAP_POLICY_VERSION)
            assessment = report.shared_assessment
            self.assertIsNotNone(assessment)
            self.assertEqual(assessment.schema_version, 'shared-task-assessment-v2')
            self.assertEqual(assessment.result.score_status, 'AVAILABLE')
            self.assertEqual(assessment.result.task_count, 34)
            self.assertEqual(len({task.task_key for task in assessment.tasks}), 34)
            self.assertEqual(assessment.result.behavioral.counts.planned, 10)
            self.assertEqual(assessment.result.behavioral.counts.passed, 10)
            self.assertEqual(len(assessment.result.selected_capabilities), 3)
            self.assertGreater(assessment.result.availability.counts.not_run, 0)
            self.assertLess(assessment.result.availability.interval.lower, assessment.result.availability.interval.upper)

            manifest = json.loads((directory / 'manifest.json').read_bytes())
            hashes = {row['path']: row['sha256'] for row in manifest['inputs']}
            parents = []
            for name in hashes:
                if name.endswith('/report.json'):
                    value = json.loads((root / name).read_bytes())
                    if value.get('policy_version') == SHARED_POLICY_VERSION:
                        parents.append((root / name, value))
            self.assertEqual(len(parents), 1)
            parent_path, retained = parents[0]
            parent_raw = parent_path.read_bytes()
            parent_sha = hashlib.sha256(parent_raw).hexdigest()
            parent = parse_evaluation_report(parent_raw)
            self.assertEqual(parent.shared_assessment.result.task_count, 31)
            self.assertEqual(parent.shared_assessment.result.overall.model_dump(), {'lower': 77.25, 'upper': 87.98})
            old_keys = {task.task_key for task in parent.shared_assessment.tasks}
            added = {task.task_key for task in assessment.tasks} - old_keys
            self.assertEqual(len(added), 3)
            self.assertEqual([task.model_dump(mode='json') for task in assessment.tasks if task.task_key in old_keys],
                             [task.model_dump(mode='json') for task in parent.shared_assessment.tasks])
            self.assertEqual([row.model_dump(mode='json') for row in assessment.observations if row.task_key in old_keys],
                             [row.model_dump(mode='json') for row in parent.shared_assessment.observations])
            for key in added:
                self.assertFalse(any(row.task_key == key and row.dimension == 'availability' for row in assessment.observations))
                self.assertTrue(any(case.dimension == 'availability' and key in case.task_keys for case in assessment.cases))
                for dimension in ('functional', 'behavioral'):
                    rows = [row for row in assessment.observations if row.task_key == key and row.dimension == dimension]
                    self.assertTrue(rows)
                    self.assertTrue(all(row.verdict == Verdict.PASS for row in rows))
                self.assertEqual(next(task for task in assessment.tasks if task.task_key == key).outcome, 'completed')
            changed = report.model_copy(deep=True)
            observation = next(row for row in changed.shared_assessment.observations
                               if row.task_key in added and row.dimension == 'functional')
            observation.verdict = Verdict.FAIL
            with self.assertRaises(ValueError):
                verify_shared_report_sources(root, changed, hashes)
            self.assertEqual(hashlib.sha256(parent_path.read_bytes()).hexdigest(), parent_sha)
            self.assertEqual(json.loads(parent_path.read_bytes()), retained)


if __name__ == '__main__':
    unittest.main()
