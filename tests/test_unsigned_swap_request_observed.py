"""One offline real-source acceptance for request counts and reused execution chain reads."""
import base64
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

from reputation_core import Verdict
from reputation_platform import unsigned_swap_campaign as campaign
from reputation_platform.swap_report import SwapEvidence

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / 'tests/fixtures/unsigned_swap_request_observed_case.json'


class RequestObservationAcceptance(unittest.TestCase):
    def test_actual_timeout_unfunded_plan_only_and_execution_chain_binding(self):
        fixture = json.loads(FIXTURE.read_bytes())
        with tempfile.TemporaryDirectory(prefix='hydrex-request-observed-') as directory:
            root = Path(directory)
            hashes = {}
            for row in fixture['files']:
                self.assertNotIn('.private', row['path'])
                raw = base64.b64decode(row['base64'], validate=True)
                self.assertEqual(hashlib.sha256(raw).hexdigest(), row['sha256'])
                path = root / row['path']
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(raw)
                hashes[row['path']] = row['sha256']
            evidence = SwapEvidence(root, hashes)
            selected = {x['task']['task_id']: x for x in fixture['cases']}
            source = {'response_deadline_ms': fixture['response_deadline_ms']}
            for label in ('H38', 'H44'):
                case = selected[label]
                facts = campaign._delivery(evidence, case['item'], case['task'], False)
                self.assertFalse(facts['authenticated'])
                self.assertIsNone(facts['observed_at'], 'Provider delivery clock must remain unassigned')
                request_time = facts['requirement_submitted_at']
                self.assertEqual(campaign._task_observed_at(facts), request_time)
                metrics, quote = campaign._metrics(evidence, source, case['item'], case['task'], facts)
                self.assertIsNone(quote)
                self.assertEqual(metrics['complete-response'][0], Verdict.FAIL if label == 'H38' else Verdict.UNKNOWN)
                self.assertIsNone(facts['observed_at'])
            self.assertIsNone(campaign._task_observed_at(None), 'A frozen plan alone does not count a real task')
            missing = deepcopy(selected['H44']['item'])
            missing['acp'].pop('history_observation')
            facts = campaign._delivery(evidence, missing, selected['H44']['task'], False)
            self.assertNotIn('requirement_submitted_at', facts)
            self.assertIsNone(campaign._task_observed_at(facts))
            wrong = deepcopy(selected['H44']['item'])
            wrong['task_key'] = '00000000-0000-4000-8000-000000000000'
            with self.assertRaises(ValueError):
                campaign._delivery(evidence, wrong, selected['H44']['task'], False)

            # Exercise the actual exporter function with an exact successful H40
            # chain pair. Only this source read is reused; no RPC is performed.
            path = ROOT / 'runtime/nox-iclone-preflight-20261023/export_campaign_sources_20261028.py'
            spec = importlib.util.spec_from_file_location('offline_campaign_exporter_test', path)
            exporter = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(exporter)
            exporter.ROOT = root
            original = root / fixture['chain_observation']
            output = root / 'runtime/export-unit'
            originals = exporter.Originals(original.parent, output)
            references = exporter.execution_chain_reference(originals, [original.parent], 8453)
            self.assertEqual(len(references), 1)
            copied = json.loads(originals.copies[references[0]])
            self.assertEqual(json.loads(copied['request_json'])['method'], 'eth_chainId')
            self.assertEqual(copied, json.loads(original.read_bytes()))
            self.assertFalse(output.exists(), 'Dry curation does not create report/source directories')
            with self.assertRaises(ValueError):
                exporter.execution_chain_reference(originals, [original.parent], 1)
            failed = root / 'runtime/controlled-failed-read'
            failed.mkdir()
            obs = deepcopy(copied)
            obs.update(http_status=429, error_kind='rate_limited', body_complete=False,
                       response_file=None, response_sha256=None)
            (failed / 'chain.observation.json').write_text(json.dumps(obs), encoding='utf-8')
            with self.assertRaises(ValueError):
                exporter.execution_chain_reference(exporter.Originals(failed, output), [failed], 8453)
            unsafe = deepcopy(copied)
            unsafe['response_file'] = '../wallet.private.json'
            (failed / 'chain.observation.json').write_text(json.dumps(unsafe), encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'public sibling'):
                exporter.execution_chain_reference(exporter.Originals(failed, output), [failed], 8453)


if __name__ == '__main__':
    unittest.main()
