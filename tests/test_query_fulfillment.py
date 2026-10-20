"""Synthetic observable deliveries; no public requests or real score samples."""

from copy import deepcopy
import json
from types import SimpleNamespace
import unittest

from reputation_core import MeasurementPurpose, ScoredSample, Verdict
from reputation_core.scoring import SERVICE_FULFILLMENT_POLICY_VERSION, calculate_scores
from reputation_platform.position_adapters import ADAPTERS, parse_position_claim
from reputation_platform.position_oracle import FACTORY, NPM, verify_position_record
from reputation_platform.query_fulfillment import DEADLINE_MS, should_stop_business, verify_query_fulfillment
from test_position_adapters import business
from test_position_oracle import POSITION, claim, evidence

KEY = 'fulfillment-request'


def observation(**changes):
    return SimpleNamespace(**{'http_status': 200, 'body_complete': True, 'error_kind': None, 'method': 'POST',
                              'elapsed_ms': 1000.0, **changes})


def verify(adapter=ADAPTERS[0], *, raw=None, answer=None, obs=None):
    raw = business(adapter, answer, KEY) if raw is None else raw
    delivery = parse_position_claim(adapter, raw, KEY)
    return verify_query_fulfillment(observation() if obs is None else obs, raw, KEY, POSITION, delivery)[0]


