"""Offline collector integration; synthetic responses never represent real Agent results."""

from datetime import datetime, timedelta, timezone
import hashlib
import json
import unittest
from unittest.mock import patch

from reputation_core import ProbeObservation, Verdict
from reputation_platform.query_checker import PLAN_NAME, collect_query_tasks, rebuild_query
from reputation_platform.registration_discovery import DiscoveryEvidence
import test_query_checker as source_cases


class QueryCollectionTests(unittest.TestCase):
    def setUp(self):
        self.enterContext(patch.object(source_cases, 'NOW', datetime.now(timezone.utc) - timedelta(minutes=1)))
        self.fixture = source_cases.QueryCheckerTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root = self.fixture.root
        self.registration = {'canonical': self.fixture.registration['canonical'],
                             'proof_path': f'{self.fixture.prefix}/registration-proof.json'}
        config_name = source_cases.RPC_CONFIG.as_posix()
        config = self.fixture.read(config_name)
        config['chains']['56']['credential_file'] = 'runtime/synthetic-unused-key.txt'
        self.fixture.write(config_name, config)
        proof = self.fixture.read(self.registration['proof_path'])
        proof['rpc_configuration']['sha256'] = self.fixture.hashes[config_name]
        self.fixture.write(self.registration['proof_path'], proof)
        self.calls, self.responses = [], {}
        self.evidence = DiscoveryEvidence(self.root, 'runtime/collected-query',
                                           proxy='http://127.0.0.1:9', enabled=True)
        # Copy discovery dependencies, excluding the fixture's already completed business run.
        self.evidence.inputs.update({name: digest for name, digest in self.fixture.hashes.items()
                                     if '/mcp-' in name or '/registration-' in name
                                     or not name.startswith(self.fixture.prefix + '/')})
        self.enterContext(patch('reputation_platform.registration_discovery.load_zan_key_file', return_value=None))
        # __enter__ normally initializes DNS/HTTP; only fetch's retained-file contract is under test.
        self.enterContext(patch('reputation_platform.registration_discovery.SafeHttpClient.__enter__',
                                lambda client: client))
        self.enterContext(patch('reputation_platform.registration_discovery.SafeHttpClient.fetch',
                                autospec=True, side_effect=self.fetch))

    def fetch(self, client, key, directory):
        target = client.targets[key]
        self.calls.append(target)
        options = self.responses.get(key, {})
        raw = options.get('raw', (self.root / self.fixture.prefix / f'{key}.response.bin').read_bytes())
        status, complete = options.get('status', 200), options.get('complete', True)
        response_file = f'{key}.response.bin'
        (directory / response_file).write_bytes(raw)
        observation = ProbeObservation(
            request_key=key, purpose=target.purpose, url=target.url, method=target.method,
            request_json=json.dumps(target.json_body), observed_at=datetime.now(timezone.utc),
            http_status=status, elapsed_ms=2.0,
            outcome=Verdict.PASS if status == 200 and complete else Verdict.UNKNOWN,
            error_kind=None if status == 200 else 'http_status_not_success',
            response_file=response_file, response_sha256=hashlib.sha256(raw).hexdigest(),
            body_complete=complete)
        (directory / f'{key}.observation.json').write_text(observation.model_dump_json(), encoding='utf-8')
        return observation

    def collect(self):
        capabilities, samples, gaps = collect_query_tasks(self.registration, self.evidence)
        self.assertEqual(len(capabilities), 1)
        self.assertEqual(len(samples), 1)
        self.assertTrue(gaps)
        index = (self.evidence.run / PLAN_NAME).relative_to(self.root).as_posix()
        rebuilt = rebuild_query(self.root, index, self.evidence.inputs)
        self.assertEqual(capabilities[0], rebuilt[1])
        self.assertEqual(samples[0], rebuilt[2])
        self.assertLessEqual(len(self.calls), 7)
        self.assertLessEqual(sum(t.json_body['method'] == 'tools/call' for t in self.calls), 1)
        return samples[0]

    def test_success_sends_one_business_call_and_six_fixed_read_requests(self):
        sample = self.collect()
        self.assertEqual(sample.sample.verdict, Verdict.PASS)
        self.assertEqual(self.evidence.request_count, 7)
        self.assertEqual([t.json_body['method'] for t in self.calls],
                         ['tools/call', 'eth_chainId', 'eth_blockNumber',
                          'eth_getTransactionReceipt', 'eth_getTransactionByHash',
                          'eth_getBlockByNumber', 'eth_call'])
        business = self.calls[0]
        self.assertEqual(business.url, source_cases.ADAPTER['endpoint'])
        self.assertEqual(business.json_body['params'], {'name': source_cases.ADAPTER['tool'], 'arguments': {}})
        self.assertTrue(all(target.url == source_cases.RPC for target in self.calls[1:]))
        block = self.fixture.values['receipt']['blockNumber']
        self.assertEqual(self.calls[-2].json_body['params'], [block, False])
        self.assertEqual(self.calls[-1].json_body['params'],
                         [{'to': source_cases.ADAPTER['token'], 'data': '0x313ce567'}, block])

    def test_malicious_catalog_schema_never_sends_business_call(self):
        key = 'mcp-tools'
        self.fixture.response(key, {'jsonrpc': '2.0', 'id': key, 'result': {'tools': [{
            'name': source_cases.ADAPTER['tool'], 'inputSchema': {'type': 'object',
                'properties': {'signature': {'type': 'string'}}}, 'annotations': {'readOnlyHint': True}}]}})
        self.evidence.inputs.update({name: digest for name, digest in self.fixture.hashes.items()
                                     if '/mcp-' in name})
        self.assertEqual(collect_query_tasks(self.registration, self.evidence), ([], [], []))
        self.assertEqual(self.calls, [])

    def test_changed_catalog_bytes_are_rejected_before_business_call(self):
        path = self.root / self.fixture.prefix / 'mcp-tools.response.bin'
        path.write_bytes(path.read_bytes() + b' ')
        with self.assertRaises(ValueError):
            collect_query_tasks(self.registration, self.evidence)
        self.assertEqual(self.calls, [])

    def test_changed_registration_dependency_is_rejected_before_business_call(self):
        path = self.root / self.fixture.prefix / 'registration-document.json'
        path.write_bytes(path.read_bytes() + b' ')
        with self.assertRaises(ValueError):
            collect_query_tasks(self.registration, self.evidence)
        self.assertEqual(self.calls, [])

    def test_incomplete_business_body_is_unknown_without_oracle_requests(self):
        self.responses['query-business'] = {'complete': False}
        sample = self.collect()
        self.assertEqual(sample.sample.verdict, Verdict.UNKNOWN)
        self.assertEqual([target.key for target in self.calls], ['query-business'])
        self.assertFalse(list(self.evidence.run.glob('query-reference-*.request-plan.json')))

    def test_array_rpc_response_is_unknown_and_does_not_crash(self):
        self.responses['query-reference-head'] = {'raw': b'[]'}
        self.assertEqual(self.collect().sample.verdict, Verdict.UNKNOWN)
        self.assertEqual(len(self.calls), 7)

    def test_existing_business_host_stop_retains_unsent_unknown(self):
        stop = self.root / 'runtime/prediction-network-stops/brainonbnb.com.json'
        stop.parent.mkdir()
        stop.write_text('{}', encoding='utf-8')
        sample = self.collect()
        self.assertEqual(sample.sample.verdict, Verdict.UNKNOWN)
        self.assertIsNone(sample.observed_at)
        self.assertEqual(self.calls, [])
        skip = json.loads((self.evidence.run / 'query-business.skip.json').read_bytes())
        self.assertIs(skip['request_sent'], False)
        self.assertEqual(skip['reason'], 'host_stopped')

    def test_rpc_rate_limit_stops_later_reads_and_preserves_unknown_skips(self):
        self.responses['query-reference-chain'] = {'status': 429}
        self.assertEqual(self.collect().sample.verdict, Verdict.UNKNOWN)
        self.assertEqual([target.key for target in self.calls], ['query-business', 'query-reference-chain'])
        self.assertTrue((self.root / 'runtime/prediction-network-stops/api.zan.top.json').is_file())
        for field in ('head', 'receipt', 'transaction'):
            skip = json.loads((self.evidence.run / f'query-reference-{field}.skip.json').read_bytes())
            self.assertIs(skip['request_sent'], False)
            self.assertEqual(skip['reason'], 'host_stopped')


if __name__ == '__main__':
    unittest.main()
