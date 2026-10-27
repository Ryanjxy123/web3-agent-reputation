"""One offline acceptance using the real, selectively exported swap batch.

Run only after a batch exists: SWAP_REPORT_DIR identifies that public directory.
No synthetic network, wallet signatures, or production evidence mutations.
"""
from copy import deepcopy
import json
import os
from pathlib import Path
import unittest

from reputation_core import Verdict
from reputation_core.chain_view import describe_chain_action
from reputation_core.prediction_chain import calldata
from reputation_core.scoring import SWAP_EVIDENCE_POLICY_VERSION, SWAP_POLICY_VERSION, calculate_scores
from reputation_core.swap import SWAP_METHOD, verify_swap_execution, verify_swap_function
from reputation_platform.db import _validated_report
from reputation_platform.evaluation_report import render_evaluation_report
from reputation_platform.swap_report import (ORIGIN, PROTOCOLS, SwapEvidence, _execution, _simulation,
    _task_request, verify_swap_report_sources)

ROOT = Path(__file__).resolve().parents[1]


class SwapReportAcceptance(unittest.TestCase):
    def test_real_replay_and_essential_boundaries(self):
        supplied = os.environ.get('SWAP_REPORT_DIR')
        if supplied is None:
            self.skipTest('NOT_RUN: set SWAP_REPORT_DIR to an actual retained public batch; no synthetic substitute')
        directory = (ROOT / supplied).resolve()
        manifest = json.loads((directory / 'manifest.json').read_bytes())
        hashes = {item['path']: item['sha256'] for item in manifest['inputs']}
        report = _validated_report(json.loads((directory / 'report.json').read_bytes()))
        self.assertEqual(verify_swap_report_sources(ROOT, report, hashes), report.registration_reference)
        expected_status = os.environ.get('SWAP_EXPECTED_STATUS', 'COMPLETE')
        self.assertIn(expected_status, ('COMPLETE', 'PARTIAL'))
        self.assertEqual(report.scores.status, expected_status)
        if expected_status == 'COMPLETE':
            self.assertIsNotNone(report.scores.overall)
        else:
            # Explicit acceptance of this real stopped reassessment, never a
            # substitution for the still-unmet complete-score product target.
            self.assertIsNone(report.scores.overall)
            self.assertEqual(report.scores.availability.value, 95.67)
            self.assertEqual((report.scores.availability.passed, report.scores.availability.unknown), (9, 1))
            self.assertEqual((report.scores.functional.passed, report.scores.functional.unknown), (2, 5))
            self.assertIsNone(report.scores.functional.value)
            self.assertEqual(report.scores.behavioral.value, 100.0)
            self.assertEqual(report.scores.behavioral.passed, 7)
        expanded = report.policy_version == SWAP_EVIDENCE_POLICY_VERSION
        count = 31 if expanded else 24
        self.assertEqual(len(report.samples), count)
        self.assertEqual(len({item.sample.task_key for item in report.samples}), count)
        if expanded:
            scored = [item.sample for item in report.samples]
            self.assertEqual(report.scores.functional.planned, 14)
            self.assertEqual(report.scores.functional.passed + report.scores.functional.failed, 12)
            self.assertEqual(report.scores.functional.unknown, 2)
            # One less decisive task is 11/14, below the exact 80% gate.
            decisive = [index for index, sample in enumerate(scored)
                        if sample.purpose == 'functional' and sample.verdict in (Verdict.PASS, Verdict.FAIL)]
            eleven = deepcopy(scored)
            eleven[decisive[-1]] = eleven[decisive[-1]].model_copy(update={'verdict': Verdict.UNKNOWN})
            below = calculate_scores(eleven, policy_version=SWAP_EVIDENCE_POLICY_VERSION)
            self.assertIsNone(below.functional.value)
            self.assertIsNone(below.overall)
            self.assertEqual(below.status, 'PARTIAL')
            # FAIL is decisive evidence, stays in the denominator and lowers score.
            failed = deepcopy(scored)
            for index in decisive:
                failed[index] = failed[index].model_copy(update={'verdict': Verdict.PASS})
            failed[decisive[-1]] = failed[decisive[-1]].model_copy(update={'verdict': Verdict.FAIL})
            with_failure = calculate_scores(failed, policy_version=SWAP_EVIDENCE_POLICY_VERSION)
            self.assertEqual(with_failure.functional.value, 91.67)
            self.assertEqual(with_failure.status, 'COMPLETE')
            # No fixed functional maximum; a larger bound group remains scored
            # only when its full decisive coverage reaches the same threshold.
            extra = scored[decisive[0]].model_copy(update={
                'sample_id': 'offline-boundary-extra', 'task_key': 'offline-boundary-extra', 'verdict': Verdict.PASS})
            self.assertEqual(calculate_scores([*scored, extra], policy_version=SWAP_EVIDENCE_POLICY_VERSION).functional.planned, 15)
            with self.assertRaisesRegex(ValueError, 'sample count exceeds'):
                calculate_scores(scored, policy_version=SWAP_POLICY_VERSION)
            old_directory = ROOT / os.environ.get('SWAP_V1_REPORT_DIR', 'runtime/spraay-public-reassessment-20261027')
            old_raw = json.loads((old_directory / 'report.json').read_bytes())
            old_report = _validated_report(old_raw)
            old_manifest = json.loads((old_directory / 'manifest.json').read_bytes())
            self.assertEqual(verify_swap_report_sources(ROOT, old_report,
                {item['path']: item['sha256'] for item in old_manifest['inputs']}), old_report.registration_reference)
            self.assertEqual(old_report.policy_version, SWAP_POLICY_VERSION)
            self.assertEqual(old_report.scores.status, 'PARTIAL')
            self.assertEqual(old_report.scores.availability.value, 95.67)
            self.assertEqual((old_report.scores.functional.passed, old_report.scores.functional.unknown), (2, 5))
            self.assertIsNone(old_report.scores.functional.value)
            self.assertIsNone(old_report.scores.overall)
        reader = SwapEvidence(ROOT, hashes)
        origin = reader.json((directory / ORIGIN).relative_to(ROOT).as_posix())
        campaign = reader.json(origin['campaign'])
        protocol = reader.json(PROTOCOLS)['chains'][str(campaign['execution_chain_id'])]
        entry = next(item for item in origin['tasks'] if item['slot'].startswith('B') and item.get('send_intent'))
        data = reader.json(entry['input_file'])
        request = _task_request({'input': data}, protocol)
        builder = reader.json(entry['response_file'])
        records = reader.rpc_records(entry['rpc_observations'], set(protocol['rpc_urls']))
        simulation = _simulation(records, request, builder)
        self.assertEqual(verify_swap_function(request, builder, simulation).verdict, Verdict.PASS)
        execution = _execution(records, request, builder, reader.json(entry['send_intent']))
        self.assertEqual(verify_swap_execution(request, builder, execution).verdict, Verdict.PASS)
        action = describe_chain_action(execution['transaction'], execution['receipt'], execution['block'],
            sample_id='actual-batch-acceptance', verdict=Verdict.PASS, evidence=[])
        self.assertEqual(action.action, 'swap_batch')
        self.assertEqual(action.transaction_hash, execution['expected_transaction_hash'])
        html = render_evaluation_report(report)
        self.assertTrue('最低到账及精确授权' in html, 'Swap HTML must explain minimum output and exact allowance')
        if expanded:
            self.assertTrue('全部14项任务' in html and '80%' in html,
                            'V2 HTML must disclose its full functional plan and coverage threshold')
        self.assertFalse('MCP tools/list' in html, 'Swap HTML must not describe MCP discovery scoring')
        self.assertFalse('包装原生币、兑换、最终增仓' in html, 'Swap HTML must not describe liquidity scoring')

        changed = deepcopy(builder)
        q = builder['quote']
        changed['transactions']['swap']['data'] = calldata(SWAP_METHOD, request.token_in, request.token_out,
            q['feeTier'], '0x1111111111111111111111111111111111111111', request.amount_in,
            int(q['tokenOut']['minimumAmountRaw']), 0)
        self.assertEqual(verify_swap_function(request, changed, simulation).verdict, Verdict.FAIL)
        self.assertEqual(verify_swap_execution(request, builder, None).verdict, Verdict.UNKNOWN)
        corrupted = dict(hashes)
        corrupted[entry['response_file']] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'source changed'):
            verify_swap_report_sources(ROOT, report, corrupted)