class QueryFulfillmentTests(unittest.TestCase):
    def test_same_both_protocols_and_wrong_facts_do_not_copy_functional_verdict(self):
        for adapter in ADAPTERS:
            self.assertEqual(verify(adapter), Verdict.PASS)
            wrong = {**claim(), 'fee': 100, 'tickLower': -90}
            raw = business(adapter, wrong, KEY)
            delivery = parse_position_claim(adapter, raw, KEY)
            functional, _, _ = verify_position_record(delivery, POSITION, 56, NPM, FACTORY, evidence())
            self.assertEqual(functional, Verdict.FAIL)
            self.assertEqual(verify(adapter, raw=raw), Verdict.PASS)

    def test_complete_wrong_request_subject_and_missing_delivery_are_failures(self):
        for adapter in ADAPTERS:
            self.assertEqual(verify(adapter, raw=business(adapter, key='wrong-id')), Verdict.FAIL)
            self.assertEqual(verify(adapter, answer={**claim(), 'positionId': '999'}), Verdict.FAIL)
            for field in ('reportedPositionId', 'reportedChain'):
                if adapter['protocol'] == 'A2A':
                    self.assertEqual(verify(adapter, answer={**claim(), field: '999' if field.endswith('Id') else 97}), Verdict.FAIL)
            raw = json.dumps({'jsonrpc': '2.0', 'id': KEY, 'result': {}}).encode()
            self.assertEqual(verify(adapter, raw=raw), Verdict.FAIL)
            raw = business(adapter, key=KEY)
            for field in claim():
                delivery = claim()
                delivery.pop(field)
                self.assertEqual(verify_query_fulfillment(observation(), raw, KEY, POSITION, delivery)[0], Verdict.FAIL)
        raw = business(ADAPTERS[0], key=KEY)
        malformed = {**claim(), 'fee': True}
        self.assertEqual(verify_query_fulfillment(observation(), raw, KEY, POSITION, malformed)[0], Verdict.FAIL)

    def test_timeout_late_and_platform_errors_are_unknown(self):
        for adapter in ADAPTERS:
            for changes in ({'elapsed_ms': DEADLINE_MS + 0.01}, {'error_kind': 'ReadTimeout'},
                            {'error_kind': 'ConnectError'}, {'error_kind': 'destination_policy_blocked'},
                            {'http_status': 503}, {'http_status': 429}, {'http_status': 402},
                            {'body_complete': False}, {'elapsed_ms': float('nan')},
                            {'elapsed_ms': -1}, {'elapsed_ms': float('inf')}):
                with self.subTest(adapter=adapter['id'], changes=changes):
                    self.assertEqual(verify(adapter, obs=observation(**changes)), Verdict.UNKNOWN)
            self.assertEqual(verify(adapter, obs=observation(elapsed_ms=DEADLINE_MS)), Verdict.PASS)
            # Lateness does not erase a separately established wrong-subject violation.
            self.assertEqual(verify(adapter, answer={**claim(), 'positionId': '999'},
                                    obs=observation(elapsed_ms=DEADLINE_MS + 1)), Verdict.FAIL)
        self.assertEqual(verify_query_fulfillment(None, b'', KEY, POSITION, None)[0], Verdict.UNKNOWN)

    def test_dependency_and_self_reported_tool_errors_do_not_establish_responsibility(self):
        for error in ({}, None, {'code': -32603, 'message': 'upstream unavailable'},
                      {'code': -32005, 'message': 'quota'}, {'code': 429, 'message': 'Too many requests'},
                      {'code': -32000, 'message': 'not found'}, {'code': -32000, 'message': 'execution failed'},
                      {'code': '-32602', 'message': 'invalid'}, {'code': -32602},
                      {'code': -32602, 'message': ''}):
            raw = json.dumps({'jsonrpc': '2.0', 'id': KEY, 'error': error}).encode()
            self.assertEqual(verify(raw=raw), Verdict.UNKNOWN)
        for adapter in ADAPTERS:
            envelope = json.loads(business(adapter, key=KEY))
            envelope['result']['isError'] = True
            self.assertEqual(verify(adapter, raw=json.dumps(envelope).encode()), Verdict.UNKNOWN)
        envelope = json.loads(business(ADAPTERS[1], key=KEY))
        envelope['result']['parts'][0]['data']['result'] = {'error': 'unreadable', 'detail': 'Position RPC unavailable'}
        self.assertEqual(verify(ADAPTERS[1], raw=json.dumps(envelope).encode()), Verdict.UNKNOWN)
        for code in (-32601, -32602):
            raw = json.dumps({'jsonrpc': '2.0', 'id': KEY,
                              'error': {'code': code, 'message': 'Rejected reviewed valid request'}}).encode()
            self.assertEqual(verify(raw=raw), Verdict.FAIL)

    def test_non_protocol_malformed_and_ambiguous_error_responses_stay_unknown(self):
        for raw in (b'<html>proxy error</html>', b'{}', b'[]', b'{',
                    b'{"jsonrpc":"2.0","id":"fulfillment-request","id":"fulfillment-request","result":{}}'):
            self.assertEqual(verify(raw=raw), Verdict.UNKNOWN)
        raw = json.dumps({'jsonrpc': '2.0', 'id': KEY, 'result': {},
                          'error': {'code': -32602, 'message': 'ambiguous'}}).encode()
        self.assertEqual(verify(raw=raw), Verdict.UNKNOWN)

    def test_explicit_tool_safety_errors_stop_the_host_without_scanning_successful_output(self):
        obs = observation()
        self.assertTrue(should_stop_business(observation(http_status=402), b''))
        self.assertTrue(should_stop_business(obs, json.dumps({'error': {'code': -32005}}).encode()))
        for text in ('quota exceeded', 'Too many requests', 'payment_required', 'authentication required'):
            mcp = {'jsonrpc': '2.0', 'id': KEY, 'result': {'isError': True,
                   'content': [{'type': 'text', 'text': text}]}}
            a2a = {'jsonrpc': '2.0', 'id': KEY, 'result': {'kind': 'message', 'parts': [
                {'kind': 'data', 'data': {'result': {'error': text}}}]}}
            for envelope in (mcp, a2a):
                self.assertTrue(should_stop_business(obs, json.dumps(envelope).encode()))
                self.assertEqual(verify(raw=json.dumps(envelope).encode()), Verdict.UNKNOWN)
            mcp['result']['isError'] = False
            self.assertFalse(should_stop_business(obs, json.dumps(mcp).encode()))
        self.assertFalse(should_stop_business(obs, b'not json'))
        self.assertFalse(should_stop_business(obs, json.dumps({'result': {'isError': True,
                         'content': [{'type': 'text', 'text': 'position RPC unavailable'}]}}).encode()))

    def test_seven_decisive_tasks_and_cross_dimension_exclusivity_remain_required(self):
        def sample(index, purpose, verdict=Verdict.PASS):
            return ScoredSample(sample_id=f'{purpose.value}-{index}', task_key=f'position:{index}',
                                purpose=purpose, verdict=verdict, elapsed_ms=1000.0, reason='synthetic', evidence=[])
        b = [sample(i, MeasurementPurpose.BEHAVIORAL) for i in range(7)]
        score = lambda samples: calculate_scores(samples, policy_version=SERVICE_FULFILLMENT_POLICY_VERSION)
        self.assertIsNone(score(b[:6]).behavioral.value)
        self.assertEqual(score(b).behavioral.value, 100)
        unknown = deepcopy(b)
        unknown[0].verdict = Verdict.UNKNOWN
        self.assertIsNone(score(unknown).behavioral.value)
        failed = deepcopy(b)
        failed[0].verdict = Verdict.FAIL
        self.assertEqual(score(failed).behavioral.value, 85.71)
        with self.assertRaisesRegex(ValueError, 'duplicate task_key'):
            score([*b, sample(0, MeasurementPurpose.FUNCTIONAL)])
        self.assertIsNone(score(b).overall)


if __name__ == '__main__':
    unittest.main()
