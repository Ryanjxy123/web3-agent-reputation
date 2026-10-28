"""One offline acceptance: retained bytes, prospective slots, and critical failures."""
import copy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4

from reputation_core import Verdict
from reputation_core.reporting import parse_evaluation_report
from reputation_platform import unsigned_swap_campaign as campaign
from reputation_platform import unsigned_swap_report as old
from reputation_platform.swap_report import SwapEvidence

ROOT = Path(__file__).resolve().parents[1]


class OverlayEvidence(SwapEvidence):
    def __init__(self, root, hashes, overlay):
        self.overlay = {name: json.dumps(value).encode() for name, value in overlay.items()}
        super().__init__(root, dict(hashes, **{name: hashlib.sha256(raw).hexdigest()
                                             for name, raw in self.overlay.items()}))

    def raw(self, name):
        return self.overlay[name] if name in self.overlay else super().raw(name)


class UnsignedCampaignAcceptance(unittest.TestCase):
    def test_retained_replay_prospective_slots_and_failure_classification(self):
        with tempfile.TemporaryDirectory(prefix='unsigned-campaign-') as temporary:
            root = ROOT
            report_dir = 'runtime/hydrex-routing-shared-20261028-v6'
            if not (root / report_dir / 'report.json').exists():
                root = Path(temporary)
                with tarfile.open(ROOT / 'data/public-reports-transaction-v3.tar.gz') as archive:
                    for member in archive.getmembers():
                        target = (root / member.name).resolve()
                        self.assertTrue(member.isfile() and target.is_relative_to(root))
                        target.parent.mkdir(parents=True, exist_ok=True)
                        target.write_bytes(archive.extractfile(member).read())
            raw_report = (root / report_dir / 'report.json').read_bytes()
            report = parse_evaluation_report(raw_report)
            manifest = json.loads((root / report_dir / 'manifest.json').read_bytes())
            hashes = {row['path']: row['sha256'] for row in manifest['inputs']}
            self.assertEqual(old.verify_unsigned_swap_report_sources(root, report, hashes), report.registration_reference)
            self.assertEqual((root / report_dir / 'report.json').read_bytes(), raw_report)
            source_path = 'runtime/unsigned-swap-public-20261028/hydrex-source-v2.json'
            source = json.loads((root / source_path).read_bytes())
            # The new adapter pins its ADR; the old manifest remains unchanged.
            campaign_adr = (ROOT / campaign.ADR).read_bytes()
            if root != ROOT:
                (root / campaign.ADR).parent.mkdir(parents=True, exist_ok=True)
                (root / campaign.ADR).write_bytes(campaign_adr)
            hashes[campaign.ADR] = hashlib.sha256(campaign_adr).hexdigest()
            evidence = SwapEvidence(root, hashes)
            fresh = source['tasks'][1]
            planned = {'retained': True}
            facts = campaign._delivery(evidence, fresh, planned, True)
            metrics, quote = campaign._metrics(evidence, source, fresh, planned, facts)
            self.assertEqual(metrics['onchain-fulfillment'][0], Verdict.PASS)
            self.assertEqual(metrics['route-filter'][0], Verdict.UNKNOWN)

            # Controlled unit mutations are not new public samples or transactions.
            records = old._records(evidence, fresh['acp']['rpc_observations'])
            submission, submission_block = campaign._optional_event(records,
                facts['plan']['contract'], old.SUBMITTED, fresh['acp']['job_id'], fresh['acp']['provider_wallet'])
            for missing in ('event', 'header'):
                incomplete_records = ([] if missing == 'event' else [row for row in records
                    if not (row['method'] == 'eth_getBlockByNumber'
                            and row['params'] == [submission['blockNumber'], False])])
                with self.subTest(missing_campaign_source=missing), patch.object(old, '_records', return_value=incomplete_records):
                    incomplete_delivery = campaign._delivery(evidence, fresh, planned, True)
                    self.assertFalse(incomplete_delivery['authenticated'])
                    self.assertIsNone(incomplete_delivery['elapsed_ms'])
                    checked, _ = campaign._metrics(evidence, source, fresh, planned, incomplete_delivery)
                    self.assertTrue(all(verdict == Verdict.UNKNOWN for verdict, _ in checked.values()))
                    if missing == 'header':
                        seen, header = campaign._optional_event(incomplete_records, facts['plan']['contract'],
                            old.SUBMITTED, fresh['acp']['job_id'], fresh['acp']['provider_wallet'])
                        self.assertIsNotNone(seen)
                        self.assertIsNone(header)
                        self.assertIsNone(campaign._timeout(evidence, fresh, facts['plan'], incomplete_records,
                            {'number': '0x1', 'timestamp': '0x1'}, fresh['acp']['history_observation']))
            for conflict, message in [('digest', 'onchain deliverable mismatch'),
                                      ('actor', 'event actor mismatch'),
                                      ('header', 'canonical block'),
                                      ('receipt', 'receipt contradicts')]:
                changed_records = copy.deepcopy(records)
                for row in changed_records:
                    if conflict == 'header' and row['method'] == 'eth_getBlockByNumber' and row['params'] == [submission['blockNumber'], False]:
                        row['value']['hash'] = '0x' + '00' * 32
                    if conflict == 'receipt' and row['method'] == 'eth_getTransactionReceipt' and row['value']['transactionHash'].lower() == submission['transactionHash'].lower():
                        row['value']['blockHash'] = '0x' + '00' * 32
                    logs = (row['value'].get('logs', []) if row['method'] == 'eth_getTransactionReceipt'
                            else row['value'] if row['method'] == 'eth_getLogs' else [])
                    for log in logs:
                        if log['topics'][0].lower() == old.SUBMITTED and old._uint(log['topics'][1]) == int(fresh['acp']['job_id']):
                            if conflict == 'digest':
                                log['data'] = '0x' + '00' * 32
                            elif conflict == 'actor':
                                log['topics'][2] = '0x' + '00' * 32
                with self.subTest(conflicting_campaign_source=conflict), patch.object(old, '_records', return_value=changed_records):
                    with self.assertRaisesRegex(ValueError, message):
                        campaign._delivery(evidence, fresh, planned, True)

            no_execution = dict(fresh, execution=None)
            for field, criterion in [('slippage', 'default-slippage'), ('taker', 'undocumented-taker-default')]:
                changed = copy.deepcopy(facts)
                changed['frozen']['requirement'].pop(field)
                checked, _ = campaign._metrics(evidence, source, no_execution, planned, changed)
                self.assertEqual(checked[criterion][0], Verdict.PASS if field == 'slippage' else Verdict.UNKNOWN)
                self.assertEqual(checked['onchain-fulfillment'][0], Verdict.UNKNOWN)
            for body, expected in [({'status': 'rejected', 'error': 'invalid amount must be positive'}, Verdict.PASS),
                                   ({'error': 'upstream HTTP 500'}, Verdict.UNKNOWN)]:
                changed = copy.deepcopy(facts)
                changed['frozen']['requirement']['amount'] = '0'
                changed['delivery'] = body
                checked, _ = campaign._metrics(evidence, source, no_execution, planned, changed)
                self.assertEqual(checked['safe-validation'][0], expected)
                self.assertEqual(checked['execution-effect'][0], Verdict.UNKNOWN)
                self.assertEqual(checked['complete-response'][0], Verdict.UNKNOWN)
            for body, expected in [({'error': 'upstream HTTP 500'}, Verdict.FAIL),
                                   ({'status': 'no_route', 'reason': 'insufficient liquidity'}, Verdict.UNKNOWN)]:
                changed = copy.deepcopy(facts)
                changed['delivery'] = body
                checked, _ = campaign._metrics(evidence, source, no_execution, planned, changed)
                self.assertEqual(checked['complete-response'][0], expected)
                self.assertEqual(checked['execution-effect'][0], Verdict.UNKNOWN)
            for body in ({}, {'quote': {'calldata': '0x'}}):
                changed = copy.deepcopy(facts)
                changed['delivery'] = body
                checked, _ = campaign._metrics(evidence, source, no_execution, planned, changed)
                self.assertEqual(checked['complete-response'][0], Verdict.FAIL)
                self.assertEqual(checked['deliverable-schema'][0], Verdict.FAIL)
            incomplete = copy.deepcopy(facts)
            incomplete['authenticated'] = False
            incomplete['timeout_proven'] = False
            incomplete['elapsed_ms'] = 900000
            checked, _ = campaign._metrics(evidence, source, no_execution, planned, incomplete)
            self.assertEqual(checked['complete-response'][0], Verdict.UNKNOWN)

            # Controlled clock/range unit fixture: not a claimed chain observation.
            observed = int(campaign._time(evidence.json(fresh['acp']['history_observation'])['observed_at']).timestamp())
            funded = {'number': '0x1', 'timestamp': hex(observed - 700)}
            topics = [old.SUBMITTED, '0x' + format(int(fresh['acp']['job_id']), '064x'),
                      old._topic(fresh['acp']['provider_wallet'])]
            request_plan = facts['plan']
            records = [{'method': 'eth_chainId', 'params': [], 'value': hex(request_plan['chain_id']), 'error': None}]
            for block, timestamp in [('0x2', observed - 500), ('0x3', observed - 1)]:
                records.extend([
                    {'method': 'eth_getLogs', 'params': [{'address': request_plan['contract'], 'topics': topics,
                         'fromBlock': '0x1', 'toBlock': block}], 'value': [], 'error': None},
                    {'method': 'eth_getBlockByNumber', 'params': [block, False],
                     'value': {'number': block, 'timestamp': hex(timestamp)}, 'error': None}])
            elapsed = campaign._timeout(evidence, fresh, request_plan, records, funded,
                                         fresh['acp']['history_observation'])
            self.assertEqual(elapsed, 699000)
            self.assertIsNone(campaign._timeout(evidence, fresh, request_plan, records[1:], funded,
                                                fresh['acp']['history_observation']))
            incomplete.update(timeout_proven=True, elapsed_ms=elapsed)
            checked, _ = campaign._metrics(evidence, source, no_execution, planned, incomplete)
            self.assertEqual(checked['complete-response'][0], Verdict.FAIL)

            # Direction-neutral field mapping is authenticated by the same retained
            # simulation and transaction, without editing either original artifact.
            intent = evidence.json(fresh['execution']['intent_path'])
            mapped = copy.deepcopy(intent)
            mapped['pre_input_raw'] = mapped.pop('pre_usdc_raw')
            mapped['pre_output_raw'] = mapped.pop('pre_weth_raw')
            mapped_path = 'runtime/campaign-unit/intent.json'
            mapped_evidence = OverlayEvidence(root, hashes, {mapped_path: mapped})
            mapped_item = copy.deepcopy(fresh)
            mapped_item['execution']['intent_path'] = mapped_path
            checked = old._execution(mapped_evidence, mapped_item, quote['expected'], quote['decoded'],
                                     quote['transaction'], quote['simulation'][2],
                                     balance_fields=('pre_input_raw', 'pre_output_raw'))
            self.assertEqual(checked[0], Verdict.PASS)
            with self.assertRaisesRegex(ValueError, 'pre-balances'):
                old._execution(mapped_evidence, mapped_item, quote['expected'], quote['decoded'],
                               quote['transaction'], quote['simulation'][2],
                               balance_fields=('pre_output_raw', 'pre_input_raw'))

            old_labels = ['H01', 'H02']
            new_key = str(uuid4())
            new_request = evidence.json(fresh['plan'])['tasks'][0]['requirement']
            groups = [{'group_id': group.group_id, 'source': group.source_references[0], 'scope': group.title}
                      for group in report.shared_assessment.capabilities[0].declaration_groups]
            plan = {'status': 'FROZEN', 'frozen_at': '2026-10-28T09:34:29+00:00',
                'registration_reference': source['registration_reference'],
                'candidate_key': source['candidate_key'],
                'new_tasks': [{'task_id': 'H03', 'task_key': new_key, 'request': new_request,
                               'planned_actual_execution': True}],
                'retained_tasks': [{'task_id': label, 'task_key': task['task_key'], 'source': source_path}
                                   for label, task in zip(old_labels, source['tasks'])],
                'capability': {'capability_id': 'erc20-swap-routing', 'declaration_groups': groups},
                'cases': [], 'comparison_groups': []}
            for case in report.shared_assessment.cases:
                labels = [old_labels[[task['task_key'] for task in source['tasks']].index(key)] for key in case.task_keys]
                labels.append('H03')
                plan['cases'].append({'case_id': case.case_id, 'dimension': case.dimension,
                    'declaration_group_id': case.declaration_group_id, 'criterion_ids': case.criterion_ids,
                    'normal_execution': case.normal_execution, 'required_decisive': 2 if case.normal_execution else 1,
                    'planned_task_ids': labels})
            plan_path = 'runtime/campaign-unit/plan.json'
            campaign_evidence = OverlayEvidence(root, hashes, {plan_path: plan})
            expanded = dict(source, schema_version='unsigned-swap-evidence-v2', adapter=campaign.ADAPTER,
                campaign_plan=plan_path, tasks=[{'task_key': task['task_key'], 'retained_source': source_path}
                                                for task in source['tasks']])
            replay = old._report(root, campaign_evidence, expanded, datetime(2026, 10, 28, tzinfo=timezone.utc))
            self.assertEqual(replay.shared_assessment.result.task_count, 3)
            self.assertIsNone(replay.scores.overall)
            self.assertIsNone(replay.shared_assessment.result.behavioral.interval)
            missing = next(row for row in replay.shared_assessment.tasks if row.task_key == new_key)
            self.assertEqual(missing.outcome, 'unknown')
            self.assertFalse(any(row.task_key == new_key for row in replay.shared_assessment.observations))
            self.assertEqual((root / report_dir / 'report.json').read_bytes(), raw_report)

            changed_plan = copy.deepcopy(plan)
            changed_plan['new_tasks'].append(copy.deepcopy(changed_plan['new_tasks'][0]))
            with self.assertRaisesRegex(ValueError, 'Duplicate campaign task labels'):
                campaign.campaign_report(root, OverlayEvidence(root, hashes, {plan_path: changed_plan}),
                                         expanded, datetime(2026, 10, 28, tzinfo=timezone.utc))


if __name__ == '__main__':
    unittest.main()
