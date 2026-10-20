"""Replay the real 24-slot query report through the production source gate offline.

The retained fixture is optional in clean checkouts. No identity, oracle or
business verifier is stubbed; source mutations use a temporary evidence copy.
"""

from contextlib import ExitStack
import hashlib
import json
from pathlib import Path
import shutil
import socket
import tempfile
import unittest
from unittest.mock import patch

import psycopg

from reputation_core import MeasurementPurpose, Verdict
from reputation_core.scoring import SERVICE_CONTRACT_POLICY_VERSION
from reputation_platform.db import Repository, _validated_report
from reputation_platform.generic_evaluation import verify_generic_report_sources
from reputation_platform.position_checker import CAPABILITY_ID
from reputation_platform.position_fulfillment import PLAN_NAME


ROOT = Path(__file__).resolve().parents[1]
RUN = Path('runtime/generic-evaluation-20261020T082507Z-7406b7e4')


class GenericFulfillmentSourceRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        manifest, report = ROOT / RUN / 'manifest.json', ROOT / RUN / 'report.json'
        if not manifest.is_file() or not report.is_file():
            raise unittest.SkipTest('Retained real query fulfillment fixture is not distributed in this checkout.')
        if any(not (ROOT / item['path']).is_file() for item in json.loads(manifest.read_bytes())['inputs']):
            raise unittest.SkipTest('Retained real fulfillment fixture dependencies are absent in this checkout.')

    def setUp(self):
        stack = self.enterContext(ExitStack())
        self.guards = [stack.enter_context(patch.object(target, name, side_effect=AssertionError(
            'Retained source regression forbids network and database connections.')))
            for target, name in ((socket.socket, 'connect'), (socket.socket, 'connect_ex'),
                                 (socket, 'create_connection'), (socket, 'getaddrinfo'),
                                 (psycopg, 'connect'), (Repository, '_connect'))]
        self.repo = Repository('offline-source-regression-unused', ROOT)
        _, self.hashes = self.repo._manifest(ROOT / RUN)
        self.report = _validated_report(json.loads((ROOT / RUN / 'report.json').read_bytes()))

    def tearDown(self):
        for guard in self.guards:
            guard.assert_not_called()

    def test_formal_load_accepts_ten_a_seven_f_and_seven_independent_query_b_without_mech_plan(self):
        self.assertFalse(any(Path(name).name == 'generic-mech-task-plan.json' for name in self.hashes))
        loaded = self.repo._load_report(RUN)
        report = loaded.report
        self.assertEqual(len(report.samples), 24)
        purposes = {purpose: [s for s in report.samples if s.sample.purpose == purpose]
                    for purpose in (MeasurementPurpose.AVAILABILITY, MeasurementPurpose.FUNCTIONAL,
                                    MeasurementPurpose.BEHAVIORAL)}
        self.assertEqual([len(samples) for samples in purposes.values()], [10, 7, 7])
        functional, behavioral = purposes[MeasurementPurpose.FUNCTIONAL], purposes[MeasurementPurpose.BEHAVIORAL]
        self.assertEqual([s.sample.verdict for s in functional + behavioral], [Verdict.PASS] * 14)
        self.assertTrue({s.sample.task_key for s in functional}.isdisjoint(s.sample.task_key for s in behavioral))
        self.assertTrue(all(s.capability_id == CAPABILITY_ID for s in functional + behavioral))
        self.assertEqual(report.scores.status, 'COMPLETE')
        self.assertEqual(report.scores, self.report.scores)
        self.assertEqual(loaded.registration_reference, report.registration_reference)

    def test_missing_fulfillment_plan_and_unverified_behavioral_sample_are_rejected(self):
        hashes = {name: digest for name, digest in self.hashes.items() if Path(name).name != PLAN_NAME}
        with self.assertRaisesRegex(ValueError, 'complete independent evidence plan'):
            verify_generic_report_sources(ROOT, self.report, hashes)
        report = self.report.model_copy(deep=True)
        extra = next(s for s in report.samples if s.sample.purpose == MeasurementPurpose.BEHAVIORAL)
        # Stay within the seven-B ceiling so this reaches the generic source gate.
        report.policy_version = SERVICE_CONTRACT_POLICY_VERSION
        report.samples = [s for s in report.samples if s.sample.purpose == MeasurementPurpose.AVAILABILITY]
        report.capabilities = [c for c in report.capabilities if c.capability_id != CAPABILITY_ID]
        extra.sample.sample_id = 'unverified-behavioral-task'
        extra.sample.task_key = 'unverified-query:999999999'
        extra.sample.evidence = []
        extra.capability_id = None
        report.samples.append(extra)
        with self.assertRaisesRegex(ValueError, 'not yet supplied business-task verification'):
            verify_generic_report_sources(ROOT, report, hashes)

    def test_changed_behavioral_verdict_task_binding_and_agent_identity_are_rejected(self):
        for mutation in ('verdict', 'task_binding', 'identity'):
            report = self.report.model_copy(deep=True)
            target = next(s for s in report.samples if s.sample.purpose == MeasurementPurpose.BEHAVIORAL)
            if mutation == 'verdict':
                target.sample.verdict = Verdict.FAIL
            elif mutation == 'task_binding':
                target.sample.task_key = target.sample.task_key.rsplit(':', 1)[0] + ':999999999'
            else:
                report.registration_reference = report.registration_reference.rsplit(':', 1)[0] + ':999999999'
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                verify_generic_report_sources(ROOT, report, self.hashes)

    def test_rehashed_behavioral_request_input_still_must_match_its_frozen_subject(self):
        with tempfile.TemporaryDirectory(prefix='generic-fulfillment-source-') as temporary:
            root = Path(temporary)
            for name in self.hashes:
                destination = root / name
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(ROOT / name, destination)
            name = (RUN / 'fulfillment-business-7.request-plan.json').as_posix()
            path = root / name
            request = json.loads(path.read_bytes())
            request['json']['params']['arguments']['position'] = '999999999'
            raw = json.dumps(request).encode()
            path.write_bytes(raw)
            hashes = {**self.hashes, name: hashlib.sha256(raw).hexdigest()}
            with self.assertRaises(ValueError):
                verify_generic_report_sources(root, self.report, hashes)


if __name__ == '__main__':
    unittest.main()
