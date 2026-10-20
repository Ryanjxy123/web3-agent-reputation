"""Synthetic protocol fixtures, separate from retained real pilot evidence."""

from copy import deepcopy
import json
import unittest

from reputation_platform.position_adapters import (ADAPTERS, BRAIN_SCHEMA, HALLMARK_SCHEMA,
    match_position_adapter, parse_position_claim, position_arguments, position_request)
from test_position_oracle import POSITION, claim

BRAIN, HALLMARK = ADAPTERS


def identity(adapter=BRAIN, agent_id=1):
    return {'canonical': f'eip155:56:0x{"12" * 20}:{agent_id}', 'registration_verified': True,
            'document': {}, 'token_uri': 'data:application/json;base64,e30=',
            'services': [{'name': adapter['protocol'], 'endpoint': adapter['endpoint']}]}


def catalog(adapter=BRAIN):
    if adapter == BRAIN:
        return [{'name': adapter['tool'], 'description': 'Free read, reviewed source.',
                 'inputSchema': deepcopy(BRAIN_SCHEMA),
                 'annotations': {'readOnlyHint': True, 'destructiveHint': False}}]
    return {'type': 'AgentCard', 'url': adapter['endpoint'], 'protocolVersion': '0.3.0',
            'preferredTransport': 'JSONRPC', 'provider': {'organization': 'Hallmark'},
            'security': [], 'securitySchemes': {}, 'supportsAuthenticatedExtendedCard': False,
            'skills': [{'id': 'analyse', 'inputSchema': deepcopy(HALLMARK_SCHEMA)}]}


def business(adapter=BRAIN, answer=None, key='request-1'):
    c = claim() if answer is None else answer
    if adapter == BRAIN:
        value = {'service': 'lp_position_look', 'positions': 1, 'position': c['positionId'],
                 'pool': {'token0': c['token0'], 'token1': c['token1'],
                          'fee_tier_pct': c['fee'] / 10000, 'ticks': [c['tickLower'], c['tickUpper']]}}
        result = {'content': [{'type': 'text', 'text': json.dumps(value)}]}
    else:
        position = {'tokenId': c.get('reportedPositionId', c['positionId']),
                    'token0': {'address': c['token0']}, 'token1': {'address': c['token1']},
                    'fee': c['fee'], 'tickLower': c['tickLower'], 'tickUpper': c['tickUpper']}
        value = {'skill': 'analyse', 'chainId': c.get('reportedChain', 56),
                 'subject': {'tokenId': c['positionId']}, 'facts': {'position': position}}
        result = {'kind': 'message', 'role': 'agent', 'parts': [
            {'kind': 'data', 'data': {'skill': 'analyse', 'result': value}}]}
    return json.dumps({'jsonrpc': '2.0', 'id': key, 'result': result}).encode()


