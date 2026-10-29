"""One targeted offline acceptance for retained real typed HTTP400 responses."""
import copy
import json
from pathlib import Path
import unittest
from reputation_core import Verdict
from reputation_platform import atomic_swap_report as adapter


class TypedRejectionAcceptance(unittest.TestCase):
    def test_real_errors_match_independent_invalid_fields_and_success_summary_does_not(self):
        fixture = json.loads((Path(__file__).parent/'fixtures/atomic_swap_rejection_case.json').read_bytes())
        class Evidence:
            def json(self, path):
                return fixture['schema']
        plan = {'source_snapshot': {'path': 'retained-openapi'}, 'response_mapping': fixture['mapping']}
        for case in fixture['cases']:
            rows = [{'complete': True, 'obs': {'http_status': 400}, 'body': case['response']}]
            metrics, _ = adapter._metrics(Evidence(), plan, None, case['planned'], {}, rows)
            # Generic range text does not identify the omitted token field.
            expected = Verdict.UNKNOWN if case['planned']['task_id'] in ('A33', 'A34') else Verdict.PASS
            self.assertEqual(metrics['safe-rejection'][0], expected, case['planned']['task_id'])
        case = fixture['cases'][0]
        success = dict(case['response'], kind='result')
        self.assertIsNone(adapter._rejection_error(success, '/error'))
        unrelated = dict(case['response'], summary='Upstream RPC unavailable while quoting amount')
        rows = [{'complete': True, 'obs': {'http_status': 400}, 'body': unrelated}]
        self.assertEqual(adapter._metrics(Evidence(), plan, None, case['planned'], {}, rows)[0]['safe-rejection'][0], Verdict.UNKNOWN)
        mixed = copy.deepcopy(case['planned']); mixed['requests'][0]['json']['slippageBps'] = 0
        invalid = adapter._invalid_input_fields(Evidence(), plan, mixed)
        self.assertFalse(adapter._rejection_matches(case['response']['summary'], mixed, invalid))
        self.assertEqual(adapter._rejection_error({'jsonrpc':'2.0','error':{'code':-32602,'message':'sellAmount must be positive'}}, '/error'), 'sellAmount must be positive')


if __name__ == '__main__':
    unittest.main()
