"""Synthetic retained bytes; registration is explicitly stubbed, never a real score."""

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from reputation_core import EvaluationReport, MeasurementPurpose, ProbeObservation, Verdict
from reputation_platform.position_adapters import ADAPTERS, position_request
from reputation_platform.position_checker import (CAPABILITY_ID, CHECKER_ID, CONFIG, PLAN_NAME, POLICY,
    VERSION, rebuild_position, verify_position_samples)
from reputation_platform.position_oracle import FACTORY, NPM
from reputation_platform.protocol_evaluation import ACCEPT
from reputation_platform.registration_discovery import RPC_CONFIG
from test_position_adapters import business, catalog, identity
from test_position_oracle import claim, evidence

RPC = 'https://api.zan.top/node/v1/bsc/mainnet'
NOW = datetime(2026, 10, 19, tzinfo=timezone.utc)


class PositionFixture:
    def __init__(self, adapter=ADAPTERS[0], ids=('123', '124'), *, complete=True, missing_head=False, invalid_ids=()):
        self.temp = TemporaryDirectory(prefix='position-synthetic-')
        self.root = Path(self.temp.name).resolve()
        self.adapter, self.ids, self.hashes = adapter, list(ids), {}
        self.prefix, self.clock = 'runtime/synthetic-position', NOW
        self.canonical = identity(adapter)
        self.stub = patch('reputation_platform.position_checker.verify_registration_proof', return_value=self.canonical)
        self.stub.start()
        self.discovery()
        self.discovery_hashes = dict(self.hashes)
        if complete:
            self.complete(missing_head=missing_head, invalid_ids=invalid_ids)

    def close(self):
        self.stub.stop()
        self.temp.cleanup()

    def tick(self):
        self.clock += timedelta(seconds=1)
        return self.clock.isoformat()

    def write(self, name, value):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        raw = value if isinstance(value, bytes) else json.dumps(value, ensure_ascii=False).encode()
        path.write_bytes(raw)
        self.hashes[name] = hashlib.sha256(raw).hexdigest()
        return name

    def read(self, name):
        return json.loads((self.root / name).read_bytes())

    def mutate(self, name, change):
        value = self.read(name)
        change(value)
        self.write(name, value)

    def request(self, key, body, value=None, *, url=RPC, headers=None,
                method='POST', purpose=MeasurementPurpose.BACKGROUND, raw=None, status=200):
        name = f'{self.prefix}/{key}.request-plan.json'
        created = self.tick()
        self.write(name, {'created_at': created, 'key': key, 'url': url, 'method': method,
            'json': body, 'headers': headers, 'measurement_purpose': purpose.value, 'execution_enabled': True,
            'retries': 0, 'timeout_seconds': 45, 'max_body_bytes': 1048576,
            'rpc_configuration_source': 'operator-static-not-metadata' if url == RPC else None})
        if raw is None:
            raw = b'' if status == 204 else json.dumps({'jsonrpc': '2.0', 'id': key, 'result': value}).encode()
        response_file = f'{key}.response.bin'
        self.write(f'{self.prefix}/{response_file}', raw)
        obs = ProbeObservation(request_key=key, purpose=purpose, url=url, method=method,
            request_json=json.dumps(body) if method == 'POST' else None, observed_at=self.clock + timedelta(milliseconds=10),
            http_status=status, elapsed_ms=1, outcome=Verdict.PASS, error_kind=None,
            response_file=response_file, response_sha256=hashlib.sha256(raw).hexdigest(), body_complete=True)
        self.write(f'{self.prefix}/{key}.observation.json', json.loads(obs.model_dump_json()))
        return name

    def response(self, key, raw):
        self.write(f'{self.prefix}/{key}.response.bin', raw)
        self.mutate(f'{self.prefix}/{key}.observation.json',
            lambda value: value.update(response_sha256=hashlib.sha256(raw).hexdigest()))

    def skip(self, key, reason, **extra):
        return self.write(f'{self.prefix}/{key}.skip.json', {'created_at': self.tick(), 'key': key,
            'request_sent': False, 'reason': reason, **extra})

    def discovery(self):
        self.write(POLICY, b'Synthetic engineering policy; no real Agent evaluation.')
        self.write(RPC_CONFIG.as_posix(), {'configuration_source': 'operator-static-not-metadata',
            'confirmation_distance': 64, 'chains': {'56': {'rpc_url': RPC, 'authentication': 'zan', 'credential_file': 'unused'}}})
        self.write(CONFIG, {'schema_version': 'position-read-tasks-v1', 'chain': 56, 'npm': NPM,
            'factory': FACTORY, 'position_ids': self.ids})
        document = self.write(f'{self.prefix}/registration-document.json', self.canonical['document'])
        self.proof = self.write(f'{self.prefix}/registration-proof.json', {
            'source_refs': [{'path': document, 'sha256': self.hashes[document]}],
            'rpc_configuration': {'path': RPC_CONFIG.as_posix(), 'sha256': self.hashes[RPC_CONFIG.as_posix()]},
            'directory': None, 'document': {'evidence': [{'path': document, 'sha256': self.hashes[document]}]}, 'rpc': {}})
        self.headers = {**ACCEPT, 'MCP-Protocol-Version': '2025-06-18'} if self.adapter['protocol'] == 'MCP' else None
        if self.adapter['protocol'] == 'MCP':
            init = self.request('mcp-initialize', {'jsonrpc': '2.0', 'id': 'mcp-initialize',
                'method': 'initialize', 'params': {'protocolVersion': '2025-03-26', 'capabilities': {},
                'clientInfo': {'name': 'synthetic-test', 'version': '1'}}},
                {'protocolVersion': '2025-06-18', 'capabilities': {'tools': {}}}, url=self.adapter['endpoint'], headers=ACCEPT)
            notify = self.request('mcp-initialized', {'jsonrpc': '2.0', 'method': 'notifications/initialized'},
                url=self.adapter['endpoint'], headers=self.headers, status=204)
            tools = self.request('mcp-tools', {'jsonrpc': '2.0', 'id': 'mcp-tools', 'method': 'tools/list', 'params': {}},
                {'tools': catalog(self.adapter)}, url=self.adapter['endpoint'], headers=self.headers)
            self.descriptor = {'protocol': 'MCP', 'endpoint': self.adapter['endpoint'],
                'initialize_request': init, 'initialized_request': notify, 'catalog_request': tools}
        else:
            card = self.request('a2a-document', None, url=self.adapter['endpoint'], method='GET',
                raw=json.dumps(catalog(self.adapter)).encode())
            self.descriptor = {'protocol': 'A2A', 'endpoint': self.adapter['endpoint'], 'card_request': card}

    def complete(self, *, missing_head=False, invalid_ids=()):
        self.execution = self.write(f'{self.prefix}/position-execution-plan.json', {**self.adapter,
            'schema_version': 'position-execution-v1', 'canonical': self.canonical['canonical'], 'proof_path': self.proof,
            'created_at': self.tick(), 'discovery': self.descriptor, 'new_card_request': None,
            'checker_id': CHECKER_ID, 'checker_version': VERSION, 'policy_version': 'service-contract-v1',
            'chain': 56, 'npm': NPM, 'factory': FACTORY, 'position_ids': self.ids,
            'config': {'path': CONFIG, 'sha256': self.hashes[CONFIG]}, 'policy': {'path': POLICY, 'sha256': self.hashes[POLICY]},
            'request_count_start': 12, 'request_count_after_discovery': 12,
            'max_business_calls': len(self.ids), 'max_requests': 28, 'max_total_requests': 64,
            'timeout_seconds': 45, 'max_body_bytes': 1048576, 'retries': 0, 'paid_calls': 0, 'mainnet_writes': False})
        values, count = evidence(), 0
        if missing_head:
            values['head'] = None
        block = '0x64'
        specs = {'chain': ('eth_chainId', []), 'head': ('eth_blockNumber', []),
            'header': ('eth_getBlockByNumber', [block, False]), 'npm_code': ('eth_getCode', [NPM, block]),
            'factory': ('eth_call', [{'to': NPM, 'data': '0xc45a0155'}, block]), 'factory_code': ('eth_getCode', [FACTORY, block])}
        shared = {}
        for field, (method, params) in specs.items():
            key = 'position-reference-' + field.replace('_', '-')
            if missing_head and field not in ('chain', 'head'):
                shared[field] = self.skip(key, 'reference_dependency_unavailable', field=field)
            else:
                shared[field] = self.request(key, {'jsonrpc': '2.0', 'id': key, 'method': method, 'params': params}, values[field])
                count += 1
        tasks = []
        for token_id in self.ids:
            row = {'position_id': token_id, 'rpc_requests': {}}
            for field, selector in [('positions', '0x99fbab88'), ('owner', '0x6352211e')]:
                key, full_field = 'position-reference-' + token_id + '-' + field, token_id + '-' + field
                if missing_head:
                    row['rpc_requests'][field] = self.skip(key, 'reference_dependency_unavailable', field=full_field)
                else:
                    params = [{'to': NPM, 'data': selector + f'{int(token_id):064x}'}, block]
                    value = '0x' + '0' * 64 if field == 'owner' and token_id in invalid_ids else values[field]
                    row['rpc_requests'][field] = self.request(key, {'jsonrpc': '2.0', 'id': key, 'method': 'eth_call', 'params': params}, value)
                    count += 1
            key = 'position-business-' + token_id
            if missing_head or token_id in invalid_ids:
                row['business_request'] = self.skip(key, 'reference_unavailable')
            else:
                answer = {**claim(), 'positionId': token_id}
                row['business_request'] = self.request(key, position_request(self.adapter, key, token_id),
                    url=self.adapter['endpoint'], headers=self.headers, purpose=MeasurementPurpose.FUNCTIONAL,
                    raw=business(self.adapter, answer, key))
                count += 1
            tasks.append(row)
        self.plan = self.write(f'{self.prefix}/{PLAN_NAME}', {'schema_version': 'position-checker-evidence-v1',
            'checker_id': CHECKER_ID, 'checker_version': VERSION, 'policy_version': 'service-contract-v1',
            'created_at': self.tick(), 'execution_plan': self.execution, 'rpc_requests': shared, 'tasks': tasks,
            'request_count_end': 12 + count})

    def rebuild(self):
        return rebuild_position(self.root, self.plan, self.hashes)

    def report(self):
        canonical, capability, samples, _, _ = self.rebuild()
        return EvaluationReport(policy_version='service-contract-v1', candidate_key='synthetic-position',
            name='Synthetic fixture; no real Agent score', registration_reference=canonical,
            generated_at=self.clock + timedelta(seconds=1), scope='Synthetic fixed bytes',
            scope_exclusions=['No network or real registration'], evaluation_window='Synthetic', approach='Offline',
            samples=samples, capabilities=[capability], source_references=sorted(self.hashes), limitations=[])


