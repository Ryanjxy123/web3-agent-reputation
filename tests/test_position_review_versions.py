"""Versioned local reviews keep new intake independent from historical replay."""

from contextlib import ExitStack
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import socket
import unittest
from unittest.mock import patch

import psycopg

from reputation_platform.db import Repository
from reputation_platform.position_contracts import CONFIG, REVIEW_CONFIG_ENV, review_config_path
from reputation_platform.position_fulfillment import INTENT_NAME
import test_position_fulfillment as fixtures

ROOT = Path(__file__).resolve().parents[1]
NEXT_CONFIG = 'configs/position-adapter-reviews-v2.json'
REAL_RUNS = (Path('runtime/generic-evaluation-20261020T082507Z-7406b7e4'),
             Path('runtime/generic-evaluation-20261020T085451Z-32e1fbd4'))


class ReviewVersionTests(unittest.TestCase):
    def test_review_path_rejects_noncanonical_and_escaping_choices(self):
        for value in (None, 1, '', '../review.json', 'configs/../review.json',
                      'configs//review.json', './review.json', 'configs\\review.json',
                      (ROOT / CONFIG).as_posix()):
            with self.subTest(path=value), self.assertRaises(ValueError):
                review_config_path(ROOT, value)
        self.assertEqual(review_config_path(ROOT, NEXT_CONFIG), NEXT_CONFIG)

    def test_new_collection_freezes_selected_review_and_rejects_path_or_digest_tampering(self):
        case = fixtures.PositionFulfillmentTests()
        case.setUp()
        self.addCleanup(case.doCleanups)
        fixture, collector = case.fixture()
        config = json.loads((fixture.root / CONFIG).read_bytes())
        third = deepcopy(config['adapters'][0])
        third.update(id='third-reviewed/v1', endpoint='https://third.example.test/mcp',
                     tool='read_position', provider='Third provider')
        config['adapters'].append(third)
        fixture.write(NEXT_CONFIG, config)
        collector.inputs.pop(CONFIG)
        with patch.dict(os.environ, {REVIEW_CONFIG_ENV: NEXT_CONFIG}):
            _, samples, _ = case.collect(fixture, collector)
        intent_ref = case.path(fixture, collector, INTENT_NAME)
        intent_path = fixture.root / intent_ref
        intent_raw = intent_path.read_bytes()
        self.assertEqual(json.loads(intent_raw)['review_config_path'], NEXT_CONFIG)
        self.assertEqual(collector.inputs[NEXT_CONFIG], fixture.hashes[NEXT_CONFIG])
        self.assertNotIn(CONFIG, collector.inputs)
        # Historical/default config is unnecessary when a new plan freezes another version.
        (fixture.root / CONFIG).unlink()
        with patch.dict(os.environ, {REVIEW_CONFIG_ENV: 'configs/missing-deployment-choice.json'}):
            self.assertEqual(case.rebuild(fixture, collector)[2], samples)
            for invalid in (None, '../review.json', '/review.json', 'configs/not-in-manifest.json'):
                with self.subTest(path=invalid):
                    case.mutate(fixture, collector, INTENT_NAME,
                                lambda value: value.update(review_config_path=invalid))
                    with self.assertRaises(ValueError):
                        case.rebuild(fixture, collector)
                    fixture.write(intent_ref, intent_raw)
                    collector.inputs[intent_ref] = fixture.hashes[intent_ref]
            review_path = fixture.root / NEXT_CONFIG
            review_raw = review_path.read_bytes()
            review_path.write_bytes(review_raw + b'\n')
            with self.assertRaisesRegex(ValueError, 'retained report source changed'):
                case.rebuild(fixture, collector)
            review_path.write_bytes(review_raw)
            self.assertEqual(case.rebuild(fixture, collector)[2], samples)
        self.assertEqual(case.socket_dial.call_count, 0)


class ProductionReviewVersionTests(unittest.TestCase):
    def test_existing_production_reports_ignore_current_selection(self):
        if any(not (ROOT / run / 'manifest.json').is_file() for run in REAL_RUNS):
            self.skipTest('Retained production query reports are not distributed in this checkout.')
        with ExitStack() as stack:
            guards = {name: stack.enter_context(patch.object(target, attribute,
                side_effect=AssertionError('Review version replay forbids network and database connections.')))
                for name, target, attribute in (
                    ('connect', socket.socket, 'connect'), ('connect_ex', socket.socket, 'connect_ex'),
                    ('create_connection', socket, 'create_connection'), ('dns', socket, 'getaddrinfo'),
                    ('psycopg', psycopg, 'connect'), ('repository', Repository, '_connect'))}
            stack.enter_context(patch.dict(os.environ, {REVIEW_CONFIG_ENV: 'configs/not-deployed-review.json'}))
            initial_config_hash = hashlib.sha256((ROOT / CONFIG).read_bytes()).hexdigest()
            repo = Repository('unused-offline-review-version-test', ROOT)
            for run in REAL_RUNS:
                with self.subTest(run=run.as_posix()):
                    self.assertNotIn('review_config_path', json.loads((ROOT / run / INTENT_NAME).read_bytes()))
                    expected = json.loads((ROOT / run / 'report.json').read_bytes())
                    loaded = repo._load_report(run)
                    self.assertEqual(loaded.report.scores.model_dump(mode='json'), expected['scores'])
                    self.assertEqual(len(loaded.report.samples), 24)
                    self.assertEqual(loaded.report.policy_version, 'service-fulfillment-v1')
            self.assertEqual(hashlib.sha256((ROOT / CONFIG).read_bytes()).hexdigest(), initial_config_hash)
            for guard in guards.values():
                guard.assert_not_called()


if __name__ == '__main__':
    unittest.main()
