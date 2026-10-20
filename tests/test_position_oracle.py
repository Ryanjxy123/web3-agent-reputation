"""Synthetic fixed-block ABI fixtures; these are not real Agent evaluations."""

from copy import deepcopy
import unittest

from reputation_core import Verdict
from reputation_platform.position_oracle import FACTORY, NPM, position_reference, verify_position_record

POSITION = '123'
TOKEN0, TOKEN1 = '0x' + '11' * 20, '0x' + '22' * 20


def position_bytes(**changes):
    fields = {'nonce': 0, 'operator': 0, 'token0': int(TOKEN0, 16), 'token1': int(TOKEN1, 16),
              'fee': 500, 'tickLower': -100, 'tickUpper': 100, 'liquidity': 10,
              'growth0': 0, 'growth1': 0, 'owed0': 0, 'owed1': 0}
    fields.update(changes)
    return '0x' + ''.join(f'{v % 2**256:064x}' for v in fields.values())


def evidence():
    return {'chain': '0x38', 'head': '0xa4',
            'header': {'number': '0x64', 'hash': '0x' + '33' * 32, 'timestamp': '0x1'},
            'npm_code': '0x6000', 'factory': '0x' + f'{int(FACTORY, 16):064x}',
            'factory_code': '0x6000', 'positions': position_bytes(),
            'owner': '0x' + f'{int("44" * 20, 16):064x}'}


def claim():
    return {'positionId': POSITION, 'token0': TOKEN0, 'token1': TOKEN1,
            'fee': 500, 'tickLower': -100, 'tickUpper': 100}


def verify(answer=None, values=None, **kwargs):
    return verify_position_record(claim() if answer is None else answer, POSITION, kwargs.get('chain_id', 56),
                                  kwargs.get('npm', NPM), kwargs.get('factory', FACTORY),
                                  evidence() if values is None else values)


class PositionOracleTests(unittest.TestCase):
    def test_complete_static_match_and_confirmation_binding(self):
        verdict, _, detail = verify()
        self.assertEqual(verdict, Verdict.PASS)
        self.assertEqual(detail['expected'], claim())
        self.assertEqual(detail['confirmations'], 64)
        self.assertEqual(detail['mismatched_fields'], [])
        self.assertEqual(position_reference(POSITION, 56, NPM, FACTORY, evidence())['block_number'], 100)

    def test_typed_wrong_answer_subject_and_reported_chain_are_failures(self):
        for field, value in {'positionId': '124', 'token0': TOKEN1, 'token1': TOKEN0,
                             'fee': 100, 'tickLower': -90, 'tickUpper': 90,
                             'reportedChain': 97, 'reportedPositionId': '124'}.items():
            with self.subTest(field=field):
                answer = {**claim(), field: value}
                verdict, _, detail = verify(answer)
                self.assertEqual(verdict, Verdict.FAIL)
                self.assertIn(field, detail['mismatched_fields'])

    def test_missing_or_malformed_claim_never_becomes_failure(self):
        self.assertEqual(verify_position_record(None, POSITION, 56, NPM, FACTORY, evidence())[0], Verdict.UNKNOWN)
        for field in claim():
            for value in (None, [], True):
                with self.subTest(field=field, value=value):
                    self.assertEqual(verify({**claim(), field: value})[0], Verdict.UNKNOWN)
            answer = claim()
            answer.pop(field)
            self.assertEqual(verify(answer)[0], Verdict.UNKNOWN)
        for field, value in {'fee': 500.0, 'tickLower': '-100', 'reportedChain': True,
                             'reportedPositionId': '0123'}.items():
            self.assertEqual(verify({**claim(), field: value})[0], Verdict.UNKNOWN)

    def test_incomplete_or_conflicting_references_are_unknown_even_for_wrong_claim(self):
        for field in evidence():
            with self.subTest(field=field):
                values = evidence()
                values.pop(field)
                self.assertEqual(verify({**claim(), 'fee': 100}, values)[0], Verdict.UNKNOWN)
                with self.assertRaises(ValueError):
                    position_reference(POSITION, 56, NPM, FACTORY, values)
        for field, value in {'chain': '0x1', 'head': '0xa3', 'npm_code': '0x',
                             'factory_code': '0x0', 'factory': '0x' + '0' * 64,
                             'owner': '0x' + '0' * 64, 'positions': '0x'}.items():
            self.assertEqual(verify(values={**evidence(), field: value})[0], Verdict.UNKNOWN)
        for field, value in {'number': '0x63', 'hash': '0x1234', 'timestamp': '0x00'}.items():
            values = evidence()
            values['header'][field] = value
            self.assertEqual(verify(values=values)[0], Verdict.UNKNOWN)

    def test_canonical_abi_address_width_tick_sign_and_protocol_bounds(self):
        for change in ({'nonce': 2**96}, {'operator': 2**160}, {'token0': 0},
                       {'token1': 2**160}, {'fee': 2**24}, {'fee': 0},
                       {'tickLower': 2**24 - 100}, {'tickUpper': 2**23},
                       {'tickLower': -887273}, {'tickUpper': 887273},
                       {'tickLower': 100}, {'liquidity': 2**128}, {'owed0': 2**128}):
            with self.subTest(change=change):
                self.assertEqual(verify(values={**evidence(), 'positions': position_bytes(**change)})[0], Verdict.UNKNOWN)
        for field in ('factory', 'owner'):
            values = evidence()
            values[field] = '0x' + 'f' * 64
            self.assertEqual(verify(values=values)[0], Verdict.UNKNOWN)

    def test_zero_liquidity_nonzero_dead_owner_and_dynamic_claims_do_not_change_scope(self):
        values = evidence()
        values['positions'] = position_bytes(liquidity=0, owed0=999)
        values['owner'] = '0x' + f'{int("dead" * 10, 16):064x}'
        answer = {**claim(), 'liquidity': 'wrong', 'currentTick': 9999999, 'inRange': False}
        self.assertEqual(verify(answer, values)[0], Verdict.PASS)
        before = deepcopy(values)
        verify(answer, values)
        self.assertEqual(values, before)
        for kwargs in ({'chain_id': True}, {'chain_id': 97}, {'npm': TOKEN0}, {'factory': TOKEN1}):
            self.assertEqual(verify(**kwargs)[0], Verdict.UNKNOWN)


if __name__ == '__main__':
    unittest.main()
