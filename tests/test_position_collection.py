"""Real DiscoveryEvidence orchestration with an explicit offline transport stub."""

from datetime import datetime, timezone
import hashlib
import json
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from reputation_core import MeasurementPurpose, ProbeObservation, Verdict
from reputation_platform.position_adapters import ADAPTERS
from reputation_platform.position_checker import PLAN_NAME, collect_position_tasks, rebuild_position
from reputation_platform.registration_discovery import DiscoveryEvidence
from test_position_adapters import business, catalog
from test_position_checker import PositionFixture
from test_position_oracle import claim, evidence as oracle_values


class PositionCollectionTests(unittest.TestCase):
    def setUp(self):
        self.calls = []
        self.failure = None

    def fixture(self, adapter=ADAPTERS[0], ids=('123', '124'), **kwargs):
        f = PositionFixture(adapter, ids=ids, complete=False)
        self.addCleanup(f.close)
        collector = DiscoveryEvidence(f.root, 'runtime/collected', proxy='http://127.0.0.1:7890', enabled=True,
                                      timeout_seconds=kwargs.get('timeout', 15), max_requests=64)
        collector.inputs.update(f.hashes)
        self.values, self.adapter = oracle_values(), adapter
        return f, collector

    def transport(self):
        parent = self

        class OfflineClient:
            def __init__(self, targets, **kwargs):
                self.target = targets[0]
                self.timeout = kwargs['timeout_seconds']

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def fetch(self, key, output):
                target = self.target
                parent.calls.append((key, target, self.timeout))
                status = 200
                if target.method == 'GET':
                    raw = json.dumps(catalog(parent.adapter)).encode()
                elif key.startswith('position-business-'):
                    token_id = key.removeprefix('position-business-')
                    raw = business(parent.adapter, {**claim(), 'positionId': token_id}, key)
                else:
                    field = key.rsplit('-', 1)[1]
                    if 'npm-code' in key:
                        field = 'npm_code'
                    elif 'factory-code' in key:
                        field = 'factory_code'
                    # Actual field keys retain underscores in the request key only for these fields.
                    field = key.removeprefix('position-reference-') if key in (
                        'position-reference-npm_code', 'position-reference-factory_code') else field
                    raw = json.dumps({'jsonrpc': '2.0', 'id': key, 'result': parent.values[field]}).encode()
                if parent.failure:
                    replacement = parent.failure(key)
                    if replacement:
                        status, raw = replacement
                filename = key + '.response.bin'
                (output / filename).write_bytes(raw)
                observed = ProbeObservation(request_key=key, purpose=target.purpose, url=target.url,
                    method=target.method, request_json=json.dumps(target.json_body) if target.method == 'POST' else None,
                    observed_at=datetime.now(timezone.utc), http_status=status, elapsed_ms=0,
                    outcome=Verdict.PASS if status == 200 else Verdict.UNKNOWN,
                    error_kind=None if status == 200 else 'http_status_not_success', response_file=filename,
                    response_sha256=hashlib.sha256(raw).hexdigest(), body_complete=True)
                (output / (key + '.observation.json')).write_text(observed.model_dump_json(), encoding='utf-8')
                return observed

        return patch('reputation_platform.registration_discovery.SafeHttpClient', OfflineClient)

    def collect(self, f, collector):
        with self.transport(), patch('reputation_platform.registration_discovery.load_zan_key_file', return_value=None):
            return collect_position_tasks({'proof_path': f.proof, 'canonical': f.canonical['canonical']}, collector)

    def test_two_protocols_use_one_collector_and_keep_operator_timeout(self):
        for adapter in ADAPTERS:
            with self.subTest(adapter=adapter['id']):
                self.calls.clear()
                f, collector = self.fixture(adapter, ids=tuple(str(n) for n in range(123, 130)))
                capabilities, samples, _ = self.collect(f, collector)
                self.assertEqual([s.sample.verdict for s in samples], [Verdict.PASS] * 7)
                self.assertEqual(len(self.calls), 27)
                self.assertEqual(collector.request_count, 27)
                self.assertEqual(collector.timeout_seconds, 15)
                self.assertTrue(all(timeout == 15 for _, _, timeout in self.calls))
                self.assertEqual(capabilities[0].protocol, adapter['protocol'])
                plan = (collector.run / PLAN_NAME).relative_to(f.root).as_posix()
                self.assertEqual(rebuild_position(f.root, plan, collector.inputs)[2], samples)
                self.assertEqual(len([t for _, t, _ in self.calls if t.purpose == MeasurementPurpose.FUNCTIONAL]), 7)

    def test_missing_head_never_fabricates_block_or_sends_business(self):
        f, collector = self.fixture(ids=tuple(str(n) for n in range(123, 130)))
        self.values['head'] = None
        _, samples, _ = self.collect(f, collector)
        self.assertEqual([s.sample.verdict for s in samples], [Verdict.UNKNOWN] * 7)
        self.assertEqual([key for key, _, _ in self.calls], ['position-reference-chain', 'position-reference-head'])
        skips = list(collector.run.glob('*.skip.json'))
        self.assertEqual(len(skips), 25)
        self.assertFalse(any(t.purpose == MeasurementPurpose.FUNCTIONAL for _, t, _ in self.calls))

    def test_rpc_semantic_quota_stops_host_and_keeps_all_tasks_unknown(self):
        for code in (-32005, -32016, 429):
            with self.subTest(code=code):
                self.calls.clear()
                f, collector = self.fixture()
                def fail(key):
                    if key == 'position-reference-123-owner':
                        return 200, json.dumps({'jsonrpc': '2.0', 'id': key,
                            'error': {'code': code, 'message': 'quota exceeded'}}).encode()
                self.failure = fail
                _, samples, _ = self.collect(f, collector)
                self.assertEqual([s.sample.verdict for s in samples], [Verdict.UNKNOWN] * 2)
                self.assertEqual(len(self.calls), 8)
                self.assertTrue((f.root / 'runtime/prediction-network-stops/api.zan.top.json').is_file())
                self.assertFalse(any(t.purpose == MeasurementPurpose.FUNCTIONAL for _, t, _ in self.calls))
                self.assertEqual(json.loads((collector.run / 'position-reference-124-owner.skip.json').read_bytes())['reason'], 'host_stopped')

    def test_http_payment_stops_provider_without_losing_other_frozen_tasks(self):
        f, collector = self.fixture()
        self.failure = lambda key: (402, b'{"error":"payment required"}') if key == 'position-business-123' else None
        _, samples, _ = self.collect(f, collector)
        self.assertEqual([s.sample.verdict for s in samples], [Verdict.UNKNOWN] * 2)
        self.assertEqual(len([t for _, t, _ in self.calls if t.purpose == MeasurementPurpose.FUNCTIONAL]), 1)
        self.assertEqual(json.loads((collector.run / 'position-business-124.skip.json').read_bytes())['reason'], 'host_stopped')

    def test_business_jsonrpc_quota_stops_provider_with_same_source_rule(self):
        for code in (-32005, -32016, 429):
            with self.subTest(code=code):
                self.calls.clear()
                f, collector = self.fixture()
                self.failure = lambda key: (200, json.dumps({'jsonrpc': '2.0', 'id': key,
                    'error': {'code': code, 'message': 'quota exceeded'}}).encode()) if key == 'position-business-123' else None
                _, samples, _ = self.collect(f, collector)
                self.assertEqual([s.sample.verdict for s in samples], [Verdict.UNKNOWN] * 2)
                self.assertEqual(len([t for _, t, _ in self.calls if t.purpose == MeasurementPurpose.FUNCTIONAL]), 1)
                self.assertEqual(json.loads((collector.run / 'position-business-124.skip.json').read_bytes())['reason'], 'host_stopped')

    def test_global_budget_keeps_explicit_unknown_samples(self):
        f, collector = self.fixture()
        collector.request_count = 63
        _, samples, _ = self.collect(f, collector)
        self.assertEqual(collector.request_count, 64)
        self.assertEqual(len(self.calls), 1)
        self.assertEqual([s.sample.verdict for s in samples], [Verdict.UNKNOWN] * 2)
        self.assertEqual(collector.max_requests, 64)

    def test_disabled_unsupported_schema_and_corrupt_catalog_send_no_requests(self):
        self.assertEqual(collect_position_tasks({}, SimpleNamespace(enabled=False)), ([], [], []))
        f, collector = self.fixture()
        tools_raw = f'{f.prefix}/mcp-tools.response.bin'
        f.response('mcp-tools', b'{"jsonrpc":"2.0","id":"mcp-tools","result":{"tools":[]}}')
        collector.inputs.update(f.hashes)
        self.assertEqual(self.collect(f, collector), ([], [], []))
        self.assertEqual(self.calls, [])
        for adapter in ADAPTERS:
            f, collector = self.fixture(adapter)
            name = tools_raw if adapter['protocol'] == 'MCP' else f'{f.prefix}/a2a-document.response.bin'
            (f.root / name).write_bytes(b'corrupted without updating manifest')
            with self.assertRaises(ValueError):
                self.collect(f, collector)
            self.assertEqual(self.calls, [])

    def test_exact_registered_card_fallback_uses_one_get_within_phase_budget(self):
        f, collector = self.fixture(ADAPTERS[1])
        card_url = 'https://hallmark-agents.vercel.app/rebalancer/.well-known/agent-card.json'
        f.canonical['services'].append({'name': 'agent-card', 'endpoint': card_url})
        for name in list(collector.inputs):
            if '/a2a-document.' in name:
                collector.inputs.pop(name)
        _, samples, _ = self.collect(f, collector)
        self.assertEqual([s.sample.verdict for s in samples], [Verdict.PASS] * 2)
        gets = [t for _, t, _ in self.calls if t.method == 'GET']
        self.assertEqual([t.url for t in gets], [card_url])
        self.assertEqual(len(self.calls), 13)


if __name__ == '__main__':
    unittest.main()
