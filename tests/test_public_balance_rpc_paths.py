"""One narrow path-admission combination; no archive, database or network work."""
import json
from pathlib import Path
import unittest

from scripts.public_reports import public_path

ROOT = Path(__file__).resolve().parents[1]


class PublicBalanceRpcPaths(unittest.TestCase):
    def test_fixed_block_public_layout_and_private_negatives(self):
        fixture = json.loads((ROOT / 'tests/fixtures/public_balance_rpc_paths_case.json').read_bytes())
        self.assertEqual(len(fixture['public_paths']), 28)
        for name in fixture['public_paths']:
            self.assertEqual(public_path(name), name)
        sample = fixture['public_paths'][0]
        parts = sample.split('/')
        generic = sample.replace(parts[1], 'generic-trading-campaign-20300101', 1)
        self.assertEqual(public_path(generic), generic)
        for name in [
            sample.replace('/chain/', '/wallet/'),
            sample.replace('/chain/', '/'),
            sample.replace(parts[3], 'not-a-uuid', 1),
            sample.replace(parts[5], '00000000-0000-0000-0000-000000000000', 1),
            sample.replace(parts[1], parts[1] + '.private', 1),
            sample.replace(parts[1], 'secrets', 1),
            sample.replace(parts[1], 'password-campaign', 1),
            sample.replace(parts[1], 'apikey-campaign', 1),
            sample.replace(parts[1], 'api-key-campaign', 1),
            sample.replace('balance-after-', 'balance-before-'),
            sample.replace('balance-after-', 'balance_after_'),
            sample.replace('.observation.json', '.private.observation.json'),
            sample.replace('.observation.json', '.REQUEST_INTENT.json'),
            sample.replace('.observation.json', '.json'),
            sample.replace('balance-after-0', 'balance-after-password'),
            sample.replace('balance-after-0', 'balance-after-apikey'),
            sample.replace('/states/', '/states/../'),
            sample.replace('/', '\\'),
            'runtime/wallet/balance-after-0.observation.json',
            'runtime/wallet/balance-before.json',
            'runtime/wallet/password.json',
            'runtime/wallet/apikey.json',
        ]:
            with self.subTest(rejected=name), self.assertRaises(ValueError):
                public_path(name)


if __name__ == '__main__':
    unittest.main()
