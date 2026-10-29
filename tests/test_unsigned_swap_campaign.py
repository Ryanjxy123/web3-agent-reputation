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
            reassessment_adr = (ROOT / campaign.REASSESSMENT_ADR).read_bytes()
            if root != ROOT:
                (root / campaign.REASSESSMENT_ADR).write_bytes(reassessment_adr)
            hashes[campaign.REASSESSMENT_ADR] = hashlib.sha256(reassessment_adr).hexdigest()
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
            # Controlled native-schema projection: authentic request bytes and
            # legacy no-mapping behavior remain untouched. Not a public sample.
            field_map = {'fromTokenAddress': 'sellToken', 'toTokenAddress': 'buyToken',
                         'amount': 'amountIn', 'taker': 'buyer', 'slippage': 'slippageBps',
                         'source': 'aggregator'}
            native = copy.deepcopy(facts)
            original_request = native['frozen']['requirement']
            native_request = {field_map.get(key, key): value for key, value in original_request.items()}
            native_request['aggregator'] = 'native-route'
            native['frozen'] = dict(native['frozen'], offering='safe_quote', requirement=native_request)
            native['request_mapping'] = {'fields': field_map,
                'source_values': {'native-route': original_request['source']},
                'default_slippage_bps': 100, 'slippage_maximum_bps': 2000,
                'route_offerings': ['safe_quote']}
            native_schema = {'properties': {name: {'type': 'string'} for name in field_map.values()},
                'required': ['sellToken', 'buyToken', 'amountIn', 'buyer']}
            native_schema['properties']['slippageBps'] = {'type': 'integer',
                'description': 'Max slippage in basis points (default 100 = 1%, hard cap 2000 = 20%).'}
            native_schema['properties']['aggregator'] = {'type': 'string', 'enum': ['native-route']}
            native['detail'] = dict(native['detail'], offerings=[{'name': 'safe_quote', 'requirements': native_schema}])
            before_projection = copy.deepcopy(native)
            native_metrics, native_quote = campaign._metrics(evidence, source, no_execution, planned, native)
            self.assertEqual(native_quote['expected'], quote['expected'])
            self.assertEqual(native_metrics['intent-binding'][0], Verdict.PASS)
            self.assertEqual(native['frozen'], before_projection['frozen'])
            self.assertEqual(native['detail'], before_projection['detail'])
            self.assertEqual(campaign._request_view(facts)[0], facts['frozen']['requirement'])
            for field, message, criterion in [('buyer', 'buyer is required', 'safe-validation'),
                                               ('aggregator', 'unsupported aggregator', 'safe-source-validation'),
                                               ('slippageBps', 'slippageBps out of range', 'safe-validation')]:
                changed = copy.deepcopy(native)
                if field == 'buyer':
                    changed['frozen']['requirement'].pop(field)
                else:
                    changed['frozen']['requirement'][field] = 2001 if field == 'slippageBps' else 'unsupported'
                changed['delivery'] = {'error': message}
                checked, _ = campaign._metrics(evidence, source, no_execution, planned, changed)
                self.assertEqual(checked[criterion][0], Verdict.PASS)
            omitted = copy.deepcopy(native)
            omitted['frozen']['requirement'].pop('slippageBps')
            checked, _ = campaign._metrics(evidence, source, no_execution, planned, omitted)
            self.assertEqual(checked['default-slippage'][0], Verdict.PASS)
            wrong_default = copy.deepcopy(native)
            wrong_default['request_mapping']['default_slippage_bps'] = 101
            with self.assertRaisesRegex(ValueError, 'default slippage mapping differs'):
                campaign._metrics(evidence, source, no_execution, planned, wrong_default)
            auxiliary = copy.deepcopy(native)
            auxiliary['frozen'] = dict(auxiliary['frozen'], offering='batch_screen', requirement={'tokens': ['0x1']})
            auxiliary['delivery'] = {'screened': 1, 'results': []}
            checked, result = campaign._metrics(evidence, source, no_execution, planned, auxiliary)
            self.assertIsNone(result)
            self.assertTrue(all(verdict == Verdict.UNKNOWN for verdict, _ in checked.values()))
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

            # Controlled verification-boundary fixture: a different authenticated
            # registry owner may bind the same exact service. It is not a claim
            # that the original on-chain owner has changed.
            verified_identity = campaign.verify_registration_proof(root, source['registration_proof'],
                                                                    source['registration_reference'])
            role_proof = copy.deepcopy(evidence.json(source['registration_proof']))
            role_proof['rpc']['owner']['value'] = '0x' + format(1, '064x')
            self.assertNotEqual('0x' + role_proof['rpc']['owner']['value'][-40:], facts['provider'])
            role_evidence = OverlayEvidence(root, hashes, {plan_path: plan, source['registration_proof']: role_proof})
            with patch.object(campaign, 'verify_registration_proof', return_value=verified_identity) as verifier:
                role_report = campaign.campaign_report(root, role_evidence, expanded,
                                                       datetime(2026, 10, 28, tzinfo=timezone.utc))
                self.assertEqual(role_report.shared_assessment.result.task_count, 3)
                verifier.assert_called_once_with(root, source['registration_proof'], source['registration_reference'])
            wrong_service = copy.deepcopy(verified_identity)
            wrong_service['document']['services'] = [{'endpoint': 'https://app.virtuals.io/acp/agent/another-service'}]
            wrong_service['document']['walletAddress'] = facts['provider']
            with patch.object(campaign, 'verify_registration_proof', return_value=wrong_service):
                with self.assertRaisesRegex(ValueError, 'Registration does not bind this campaign service'):
                    campaign.campaign_report(root, role_evidence, expanded,
                                             datetime(2026, 10, 28, tzinfo=timezone.utc))

            # Controlled append-only lineage: original tasks keep their first
            # authenticated freeze and declaration defaults across later additions.
            lineage_root = copy.deepcopy(plan)
            lineage_paths = [plan_path, 'runtime/campaign-unit/plan-v2.json', 'runtime/campaign-unit/plan-v3.json']
            snapshots = ['runtime/campaign-unit/detail-v1.json', 'runtime/campaign-unit/detail-v2.json',
                         'runtime/campaign-unit/detail-v3.json']
            overlay = {}
            revisions = []
            appended_keys = [new_key, str(uuid4()), str(uuid4())]
            for index, frozen in enumerate(('2026-10-28T09:34:29+00:00',
                                            '2026-10-28T10:16:50+00:00',
                                            '2026-10-28T15:40:10+00:00')):
                revision = copy.deepcopy(lineage_root if not index else revisions[-1])
                revision['frozen_at'] = frozen
                revision['request_mapping'] = {'fields': {'amount': 'amount'},
                                               'default_slippage_bps': 50 + index * 25}
                detail = {'data': {'id': fresh['acp']['provider_id'],
                                  'walletAddress': fresh['acp']['provider_wallet'],
                                  'observed_default_slippage': 50 + index * 25}}
                overlay[snapshots[index]] = detail
                revision['source_snapshot'] = {'path': snapshots[index],
                    'sha256': hashlib.sha256(json.dumps(detail).encode()).hexdigest()}
                if index:
                    revision['previous_plan'] = {'path': lineage_paths[index - 1],
                        'sha256': hashlib.sha256(json.dumps(revisions[-1]).encode()).hexdigest()}
                    task = dict(copy.deepcopy(lineage_root['new_tasks'][0]),
                                task_id='H0' + str(index + 3), task_key=appended_keys[index])
                    revision['new_tasks'].append(task)
                    for case in revision['cases']:
                        case['planned_task_ids'].append(task['task_id'])
                revisions.append(revision)
                overlay[lineage_paths[index]] = revision
            lineage_evidence = OverlayEvidence(root, hashes, overlay)
            self.assertEqual([row['frozen_at'] for row in campaign._campaign_lineage(lineage_evidence, lineage_paths[-1])],
                             [campaign._time(row['frozen_at']) for row in revisions])
            inherited = dict(expanded, campaign_plan=lineage_paths[-1], tasks=[*expanded['tasks'],
                dict(no_execution, task_key=appended_keys[0], simulation=None),
                dict(no_execution, task_key=appended_keys[1], simulation=None)])
            submitted_at = {appended_keys[0]: campaign._time('2026-10-28T09:50:00+00:00'),
                            appended_keys[1]: campaign._time('2026-10-28T10:22:00+00:00'),
                            appended_keys[2]: campaign._time('2026-10-28T10:22:00+00:00')}
            observed_defaults = {}
            observed_mappings = {}

            def unit_delivery(_evidence, item, _planned, _retained):
                value = copy.deepcopy(facts)
                value['requirement_submitted_at'] = submitted_at.get(item['task_key'], value['requirement_submitted_at'])
                return value

            def unit_metrics(_evidence, _source, item, _planned, delivered):
                if item and item['task_key'] in submitted_at:
                    observed_defaults[item['task_key']] = delivered['contract_detail']['observed_default_slippage']
                    observed_mappings[item['task_key']] = delivered['request_mapping']['default_slippage_bps']
                return {name: campaign.UNKNOWN for name in campaign.METRICS}, None

            with patch.object(campaign, '_delivery', side_effect=unit_delivery), patch.object(campaign, '_metrics', side_effect=unit_metrics):
                inherited_report = campaign.campaign_report(root, lineage_evidence, inherited,
                                                            datetime(2026, 10, 28, tzinfo=timezone.utc))
                self.assertEqual(inherited_report.shared_assessment.result.task_count, 5)
                self.assertEqual(observed_defaults, {appended_keys[0]: 50, appended_keys[1]: 75})
                self.assertEqual(observed_mappings, {appended_keys[0]: 50, appended_keys[1]: 75})
                too_early = dict(inherited, tasks=[*inherited['tasks'],
                    dict(no_execution, task_key=appended_keys[2], simulation=None)])
                with self.assertRaisesRegex(ValueError, 'predates campaign freeze'):
                    campaign.campaign_report(root, lineage_evidence, too_early,
                                             datetime(2026, 10, 28, tzinfo=timezone.utc))
                duplicate_execution = copy.deepcopy(inherited)
                for task in duplicate_execution['tasks']:
                    if task['task_key'] in appended_keys[:2]:
                        task['execution'] = fresh['execution']
                with self.assertRaisesRegex(ValueError, 'execution transaction is reused across tasks'):
                    campaign.campaign_report(root, lineage_evidence, duplicate_execution,
                                             datetime(2026, 10, 28, tzinfo=timezone.utc))
            for mutation, message in [('time', 'predates its previous freeze'),
                                      ('digest', 'previous plan digest mismatch'),
                                      ('input', 'changed or removed an original task'),
                                      ('criterion', 'changed original case rules'),
                                      ('membership', 'changed original task case assignments')]:
                changed_revision = copy.deepcopy(revisions[-1])
                if mutation == 'time':
                    changed_revision['frozen_at'] = '2026-10-28T09:00:00+00:00'
                elif mutation == 'digest':
                    changed_revision['previous_plan']['sha256'] = '00' * 32
                elif mutation == 'input':
                    changed_revision['new_tasks'][0]['request']['amount'] = '1'
                elif mutation == 'criterion':
                    changed_revision['cases'][0]['required_decisive'] += 1
                else:
                    changed_revision['cases'][0]['planned_task_ids'].remove('H03')
                changed_overlay = dict(overlay, **{lineage_paths[-1]: changed_revision})
                with self.subTest(lineage_conflict=mutation), self.assertRaisesRegex(ValueError, message):
                    campaign._campaign_lineage(OverlayEvidence(root, hashes, changed_overlay), lineage_paths[-1])

            # A separate assessment can regroup cases retrospectively without
            # rewriting an append-only ancestor or inventing a new task freeze.
            independent = copy.deepcopy(revisions[-1])
            independent.pop('previous_plan')
            independent['frozen_at'] = '2026-10-29T00:00:00+00:00'
            independent['retained_tasks'].extend(dict(copy.deepcopy(task),
                origin_campaign={'path': lineage_paths[-1],
                    'sha256': hashlib.sha256(json.dumps(revisions[-1]).encode()).hexdigest()},
                retention_purpose='retrospective-case-remap') for task in independent['new_tasks'])
            independent['new_tasks'] = []
            independent_path = 'runtime/campaign-unit/independent.json'
            independent_overlay = dict(overlay, **{independent_path: independent})
            independent_source = dict(inherited, campaign_plan=independent_path)
            with patch.object(campaign, '_delivery', side_effect=unit_delivery), patch.object(campaign, '_metrics', side_effect=unit_metrics):
                mapped_report = campaign.campaign_report(root, OverlayEvidence(root, hashes, independent_overlay),
                    independent_source, datetime(2026, 10, 29, tzinfo=timezone.utc))
                self.assertEqual(mapped_report.shared_assessment.result.task_count, 5)
                self.assertIn('回顾映射', mapped_report.evaluation_window)
                changed = copy.deepcopy(independent)
                changed['retained_tasks'][2]['request']['amount'] = '1'
                with self.assertRaisesRegex(ValueError, 'differs from original frozen request'):
                    campaign.campaign_report(root, OverlayEvidence(root, hashes,
                        dict(overlay, **{independent_path: changed})), independent_source,
                        datetime(2026, 10, 29, tzinfo=timezone.utc))

            # Pure scoring control, never public transaction evidence: four real
            # decisive samples per direction are required; UNKNOWN cannot fill it.
            control = report.shared_assessment.model_dump(mode='json')
            control.pop('result')
            capability = control['capabilities'][0]['capability_id']
            control['tasks'], control['cases'], control['observations'] = [], [], []
            for direction in ('forward', 'reverse'):
                keys = [str(uuid4()) for _ in range(4)]
                control['cases'].append({'case_id': direction, 'capability_id': capability,
                    'dimension': 'behavioral', 'declaration_group_id': None, 'title': direction,
                    'criterion_ids': ['onchain-fulfillment'], 'task_keys': keys,
                    'normal_execution': True, 'required_decisive': 4})
                for key in keys:
                    control['tasks'].append(dict(report.shared_assessment.tasks[0].model_dump(mode='json'),
                                                 task_key=key, outcome='completed'))
                    control['observations'].append({'task_key': key, 'case_id': direction,
                        'criterion_id': 'onchain-fulfillment', 'dimension': 'behavioral',
                        'verdict': 'PASS', 'reason': 'Controlled unit fixture only', 'evidence': [],
                        'measurement_validity': 'valid', 'elapsed_ms': None})
            complete = campaign.SharedAssessment.model_validate_json(json.dumps(control))
            self.assertIsNotNone(complete.result.behavioral.interval)
            control['observations'][-1]['verdict'] = 'UNKNOWN'
            insufficient = campaign.SharedAssessment.model_validate_json(json.dumps(control))
            self.assertIsNone(insufficient.result.behavioral.interval)

            changed_plan = copy.deepcopy(plan)
            changed_plan['new_tasks'].append(copy.deepcopy(changed_plan['new_tasks'][0]))
            with self.assertRaisesRegex(ValueError, 'Duplicate campaign task labels'):
                campaign.campaign_report(root, OverlayEvidence(root, hashes, {plan_path: changed_plan}),
                                         expanded, datetime(2026, 10, 28, tzinfo=timezone.utc))


if __name__ == '__main__':
    unittest.main()
