"""One retained public cohort replay and essential integrity/state boundaries."""

from copy import deepcopy
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'packages/core/src'), str(ROOT / 'services/platform/src'), str(ROOT / 'scripts')]

from chain_execution_evidence import restore_package
from reputation_core.omen_execution import SAFE_FAILURE, SAFE_SUCCESS, verify_omen_execution
from reputation_platform.chain_evidence import build_execution_reviews
from reputation_platform.worker import evaluate


class ChainExecutionEvidenceTest(unittest.TestCase):
    def test_real_cohort_and_necessary_failure_boundaries(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            bundle = restore_package(root, ROOT / 'data/chain-execution-evidence-v1.tar.gz')
            captured = {}

            def record(proof, **kwargs):
                captured[kwargs['service_id']] = (deepcopy(proof), deepcopy(kwargs))
                return verify_omen_execution(proof, **kwargs)

            with (patch('socket.create_connection', side_effect=AssertionError('Offline replay contacted network')),
                  patch('reputation_platform.chain_evidence.verify_omen_execution', side_effect=record)):
                reviews = build_execution_reviews(root, bundle)
            self.assertEqual(len(reviews), 10)
            self.assertEqual([view.candidate_key for view, _ in reviews], [
                'olas-omen-trader-' + str(i) for i in (1953, 219, 1949, 415, 1968, 1781, 1788, 1969, 1784, 1684)])
            self.assertEqual([view.actions[0].verdict.value for view, _ in reviews],
                             ['PASS', 'PASS', 'UNKNOWN', 'PASS', 'PASS', 'PASS', 'PASS', 'UNKNOWN', 'PASS', 'PASS'])
            self.assertTrue(all(not hasattr(view, 'scores') for view, _ in reviews))
            self.assertNotIn('MultiSend', reviews[0][0].actions[0].method)
            self.assertIn('沿用已有授权', reviews[0][0].actions[0].method)
            self.assertIn('MultiSend → approve → buy', reviews[1][0].actions[0].method)
            self.assertTrue(any('签名阈值' in check.explanation for check in reviews[2][0].checks))
            proof, parameters = captured[219]
            failed = deepcopy(proof)
            next(log for log in failed['receipt']['logs'] if log['topics'][0] == SAFE_SUCCESS)['topics'][0] = SAFE_FAILURE
            self.assertEqual(verify_omen_execution(failed, **parameters).verdict.value, 'FAIL')
            wrong_position = deepcopy(proof)
            wrong_position['position_id_before'] = '0x' + f"{int(proof['position_id_before'], 16) + 1:064x}"
            self.assertEqual(verify_omen_execution(wrong_position, **parameters).verdict.value, 'FAIL')
            unsupported = deepcopy(proof)
            unsupported['transaction']['input'] = '0x00000000' + unsupported['transaction']['input'][10:]
            self.assertEqual(verify_omen_execution(unsupported, **parameters).verdict.value, 'UNKNOWN')

            cohort_source = root / json.loads(bundle.read_bytes())['inputs']['cohort']['path']
            with cohort_source.open('ab') as stream:
                stream.write(b' ')
            with self.assertRaisesRegex(ValueError, 'digest mismatch'):
                build_execution_reviews(root, bundle)

        repo = Mock()
        repo.get_agent.return_value = object()
        evaluate(repo, {'reference': 'eip155:100:0x9338b5153ae39bb89f50468e608ed9d764b755fd:219',
                        'id': 'local-test', 'fencing_token': 1}, 'worker', [], enabled=True, proxy='http://127.0.0.1:7897')
        self.assertEqual(repo.finalize_job.call_args.kwargs['status'], 'NEEDS_INFO')
        self.assertEqual(repo.finalize_job.call_args.kwargs['candidate_key'], 'olas-omen-trader-219')


if __name__ == '__main__':
    unittest.main()
