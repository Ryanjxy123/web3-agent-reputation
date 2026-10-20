"""Offline replay of the retained Brain run that exposed mixed A/F evidence counting.

The real retained fixture is optional in clean checkouts. No registration, source
verifier or oracle is stubbed; mutations affect only in-memory report objects.
"""

from contextlib import ExitStack
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from reputation_core import MeasurementPurpose, Verdict
from reputation_platform.db import Repository
from reputation_platform.generic_evaluation import verify_generic_report_sources
from reputation_platform.position_checker import CAPABILITY_ID

ROOT = Path(__file__).resolve().parents[1]
RUN = Path('runtime/generic-evaluation-20261019T181403Z-ea6a1c57')


class GenericPositionSourceRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        manifest, report = ROOT / RUN / 'manifest.json', ROOT / RUN / 'report.json'
        if not manifest.is_file() or not report.is_file():
            raise unittest.SkipTest('Retained real Brain position run is not distributed in this checkout.')
        inputs = json.loads(manifest.read_bytes())['inputs']
        if any(not (ROOT / item['path']).is_file() for item in inputs):
            raise unittest.SkipTest('Retained real Brain regression fixture dependencies are absent in this checkout.')

    def setUp(self):
        stack = self.enterContext(ExitStack())
        self.network_guards = [stack.enter_context(patch(target, side_effect=AssertionError(
            'This retained-evidence regression must not create a socket or connect to a database.')))
            for target in ('socket.socket', 'socket.create_connection', 'socket.getaddrinfo', 'psycopg.connect')]
        self.repo = Repository('postgresql://offline-regression-unused', ROOT)
        _, self.hashes = self.repo._manifest(ROOT / RUN)

    def tearDown(self):
        for guard in self.network_guards:
            guard.assert_not_called()

    def load(self):
        return self.repo._load_report(RUN).report

    def test_formal_load_accepts_seven_functional_samples_sharing_availability_sources(self):
        report = self.load()
        availability = [item for item in report.samples
                        if item.sample.purpose == MeasurementPurpose.AVAILABILITY]
        functional = [item for item in report.samples if item.capability_id == CAPABILITY_ID]
        self.assertEqual(len(availability), 10)
        self.assertEqual(len(functional), 7)
        self.assertEqual([item.sample.verdict for item in functional], [Verdict.PASS] * 7)
        plans = {name for item in availability for name in item.sample.evidence
                 if name.endswith('-availability-plan.json')}
        self.assertEqual(len(plans), 1)
        plan_name = next(iter(plans))
        self.assertTrue(all(plan_name in item.sample.evidence for item in functional))
        self.assertEqual(verify_generic_report_sources(ROOT, report, self.hashes), report.registration_reference)

    def test_missing_or_reordered_availability_slots_still_fail_source_verification(self):
        original = self.load()
        for mutation in ('missing', 'reordered'):
            report = original.model_copy(deep=True)
            indices = [index for index, item in enumerate(report.samples)
                       if item.sample.purpose == MeasurementPurpose.AVAILABILITY]
            if mutation == 'missing':
                report.samples.pop(indices[0])
            else:
                first, second = indices[:2]
                report.samples[first], report.samples[second] = report.samples[second], report.samples[first]
            with self.subTest(mutation=mutation), self.assertRaisesRegex(
                    ValueError, 'preserve every planned availability slot in order'):
                verify_generic_report_sources(ROOT, report, self.hashes)

    def test_mutated_functional_task_binding_still_fails_source_verification(self):
        report = self.load().model_copy(deep=True)
        target = next(item for item in report.samples if item.capability_id == CAPABILITY_ID)
        target.sample.task_key = target.sample.task_key.rsplit(':', 1)[0] + ':999999999'
        with self.assertRaisesRegex(ValueError, 'Position report differs'):
            verify_generic_report_sources(ROOT, report, self.hashes)


if __name__ == '__main__':
    unittest.main()
