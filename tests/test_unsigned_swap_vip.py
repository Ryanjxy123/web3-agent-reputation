"""One real reverse quote, critical permit negatives, and old ABI equivalence.

Mutations below are engineering checks, never additional public task samples.
"""
import hashlib
import json
from pathlib import Path
import unittest

from reputation_platform.unsigned_swap_protocol import (
    UNISWAP_V3_VIP,
    UnsignedSwapMismatch,
    decode_unsigned_swap,
    verify_unsigned_swap_intent,
)


FIXTURES = Path(__file__).parent / 'fixtures'


class UnsignedSwapVipTests(unittest.TestCase):
    def test_real_vip_reverse_quote_and_original_quote_equivalence(self):
        case = json.loads((FIXTURES / 'unsigned_swap_vip_case.json').read_bytes())
        transaction, expected = case['transaction'], case['expected']
        fact = verify_unsigned_swap_intent(transaction, expected, chain_id=case['chain_id'])
        self.assertEqual(fact['protocol'], 'hydrex-multirouter')
        self.assertTrue(fact['call_shapes_supported'])
        self.assertFalse(fact['opaque_payloads'])
        self.assertFalse(fact['unsupported_actions'])
        self.assertEqual(fact['earliest_known_deadline'], 1793181491)
        self.assertFalse(fact['deployment_verified'])
        self.assertFalse(fact['simulation_verified'])
        self.assertFalse(fact['execution_verified'])
        action, = [a for a in fact['actions'] if a['kind'] == 'uniswap-v3-vip']
        self.assertEqual((action['token_in'], action['token_out'], action['amount']),
                         (expected['token_in'], expected['token_out'], expected['amount_in']))
        self.assertEqual(action['recipient'], action['target'])
        hop, = action['hops']
        self.assertEqual((hop['fork_id'], hop['pool_id'], hop['sqrt_price_limit']),
                         (6, 200, 4295128740))
        self.assertEqual((hop['token_in'], hop['token_out']),
                         (expected['token_in'], expected['token_out']))
        self.assertFalse(hop['pool_binding_verified'])
        fee, = [f for f in fact['fees'] if f['kind'] == 'settler-output-balance-fraction']
        self.assertEqual((fee['token'], fee['ppm'], fee['denominator']),
                         (expected['token_out'], 1500, 1_000_000))

        raw = bytes.fromhex(transaction['data'][2:])
        signature = bytes.fromhex(UNISWAP_V3_VIP[2:])
        self.assertEqual(raw.count(signature), 1)
        start = raw.index(signature) + 4

        def word(slot):
            return int.from_bytes(raw[start + slot * 32:start + (slot + 1) * 32], 'big')

        def changed_word(slot, value):
            changed = bytearray(raw)
            changed[start + slot * 32:start + (slot + 1) * 32] = value.to_bytes(32, 'big')
            return dict(transaction, data='0x' + changed.hex())

        # A nonce-bearing or signed permit is outside the exact AllowanceHolder
        # flow. Alias the path bytes as the signature to make it nonempty.
        for slot, value in ((3, 1), (6, word(5)), (2, expected['amount_in'] + 1),
                            (1, 1), (0, 1)):
            with self.subTest(unsafe_vip_slot=slot), self.assertRaises(ValueError):
                verify_unsigned_swap_intent(changed_word(slot, value), expected, chain_id=8453)
        shortened = decode_unsigned_swap(changed_word(4, 1793181400), chain_id=8453)
        self.assertEqual(shortened['earliest_known_deadline'], 1793181400)

        changed = bytearray(raw)
        path_start = start + word(5) + 32
        changed[path_start + 24:path_start + 44] = bytes.fromhex(expected['token_in'][2:])
        with self.assertRaisesRegex(ValueError, 'VIP output path'):
            decode_unsigned_swap(dict(transaction, data='0x' + changed.hex()), chain_id=8453)
        with self.assertRaises(UnsignedSwapMismatch):
            verify_unsigned_swap_intent(transaction, dict(expected, minimum_out=940252), chain_id=8453)

        # These digests were calculated from the unchanged original decoder at
        # HEAD and the two already-public real quote fixtures, before this change.
        originals = json.loads((FIXTURES / 'unsigned_swap_protocol_cases.json').read_bytes())
        self.assertEqual(len(originals), len(case['original_fixture_decoded_sha256']))
        for original, digest in zip(originals, case['original_fixture_decoded_sha256']):
            decoded = decode_unsigned_swap(original['transaction'], chain_id=original['chain_id'])
            actual = hashlib.sha256(json.dumps(decoded, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
            self.assertEqual(actual, digest)
