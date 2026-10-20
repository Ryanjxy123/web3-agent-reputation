"""Offline contract/security checks; synthetic providers are not scored evaluations."""

from copy import deepcopy
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from reputation_platform.position_contracts import (
    CONFIG, SCHEMA_VERSION, SAFETY, load_contract_reviews, match_contract,
    parse_contract, request_contract,
)
from reputation_platform.position_adapters import position_request
from test_position_adapters import business, catalog, identity, BRAIN, HALLMARK
from test_position_oracle import POSITION, claim

ROOT = Path(__file__).resolve().parents[1]


class PositionContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = load_contract_reviews(ROOT)

    def test_real_review_dependencies_are_available_and_both_legacy_contracts_match(self):
        self.assertEqual(self.config['schema_version'], SCHEMA_VERSION)
        for adapter, legacy in zip(self.config['adapters'], (BRAIN, HALLMARK), strict=True):
            self.assertGreater(len(adapter['review_dependencies']), 1)
            self.assertEqual(match_contract(identity(legacy), legacy['endpoint'], catalog(legacy), self.config), adapter)
            actual = parse_contract(adapter, business(legacy), 'request-1', POSITION)
            self.assertEqual({key: actual[key] for key in claim()}, claim())
            self.assertEqual(request_contract(adapter, 'request-1', POSITION), position_request(legacy, 'request-1', POSITION))

    def test_third_reviewed_provider_with_different_tool_reuses_same_mapping(self):
        # Local fixture only: adding an actual provider still requires authenticated review evidence.
        config = deepcopy(self.config)
        adapter = deepcopy(config['adapters'][0])
        adapter.update(id='third-provider/v1', endpoint='https://third.example.test/mcp',
                       tool='read_position', provider='Third provider')
        config['adapters'].append(adapter)
        service = {**BRAIN, 'endpoint': adapter['endpoint'], 'tool': adapter['tool']}
        tools = catalog()
        tools[0]['name'] = adapter['tool']
        selected = match_contract(identity(service, agent_id=90210), adapter['endpoint'], tools, config)
        self.assertEqual(selected, adapter)
        self.assertEqual(request_contract(selected, 'request-1', POSITION)['params']['name'], 'read_position')
        self.assertEqual(parse_contract(selected, business(), 'request-1'), claim())
        self.assertIsNone(match_contract(identity(service), adapter['endpoint'], tools, self.config))

    def test_a2a_renamed_skill_is_mapped_without_provider_specific_scoring(self):
        config = deepcopy(self.config)
        adapter = config['adapters'][1]
        adapter.update(id='other-a2a/v1', endpoint='https://other.example.test/a2a',
                       tool='inspect', provider='Other provider')
        service = {**HALLMARK, 'endpoint': adapter['endpoint']}
        card = catalog(HALLMARK)
        card['url'] = adapter['endpoint']
        card['provider']['organization'] = adapter['provider']
        card['skills'][0]['id'] = adapter['tool']
        self.assertEqual(match_contract(identity(service), adapter['endpoint'], card, config), adapter)
        body = request_contract(adapter, 'request-1', POSITION)
        self.assertEqual(body['params']['message']['parts'][0]['data']['skill'], 'inspect')
        raw = business(HALLMARK).replace(b'analyse', b'inspect')
        actual = parse_contract(adapter, raw, 'request-1')
        self.assertEqual({key: actual[key] for key in claim()}, claim())
        self.assertIsNone(parse_contract(adapter, business(HALLMARK), 'request-1'))

    def test_identity_and_registered_endpoint_required(self):
        for adapter, legacy in zip(self.config['adapters'], (BRAIN, HALLMARK), strict=True):
            for changes in ({'registration_verified': False}, {'document': None}, {'services': []},
                            {'token_uri': 'ipfs://not-authenticated'}, {'canonical': 'eip155:97:registry:1'}):
                self.assertIsNone(match_contract({**identity(legacy), **changes}, adapter['endpoint'], catalog(legacy), self.config))
            self.assertIsNone(match_contract(identity(legacy), 'https://unknown.example.test', catalog(legacy), self.config))

    def test_untrusted_schema_payments_auth_and_readonly_hints_do_not_grant_permission(self):
        for adapter, legacy in zip(self.config['adapters'], (BRAIN, HALLMARK), strict=True):
            for mutation in ('extra_input', 'open_schema', 'schema_bool', 'duplicate', 'price', 'auth', 'destructive'):
                with self.subTest(protocol=adapter['protocol'], mutation=mutation):
                    value = catalog(legacy)
                    skill = value[0] if legacy == BRAIN else value['skills'][0]
                    if mutation == 'extra_input':
                        skill['inputSchema']['properties']['signature'] = {'type': 'string'}
                    elif mutation == 'open_schema':
                        skill['inputSchema']['additionalProperties'] = True
                    elif mutation == 'schema_bool':
                        skill['inputSchema']['additionalProperties'] = 0
                    elif mutation == 'duplicate':
                        (value if legacy == BRAIN else value['skills']).append(deepcopy(skill))
                    elif mutation == 'price':
                        skill['price'] = 1
                    elif mutation == 'auth':
                        skill['security'] = [{'bearer': []}]
                    else:
                        skill['annotations'] = {'readOnlyHint': True, 'destructiveHint': True}
                    self.assertIsNone(match_contract(identity(legacy), adapter['endpoint'], value, self.config))

    def test_missing_unsafe_or_ambiguous_review_does_not_match(self):
        for change in ({'review_dependencies': []}, {'safety': {**SAFETY, 'free': False}},
                       {'safety': {**SAFETY, 'reviewed': 1}}, {'output_mapping': 'arbitrary-code'},
                       {'endpoint': 'http://brainonbnb.com/mcp'}):
            config = deepcopy(self.config)
            config['adapters'][0].update(change)
            self.assertIsNone(match_contract(identity(), config['adapters'][0]['endpoint'], catalog(), config))
        config = deepcopy(self.config)
        config['adapters'].append(deepcopy(config['adapters'][0]))
        self.assertIsNone(match_contract(identity(), BRAIN['endpoint'], catalog(), config))

    def test_wrong_task_is_retained_for_verifier_and_wrong_envelope_id_rejected(self):
        for adapter, legacy in zip(self.config['adapters'], (BRAIN, HALLMARK), strict=True):
            wrong = {**claim(), 'positionId': '999'}
            self.assertEqual(parse_contract(adapter, business(legacy, wrong), 'request-1', POSITION)['positionId'], '999')
            self.assertIsNone(parse_contract(adapter, business(legacy, key='wrong'), 'request-1', POSITION))
            self.assertIsNone(parse_contract(adapter, business(legacy), 'request-1', '001'))
            for raw in (b'bad json', b'[]', b'{}', business(legacy).replace(b'"request-1"', b'"other","id":"request-1"', 1)):
                self.assertIsNone(parse_contract(adapter, raw, 'request-1'))

    def test_load_rejects_missing_changed_or_escaping_review_files(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'review.txt'
            source.write_text('reviewed source', encoding='utf-8')
            config = deepcopy(self.config)
            config['adapters'] = [config['adapters'][0]]
            adapter = config['adapters'][0]
            adapter['review_dependencies'] = [{'path': source.name, 'sha256': hashlib.sha256(source.read_bytes()).hexdigest()}]
            path = root / 'review-config.json'
            path.write_text(json.dumps(config), encoding='utf-8')
            self.assertEqual(load_contract_reviews(root, path.name), config)
            source.write_text('changed source', encoding='utf-8')
            with self.assertRaises(ValueError):
                load_contract_reviews(root, path.name)
            source.unlink()
            with self.assertRaises(ValueError):
                load_contract_reviews(root, path.name)
            adapter['review_dependencies'][0]['path'] = '../outside.txt'
            path.write_text(json.dumps(config), encoding='utf-8')
            with self.assertRaises(ValueError):
                load_contract_reviews(root, path.name)
            with self.assertRaises(ValueError):
                load_contract_reviews(root, '../review-config.json')


if __name__ == '__main__':
    unittest.main()
