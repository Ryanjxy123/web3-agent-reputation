"""Worker liveness is separate from HTTP health and Agent scoring."""

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
import unittest
from unittest.mock import Mock, patch
from uuid import uuid4

from fastapi.testclient import TestClient
import psycopg
from psycopg import sql
from psycopg.rows import dict_row

from reputation_platform.api import create_app
from reputation_platform.db import Repository
from reputation_platform.runtime_status import worker_status
from reputation_platform.settings import load_database_url
from reputation_platform.worker import main

REFERENCE = 'eip155:56:0x8004a169fb4a3325136eb29fa0ceb6d2e539a432:49467'


class RuntimeStatusTests(unittest.TestCase):
    def test_absent_stale_stopped_and_each_online_mode(self):
        now = datetime.now(timezone.utc)
        self.assertEqual(worker_status(None, now).state, 'unavailable')
        for mode in ('public-off', 'scoped', 'online'):
            row = {'mode': mode, 'scope_reference': REFERENCE if mode == 'scoped' else None,
                   'stopped': False, 'last_seen_at': now - timedelta(seconds=30)}
            self.assertEqual(worker_status(row, now).state, mode)
            self.assertEqual(worker_status({**row, 'last_seen_at': now - timedelta(seconds=91)}, now).state, 'unavailable')
            self.assertEqual(worker_status({**row, 'stopped': True}, now).state, 'stopped')

    def test_worker_lifecycle_records_default_off_scope_and_normal_exit(self):
        for args, mode, scope in (([], 'public-off', None),
            (['--enable-public-readonly', '--proxy', 'http://127.0.0.1:7897', '--public-reference', REFERENCE], 'scoped', REFERENCE),
            (['--enable-public-readonly', '--proxy', 'http://127.0.0.1:7897'], 'online', None)):
            with self.subTest(mode=mode), patch('sys.argv', ['worker', '--once', *args]), patch(
                'reputation_platform.worker.load_database_url', return_value='unused'), patch(
                'reputation_platform.worker.Repository') as factory:
                repo = factory.return_value
                repo.claim_job.return_value = None
                main()
                calls = repo.worker_heartbeat.call_args_list
                self.assertGreaterEqual(len(calls), 2)
                self.assertEqual(calls[0].args[1:], (mode, scope))
                self.assertEqual(calls[-1].args[1:], (mode, scope))
                self.assertEqual(calls[-1].kwargs, {'stopped': True})

    def test_runtime_api_does_not_report_database_or_worker_online_on_database_error(self):
        repo = Mock()
        repo.runtime_status.side_effect = psycopg.OperationalError('private database credentials')
        with TestClient(create_app(repo)) as client:
            response = client.get('/api/runtime')
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['api'], 'ok')
        self.assertEqual(payload['database'], 'unavailable')
        self.assertEqual(payload['worker']['state'], 'unavailable')
        self.assertIsNone(payload['queued'])
        self.assertNotIn('credentials', response.text)

    def test_invalid_scope_or_unsafe_heartbeat_rejected_before_database(self):
        repo = Repository('unused')
        with patch.object(repo, '_connect') as connect:
            for mode, reference in (('scoped', None), ('scoped', 'https://secret.example/key'),
                                    ('public-off', REFERENCE), ('other', None)):
                with self.assertRaises(ValueError):
                    repo.worker_heartbeat('worker-test', mode, reference)
            connect.assert_not_called()

    def test_real_postgres_isolated_schema_rolls_back_heartbeat_queue_and_renewal(self):
        """All DDL/DML lives in one rollback-only unique schema; existing tables are untouched."""
        schema = 'runtime_status_verify_' + uuid4().hex
        with psycopg.connect(load_database_url(), row_factory=dict_row) as connection:
            connection.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(schema)))
            connection.execute(sql.SQL('SET LOCAL search_path TO {}').format(sql.Identifier(schema)))

            class IsolatedRepository(Repository):
                @contextmanager
                def _connect(self):
                    yield connection

            repo = IsolatedRepository('unused')
            try:
                repo.initialize()
                state = repo.runtime_status()
                self.assertEqual((state.database, state.queued, state.running, state.worker.state), ('ready', 0, 0, 'unavailable'))
                repo.worker_heartbeat('test-worker', 'scoped', REFERENCE)
                self.assertEqual(repo.runtime_status().worker.scope_reference, REFERENCE)
                self.assertEqual(repo.runtime_status().worker.state, 'scoped')
                job = repo.create_job(REFERENCE)
                self.assertEqual(repo.runtime_status().queued, 1)
                lease = repo.claim_job('test-worker')
                self.assertEqual(repo.runtime_status().running, 1)
                connection.execute("UPDATE worker_heartbeats SET last_seen_at=clock_timestamp()-interval '5 minutes'")
                self.assertEqual(repo.runtime_status().worker.state, 'unavailable')
                repo.renew_job(job.id, 'test-worker', lease['fencing_token'])
                self.assertEqual(repo.runtime_status().worker.state, 'scoped')
                repo.worker_heartbeat('recent-stopped', 'public-off', stopped=True)
                self.assertEqual(repo.runtime_status().worker.state, 'scoped', 'Fresh active worker wins over newer stopped worker')
                repo.finalize_job(job.id, 'test-worker', lease['fencing_token'], status='NEEDS_INFO', message='Rollback-only test')
                repo.worker_heartbeat('test-worker', 'scoped', REFERENCE, stopped=True)
                state = repo.runtime_status()
                self.assertEqual((state.queued, state.running, state.worker.state), (0, 0, 'stopped'))
                with TestClient(create_app(repo)) as client:
                    response = client.get('/api/runtime')
                    self.assertEqual(response.json()['worker']['state'], 'stopped')
                    self.assertNotIn('worker_id', response.text)
            finally:
                connection.rollback()
            self.assertIsNone(connection.execute('SELECT schema_name FROM information_schema.schemata WHERE schema_name=%s', (schema,)).fetchone())


if __name__ == '__main__':
    unittest.main()
