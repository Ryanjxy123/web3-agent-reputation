"""One offline check: actual public MCP bytes, complete isolated guards, no operator phase."""
import base64
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import unittest

from eth_hash.auto import keccak
from reputation_platform.cow_swap_protocol import CowSwapMismatch, derive_cow_argument
from reputation_platform.cow_swap_report import _derived

ROOT = Path(__file__).resolve().parents[1]


class CowCampaignDerivationAcceptance(unittest.TestCase):
    def test_real_build_isolation_hash_and_unsupported_expressions(self):
        fixture = json.loads((ROOT / 'tests/fixtures/cow_swap_pilot_public_case.json').read_bytes())
        prior = {}
        for row in fixture['files']:
            if '/fetch/' not in row['path'] or not row['path'].endswith('.response.bin'):
                continue
            raw = base64.b64decode(row['base64'], validate=True)
            self.assertEqual(hashlib.sha256(raw).hexdigest(), row['sha256'])
            stage = Path(row['path']).name.split('.')[0]
            prior[stage] = {'payload': json.loads(json.loads(raw)['result']['content'][0]['text'])}
        original = deepcopy(prior)
        portable = json.loads((ROOT / 'tests/fixtures/cow_campaign_derivation_case.json').read_bytes())
        directory = ROOT / 'runtime/ophis-cow-campaign-draft-20261029'
        old_path = directory / 'plan-draft.json'
        if old_path.exists():
            self.assertEqual(hashlib.sha256(old_path.read_bytes()).hexdigest(), portable['previous_draft_sha256'])
            draft_path = directory / 'plan-draft-v2.json'
            self.assertEqual(hashlib.sha256(draft_path.read_bytes()).hexdigest(), portable['draft_sha256'])
            old, plan = json.loads(old_path.read_bytes()), json.loads(draft_path.read_bytes())
            self.assertEqual(plan['status'], 'DRAFT')
            self.assertIsNone(plan['frozen_at'])
            self.assertEqual(old['cases'], plan['cases'])
            self.assertEqual(len(plan['tasks']), 30)
            for before, task in zip(old['tasks'], plan['tasks']):
                self.assertEqual(before['task_key'], task['task_key'])
                self.assertEqual(before['expected'], task['expected'])
                if not task['expected']['safe_rejection']:
                    self.assertEqual(before, task)
            self.assertEqual([t for t in plan['tasks'] if t['expected']['safe_rejection']], portable['tasks'])
            for source in plan['operator_policy']['source_refs']:
                self.assertEqual(hashlib.sha256((ROOT / source['path']).read_bytes()).hexdigest(), source['sha256'])
                self.assertEqual((ROOT / source['path']).read_bytes(), (ROOT / source['execute_path']).read_bytes())
        else:
            print('Local runtime draft/snapshot cross-check NOT_RUN; portable real-response derivation check runs below.')
        build = prior['build']['payload']
        baseline = {'chainId': portable['chain_id'], 'owner': portable['owner'], 'order': build['order'],
            'fullAppData': build['fullAppData'], 'signingDomain': build['signing']['domain'],
            'orderbookUrl': build['orderbookUrl']}
        for task in portable['tasks']:
            self.assertEqual([x['stage'] for x in task['requests']], ['quote', 'build', 'validate'])
            spec = task['requests'][-1]
            args = dict(spec['arguments'])
            for key, value in spec['derived_arguments'].items():
                args[key] = derive_cow_argument(value, prior)
                self.assertEqual(args[key], _derived(value, prior))
            self.assertEqual(set(args), set(baseline))
            self.assertEqual(set(args['order']), set(baseline['order']))
            invalid = task['expected']['invalid_field']
            restored = deepcopy(args)
            if invalid == 'appCode':
                app = json.loads(args['fullAppData'])
                original_app = json.loads(baseline['fullAppData'])
                self.assertEqual(app.pop('appCode'), 'offline-invalid-appcode')
                original_app.pop('appCode')
                self.assertEqual(app, original_app)
                self.assertEqual(args['order']['appData'], '0x' + keccak(args['fullAppData'].encode()).hex())
                restored['fullAppData'] = baseline['fullAppData']
                restored['order']['appData'] = baseline['order']['appData']
            elif invalid in {'receiver', 'appData', 'feeAmount', 'expired'}:
                key = 'validTo' if invalid == 'expired' else invalid
                self.assertNotEqual(restored['order'][key], baseline['order'][key])
                restored['order'][key] = baseline['order'][key]
            elif invalid == 'domain':
                self.assertNotEqual(restored['signingDomain']['verifyingContract'], baseline['signingDomain']['verifyingContract'])
                restored['signingDomain']['verifyingContract'] = baseline['signingDomain']['verifyingContract']
            elif invalid == 'orderbook':
                self.assertNotEqual(restored['orderbookUrl'], baseline['orderbookUrl'])
                restored['orderbookUrl'] = baseline['orderbookUrl']
            self.assertEqual(restored, baseline, task['task_id'])
        self.assertEqual(prior, original, 'Derivation must not mutate retained response objects')
        self.assertEqual(derive_cow_argument({'rule': 'quote-minimum', 'stage': 'quote',
            'pointer': '/quote/buyAmount', 'slippage_bps': 50}, prior),
            str((int(prior['quote']['payload']['quote']['buyAmount']) * 9950 + 9999) // 10000))
        for spec in [
            {'rule': 'eval', 'code': 'anything'},
            {'rule': 'object-overlay', 'base': {'rule': 'stage-value', 'stage': 'build', 'pointer': '/order'},
             'overrides': {'/new-field': 'unreviewed'}},
            {'rule': 'keccak-utf8', 'value': {'rule': 'stage-value', 'stage': 'build', 'pointer': '/order'}},
        ]:
            with self.assertRaises(CowSwapMismatch):
                derive_cow_argument(spec, prior)
        deep = {'rule': 'stage-value', 'stage': 'build', 'pointer': '/fullAppData'}
        for _ in range(10):
            deep = {'rule': 'keccak-utf8', 'value': deep}
        with self.assertRaises(CowSwapMismatch):
            derive_cow_argument(deep, prior)


if __name__ == '__main__':
    unittest.main()
