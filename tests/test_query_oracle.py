"""Synthetic engineering cases; these fixtures are not real Agent evaluations."""

from copy import deepcopy
import unittest

from reputation_core import Verdict
from reputation_core.behavior import TRANSFER
from reputation_platform.query_oracle import verify_transfer_record


TX = '0x' + '11' * 32
BLOCK = '0x' + '22' * 32
TOKEN = '0x' + '33' * 20
SENDER = '0x' + '44' * 20
DEAD = '0x' + '00' * 18 + 'dead'
ZERO = '0x' + '00' * 20


def evidence(amount=1250, decimals=3):
    binding = {'blockHash': BLOCK, 'blockNumber': '0x64', 'transactionIndex': '0x0'}
    log = {**binding, 'address': TOKEN, 'transactionHash': TX, 'removed': False,
           'logIndex': '0x2', 'topics': [TRANSFER, '0x' + '0' * 24 + SENDER[2:],
                                     '0x' + '0' * 24 + DEAD[2:]], 'data': '0x' + f'{amount:064x}'}
    return {'chain': '0x38', 'head': '0xa4', 'decimals': '0x' + f'{decimals:064x}',
            'transaction': {**binding, 'hash': TX, 'chainId': '0x38', 'from': SENDER, 'to': TOKEN},
            'receipt': {**binding, 'transactionHash': TX, 'from': SENDER, 'to': TOKEN,
                        'status': '0x1', 'logs': [log]},
            'header': {'hash': BLOCK, 'number': '0x64', 'transactions': [TX]}}


def verify(values, claimed=1, **kwargs):
    return verify_transfer_record(claimed, kwargs.get('tx_hash', TX), kwargs.get('chain_id', 56),
                                  kwargs.get('token', TOKEN), kwargs.get('recipients', (DEAD, ZERO)), values)


