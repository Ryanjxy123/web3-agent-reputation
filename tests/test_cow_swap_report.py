"""One offline acceptance: real public pilot bytes plus explicit controlled negatives."""
import base64
import copy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from eth_hash.auto import keccak
from reputation_core import Verdict
from reputation_platform import cow_swap_report as adapter
from reputation_platform.cow_swap_protocol import TRADE_TOPIC, inspect_cow_order, order_uid_key
from reputation_platform.swap_report import SwapEvidence

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / 'tests/fixtures/cow_swap_pilot_public_case.json'


class OverlayEvidence(SwapEvidence):
    def __init__(self, original, overlay):
        self.overlay = {name: json.dumps(value).encode() for name, value in overlay.items()}
        super().__init__(original.root, dict(original.hashes,
            **{name: hashlib.sha256(raw).hexdigest() for name, raw in self.overlay.items()}))

    def raw(self, name):
        return self.overlay[name] if name in self.overlay else super().raw(name)


class CowReportDraftAcceptance(unittest.TestCase):
    def test_real_pilot_uid_effects_missing_evidence_and_draft_guards(self):
        fixture = json.loads(FIXTURE.read_bytes())
        with tempfile.TemporaryDirectory(prefix='cow-offline-') as temporary:
            root = Path(temporary)
            hashes = {}
            for row in fixture['files']:
                raw = base64.b64decode(row['base64'], validate=True)
                self.assertEqual(hashlib.sha256(raw).hexdigest(), row['sha256'])
                self.assertNotIn('.private', row['path'])
                path = root / row['path']
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(raw)
                hashes[row['path']] = row['sha256']
            adr = root / adapter.ADR
            adr.parent.mkdir(parents=True, exist_ok=True)
            adr.write_bytes((ROOT / adapter.ADR).read_bytes())
            hashes[adapter.ADR] = hashlib.sha256(adr.read_bytes()).hexdigest()
            evidence = SwapEvidence(root, hashes)
            source = evidence.json(fixture['source'])
            plan = evidence.json(source['campaign_plan'])
            task, item = plan['tasks'][0], source['tasks'][0]
            clock = adapter._time(evidence.json(item['task_intent'])['frozen_at'])
            rows = adapter._http_task(evidence, plan, task, item, clock)
            metrics, facts = adapter._metrics(evidence, plan, task, item, rows, clock)
            for name in ('complete-response', 'quote-binding', 'order-binding', 'appdata-policy',
                         'fee-binding', 'validation-binding', 'onchain-fulfillment'):
                self.assertEqual(metrics[name][0], Verdict.PASS, name)
            self.assertEqual(facts['uid'], '0xbbf8b16dc9736e3d469e064dc5440dcfaf6659d2cf7ce46fd8afee64ffd6f9c6176501c795dbc31259bb86a49eb8a88ff2298b856ae240eb')
            fulfillment = metrics['onchain-fulfillment'][2]
            self.assertEqual(fulfillment['input_debit_raw'], '100000')
            self.assertEqual(fulfillment['output_credit_raw'], '41856540788113')
            self.assertEqual(fulfillment['confirmation_distance'], 91)
            self.assertEqual(fulfillment['remaining_allowance_raw'], '0')
            self.assertEqual(metrics['submit-binding'][0], Verdict.UNKNOWN)

            material = adapter._material(plan, rows[1])
            expected = dict(task['expected'], recipient=task['expected']['owner'], minimum_out='41629291989146',
                valid_to_min=facts['valid_to'], valid_to_max=facts['valid_to'])
            for label in ('owner', 'amount', 'domain', 'appData', 'deadline', 'fee'):
                changed, independent = copy.deepcopy(material), dict(expected)
                if label == 'owner': changed['owner'] = '0x' + '1' * 40
                if label == 'amount': changed['order']['sellAmount'] = '100001'
                if label == 'domain': changed['domain']['chainId'] = 1
                if label == 'appData': changed['full_app_data'] += ' '
                if label == 'deadline': changed['order']['validTo'] += 1
                if label == 'fee': changed['order']['feeAmount'] = '1'
                with self.subTest(negative=label), self.assertRaises(ValueError):
                    inspect_cow_order(changed, independent, plan['protocol_binding'], plan['app_data_policy'])

            # Controlled unsigned alternative proves policy is data, not an Ophis
            # name/recipient/zero-fee constant in the shared protocol module.
            alternative = copy.deepcopy(material)
            app = json.loads(alternative['full_app_data'])
            app['appCode'] = 'controlled-other-service'
            app['metadata']['partnerFee'] = []
            alternative['full_app_data'] = json.dumps(app, separators=(',', ':'))
            app_hash = '0x' + keccak(alternative['full_app_data'].encode()).hex()
            alternative['app_data_hash'] = alternative['order']['appData'] = app_hash
            alternative['order'].update(sellAmount='99999', feeAmount='1')
            other = inspect_cow_order(alternative, dict(expected, signed_fee_amount='1'),
                plan['protocol_binding'], {'required_values': {'/appCode': 'controlled-other-service'}})
            self.assertNotEqual(order_uid_key(8453, other['uid']), order_uid_key(8453, facts['uid']))
            # A transaction hash is deliberately absent from the deduplication key.
            self.assertEqual(len({order_uid_key(8453, facts['uid']), order_uid_key(8453, other['uid'])}), 2)
            self.assertEqual(len({order_uid_key(8453, facts['uid']), order_uid_key(8453, facts['uid'])}), 1)

            execution = item['execution']
            def without(method):
                value = copy.deepcopy(item)
                value['execution']['rpc_observations'] = [name for name in execution['rpc_observations']
                    if json.loads(evidence.json(name)['request_json'])['method'] != method]
                return adapter._execution(evidence, plan, task, value, facts, clock)[0]
            self.assertEqual(without('eth_getTransactionReceipt'), Verdict.UNKNOWN)
            self.assertEqual(without('eth_getBlockByNumber'), Verdict.UNKNOWN)

            receipt_name = next(name for name in execution['rpc_observations']
                if json.loads(evidence.json(name)['request_json'])['method'] == 'eth_getTransactionReceipt')
            observation = evidence.json(receipt_name)
            body_name = (Path(receipt_name).parent / observation['response_file']).as_posix()
            body = evidence.json(body_name)
            changed = copy.deepcopy(body)
            trade = next(log for log in changed['result']['logs'] if log['address'].lower() == facts['settlement']
                         and log['topics'][0].lower() == TRADE_TOPIC)
            trade['address'] = '0x' + '2' * 40
            changed_obs = dict(observation, response_sha256=hashlib.sha256(json.dumps(changed).encode()).hexdigest())
            bad = OverlayEvidence(evidence, {receipt_name: changed_obs, body_name: changed})
            with self.assertRaises(ValueError):
                adapter._execution(bad, plan, task, item, facts, clock)
            wrong_pre = copy.deepcopy(evidence.json(execution['prestate']['snapshot']))
            wrong_pre['prepared_order_sha256'] = '0' * 64
            with self.assertRaises(ValueError):
                adapter._execution(OverlayEvidence(evidence, {execution['prestate']['snapshot']: wrong_pre}),
                    plan, task, item, facts, clock)

            # DRAFT is rejected before a report directory or software snapshots exist.
            target = root / 'runtime/not-a-public-report'
            with self.assertRaises(ValueError):
                adapter.build_cow_swap_report(root, Path(fixture['source']), target)
            self.assertFalse(target.exists())
            with self.assertRaises(ValueError):
                adapter._public_path(root, 'runtime/secret/SIGNED_ORDER.private.json')

            # Controlled assessment freeze is only unit input. Real public HTTP,
            # identity and chain bytes remain unchanged; no report is published.
            frozen = copy.deepcopy(plan)
            frozen.update(status='FROZEN', frozen_at='2026-10-28T18:30:00+00:00')
            replay = adapter.replay_cow_swap_sources(root,
                OverlayEvidence(evidence, {source['campaign_plan']: frozen}), source,
                datetime(2026, 10, 29, tzinfo=timezone.utc))
            self.assertEqual(len(replay.shared_assessment.tasks), 30)
            self.assertEqual(sum(task.outcome == 'completed' for task in replay.shared_assessment.tasks), 1)
            self.assertIsNotNone(replay.scores.availability.value)
            self.assertIsNotNone(replay.scores.functional.value)  # missing declarations do not hard-gate A/F
            self.assertIsNone(replay.scores.behavioral.value)  # eight normal UID targets remain
            self.assertIsNone(replay.scores.overall)


if __name__ == '__main__':
    unittest.main()
