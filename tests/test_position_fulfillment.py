"""Real collector and source reconstruction over synthetic offline bytes, never real scores."""

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import socket
import unittest
from unittest.mock import patch

from reputation_core import EvaluationReport, MeasurementPurpose, ProbeObservation, Verdict
from reputation_platform.position_adapters import ADAPTERS
from reputation_platform.position_contracts import CONFIG, load_contract_reviews
from reputation_platform.position_fulfillment import (
    EXECUTION_NAME, PLAN_NAME, POLICY, POLICY_VERSION, SELECTION_NAME,
    collect_position_fulfillment, rebuild_position_fulfillment, verify_position_fulfillment_samples,
)
from reputation_platform.registration_discovery import DiscoveryEvidence
from test_position_adapters import business, catalog
from test_position_checker import PositionFixture
from test_position_oracle import claim, evidence as oracle_values

ROOT = Path(__file__).resolve().parents[1]


class PositionFulfillmentTests(unittest.TestCase):
    def setUp(self):
        self.calls, self.failure = [], None
        self.network = patch.object(socket, 'create_connection', side_effect=AssertionError('Offline test touched a socket'))
        self.socket_dial = self.network.start()
        self.addCleanup(self.network.stop)

    def fixture(self, adapter=ADAPTERS[0], *, budget=64):
        f = PositionFixture(adapter, complete=False)
        self.addCleanup(f.close)
        f.write(POLICY, b'Synthetic engineering policy; not a real Agent evaluation.')
        config = json.loads((ROOT / CONFIG).read_bytes())
        reviewed = next(deepcopy(item) for item in config['adapters'] if item['protocol'] == adapter['protocol'])
        source = f.write('runtime/synthetic-position/review.txt', b'Synthetic local reviewed contract fixture.')
        reviewed['review_dependencies'] = [{'path': source, 'sha256': f.hashes[source]}]
        config['adapters'] = [reviewed]
        f.write(CONFIG, config)
        self.assertEqual(load_contract_reviews(f.root), config)
        collector = DiscoveryEvidence(f.root, 'runtime/fulfillment-collected',
            proxy='http://127.0.0.1:7890', enabled=True, timeout_seconds=15, max_requests=budget)
        collector.inputs.update(f.hashes)
        self.values, self.adapter = oracle_values(), adapter
        return f, collector

    def transport(self):
        parent = self

        class OfflineClient:
            def __init__(self, targets, **kwargs):
                self.target = targets[0]

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def fetch(self, key, output):
                target = self.target
                parent.calls.append((key, target))
                elapsed, status, error = 0, 200, None
                if target.method == 'GET':
                    raw = json.dumps(catalog(parent.adapter)).encode()
                elif key.startswith('fulfillment-business-'):
                    body = target.json_body
                    token_id = (body['params']['arguments']['position'] if parent.adapter['protocol'] == 'MCP'
                                else body['params']['message']['parts'][0]['data']['input']['tokenId'])
                    raw = business(parent.adapter, {**claim(), 'positionId': token_id}, key)
                else:
                    field = key.removeprefix('fulfillment-reference-')
                    if field == 'supply':
                        value = '0x' + f'{1400:064x}'
                    elif field.startswith('index-'):
                        value = '0x' + f'{1000 + int(field.removeprefix("index-")):064x}'
                    elif field.startswith('position-'):
                        value = parent.values['positions']
                    else:
                        value = parent.values[field.replace('-', '_')]
                    raw = json.dumps({'jsonrpc': '2.0', 'id': key, 'result': value}).encode()
                if parent.failure:
                    changes = parent.failure(key, target)
                    if changes:
                        status, raw, elapsed, error = changes
                filename = key + '.response.bin'
                (output / filename).write_bytes(raw)
                obs = ProbeObservation(request_key=key, purpose=target.purpose, url=target.url,
                    method=target.method, request_json=json.dumps(target.json_body) if target.method == 'POST' else None,
                    observed_at=datetime.now(timezone.utc), http_status=status, elapsed_ms=elapsed,
                    outcome=Verdict.PASS if status == 200 else Verdict.UNKNOWN, error_kind=error,
                    response_file=filename, response_sha256=hashlib.sha256(raw).hexdigest(), body_complete=True)
                (output / (key + '.observation.json')).write_text(obs.model_dump_json(), encoding='utf-8')
                return obs

        return patch('reputation_platform.registration_discovery.SafeHttpClient', OfflineClient)

    def collect(self, f, collector):
        with self.transport(), patch('reputation_platform.registration_discovery.load_zan_key_file', return_value=None):
            result = collect_position_fulfillment({'proof_path': f.proof, 'canonical': f.canonical['canonical']}, collector)
        self.assertEqual(self.socket_dial.call_count, 0)
        return result

    def path(self, f, collector, name):
        return (collector.run / name).relative_to(f.root).as_posix()

    def rebuild(self, f, collector):
        return rebuild_position_fulfillment(f.root, self.path(f, collector, PLAN_NAME), collector.inputs)

    def mutate(self, f, collector, name, update):
        path = self.path(f, collector, name)
        value = json.loads((f.root / path).read_bytes())
        update(value)
        f.write(path, value)
        collector.inputs[path] = f.hashes[path]

    def report(self, f, collector):
        canonical, capability, samples, _, _ = self.rebuild(f, collector)
        return EvaluationReport(policy_version=POLICY_VERSION, candidate_key='synthetic-fulfillment',
            name='Synthetic fixture; no real Agent score', registration_reference=canonical,
            generated_at=datetime.now(timezone.utc) + timedelta(minutes=1), scope='Synthetic offline task bytes',
            scope_exclusions=['No real identity, service or score'], evaluation_window='Synthetic', approach='Offline',
            samples=samples, capabilities=[capability], source_references=sorted(collector.inputs), limitations=[])

    def test_both_protocols_collect_and_independently_rebuild_seven_f_and_seven_disjoint_b(self):
        task_keys = []
        for adapter in ADAPTERS:
            with self.subTest(protocol=adapter['protocol']):
                self.calls.clear()
                f, collector = self.fixture(adapter)
                capabilities, samples, _ = self.collect(f, collector)
                self.assertEqual([s.sample.verdict for s in samples], [Verdict.PASS] * 14)
                self.assertEqual([s.sample.purpose for s in samples], [MeasurementPurpose.FUNCTIONAL] * 7 + [MeasurementPurpose.BEHAVIORAL] * 7)
                self.assertEqual(len({s.sample.task_key for s in samples}), 14)
                self.assertTrue(set(s.sample.task_key for s in samples[:7]).isdisjoint(s.sample.task_key for s in samples[7:]))
                self.assertEqual(capabilities[0].protocol, adapter['protocol'])
                self.assertEqual(self.rebuild(f, collector)[2], samples)
                self.assertEqual(collector.request_count, len(list(collector.run.glob('*.observation.json'))))
                self.assertEqual(collector.request_count, 42)
                self.assertEqual(verify_position_fulfillment_samples(f.root, self.report(f, collector), collector.inputs),
                                 {s.sample.sample_id for s in samples})
                task_keys.append([s.sample.task_key for s in samples])
        self.assertEqual(*task_keys)

    def test_b_uses_delivery_contract_without_repeating_functional_truth(self):
        f, collector = self.fixture()

        def wrong_facts(key, target):
            if key.startswith('fulfillment-business-'):
                token_id = target.json_body['params']['arguments']['position']
                return 200, business(self.adapter, {**claim(), 'positionId': token_id, 'fee': 100}, key), 0, None

        self.failure = wrong_facts
        _, samples, _ = self.collect(f, collector)
        self.assertEqual([s.sample.verdict for s in samples[:7]], [Verdict.FAIL] * 7)
        self.assertEqual([s.sample.verdict for s in samples[7:]], [Verdict.PASS] * 7)
        self.assertEqual(len([target for _, target in self.calls if target.purpose == MeasurementPurpose.BACKGROUND]), 28)

    def test_wrong_response_id_is_fail_but_network_failure_is_unknown(self):
        for mutation, verdict in (('wrong_id', Verdict.FAIL), ('method_rejected', Verdict.FAIL),
                                  ('network_error', Verdict.UNKNOWN), ('quota', Verdict.UNKNOWN)):
            with self.subTest(mutation=mutation):
                f, collector = self.fixture()

                def fail(key, target):
                    if key != 'fulfillment-business-7':
                        return None
                    if mutation == 'wrong_id':
                        return 200, business(self.adapter, {**claim(), 'positionId': target.json_body['params']['arguments']['position']}, 'another-request'), 0, None
                    if mutation == 'network_error':
                        return None, b'', 0, 'ConnectTimeout'
                    code = -32602 if mutation == 'method_rejected' else -32005
                    return 200, json.dumps({'jsonrpc': '2.0', 'id': key, 'error': {'code': code, 'message': 'rejected'}}).encode(), 0, None

                self.failure = fail
                _, samples, _ = self.collect(f, collector)
                self.assertEqual(samples[7].sample.verdict, verdict)
                self.assertEqual(len(samples), 14)

    def test_missing_reference_and_budget_keep_all_frozen_slots_without_replacement(self):
        for case in ('missing_head', 'budget'):
            with self.subTest(case=case):
                self.calls.clear()
                f, collector = self.fixture(budget=2 if case == 'budget' else 64)
                if case == 'missing_head':
                    self.values['head'] = None
                _, samples, _ = self.collect(f, collector)
                self.assertEqual(len(samples), 14)
                self.assertEqual([s.sample.verdict for s in samples], [Verdict.UNKNOWN] * 14)
                self.assertEqual(len(self.calls), 2)
                self.assertEqual(collector.request_count, 2)
                self.assertFalse(any(key.startswith('fulfillment-business-') for key, _ in self.calls))
                self.assertEqual(self.rebuild(f, collector)[2], samples)

    def test_frozen_selection_reference_time_and_task_identity_tampering_is_rejected(self):
        mutations = (
            (SELECTION_NAME, lambda x: x['slots'][0].update(position_id='999')),
            (EXECUTION_NAME, lambda x: x.update(created_at='2000-01-01T00:00:00+00:00')),
            ('fulfillment-reference-position-1049.request-plan.json', lambda x: x['json']['params'][0].update(data='0x99fbab88' + f'{999:064x}')),
            ('fulfillment-business-7.request-plan.json', lambda x: x['json']['params']['arguments'].update(position='999')),
            (PLAN_NAME, lambda x: x['tasks'].pop()),
        )
        for filename, update in mutations:
            with self.subTest(file=filename):
                f, collector = self.fixture()
                self.collect(f, collector)
                self.mutate(f, collector, filename, update)
                with self.assertRaises(ValueError):
                    self.rebuild(f, collector)

    def test_report_cannot_replace_source_verdict_or_identity(self):
        f, collector = self.fixture()
        self.collect(f, collector)
        for field in ('verdict', 'identity', 'metadata'):
            report = self.report(f, collector)
            if field == 'verdict':
                report.samples[7].sample.verdict = Verdict.FAIL
            elif field == 'identity':
                report.registration_reference = report.registration_reference.rsplit(':', 1)[0] + ':999'
            else:
                report.capabilities[0].checker_version = 'v999'
            with self.subTest(field=field), self.assertRaises(ValueError):
                verify_position_fulfillment_samples(f.root, report, collector.inputs)


if __name__ == '__main__':
    unittest.main()
