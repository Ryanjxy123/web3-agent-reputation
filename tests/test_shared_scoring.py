"""One focused pure-rule acceptance; fixtures are not real Agent experiments."""
from copy import deepcopy
from datetime import datetime, timezone
import json
import unittest

from reputation_core import EvaluationReport, parse_evaluation_report
from reputation_core.scoring import SHARED_POLICY_VERSION, SWAP_POLICY_VERSION, calculate_scores
from reputation_core.shared_scoring import SharedAssessment, shared_legacy_scores


def fixture():
    groups = [{'group_id':key, 'title':key, 'selected':selected, 'source_references':['fixture-declaration']}
              for key, selected in [('binding', True), ('display', True), ('native', False)]]
    cases = []
    for case_id, dimension, group, criterion in (
            ('a', 'availability', None, 'response'), ('f-binding', 'functional', 'binding', 'binding'),
            ('f-display', 'functional', 'display', 'display'), ('b', 'behavioral', None, 'fulfillment')):
        cases.append({'case_id':case_id, 'capability_id':'swap', 'dimension':dimension,
            'declaration_group_id':group, 'title':case_id, 'criterion_ids':[criterion],
            'task_keys':['task-1','task-2'], 'normal_execution':dimension == 'behavioral', 'required_decisive':1})
    observations = []
    for case in cases:
        for key in case['task_keys']:
            verdict = ('FAIL' if case['case_id'] == 'f-display' and key == 'task-1' else
                       'UNKNOWN' if key == 'task-2' and case['case_id'] != 'f-binding' else 'PASS')
            observations.append({'task_key':key, 'case_id':case['case_id'], 'dimension':case['dimension'],
                'criterion_id':case['criterion_ids'][0], 'verdict':verdict, 'reason':'pure fixture',
                'evidence':['fixture-evidence'], 'measurement_validity':'valid',
                'elapsed_ms':100.0 if case['dimension'] == 'availability' else None})
    return {'capabilities':[
        {'capability_id':'swap', 'title':'Swap scope', 'selected':True, 'write_operation':True,
         'declaration_groups':groups},
        {'capability_id':'limit', 'title':'Unmeasured limit orders', 'selected':False, 'write_operation':True,
         'declaration_groups':[{'group_id':'limit', 'title':'Limit orders', 'selected':False,
                                'source_references':['fixture-declaration']}]}],
        'cases':cases,
        'tasks':[{'task_key':key, 'capability_id':'swap', 'input_summary':'pure fixture',
                  'outcome':'completed' if key == 'task-1' else 'unknown', 'attribution':'unknown',
                  'observed_at':None, 'evidence':['fixture-evidence']} for key in ('task-1','task-2')],
        'observations':observations}


def model(value):
    return SharedAssessment.model_validate_json(json.dumps(value))


class SharedScoringAcceptance(unittest.TestCase):
    def test_shared_scope_uncertainty_protection_and_legacy_boundaries(self):
        data = fixture()
        assessment = model(data)
        result = assessment.result
        self.assertEqual(result.task_count, 2)
        self.assertEqual(result.observation_count, 8)
        self.assertEqual(result.selected_scope_coverage, 'FULL')
        self.assertEqual(result.declaration_coverage, 'PARTIAL')
        self.assertEqual(result.score_status, 'AVAILABLE')
        self.assertEqual((result.functional.interval.lower, result.functional.interval.upper), (50, 75))
        self.assertEqual((result.overall.lower, result.overall.upper), (50, 90))
        self.assertEqual(result.functional.counts.planned, 2)  # Same tasks, several F criteria.
        self.assertIsNone(shared_legacy_scores(assessment).overall)
        self.assertIsNone(shared_legacy_scores(assessment).functional.value)  # No midpoint/lower-bound score.

        duplicated = deepcopy(data)
        duplicated['observations'].append(deepcopy(duplicated['observations'][0]))
        with self.assertRaisesRegex(ValueError, 'duplicate task/dimension/criterion'):
            model(duplicated)

        # More easy binding requests do not dilute the equally weighted display group.
        repeated = deepcopy(data)
        for number in range(3, 12):
            key = f'task-{number}'
            repeated['tasks'].append({**repeated['tasks'][0], 'task_key':key})
            repeated['cases'][1]['task_keys'].append(key)
            repeated['observations'].append({**repeated['observations'][2], 'task_key':key, 'verdict':'PASS'})
        self.assertEqual(model(repeated).result.functional.interval, result.functional.interval)

        # A known protective exit is neither an unknown transaction result nor a completed swap.
        protected = deepcopy(data)
        protected['tasks'][1]['outcome'] = 'protected_exit'
        protected['cases'][-1]['required_decisive'] = 2  # Explicit frozen normal-execution target.
        for observation in protected['observations']:
            if observation['dimension'] == 'behavioral':
                observation['verdict'] = 'PASS'  # Protection constraint was observed, not normal fulfillment.
        protection = model(protected).result
        self.assertEqual(protection.behavioral.counts.protected_exit, 1)
        self.assertEqual(protection.behavioral.counts.unknown, 0)
        self.assertEqual(protection.behavioral.counts.passed, 1)
        self.assertIsNone(protection.behavioral.interval)
        self.assertIsNone(protection.overall)

        invalid = deepcopy(data)
        invalid['observations'][0]['measurement_validity'] = 'invalid'
        invalid['observations'][0]['verdict'] = 'FAIL'
        self.assertEqual(model(invalid).result.availability.counts.failed, 0)
        self.assertEqual(model(invalid).result.availability.counts.measurement_invalid, 1)

        major = deepcopy(data)
        next(item for item in major['observations'] if item['verdict'] == 'FAIL')['critical'] = True
        self.assertEqual(model(major).result.risk_status, 'MAJOR_VIOLATION')

        report = EvaluationReport(policy_version=SHARED_POLICY_VERSION, candidate_key='fixture', name='Fixture',
            registration_reference='fixture-identity', generated_at=datetime(2026,1,1,tzinfo=timezone.utc),
            scope='Selected swap scope only', scope_exclusions=['Unmeasured limit orders'],
            evaluation_window='pure-rule fixture', approach='synthetic rule acceptance, no external requests',
            samples=[], source_references=['fixture-evidence'], limitations=[], shared_assessment=assessment)
        serialized = report.model_dump(mode='json')
        self.assertEqual(parse_evaluation_report(serialized).shared_assessment.result, result)
        serialized['shared_assessment']['result']['overall']['lower'] = 99
        with self.assertRaisesRegex(ValueError, 'supplied shared result differs'):
            parse_evaluation_report(serialized)
        self.assertEqual(calculate_scores([], policy_version=SWAP_POLICY_VERSION).functional.planned, 7)