class PositionCheckerTests(unittest.TestCase):
    def fixture(self, *args, **kwargs):
        value = PositionFixture(*args, **kwargs)
        self.addCleanup(value.close)
        return value

    def test_both_providers_reconstruct_seven_distinct_shared_task_keys(self):
        task_keys = []
        for adapter in ADAPTERS:
            f = self.fixture(adapter, ids=tuple(str(n) for n in range(123, 130)))
            canonical, capability, samples, inputs, _ = f.rebuild()
            self.assertEqual(canonical, f.canonical['canonical'])
            self.assertEqual([s.sample.verdict for s in samples], [Verdict.PASS] * 7)
            self.assertEqual(len({s.sample.task_key for s in samples}), 7)
            self.assertEqual(capability.capability_id, CAPABILITY_ID)
            self.assertIn(adapter['provider'], capability.findings[0].explanation)
            self.assertIn(POLICY, inputs)
            self.assertEqual(verify_position_samples(f.root, f.report(), f.hashes), {s.sample.sample_id for s in samples})
            task_keys.append([s.sample.task_key for s in samples])
        self.assertEqual(*task_keys)

    def test_wrong_complete_facts_and_hallmark_internal_claims_fail(self):
        for adapter in ADAPTERS:
            f = self.fixture(adapter)
            key = 'position-business-123'
            answer = {**claim(), 'fee': 100, 'reportedChain': 97, 'reportedPositionId': '888'}
            f.response(key, business(adapter, answer, key))
            self.assertEqual(f.rebuild()[2][0].sample.verdict, Verdict.FAIL)
            self.assertEqual(f.rebuild()[2][1].sample.verdict, Verdict.PASS)
        for field, value in [('reportedChain', 97), ('reportedPositionId', '999')]:
            f = self.fixture(ADAPTERS[1])
            f.response(key, business(f.adapter, {**claim(), field: value}, key))
            self.assertEqual(f.rebuild()[2][0].sample.verdict, Verdict.FAIL)

    def test_network_tool_and_malformed_outputs_are_unknown(self):
        for raw in (b'not-json', b'{"jsonrpc":"2.0","id":"position-business-123","error":{"code":-1}}',
                    b'{"jsonrpc":"2.0","id":"position-business-123","result":{"isError":true}}'):
            f = self.fixture()
            f.response('position-business-123', raw)
            self.assertEqual(f.rebuild()[2][0].sample.verdict, Verdict.UNKNOWN)
        f = self.fixture(ids=('123',))
        f.mutate(f'{f.prefix}/position-business-123.observation.json', lambda x: x.update(http_status=402))
        self.assertEqual(f.rebuild()[2][0].sample.verdict, Verdict.UNKNOWN)

    def test_host_stops_are_reconstructed_from_original_observations(self):
        f = self.fixture()
        f.mutate(f'{f.prefix}/position-business-123.observation.json', lambda x: x.update(http_status=402))
        with self.assertRaises(ValueError):
            f.rebuild()
        second = f'{f.prefix}/position-business-124'
        f.hashes.pop(second + '.observation.json')
        f.write(second + '.skip.json', {'request_sent': False, 'reason': 'host_stopped'})
        f.mutate(f.plan, lambda x: x.update(request_count_end=x['request_count_end'] - 1))
        self.assertEqual([s.sample.verdict for s in f.rebuild()[2]], [Verdict.UNKNOWN] * 2)

        f = self.fixture()
        owner = 'position-reference-123-owner'
        f.response(owner, json.dumps({'jsonrpc': '2.0', 'id': owner,
            'error': {'code': -32005, 'message': 'quota'}}).encode())
        first = f'{f.prefix}/position-business-123'
        f.hashes.pop(first + '.observation.json')
        f.write(first + '.skip.json', {'key': 'position-business-123', 'request_sent': False,
            'reason': 'reference_unavailable', 'created_at': f.read(first + '.request-plan.json')['created_at']})
        f.mutate(f.plan, lambda x: (x['tasks'][0].update(business_request=first + '.skip.json'),
                                  x.update(request_count_end=x['request_count_end'] - 1)))
        with self.assertRaises(ValueError):
            f.rebuild()

    def test_incomplete_references_keep_all_unknown_tasks_and_explicit_skips(self):
        for missing_head, invalid_ids in [(True, ()), (False, ('123', '124'))]:
            f = self.fixture(missing_head=missing_head, invalid_ids=invalid_ids)
            _, _, samples, _, _ = f.rebuild()
            self.assertEqual([s.sample.verdict for s in samples], [Verdict.UNKNOWN] * 2)
            for row in f.read(f.plan)['tasks']:
                self.assertTrue(row['business_request'].endswith('.skip.json'))
            if missing_head:
                sent = [f.read(name) for name in f.hashes if name.endswith('.request-plan.json')]
                self.assertFalse(any(x['json'] and x['json'].get('method') in ('eth_call', 'eth_getCode') for x in sent))

    def test_missing_dependencies_raw_tampering_and_registration_hashes_reject(self):
        for mutation in ('absent-owner', 'changed-raw', 'proof-dependency'):
            f = self.fixture()
            if mutation == 'absent-owner':
                f.hashes.pop(f'{f.prefix}/position-reference-123-owner.observation.json')
            elif mutation == 'changed-raw':
                (f.root / f'{f.prefix}/position-business-123.response.bin').write_bytes(b'tampered')
            else:
                f.write(f'{f.prefix}/registration-document.json', {'injected': 'service'})
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                f.rebuild()

    def test_wrong_fixed_block_target_or_task_list_reject_even_with_new_hashes(self):
        for mutation in ('block', 'target', 'missing-task', 'reordered-task', 'counter', 'budget'):
            f = self.fixture()
            if mutation in ('block', 'target'):
                name = f'{f.prefix}/position-reference-123-positions.request-plan.json'
                f.mutate(name, lambda x: x['json']['params'].__setitem__(1, 'latest') if mutation == 'block'
                         else x['json']['params'][0].update(to=FACTORY))
            elif mutation == 'missing-task':
                f.mutate(f.plan, lambda x: x['tasks'].pop())
            elif mutation == 'reordered-task':
                f.mutate(f.plan, lambda x: x['tasks'].reverse())
            elif mutation == 'counter':
                f.mutate(f.plan, lambda x: x.update(request_count_end=64))
            else:
                f.mutate(f.execution, lambda x: x.update(max_business_calls=8))
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                f.rebuild()

    def test_completion_time_must_precede_frozen_next_step_and_report(self):
        for key in ('mcp-tools', 'position-reference-head', 'position-reference-123-owner'):
            f = self.fixture()
            f.mutate(f'{f.prefix}/{key}.observation.json', lambda x: x.update(elapsed_ms=60000))
            with self.subTest(key=key), self.assertRaises(ValueError):
                f.rebuild()
        f = self.fixture()
        report = f.report()
        report.generated_at = NOW
        with self.assertRaises(ValueError):
            verify_position_samples(f.root, report, f.hashes)

    def test_exact_schema_negotiation_and_authenticated_card_are_required(self):
        for adapter in ADAPTERS:
            f = self.fixture(adapter)
            if adapter['protocol'] == 'MCP':
                f.response('mcp-tools', json.dumps({'jsonrpc': '2.0', 'id': 'mcp-tools',
                    'result': {'tools': [{'name': adapter['tool'], 'inputSchema': {'type': 'object'}}]}}).encode())
            else:
                f.mutate(f.descriptor['card_request'], lambda x: x.update(url='https://unregistered.example/card'))
            with self.subTest(adapter=adapter['id']), self.assertRaises(ValueError):
                f.rebuild()

    def test_whole_capability_samples_and_checker_metadata_are_compared(self):
        for mutation in ('capability', 'checks', 'sample', 'omit', 'unplanned'):
            f = self.fixture()
            report = f.report()
            if mutation == 'capability':
                report.capabilities[0].description = 'overclaimed scope'
            elif mutation == 'checks':
                report.samples[0].checks[0].explanation = 'unverified replacement'
            elif mutation == 'sample':
                report.samples[0].input_summary = 'wrong endpoint'
            elif mutation == 'omit':
                report.samples.pop()
            else:
                f.hashes.pop(f.plan)
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                verify_position_samples(f.root, report, f.hashes)

    def test_unindexed_requests_skips_and_contradictory_sent_records_reject(self):
        for mutation in ('extra-sent', 'extra-plan', 'extra-skip', 'sent-and-skip'):
            f = self.fixture(ids=('123',))
            if mutation == 'sent-and-skip':
                f.write(f'{f.prefix}/position-business-123.skip.json', {'request_sent': False, 'reason': 'host_stopped'})
            elif mutation == 'extra-skip':
                f.skip('unindexed-read', 'reference_unavailable')
            else:
                extra = f.request('unindexed-read', {'jsonrpc': '2.0', 'id': 'unindexed-read',
                    'method': 'tools/call', 'params': {'name': 'unreviewed_paid_tool', 'arguments': {}}},
                    {}, url=f.adapter['endpoint'], purpose=MeasurementPurpose.FUNCTIONAL)
                if mutation == 'extra-plan':
                    f.hashes.pop(extra.removesuffix('.request-plan.json') + '.observation.json')
                    f.hashes.pop(extra.removesuffix('.request-plan.json') + '.response.bin')
            f.mutate(f.plan, lambda x: x.update(created_at=f.tick()))
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                f.rebuild()

    def test_actual_body_and_completed_response_time_respect_frozen_bounds(self):
        for mutation in ('body', 'time'):
            f = self.fixture(ids=('123',))
            if mutation == 'body':
                f.response('position-business-123', b' ' * 1048577)
            else:
                f.mutate(f'{f.prefix}/position-business-123.observation.json', lambda x: x.update(elapsed_ms=46000))
                f.mutate(f.plan, lambda x: x.update(created_at=(f.clock + timedelta(seconds=100)).isoformat()))
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                f.rebuild()

    def test_old_availability_unsent_slots_are_anchored_before_position_execution(self):
        for mutation in (None, 'missing-slot', 'wrong-offset', 'late-plan', 'contradictory-observation'):
            f = self.fixture(complete=False)
            key = 'mcp-availability-002'
            prior_name = f.write(f'{f.prefix}/mcp-availability-plan.json', {
                'created_at': f.tick(), 'policy_version': 'service-contract-v1', 'purpose': 'availability',
                'url': f.adapter['endpoint'], 'method': 'POST', 'headers': f.headers,
                'slots': [{'key': key, 'offset_seconds': 30,
                    'json': {'jsonrpc': '2.0', 'id': key, 'method': 'tools/list', 'params': {}}}]})
            skip_name = f.write(f'{f.prefix}/{key}.skip.json', {'purpose': 'availability', 'request_sent': False,
                'reason': '此前鉴权、付费或限流响应已触发停止', 'scheduled_offset_seconds': 30})
            f.complete(invalid_ids=('123', '124'))
            if mutation == 'missing-slot':
                f.mutate(prior_name, lambda x: x.update(slots=[]))
            elif mutation == 'wrong-offset':
                f.mutate(skip_name, lambda x: x.update(scheduled_offset_seconds=60))
            elif mutation == 'late-plan':
                f.mutate(prior_name, lambda x: x.update(created_at=f.read(f.execution)['created_at']))
            elif mutation == 'contradictory-observation':
                f.write(f'{f.prefix}/{key}.observation.json', f.read(f'{f.prefix}/mcp-tools.observation.json'))
            with self.subTest(mutation=mutation):
                if mutation is None:
                    self.assertEqual([s.sample.verdict for s in f.rebuild()[2]], [Verdict.UNKNOWN] * 2)
                else:
                    with self.assertRaises(ValueError):
                        f.rebuild()

    def test_non_skip_without_own_time_cannot_inherit_forged_related_time(self):
        for related in (False, True):
            f = self.fixture(complete=False)
            key = 'orphan.request-plan.json'
            f.write(f'{f.prefix}/forged-availability-plan.json', {'created_at': f.tick(),
                'policy_version': 'service-contract-v1', 'purpose': 'availability', 'url': f.adapter['endpoint'],
                'method': 'POST', 'headers': f.headers, 'slots': [{'key': key, 'offset_seconds': 30,
                    'json': {'jsonrpc': '2.0', 'id': key, 'method': 'tools/list', 'params': {}}}]})
            f.write(f'{f.prefix}/{key}', {'purpose': 'availability', 'request_sent': False,
                'scheduled_offset_seconds': 30, 'json': {'jsonrpc': '2.0', 'id': key, 'method': 'tools/call',
                    'params': {'name': 'unreviewed_paid_tool', 'arguments': {}}}})
            if related:
                f.write(f'{f.prefix}/{key}.request-plan.json', {'created_at': f.tick()})
            f.complete()
            with self.subTest(related=related), self.assertRaises(ValueError):
                f.rebuild()

    def test_same_run_prior_availability_stop_binds_business_and_keeps_valid_unknown(self):
        for case in ('sent-after-stop', 'properly-skipped', 'unbound-request', 'other-run'):
            f = self.fixture(complete=False)
            if case == 'other-run':
                f.prefix = 'runtime/other-run'
            key = 'prior-availability-001'
            prior_name = f.write(f'{f.prefix}/prior-availability-plan.json', {'created_at': f.tick(),
                'policy_version': 'service-contract-v1', 'purpose': 'availability', 'url': f.adapter['endpoint'],
                'method': 'POST', 'headers': f.headers, 'slots': [{'key': key, 'offset_seconds': 0,
                    'json': {'jsonrpc': '2.0', 'id': key, 'method': 'tools/list', 'params': {}}}]})
            request = f.request(key, {'jsonrpc': '2.0', 'id': key, 'method': 'tools/list', 'params': {}},
                url=f.adapter['endpoint'], headers=f.headers, purpose=MeasurementPurpose.AVAILABILITY,
                raw=b'{"error":"payment required"}', status=402)
            f.prefix = 'runtime/synthetic-position'
            f.complete()
            if case == 'properly-skipped':
                for token_id in f.ids:
                    stem = f'{f.prefix}/position-business-{token_id}'
                    f.hashes.pop(stem + '.observation.json')
                    f.write(stem + '.skip.json', {'request_sent': False, 'reason': 'host_stopped'})
                f.mutate(f.plan, lambda x: x.update(request_count_end=x['request_count_end'] - len(f.ids)))
            elif case == 'unbound-request':
                f.mutate(request, lambda x: x.update(headers=ACCEPT))
            with self.subTest(case=case):
                if case in ('sent-after-stop', 'unbound-request'):
                    with self.assertRaises(ValueError):
                        f.rebuild()
                else:
                    verdict = Verdict.UNKNOWN if case == 'properly-skipped' else Verdict.PASS
                    self.assertEqual([s.sample.verdict for s in f.rebuild()[2]], [verdict] * 2)


if __name__ == '__main__':
    unittest.main()
