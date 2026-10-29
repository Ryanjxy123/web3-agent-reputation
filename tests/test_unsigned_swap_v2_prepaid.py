"""Real prepaid V2 quote and necessary funding/encoding negatives; no network."""
import hashlib
import json
from pathlib import Path
import unittest

from reputation_platform.unsigned_swap_protocol import (
    TRANSFER_FROM, UNISWAP_V2, decode_unsigned_swap, verify_unsigned_swap_intent,
)

FIXTURES = Path(__file__).parent / 'fixtures'


class UnsignedSwapV2PrepaidTests(unittest.TestCase):
    def test_real_prepaid_pool_binding_and_previous_quote_equivalence(self):
        case = json.loads((FIXTURES / 'unsigned_swap_v2_prepaid_case.json').read_bytes())
        transaction, expected = case['transaction'], case['expected']
        fact = verify_unsigned_swap_intent(transaction, expected, chain_id=case['chain_id'])
        self.assertEqual(UNISWAP_V2, '0x103b48be')
        self.assertEqual(fact['earliest_known_deadline'], 1793212909)
        self.assertTrue(fact['call_shapes_supported'])
        self.assertFalse(fact['unsupported_actions'])
        self.assertEqual((fact['amount_in'], fact['minimum_out']), (20_000_000_000_000, 46_714))
        route, = [a for a in fact['actions'] if a['kind'] == 'uniswap-v2']
        transfer, = [a for a in fact['actions'] if a['kind'] == 'allowanceholder-transfer']
        pool = '0xab067c01c7f5734da168c699ae9d23a4512c9fdb'
        settler = '0x7d6839415693801e94cdc4a7d732c9a3fdbbd1d7'
        self.assertEqual((route['target'], transfer['target']), (pool, pool))
        self.assertEqual((route['recipient'], route['token_in'], route['expected_token_out']),
                         (settler, expected['token_in'], expected['token_out']))
        self.assertEqual((route['balance_ppm'], route['pool_fee_bps'], route['action_minimum_out']), (0, 25, 0))
        self.assertTrue(route['input_prepaid'])
        self.assertTrue(route['token0_for_token1'])
        self.assertFalse(route['sell_token_has_transfer_fee'])
        self.assertFalse(route['pool_tokens_verified'])
        self.assertIn(pool, fact['required_contracts'])
        for flag in ('deployment_verified', 'simulation_verified', 'execution_verified', 'fee_state_verified'):
            self.assertFalse(fact[flag])
        fee, = [f for f in fact['fees'] if f['kind'] == 'settler-output-balance-fraction']
        self.assertEqual((fee['token'], fee['ppm']), (expected['token_out'], 1500))
        raw = bytes.fromhex(transaction['data'][2:])

        def changed(*edits):
            result = bytearray(raw)
            for selector, slot, value in edits:
                signature = bytes.fromhex(selector[2:])
                self.assertEqual(raw.count(signature), 1)
                start = raw.index(signature) + 4 + slot * 32
                result[start:start + 32] = value.to_bytes(32, 'big')
            return dict(transaction, data='0x' + result.hex())

        # Recipient/pool/token mismatch, partial funding, nonce-bearing permit,
        # reserved flag bits, oversized uint24 and impossible fee all fail closed.
        negatives = [(TRANSFER_FROM, slot, value) for slot, value in
                     ((0, 1), (1, 1), (2, expected['amount_in'] + 1), (3, 1))]
        negatives += [(UNISWAP_V2, slot, value) for slot, value in
                      ((0, 1), (1, 1), (2, 1), (2, 1_000_000), (3, 1),
                       (4, 0x1905), (4, 1 << 24), (4, 10_000 << 8))]
        for edit in negatives:
            with self.subTest(edit=edit), self.assertRaises(ValueError):
                decode_unsigned_swap(changed(edit), chain_id=8453)
        # An empty-signature transfer must remain empty even for pool prepayment.
        signed = bytearray(raw)
        start = raw.index(bytes.fromhex(TRANSFER_FROM[2:])) + 4
        offset = int.from_bytes(raw[start + 160:start + 192], 'big')
        signed[start + offset:start + offset + 32] = (1).to_bytes(32, 'big')
        with self.assertRaises(ValueError):
            decode_unsigned_swap(dict(transaction, data='0x' + signed.hex()), chain_id=8453)

        # Ordinary Settler-funded V2 is allowed only at the full balance fraction.
        regular = changed((TRANSFER_FROM, 0, int(settler, 16)), (UNISWAP_V2, 2, 1_000_000))
        normal = verify_unsigned_swap_intent(regular, expected, chain_id=8453)
        normal_route, = [a for a in normal['actions'] if a['kind'] == 'uniswap-v2']
        self.assertFalse(normal_route['input_prepaid'])
        self.assertEqual(normal_route['balance_ppm'], 1_000_000)
        with self.assertRaises(ValueError):
            decode_unsigned_swap(changed((TRANSFER_FROM, 0, int(settler, 16))), chain_id=8453)
        shortened = decode_unsigned_swap(changed((TRANSFER_FROM, 4, 1793212800)), chain_id=8453)
        self.assertEqual(shortened['earliest_known_deadline'], 1793212800)

        # Four unchanged real fixtures retain their exact pre-change HEAD facts.
        for old in case['original_fixture_decoded_sha256']:
            value = json.loads((FIXTURES / old['file']).read_bytes())
            original = value[old['index']] if isinstance(value, list) else value
            decoded = decode_unsigned_swap(original['transaction'], chain_id=original['chain_id'])
            actual = hashlib.sha256(json.dumps(decoded, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
            self.assertEqual(actual, old['sha256'])
