import copy
import json
from pathlib import Path
import unittest

from reputation_platform.atomic_swap_protocol import normalize_atomic_swap, verify_atomic_swap_intent
from reputation_platform.unsigned_swap_protocol import UnsupportedUnsignedSwap, UnsignedSwapMismatch


FIXTURE = Path(__file__).parent / 'fixtures' / 'atomic_swap_protocol_case.json'


class AtomicSwapProtocolTests(unittest.TestCase):
    def test_real_seven_call_batch_and_critical_risk_boundaries(self):
        source = json.loads(FIXTURE.read_text(encoding='utf8'))
        plan, expected = source['plan'], source['expected']
        untouched = copy.deepcopy(source)
        fact = verify_atomic_swap_intent(plan, expected)
        self.assertTrue(fact['calldata_binding_verified'])
        self.assertEqual(fact['amount_in'], 100000)
        self.assertEqual(fact['minimum_out'], 42702607642243)
        self.assertEqual(fact['inner_swap_minimum_out'], 0)
        self.assertEqual(fact['commands_hex'], '0x0004')
        self.assertEqual(fact['path_hops'], [{
            'token_in': expected['token_in'].lower(), 'token_out': expected['token_out'].lower(),
            'tick_spacing': 50, 'pool_binding_verified': False}])
        self.assertEqual(fact['earliest_known_deadline'], 1793202471)
        self.assertEqual(fact['required_executor'], expected['recipient'].lower())
        self.assertEqual(fact['minimum_out_check'], 'router-total-token-balance-before-sweep')
        self.assertTrue(fact['requires_router_output_balance_accounting'])
        self.assertEqual(fact['encoded_cleanup_amounts'],
            {'token_to_permit2': 0, 'token_to_router': 0, 'permit2_to_router': 0})
        for key in ('deployment_verified', 'simulation_verified', 'execution_verified',
                    'recipient_balance_delta_verified', 'atomic_execution_verified', 'fee_state_verified'):
            self.assertFalse(fact[key])
        self.assertNotIn('calldata_binding_verified', normalize_atomic_swap(plan))
        self.assertRegex(fact['call_sequence_hash'], r'^0x[0-9a-f]{64}$')
        self.assertEqual(len(fact['required_state_reads']), 7)
        self.assertTrue(any(x['signature'] == 'allowance(address,address,address)'
                            and x['required_after_amount'] == 0 for x in fact['required_state_reads']))
        self.assertFalse(fact['required_deployment_bindings'][0]['getter_available'])

        for field in expected:
            wrong = dict(expected)
            wrong[field] = ('1' if field in ('amount_in', 'minimum_out') else '0x' + '11' * 20)
            with self.subTest(independent_mismatch=field), self.assertRaises(UnsignedSwapMismatch):
                verify_atomic_swap_intent(plan, wrong)
        missing = dict(expected); missing.pop('recipient')
        with self.assertRaises(ValueError):
            verify_atomic_swap_intent(plan, missing)
        complete = dict(expected, router=fact['router'], permit2=fact['permit2'],
                        executor=fact['required_executor'], deadline=1793202471, chain_id=8453)
        self.assertTrue(verify_atomic_swap_intent(plan, complete)['calldata_binding_verified'])
        for field in ('router', 'permit2', 'executor', 'deadline', 'chain_id'):
            wrong = dict(complete)
            wrong[field] = 1 if field in ('deadline', 'chain_id') else '0x' + '11' * 20
            with self.subTest(optional_binding=field), self.assertRaises(UnsignedSwapMismatch):
                verify_atomic_swap_intent(plan, wrong)

        def args(call):
            return bytearray.fromhex(call['data'][10:])

        def word(raw, at):
            return int.from_bytes(raw[at:at + 32], 'big')

        def changed_word(index, offset, value):
            changed = copy.deepcopy(plan)
            raw = args(changed['calls'][index])
            raw[offset:offset + 32] = value.to_bytes(32, 'big')
            changed['calls'][index]['data'] = changed['calls'][index]['data'][:10] + raw.hex()
            return changed

        execute_args = args(plan['calls'][4])
        inputs = word(execute_args, 32)
        v3 = inputs + 32 + word(execute_args, inputs + 32) + 32
        sweep = inputs + 32 + word(execute_args, inputs + 64) + 32
        # These offsets come from the documented ABI, not decoder helpers.
        self.assertEqual(word(execute_args, v3 + 32), 100000)
        self.assertEqual(word(execute_args, sweep + 64), 42702607642243)
        failures = {
            'token allowance unlimited': changed_word(2, 32, 2**256 - 1),
            'token cleanup nonzero': changed_word(6, 32, 1),
            'initial router allowance nonzero': changed_word(0, 32, 1),
            'wrong token approval spender': changed_word(2, 0, int('11' * 20, 16)),
            'Permit2 amount overflow': changed_word(3, 64, 2**160),
            'Permit2 wrong router': changed_word(3, 32, int('11' * 20, 16)),
            'Permit2 cleanup nonzero': changed_word(5, 64, 1),
            'Permit2 expiration truncation': changed_word(3, 96, 2**48),
            'execute deadline missing': changed_word(4, 64, 0),
            'SWEEP uint160 truncation': changed_word(4, sweep + 64, 2**160 + 42702607642243),
            'SWEEP wrong token': changed_word(4, sweep, int(expected['token_in'], 16)),
            'SWEEP implicit lockedBy': changed_word(4, sweep + 32, 1),
            'output escapes before SWEEP': changed_word(4, v3, int(expected['recipient'], 16)),
            'payer is router': changed_word(4, v3 + 128, 0),
            'noncanonical bool': changed_word(4, v3 + 128, 2),
            'overlapping command input': changed_word(4, inputs + 64, word(execute_args, inputs + 32)),
        }
        for name, changed in failures.items():
            with self.subTest(risk=name), self.assertRaises(ValueError):
                verify_atomic_swap_intent(changed, expected)

        for command in (0x80, 0x40, 0x0a, 0x21):
            changed = copy.deepcopy(plan)
            raw = args(changed['calls'][4])
            raw[128] = command
            changed['calls'][4]['data'] = changed['calls'][4]['data'][:10] + raw.hex()
            with self.subTest(opaque_or_permit_command=command), self.assertRaises(UnsupportedUnsignedSwap):
                normalize_atomic_swap(changed)

        wrong_recipient = changed_word(4, sweep + 32, int('11' * 20, 16))
        with self.assertRaises(UnsignedSwapMismatch):
            verify_atomic_swap_intent(wrong_recipient, expected)
        wrong_amount = changed_word(4, v3 + 32, 100001)
        with self.assertRaises(ValueError):
            verify_atomic_swap_intent(wrong_amount, expected)

        for mutate in (
            lambda x: x['calls'].pop(),
            lambda x: x.update(calls=[x['calls'][4]]),
            lambda x: x['calls'].append({'to': '0x'+'11'*20, 'value': '0', 'data': '0x40c10f19'}),
            lambda x: x['calls'][4].update(value='1'),
            lambda x: x['calls'][4].update(chainId=1),
            lambda x: x['calls'][4].update(operation=1),
            lambda x: x['calls'][4].update(data=x['calls'][4]['data']+'00'),
            lambda x: x['calls'][4].update(data='0x60806040'),
        ):
            changed = copy.deepcopy(plan); mutate(changed)
            with self.subTest(unsupported_batch=changed['calls'][-1]['data'][:10]), self.assertRaises(ValueError):
                normalize_atomic_swap(changed)

        # Publicly known integer timestamps, supplied by evidence, control all
        # expiry facts. No current time or network request is involved.
        shorter = changed_word(3, 96, 1793202400)
        self.assertEqual(normalize_atomic_swap(shorter)['earliest_known_deadline'], 1793202400)
        self.assertEqual(normalize_atomic_swap(plan, quote_deadline=1793202300)['earliest_known_deadline'], 1793202300)
        # Relocating every router reference is accepted as an unverified new
        # deployment; the parser contains no particular provider/router allowlist.
        relocated = copy.deepcopy(plan)
        old_router, new_router = fact['router'], '0x'+'ab'*20
        for call in relocated['calls']:
            if call['to'].lower() == old_router: call['to'] = new_router
            call['data'] = call['data'].lower().replace(old_router[2:], new_router[2:])
        relocated_fact = verify_atomic_swap_intent(relocated, expected)
        self.assertEqual(relocated_fact['router'], new_router)
        self.assertFalse(relocated_fact['deployment_verified'])
        self.assertEqual(source, untouched)


if __name__ == '__main__':
    unittest.main()
