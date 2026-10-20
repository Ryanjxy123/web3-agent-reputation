"""Scoped read budgets stop before constructing a network client."""

from datetime import datetime, timezone
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from reputation_core import MeasurementPurpose, ProbeObservation, Verdict
from reputation_platform.registration_discovery import DiscoveryEvidence
from reputation_platform.settings import PROJECT_ROOT


class DiscoveryBudgetTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        (self.root / 'configs').mkdir()
        (self.root / 'configs/generic-rpc.json').write_bytes((PROJECT_ROOT / 'configs/generic-rpc.json').read_bytes())

    def test_one_request_budget_preserves_unsent_second_request(self):
        evidence = DiscoveryEvidence(self.root, 'runtime/budget', 'http://127.0.0.1:7897',
                                     enabled=True, max_requests=1, timeout_seconds=45)
        observation = ProbeObservation(request_key='first', purpose=MeasurementPurpose.BACKGROUND,
            url='https://example.com/data', method='GET', observed_at=datetime.now(timezone.utc),
            request_json=None, response_file=None, response_sha256=None,
            http_status=None, elapsed_ms=1.0, outcome=Verdict.UNKNOWN, error_kind='timeout', body_complete=False)
        def fetch(key, directory):
            (directory / f'{key}.observation.json').write_text(observation.model_dump_json(), encoding='utf-8')
            return observation
        with patch('reputation_platform.registration_discovery.SafeHttpClient') as client:
            client.return_value.__enter__.return_value.fetch.side_effect = fetch
            evidence.request('first', 'https://example.com/data')
            second = evidence.request('second', 'https://example.com/data')
            client.assert_called_once()
            self.assertEqual(client.call_args.kwargs['timeout_seconds'], 45)
            self.assertTrue(client.call_args.kwargs['pin_public_dns'])
        self.assertEqual(evidence.request_count, 1)
        self.assertIsNone(second['observation'])
        self.assertEqual(json.loads((evidence.run / 'second.skip.json').read_bytes()),
                         {'request_sent': False, 'reason': 'request_budget_exhausted'})

    def test_invalid_options_are_rejected_before_network(self):
        for options in ({'timeout_seconds': float('nan')}, {'timeout_seconds': 46},
                        {'timeout_seconds': True}, {'max_requests': 0}, {'max_requests': 65},
                        {'max_requests': True}):
            with self.subTest(options=options), self.assertRaises(ValueError):
                DiscoveryEvidence(self.root, 'runtime/invalid', **options)

    def test_evidence_write_error_does_not_refund_a_transport_attempt(self):
        evidence = DiscoveryEvidence(self.root, 'runtime/write-error', 'http://127.0.0.1:7897',
                                     enabled=True, max_requests=1)
        with patch('reputation_platform.registration_discovery.SafeHttpClient') as client:
            client.return_value.__enter__.return_value.fetch.side_effect = OSError('synthetic disk error')
            with self.assertRaises(OSError):
                evidence.request('first', 'https://example.com/data')
            self.assertIsNone(evidence.request('second', 'https://example.com/data')['observation'])
            client.assert_called_once()
        self.assertEqual(evidence.request_count, 1)


if __name__ == '__main__':
    unittest.main()