class QueryOracleTests(unittest.TestCase):
    def test_sums_all_destinations_before_integer_half_up(self):
        values = evidence(750)
        second = deepcopy(values['receipt']['logs'][0])
        second.update(logIndex='0x3', data='0x' + f'{750:064x}')
        second['topics'][2] = '0x' + '0' * 64
        values['receipt']['logs'].append(second)
        verdict, _, detail = verify(values, claimed=2)
        self.assertEqual(verdict, Verdict.PASS)
        self.assertEqual(detail['raw_amount'], '1500')
        self.assertEqual(detail['matched_log_indices'], [2, 3])
        self.assertEqual(verify(values, claimed=1)[0], Verdict.FAIL)
        self.assertEqual(verify(evidence(1499), claimed=1)[0], Verdict.PASS)
        self.assertEqual(verify(evidence(1500), claimed=2)[0], Verdict.PASS)
        self.assertEqual(verify(evidence(10**75 + 5 * 10**17, 18), claimed=10**57 + 1)[0], Verdict.PASS)

    def test_reverted_and_missing_matching_transfers_are_real_failures(self):
        values = evidence()
        values['receipt'].update(status='0x0', logs=[])
        self.assertEqual(verify(values)[0], Verdict.FAIL)
        values['receipt']['status'] = '0x1'
        self.assertEqual(verify(values)[0], Verdict.FAIL)
        values = evidence()
        values['receipt']['logs'][0]['address'] = SENDER
        self.assertEqual(verify(values)[0], Verdict.FAIL)
        values['receipt']['logs'][0]['address'] = TOKEN
        values['receipt']['logs'][0]['topics'][2] = '0x' + '0' * 24 + SENDER[2:]
        self.assertEqual(verify(values)[0], Verdict.FAIL)

    def test_missing_network_or_unfinalized_results_remain_unknown(self):
        for key in evidence():
            with self.subTest(key=key):
                values = evidence()
                values[key] = None
                self.assertEqual(verify(values)[0], Verdict.UNKNOWN)
                values.pop(key)
                self.assertEqual(verify(values)[0], Verdict.UNKNOWN)
        for head in ('0xa3', '0x63', '0x00', 164, True):
            with self.subTest(head=head):
                values = evidence()
                values['head'] = head
                self.assertEqual(verify(values)[0], Verdict.UNKNOWN)

    def test_every_receipt_transaction_and_header_binding_is_required(self):
        changes = [('chain', None, '0x1'), ('transaction', 'chainId', '0x1'),
                   ('transaction', 'hash', BLOCK), ('receipt', 'transactionHash', BLOCK),
                   ('transaction', 'blockHash', TX), ('receipt', 'blockHash', TX),
                   ('header', 'hash', TX), ('transaction', 'blockNumber', '0x63'),
                   ('receipt', 'blockNumber', '0x63'), ('header', 'number', '0x63'),
                   ('transaction', 'transactionIndex', '0x1'), ('receipt', 'transactionIndex', '0x1'),
                   ('receipt', 'from', TOKEN), ('receipt', 'to', SENDER),
                   ('header', 'transactions', [BLOCK]), ('header', 'transactions', [TX, TX]),
                   ('header', 'transactions', [{'hash': TX}]), ('receipt', 'status', '0x2'),
                   ('receipt', 'chainId', '0x1')]
        for record, key, value in changes:
            with self.subTest(record=record, key=key):
                values = evidence()
                if key is None:
                    values[record] = value
                else:
                    values[record][key] = value
                self.assertEqual(verify(values)[0], Verdict.UNKNOWN)

    def test_all_logs_are_bound_even_when_token_does_not_match(self):
        changes = {'transactionHash': BLOCK, 'blockHash': TX, 'blockNumber': '0x63',
                   'transactionIndex': '0x1', 'removed': True, 'logIndex': None,
                   'address': '0x1234', 'topics': ['0x1234'], 'data': '0x0', 'chainId': '0x1'}
        for key, value in changes.items():
            with self.subTest(key=key):
                values = evidence()
                unrelated = deepcopy(values['receipt']['logs'][0])
                unrelated.update(address=SENDER, logIndex='0x3')
                unrelated[key] = value
                values['receipt']['logs'].append(unrelated)
                self.assertEqual(verify(values)[0], Verdict.UNKNOWN)
        values = evidence()
        values['receipt']['logs'].append(deepcopy(values['receipt']['logs'][0]))
        self.assertEqual(verify(values)[0], Verdict.UNKNOWN)

    def test_malformed_erc20_and_decimals_never_become_business_failure(self):
        for data in ('0x', '0x01', '0x' + '0' * 65, '0x' + 'g' * 64):
            with self.subTest(data=data):
                values = evidence()
                values['receipt']['logs'][0]['data'] = data
                self.assertEqual(verify(values)[0], Verdict.UNKNOWN)
        for topics in ([TRANSFER], [TRANSFER] * 4,
                       [TRANSFER, '0x' + 'f' * 64, '0x' + '0' * 64]):
            values = evidence()
            values['receipt']['logs'][0]['topics'] = topics
            self.assertEqual(verify(values)[0], Verdict.UNKNOWN)
        for decimals in (None, '0x12', '0x' + f'{256:064x}', True):
            values = evidence()
            values['decimals'] = decimals
            self.assertEqual(verify(values)[0], Verdict.UNKNOWN)
        self.assertEqual(verify(evidence(1, 0), claimed=1)[0], Verdict.PASS)
        self.assertEqual(verify(evidence(1, 255), claimed=0)[0], Verdict.PASS)

    def test_invalid_contract_inputs_and_inconsistent_revert_are_unknown(self):
        for claimed in (-1, True, 1.0, '1'):
            self.assertEqual(verify(evidence(), claimed=claimed)[0], Verdict.UNKNOWN)
        for kwargs in ({'tx_hash': '0x1234'}, {'token': 'not-an-address'}, {'chain_id': True},
                       {'recipients': ()}, {'recipients': (DEAD, DEAD)}, {'recipients': [DEAD]}):
            self.assertEqual(verify(evidence(), **kwargs)[0], Verdict.UNKNOWN)
        values = evidence()
        values['receipt']['status'] = '0x0'
        self.assertEqual(verify(values)[0], Verdict.UNKNOWN)

    def test_inputs_are_not_mutated_and_no_executor_claim_is_required(self):
        values = evidence()
        original = deepcopy(values)
        self.assertEqual(verify(values)[0], Verdict.PASS)
        self.assertEqual(values, original)
        values['transaction']['from'] = values['receipt']['from'] = ZERO
        self.assertEqual(verify(values)[0], Verdict.PASS)


if __name__ == '__main__':
    unittest.main()
