"""One display regression using real public H47 bytes, never new business data."""

import base64
import copy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import zlib

from reputation_core import MeasurementPurpose, SampleExplanation, ScoredSample, Verdict
from reputation_core.reporting import EvaluationReport
from reputation_platform.report_chain_view import build_report_chain_evidence


FIXTURES = Path(__file__).parent / 'fixtures'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


class CampaignObservationChainView(unittest.TestCase):
    def test_real_h47_observations_bound_swap_fees_integrity_and_legacy_bodies(self):
        fixture = json.loads((FIXTURES / 'report_chain_campaign_h47_case.json').read_bytes())
        with tempfile.TemporaryDirectory(prefix='chain-view-h47-') as temporary:
            root, permitted = Path(temporary), {}
            for item in fixture['files']:
                raw = zlib.decompress(base64.b64decode(item['base64_zlib'], validate=True))
                self.assertEqual(sha(raw), item['sha256'])
                path = root / item['path']
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(raw)
                permitted[item['path']] = item['sha256']

            h47 = SampleExplanation.model_validate_json(json.dumps(fixture['h47_sample']))
            h02 = SampleExplanation.model_validate_json(json.dumps(fixture['h02_sample']))
            # This minimal display report is engineering input. The published
            # report/score and the original raw HTTP/RPC bytes are not rewritten.
            report = EvaluationReport(candidate_key='controlled-chain-view-only', name='Display regression',
                registration_reference='controlled-display-only', generated_at=datetime(2026, 10, 29, tzinfo=timezone.utc),
                scope='Public H47/H02 display subset only', scope_exclusions=[], evaluation_window='Retained public originals',
                approach='Offline display regression, not an assessment', samples=[h47, h02],
                source_references=list(permitted), limitations=[])
            key, tx_hash = h47.sample.task_key, fixture['h47_transaction_hash']

            view = build_report_chain_evidence(root, report, permitted, key)
            self.assertEqual(len(view.actions), 8)
            self.assertEqual({action.transaction_hash for action in view.actions}, {tx_hash})
            self.assertFalse(set(fixture['fee_transaction_hashes']) & {action.transaction_hash for action in view.actions})
            swaps = [action for action in view.actions if action.action == 'swap']
            self.assertEqual(len(swaps), 1)
            self.assertIn('USDC 0.12', swaps[0].summary)
            self.assertIn('WETH 0.000050787661365675', swaps[0].summary)
            self.assertIn('WETH 0.000050533723058845', swaps[0].summary)
            # Unscoped layout remains the first eligible sample's brief view.
            default = build_report_chain_evidence(root, report, permitted)
            self.assertEqual(len(default.actions), 1)
            self.assertEqual(default.actions[0].transaction_hash, tx_hash)
            # H02 is a retained-source pointer, not an inline unsent task.
            retained = build_report_chain_evidence(root, report, permitted, h02.sample.task_key)
            self.assertTrue(retained.actions)
            self.assertEqual({action.transaction_hash for action in retained.actions},
                {'0xb4c598c9e9c215884f99c48cfb32692e4a699e23505c10fd3aa0a62ea4355e98'})

            # Controlled attachment contamination: a known unsent task cannot
            # acquire another task's execution or the batch's fee transactions.
            unsent = h47.model_copy(deep=True)
            unsent.sample.task_key = fixture['known_unexecuted_task_key']
            unsent.sample.sample_id = 'controlled-known-unexecuted-display'
            unsent_report = report.model_copy(update={'samples': [unsent]})
            self.assertEqual(build_report_chain_evidence(root, unsent_report, permitted,
                unsent.sample.task_key).actions, [])

            transaction_name = next(name for name in h47.sample.evidence
                if json.loads(json.loads((root / name).read_bytes())['request_json']).get('method')
                == 'eth_getTransactionByHash'
                and json.loads(json.loads((root / name).read_bytes())['request_json'])['params'] == [tx_hash])
            observation_path = root / transaction_name
            observation_raw = observation_path.read_bytes()
            observation = json.loads(observation_raw)
            body_name = (Path(transaction_name).parent / observation['response_file']).as_posix()
            body_path, body_raw = root / body_name, (root / body_name).read_bytes()
            body_path.unlink()
            with self.assertRaises((OSError, ValueError)):
                build_report_chain_evidence(root, report, permitted, key)
            body_path.write_bytes(body_raw + b' ')
            with self.assertRaisesRegex(ValueError, 'SHA256'):
                build_report_chain_evidence(root, report, permitted, key)
            body_path.write_bytes(body_raw)

            for changes in ({'response_file': '../transaction.response.bin'}, {'response_file': '..\\transaction.response.bin'},
                            {'body_complete': False},
                            {'http_status': 500}, {'error_kind': 'controlled-error'}, {'response_sha256': '0' * 64}):
                altered = dict(observation, **changes)
                altered_raw = json.dumps(altered).encode()
                observation_path.write_bytes(altered_raw)
                changed_hashes = dict(permitted, **{transaction_name: sha(altered_raw)})
                with self.subTest(observation=changes), self.assertRaises(ValueError):
                    build_report_chain_evidence(root, report, changed_hashes, key)
            observation_path.write_bytes(observation_raw)

            # Even a coherently rehashed body must answer its exact RPC request.
            wrong = json.loads(body_raw)
            wrong['result']['hash'] = fixture['fee_transaction_hashes'][0]
            wrong_raw = json.dumps(wrong).encode()
            altered_raw = json.dumps(dict(observation, response_sha256=sha(wrong_raw))).encode()
            body_path.write_bytes(wrong_raw)
            observation_path.write_bytes(altered_raw)
            changed_hashes = dict(permitted, **{transaction_name: sha(altered_raw), body_name: sha(wrong_raw)})
            with self.assertRaisesRegex(ValueError, 'requested hash'):
                build_report_chain_evidence(root, report, changed_hashes, key)
            body_path.write_bytes(body_raw)
            observation_path.write_bytes(observation_raw)

            for name in (fixture['origin'], fixture['source']):
                path = root / name
                original = path.read_bytes()
                path.write_bytes(original + b' ')
                with self.subTest(authenticated_source=name), self.assertRaisesRegex(ValueError, 'SHA256'):
                    build_report_chain_evidence(root, report, permitted, key)
                path.write_bytes(original)

            # Original direct-body naming remains compatible without an origin.
            legacy_paths, legacy_hashes = [], {}
            for kind in ('transaction', 'receipt', 'block'):
                name = f'legacy-history-98-wrap-{kind}.response.bin'
                raw = (FIXTURES / 'behavior-98' / f'wrap-{kind}.json').read_bytes()
                (root / name).write_bytes(raw)
                legacy_paths.append(name)
                legacy_hashes[name] = sha(raw)
            sample = ScoredSample(sample_id='controlled-legacy-view', task_key='controlled-legacy-view',
                purpose=MeasurementPurpose.BEHAVIORAL, verdict=Verdict.PASS, elapsed_ms=None,
                reason='Existing historical wrap originals', evidence=legacy_paths)
            explanation = SampleExplanation(sample=sample, title='Legacy body compatibility', input_summary='Historical wrap',
                claimed_output='Historical wrap', independent_result='Public retained originals', checks=[])
            legacy_report = report.model_copy(update={'samples': [explanation]})
            legacy = build_report_chain_evidence(root, legacy_report, legacy_hashes, sample.task_key)
            self.assertEqual([action.action for action in legacy.actions], ['wrap'])


if __name__ == '__main__':
    unittest.main()