class PositionAdapterTests(unittest.TestCase):
    def test_registered_schema_matches_across_agent_ids_and_only_sends_minimal_input(self):
        for adapter in ADAPTERS:
            for agent_id in (1, 2, 338475):
                self.assertEqual(match_position_adapter(identity(adapter, agent_id), adapter['endpoint'], catalog(adapter)), adapter)
            args = position_arguments(adapter, POSITION)
            self.assertEqual(args, {'position': POSITION} if adapter == BRAIN else {'chainId': 56, 'tokenId': POSITION})
            body = position_request(adapter, 'request-1', POSITION)
            self.assertEqual(body['method'], 'tools/call' if adapter == BRAIN else 'message/send')
            self.assertEqual(body['id'], 'request-1')
            self.assertNotIn('wallet', json.dumps(body))

    def test_unverified_identity_wrong_chain_and_unreviewed_endpoint_never_match(self):
        for adapter in ADAPTERS:
            for changes in ({'registration_verified': False}, {'document': None}, {'services': []},
                            {'token_uri': 'ipfs://cid'}, {'token_uri': 'http://example.test'},
                            {'canonical': 'eip155:97:registry:1'}):
                self.assertIsNone(match_position_adapter({**identity(adapter), **changes}, adapter['endpoint'], catalog(adapter)))
            self.assertIsNone(match_position_adapter(identity(adapter), 'https://unreviewed.example', catalog(adapter)))
        for malformed in (None, {}, {'services': None}):
            self.assertIsNone(match_position_adapter(malformed, BRAIN['endpoint'], catalog()))

    def test_read_only_hint_cannot_override_schema_auth_price_or_duplicate_skill(self):
        for adapter in ADAPTERS:
            for mutation in ('extra', 'paid', 'auth', 'open', 'duplicate', 'wrong_type'):
                with self.subTest(adapter=adapter['id'], mutation=mutation):
                    value = catalog(adapter)
                    skill = value[0] if adapter == BRAIN else value['skills'][0]
                    if mutation == 'extra':
                        skill['inputSchema']['properties']['signature'] = {'type': 'string'}
                    elif mutation == 'paid':
                        skill['pricing'] = {'amount': '1'}
                    elif mutation == 'auth':
                        skill['security'] = [{'bearer': []}]
                    elif mutation == 'open':
                        skill['inputSchema']['additionalProperties'] = True
                    elif mutation == 'wrong_type':
                        skill['inputSchema']['additionalProperties'] = 0
                    else:
                        (value if adapter == BRAIN else value['skills']).append(deepcopy(skill))
                    self.assertIsNone(match_position_adapter(identity(adapter), adapter['endpoint'], value))
        for key, value in {'security': [{'bearer': []}], 'securitySchemes': {'bearer': {}},
                           'provider': None, 'supportsAuthenticatedExtendedCard': True}.items():
            self.assertIsNone(match_position_adapter(identity(HALLMARK), HALLMARK['endpoint'], {**catalog(HALLMARK), key: value}))

    def test_both_protocols_normalize_the_same_static_claim_and_preserve_wrong_facts(self):
        for adapter in ADAPTERS:
            actual = parse_position_claim(adapter, business(adapter), 'request-1')
            self.assertEqual({k: actual[k] for k in claim()}, claim())
            wrong = {**claim(), 'positionId': '999', 'fee': 100, 'tickLower': -90,
                     'reportedChain': 97, 'reportedPositionId': '888'}
            actual = parse_position_claim(adapter, business(adapter, wrong), 'request-1')
            self.assertEqual(actual['positionId'], '999')
            self.assertEqual(actual['fee'], 100)
            if adapter == HALLMARK:
                self.assertEqual(actual['reportedChain'], 97)
                self.assertEqual(actual['reportedPositionId'], '888')

    def test_transport_errors_ambiguous_parts_bad_types_and_duplicate_json_are_unusable(self):
        for adapter in ADAPTERS:
            for raw in (b'bad json', b'[]', b'{}',
                        b'{"jsonrpc":"2.0","id":"request-1","error":{"code":402}}',
                        business(adapter, key='another-id'),
                        business(adapter).replace(b'"request-1"', b'"wrong","id":"request-1"', 1)):
                self.assertIsNone(parse_position_claim(adapter, raw, 'request-1'))
            wrong = {**claim(), 'tickLower': True}
            self.assertIsNone(parse_position_claim(adapter, business(adapter, wrong), 'request-1'))
            envelope = json.loads(business(adapter))
            if adapter == BRAIN:
                envelope['result']['isError'] = True
            else:
                envelope['result']['parts'] *= 2
            self.assertIsNone(parse_position_claim(adapter, json.dumps(envelope).encode(), 'request-1'))

    def test_fee_decimal_conversion_is_exact_and_not_a_float_rounding_shortcut(self):
        raw = business().replace(b'0.05', b'0.050000000000000000000000000001')
        self.assertIsNone(parse_position_claim(BRAIN, raw, 'request-1'))
        for fee in (b'NaN', b'Infinity', b'1e9999999', b'true'):
            self.assertIsNone(parse_position_claim(BRAIN, business().replace(b'0.05', fee), 'request-1'))
        for value in ('0123', '-1', 123, True, str(2**256)):
            with self.assertRaises(ValueError):
                position_arguments(BRAIN, value)
        with self.assertRaises(ValueError):
            position_request({**BRAIN, 'endpoint': 'https://unreviewed.example'}, 'x', POSITION)

    def test_boolean_position_count_is_not_an_integer_one(self):
        raw = business().replace(b'\\"positions\\": 1', b'\\"positions\\": true')
        self.assertNotEqual(raw, business())
        self.assertIsNone(parse_position_claim(BRAIN, raw, 'request-1'))


if __name__ == '__main__':
    unittest.main()
