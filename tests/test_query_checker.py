"""Synthetic retained bytes test source rebuilding; registration is an explicit stub."""

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from reputation_core import EvaluationReport, MeasurementPurpose, ProbeObservation, Verdict
from reputation_platform.checker_dispatch import collect_business_checks
from reputation_platform.query_checker import (
    ADAPTERS, CHECKER_ID, EMPTY_SCHEMA, PLAN_NAME, POLICY, VERSION,
    collect_query_tasks, match_query_adapter, rebuild_query, verify_query_samples,
)
from reputation_platform.protocol_evaluation import ACCEPT
from reputation_platform.registration_discovery import RPC_CONFIG
from test_query_oracle import TOKEN as SYNTHETIC_TOKEN, TX, evidence


REGISTRY = '0x8004a169fb4a3325136eb29fa0ceb6d2e539a432'
NOW = datetime(2026, 10, 19, tzinfo=timezone.utc)
ADAPTER = ADAPTERS[0]
RPC = 'https://api.zan.top/node/v1/bsc/mainnet'


def at(seconds):
    return NOW + timedelta(seconds=seconds)


def identity(agent_id=100):
    services = [{'name': 'MCP', 'endpoint': ADAPTER['endpoint']}]
    return {'canonical': f"eip155:56:{REGISTRY}:{agent_id}", 'registration_verified': True,
            'document': {'name': 'Synthetic source fixture', 'services': deepcopy(services)},
            'services': services}


def tools():
    return [{'name': ADAPTER['tool'], 'inputSchema': deepcopy(EMPTY_SCHEMA),
             'description': 'Synthetic fixture; not a real Agent invocation.'}]


class QueryCheckerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory(prefix='query-checker-test-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.hashes = {}
        self.prefix = 'runtime/synthetic-query'
        self.plan_name = f'{self.prefix}/{PLAN_NAME}'
        self.registration = identity()
        self.registration_stub = patch('reputation_platform.query_checker.verify_registration_proof',
                                       return_value=self.registration)
        self.registration_stub.start()
        self.addCleanup(self.registration_stub.stop)
        self._fixture()

    def write(self, name, value):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        raw = value if isinstance(value, bytes) else json.dumps(value, ensure_ascii=False).encode()
        path.write_bytes(raw)
        self.hashes[name] = hashlib.sha256(raw).hexdigest()
        return name

    def read(self, name):
        return json.loads((self.root / name).read_bytes())

    def request(self, key, body, result, second, purpose=MeasurementPurpose.BACKGROUND,
                url=None, status=200, headers=None):
        url = url or ADAPTER['endpoint']
        name = f'{self.prefix}/{key}.request-plan.json'
        self.write(name, {'created_at': at(second).isoformat(), 'key': key, 'url': url,
                         'method': 'POST', 'json': body, 'headers': headers or ACCEPT,
                         'measurement_purpose': purpose.value, 'execution_enabled': True,
                         'retries': 0, 'rpc_configuration_source':
                         'operator-static-not-metadata' if url == RPC else None})
        raw = (b'' if status == 204 else json.dumps(
            {'jsonrpc': '2.0', 'id': key, 'result': result}, ensure_ascii=False).encode())
        raw_name = f'{key}.response.bin'
        self.write(f'{self.prefix}/{raw_name}', raw)
        observation = ProbeObservation(
            request_key=key, purpose=purpose, url=url, method='POST', request_json=json.dumps(body),
            observed_at=at(second + 1), http_status=status, elapsed_ms=2.0, outcome=Verdict.PASS,
            error_kind=None, response_file=raw_name, response_sha256=hashlib.sha256(raw).hexdigest(),
            body_complete=True)
        self.write(f'{self.prefix}/{key}.observation.json', json.loads(observation.model_dump_json()))
        return name

    def response(self, key, response):
        raw_name = f'{self.prefix}/{key}.response.bin'
        self.write(raw_name, response)
        obs_name = f'{self.prefix}/{key}.observation.json'
        observation = self.read(obs_name)
        observation['response_sha256'] = self.hashes[raw_name]
        self.write(obs_name, observation)

    def _fixture(self):
        self.write(POLICY, b'Synthetic engineering policy fixture; no real registration proof.')
        self.write(RPC_CONFIG.as_posix(), {'configuration_source': 'operator-static-not-metadata',
                                         'confirmation_distance': 64,
                                         'chains': {'56': {'rpc_url': RPC, 'authentication': 'zan'}}})
        source_name = self.write(f'{self.prefix}/registration-document.json', self.registration['document'])
        directory_name = self.write(f'{self.prefix}/registration-directory.json', {'synthetic': 'directory'})
        rpc_name = self.write(f'{self.prefix}/registration-rpc.json', {'synthetic': 'registration RPC result'})
        proof_name = self.write(f'{self.prefix}/registration-proof.json', {
            'source_refs': [{'path': source_name, 'sha256': self.hashes[source_name]}],
            'rpc_configuration': {'path': RPC_CONFIG.as_posix(), 'sha256': self.hashes[RPC_CONFIG.as_posix()]},
            'directory': {'evidence': [{'path': directory_name, 'sha256': self.hashes[directory_name]}]},
            'document': {'evidence': [{'path': source_name, 'sha256': self.hashes[source_name]}]},
            'rpc': {'chain': {'evidence': [{'path': rpc_name, 'sha256': self.hashes[rpc_name]}]}}})
        initialize = self.request('mcp-initialize', {'jsonrpc': '2.0', 'id': 'mcp-initialize',
                                  'method': 'initialize', 'params': {'protocolVersion': '2025-06-18',
                                  'capabilities': {}, 'clientInfo': {'name': 'synthetic-test', 'version': '1'}}},
                                  {'protocolVersion': '2025-06-18', 'capabilities': {'tools': {}}}, 1)
        initialized = self.request('mcp-initialized', {'jsonrpc': '2.0', 'method': 'notifications/initialized'},
                                   None, 3, status=204,
                                   headers={**ACCEPT, 'MCP-Protocol-Version': '2025-06-18'})
        catalog = self.request('mcp-tools', {'jsonrpc': '2.0', 'id': 'mcp-tools', 'method': 'tools/list',
                                            'params': {}}, {'tools': tools()}, 5,
                               headers={**ACCEPT, 'MCP-Protocol-Version': '2025-06-18'})
        execution = self.write(f'{self.prefix}/query-execution-plan.json', {
            **ADAPTER, 'schema_version': 'query-execution-v1', 'canonical': self.registration['canonical'],
            'proof_path': proof_name, 'created_at': at(7).isoformat(), 'arguments': {},
            'max_business_calls': 1, 'max_requests': 7, 'paid_calls': 0, 'retries': 0,
            'mainnet_writes': False})
        claim = {'last_burn': {'bobai_burned': 1, 'burn_tx': 'https://bscscan.com/tx/' + TX}}
        business = self.request('query-business', {'jsonrpc': '2.0', 'id': 'query-business',
                                'method': 'tools/call', 'params': {'name': ADAPTER['tool'], 'arguments': {}}},
                                {'content': [{'type': 'text', 'text': json.dumps(claim)}]}, 8,
                                MeasurementPurpose.FUNCTIONAL,
                                headers={**ACCEPT, 'MCP-Protocol-Version': '2025-06-18'})
        self.values = evidence()
        for record in (self.values['receipt'], self.values['transaction']):
            record['to'] = ADAPTER['token']
        for log in self.values['receipt']['logs']:
            if log['address'] == SYNTHETIC_TOKEN:
                log['address'] = ADAPTER['token']
        block = self.values['receipt']['blockNumber']
        specs = {'chain': ('eth_chainId', []), 'head': ('eth_blockNumber', []),
                 'receipt': ('eth_getTransactionReceipt', [TX]),
                 'transaction': ('eth_getTransactionByHash', [TX]),
                 'header': ('eth_getBlockByNumber', [block, False]),
                 'decimals': ('eth_call', [{'to': ADAPTER['token'], 'data': '0x313ce567'}, block])}
        rpc = {}
        for index, (field, (method, params)) in enumerate(specs.items()):
            key = 'query-reference-' + field
            rpc[field] = self.request(key, {'jsonrpc': '2.0', 'id': key, 'method': method, 'params': params},
                                      self.values[field], 10 + index * 2, url=RPC)
        self.write(self.plan_name, {'schema_version': 'query-checker-evidence-v1', 'checker_id': CHECKER_ID,
                                   'checker_version': VERSION, 'policy_version': 'service-contract-v1',
                                   'adapter_id': ADAPTER['id'], 'execution_plan': execution,
                                   'catalog_request': catalog, 'initialize_request': initialize,
                                   'initialized_request': initialized, 'business_request': business,
                                   'rpc_requests': rpc})

    def rebuild(self):
        return rebuild_query(self.root, self.plan_name, self.hashes)

    def report(self):
        canonical, capability, sample, _, _ = self.rebuild()
        return EvaluationReport(policy_version='service-contract-v1', candidate_key='synthetic-query',
                                name='Synthetic fixture, not a real Agent score',
                                registration_reference=canonical, generated_at=at(40), scope='Synthetic test',
                                scope_exclusions=['No real registration, network or Agent invocation'],
                                evaluation_window='Synthetic fixed times', approach='Offline retained bytes',
                                samples=[sample], source_references=sorted(self.hashes), limitations=[],
                                capabilities=[capability])

    def test_adapter_reuses_authenticated_endpoint_across_agent_ids(self):
        for agent_id in (100, 200, 49467):
            with self.subTest(agent_id=agent_id):
                self.assertEqual(match_query_adapter(identity(agent_id), ADAPTER['endpoint'], tools()), ADAPTER)
        for change in ({'registration_verified': False}, {'document': None}, {'services': []},
                       {'token_uri': 'ipfs://unverified-cid'},
                       {'canonical': f'eip155:8453:{REGISTRY}:100'}):
            value = {**identity(), **change}
            self.assertIsNone(match_query_adapter(value, ADAPTER['endpoint'], tools()))
        self.assertIsNone(match_query_adapter(identity(), 'https://unreviewed.example/mcp', tools()))
        for catalog in ([], tools() * 2, [{'name': 'unknown', 'inputSchema': EMPTY_SCHEMA}],
                        [{'name': ADAPTER['tool'], 'inputSchema': {'type': 'object'}}],
                        [{'name': ADAPTER['tool'], 'inputSchema': {**EMPTY_SCHEMA,
                            'properties': {'callback': {'type': 'string'}}}, 'annotations': {'readOnlyHint': True}}],
                        [{'name': ADAPTER['tool'], 'inputSchema': {**EMPTY_SCHEMA, 'additionalProperties': True}}]):
            self.assertIsNone(match_query_adapter(identity(), ADAPTER['endpoint'], catalog))

    def test_unsupported_and_disabled_collection_fall_back_without_calls(self):
        for enabled in (False, True):
            no_call = SimpleNamespace(enabled=enabled, root=self.root, inputs={})
            self.assertEqual(collect_query_tasks({'proof_path': 'synthetic', 'canonical': identity()['canonical']},
                                                  no_call), ([], [], []))
        self.registration['services'] = []
        unsupported = SimpleNamespace(enabled=True, root=self.root,
                                      inputs={f'{self.prefix}/mcp-tools.observation.json': 'unused'})
        self.assertEqual(collect_query_tasks({'proof_path': 'synthetic', 'canonical': identity()['canonical']},
                                            unsupported), ([], [], []))

    def test_dispatcher_noop_and_ordered_results_preserve_collectors(self):
        registration, offline = {'canonical': 'synthetic'}, SimpleNamespace(enabled=False)
        query, mech = Mock(return_value=([], [], [])), Mock(return_value=([], [], []))
        with patch('reputation_platform.checker_dispatch.BUSINESS_CHECKERS', (('query', query), ('mech', mech))):
            self.assertEqual(collect_business_checks(registration, offline), ([], [], []))
        query.assert_called_once_with(registration, offline)
        mech.assert_called_once_with(registration, offline)
        query.return_value = (['query-capability'], ['query-sample'], ['query-gap'])
        mech.return_value = (['existing-mech-capability'], ['existing-mech-sample'], ['existing-mech-gap'])
        with patch('reputation_platform.checker_dispatch.BUSINESS_CHECKERS', (('query', query), ('mech', mech))):
            self.assertEqual(collect_business_checks(registration, offline),
                             (['query-capability', 'existing-mech-capability'],
                              ['query-sample', 'existing-mech-sample'], ['query-gap', 'existing-mech-gap']))

    def test_rebuild_closes_original_bytes_and_report_without_functional_score(self):
        canonical, capability, sample, inputs, times = self.rebuild()
        self.assertEqual(canonical, identity()['canonical'])
        self.assertEqual(sample.sample.verdict, Verdict.PASS)
        self.assertEqual(sample.sample.purpose, MeasurementPurpose.FUNCTIONAL)
        self.assertEqual(capability.checker_id, CHECKER_ID)
        self.assertEqual(set(inputs), set(sample.sample.evidence))
        self.assertEqual(set(inputs), set(self.hashes))
        self.assertIn('"raw_amount": "1250"', sample.independent_result)
        self.assertTrue(all(at(2) <= value <= at(21) for value in times))
        report = self.report()
        self.assertEqual(verify_query_samples(self.root, report, self.hashes), {'query-business'})
        self.assertIsNone(report.scores.functional.value)
        self.assertIsNone(report.scores.behavioral.value)
        self.assertIsNone(report.scores.overall)

    def test_legitimate_rpc_errors_or_missing_reference_stay_unknown(self):
        key = 'query-reference-head'
        for response in ({'jsonrpc': '2.0', 'id': key, 'error': {'code': -32000, 'message': 'RPC unavailable'}},
                         {'jsonrpc': '2.0', 'id': key, 'result': None}):
            self.response(key, response)
            self.assertEqual(self.rebuild()[2].sample.verdict, Verdict.UNKNOWN)
        for suffix in ('.observation.json', '.response.bin'):
            name = f'{self.prefix}/{key}{suffix}'
            self.hashes.pop(name)
            (self.root / name).unlink()
        self.write(f'{self.prefix}/{key}.skip.json', {'request_sent': False, 'reason': 'request budget exhausted'})
        self.assertEqual(self.rebuild()[2].sample.verdict, Verdict.UNKNOWN)
        plan = self.read(self.plan_name)
        plan['rpc_requests'].pop('header')
        plan['rpc_requests'].pop('decimals')
        self.write(self.plan_name, plan)
        key = 'query-reference-receipt'
        self.response(key, {'jsonrpc': '2.0', 'id': key, 'error': {'code': -32000, 'message': 'not available'}})
        self.assertEqual(self.rebuild()[2].sample.verdict, Verdict.UNKNOWN)

    def test_missing_oracle_request_indices_are_integrity_errors(self):
        original = self.read(self.plan_name)
        for field in ('chain', 'head', 'receipt', 'transaction', 'header', 'decimals'):
            with self.subTest(field=field):
                plan = deepcopy(original)
                plan['rpc_requests'].pop(field)
                self.write(self.plan_name, plan)
                with self.assertRaises(ValueError):
                    self.rebuild()
        self.write(self.plan_name, original)
        observation = f'{self.prefix}/query-reference-head.observation.json'
        self.hashes.pop(observation)
        with self.assertRaises(ValueError):
            self.rebuild()
        self.write(f'{self.prefix}/query-reference-head.skip.json', {'request_sent': True})
        with self.assertRaises(ValueError):
            self.rebuild()

    def test_mcp_initialization_order_and_negotiated_headers_are_enforced(self):
        for key in ('mcp-initialized', 'mcp-tools'):
            name = f'{self.prefix}/{key}.request-plan.json'
            original = self.read(name)
            for headers in (ACCEPT, {**ACCEPT, 'MCP-Protocol-Version': '2024-11-05'}):
                with self.subTest(key=key, headers=headers):
                    self.write(name, {**original, 'headers': headers})
                    with self.assertRaises(ValueError):
                        self.rebuild()
            self.write(name, original)
        for key, second in (('mcp-initialized', 1), ('mcp-tools', 3)):
            name = f'{self.prefix}/{key}.request-plan.json'
            original = self.read(name)
            with self.subTest(request_before_previous_response=key):
                self.write(name, {**original, 'created_at': at(second).isoformat()})
                with self.assertRaises(ValueError):
                    self.rebuild()
            self.write(name, original)
        name = f'{self.prefix}/mcp-tools.observation.json'
        original = self.read(name)
        request = f'{self.prefix}/mcp-tools.request-plan.json'
        self.write(request, {**self.read(request), 'created_at': at(1).isoformat()})
        self.write(name, {**original, 'observed_at': at(3).isoformat()})
        with self.assertRaises(ValueError):
            self.rebuild()

    def test_wrong_disclosed_amount_is_functional_failure(self):
        key = 'query-business'
        claim = {'last_burn': {'bobai_burned': 2, 'burn_tx': 'https://bscscan.com/tx/' + TX}}
        self.response(key, {'jsonrpc': '2.0', 'id': key,
                           'result': {'content': [{'type': 'text', 'text': json.dumps(claim)}]}})
        sample = self.rebuild()[2]
        self.assertEqual(sample.sample.verdict, Verdict.FAIL)
        self.assertEqual(verify_query_samples(self.root, self.report(), self.hashes), {'query-business'})

    def test_missing_file_hash_and_dependency_are_integrity_errors(self):
        name = f'{self.prefix}/query-reference-receipt.response.bin'
        original = (self.root / name).read_bytes()
        (self.root / name).unlink()
        with self.assertRaises(ValueError):
            self.rebuild()
        (self.root / name).write_bytes(original + b' ')
        with self.assertRaises(ValueError):
            self.rebuild()
        (self.root / name).write_bytes(original)
        missing = dict(self.hashes)
        missing.pop(name)
        with self.assertRaises(ValueError):
            rebuild_query(self.root, self.plan_name, missing)
        for name in (f'{self.prefix}/registration-rpc.json', f'{self.prefix}/registration-directory.json'):
            missing = dict(self.hashes)
            missing.pop(name)
            with self.assertRaises(ValueError):
                rebuild_query(self.root, self.plan_name, missing)
        proof_name = f'{self.prefix}/registration-proof.json'
        proof = self.read(proof_name)
        proof['source_refs'][0]['sha256'] = '0' * 64
        self.write(proof_name, proof)
        with self.assertRaises(ValueError):
            self.rebuild()

    def test_frozen_call_rpc_scope_and_catalog_tampering_are_rejected(self):
        for name, key, replacement in (
            (f'{self.prefix}/query-execution-plan.json', 'arguments', {'callback': 'https://unreviewed.example'}),
            (f'{self.prefix}/query-execution-plan.json', 'max_requests', 8),
            (f'{self.prefix}/query-business.request-plan.json', 'url', 'https://unreviewed.example/mcp'),
            (f'{self.prefix}/query-reference-head.request-plan.json', 'rpc_configuration_source', 'agent-metadata'),
        ):
            with self.subTest(name=name, key=key):
                original = self.read(name)
                self.write(name, {**original, key: replacement})
                with self.assertRaises(ValueError):
                    self.rebuild()
                self.write(name, original)
        key = 'mcp-tools'
        self.response(key, {'jsonrpc': '2.0', 'id': key, 'result': {'tools': [
            {'name': ADAPTER['tool'], 'inputSchema': {'type': 'object', 'properties': {'signature': {'type': 'string'}}}}]}})
        with self.assertRaises(ValueError):
            self.rebuild()

    def test_report_compares_entire_sample_identity_and_capability(self):
        original = self.report()
        sample_changes = {'sample': original.samples[0].sample.model_copy(update={'verdict': Verdict.FAIL}),
                          'title': 'altered', 'claimed_output': 'altered', 'independent_result': 'altered',
                          'observed_at': at(8), 'checks': [], 'input_summary': 'altered',
                          'capability_id': 'altered'}
        for field, value in sample_changes.items():
            with self.subTest(sample_field=field):
                report = original.model_copy(deep=True)
                report.samples[0] = report.samples[0].model_copy(update={field: value})
                with self.assertRaises(ValueError):
                    verify_query_samples(self.root, report, self.hashes)
        for field, value in {'task_key': 'another-task', 'evidence': [], 'reason': 'altered',
                             'sample_id': 'another-id', 'elapsed_ms': 99}.items():
            with self.subTest(scored_sample_field=field):
                report = original.model_copy(deep=True)
                report.samples[0].sample = report.samples[0].sample.model_copy(update={field: value})
                with self.assertRaises(ValueError):
                    verify_query_samples(self.root, report, self.hashes)
        for field, value in {'operation': 'another-tool', 'checker_id': 'another-checker',
                             'checker_version': 'v99', 'capability_type': 'Prediction', 'tested_scope': 'all',
                             'sample_ids': [], 'description': 'altered', 'protocol': 'A2A',
                             'findings': [], 'missing_evidence': []}.items():
            with self.subTest(capability_field=field):
                report = original.model_copy(deep=True)
                report.capabilities[0] = report.capabilities[0].model_copy(update={field: value})
                with self.assertRaises(ValueError):
                    verify_query_samples(self.root, report, self.hashes)
        report = original.model_copy(update={'registration_reference': identity(200)['canonical']})
        with self.assertRaises(ValueError):
            verify_query_samples(self.root, report, self.hashes)

    def test_checker_metadata_without_a_query_plan_is_rejected(self):
        report = self.report()
        capability = report.capabilities[0].model_copy(update={'sample_ids': []})
        report = report.model_copy(update={'samples': [], 'capabilities': [capability]})
        hashes = {name: digest for name, digest in self.hashes.items() if name != self.plan_name}
        with self.assertRaisesRegex(ValueError, 'metadata requires'):
            verify_query_samples(self.root, report, hashes)

    def test_extra_query_capability_cannot_borrow_a_valid_plan(self):
        report = self.report()
        extra = report.capabilities[0].model_copy(update={
            'capability_id': 'unreconstructed-query', 'operation': 'unreviewed-tool', 'sample_ids': []})
        report.capabilities.append(extra)
        with self.assertRaisesRegex(ValueError, 'metadata requires'):
            verify_query_samples(self.root, report, self.hashes)
        report.capabilities[-1] = extra.model_copy(update={'checker_id': 'future-checker'})
        self.assertEqual(verify_query_samples(self.root, report, self.hashes), {'query-business'})

    def test_report_and_request_times_cannot_predate_sources(self):
        report = self.report().model_copy(update={'generated_at': at(20)})
        with self.assertRaises(ValueError):
            verify_query_samples(self.root, report, self.hashes)
        execution = f'{self.prefix}/query-execution-plan.json'
        original = self.read(execution)
        for seconds in (1, 10):
            self.write(execution, {**original, 'created_at': at(seconds).isoformat()})
            with self.assertRaises(ValueError):
                self.rebuild()
        self.write(execution, original)
        request = f'{self.prefix}/query-reference-head.observation.json'
        observation = self.read(request)
        self.write(request, {**observation, 'observed_at': at(8).isoformat()})
        with self.assertRaises(ValueError):
            self.rebuild()


if __name__ == '__main__':
    unittest.main()
