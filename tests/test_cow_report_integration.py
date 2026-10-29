"""One offline integration case; its assessment freeze is controlled test data.

The HTTP, public registry and settlement originals come from the real pilot
fixture. No additional business task, network request or database write occurs.
"""

import base64
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from reputation_core import Verdict
from reputation_platform import cow_swap_report as adapter
from reputation_platform.agent_profiles import profile_from_report
from reputation_platform.db import EvidenceIntegrityError, Repository
from reputation_platform.report_chain_view import build_report_chain_evidence
from reputation_platform.shared_report import verify_shared_report_sources


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / 'tests/fixtures/cow_swap_pilot_public_case.json'


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


class CowReportIntegration(unittest.TestCase):
    def test_public_pilot_dispatch_repository_profile_chain_and_missing_transaction(self):
        fixture = json.loads(FIXTURE.read_bytes())
        with tempfile.TemporaryDirectory(prefix='cow-report-integration-') as temporary:
            root = Path(temporary).resolve()

            def save(name, value):
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(json.dumps(value, ensure_ascii=False).encode())
                return path

            for item in fixture['files']:
                raw = base64.b64decode(item['base64'], validate=True)
                self.assertEqual(digest(raw), item['sha256'])
                path = root / item['path']
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(raw)
            # These files supply immutable software snapshots to the temporary
            # builder. They are never imported from or executed in this root.
            for name in (adapter.ADR,
                         'services/platform/src/reputation_platform/cow_swap_protocol.py',
                         'services/platform/src/reputation_platform/public_service_identity.py',
                         'packages/core/src/reputation_core/shared_scoring.py',
                         'packages/core/src/reputation_core/scoring.py'):
                target = root / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes((ROOT / name).read_bytes())

            source = json.loads((root / fixture['source']).read_bytes())
            plan_path = root / source['campaign_plan']
            plan = json.loads(plan_path.read_bytes())
            # Only the assessment clock is synthetic. Its original retained
            # pilot intent and every HTTP/RPC byte keep their authenticated SHA.
            plan.update(status='FROZEN', frozen_at='2026-10-28T18:30:00+00:00')
            save(source['campaign_plan'], plan)
            for item in source['sources']:
                if item['path'] == source['campaign_plan']:
                    item['sha256'] = digest(plan_path.read_bytes())
            save(fixture['source'], source)
            directory = Path('runtime/cow-integration/report')
            with patch.object(Repository, '_connect', side_effect=AssertionError('Offline integration cannot open PostgreSQL')):
                report = adapter.build_cow_swap_report(root, Path(fixture['source']), directory)
                manifest_path = root / directory / 'manifest.json'
                manifest = json.loads(manifest_path.read_bytes())
                hashes = {item['path']: item['sha256'] for item in manifest['inputs']}
                canonical = source['registration_reference']
                self.assertEqual(verify_shared_report_sources(root, report, hashes), canonical)
                repository = Repository('unused-no-database', root)
                imported = repository._load_report(directory)
                self.assertEqual(imported.registration_reference, canonical)
                self.assertEqual(imported.report.model_dump(mode='json'), report.model_dump(mode='json'))
                self.assertTrue(any('/software/' in name for name in hashes))
                self.assertFalse(any(name.startswith(('services/', 'packages/')) for name in hashes))
                self.assertNotIn(adapter.ADR, imported.evidence_files)

                def repository_view(retained, selected):
                    # A read-only database row stub exercises the real repository
                    # view boundary without a PostgreSQL connection or write.
                    row = {'validated_json': retained.report.model_dump(mode='json'),
                           'evidence_files': retained.evidence_files,
                           'source_directory': retained.directory.relative_to(root).as_posix(),
                           'manifest_sha256': retained.manifest_hash}
                    connection = MagicMock()
                    connection.__enter__.return_value = connection
                    connection.execute.return_value.fetchone.return_value = row
                    with patch.object(repository, '_connect', return_value=connection):
                        return repository.report_chain_evidence('00000000-0000-4000-8000-000000000001', selected)

                profile = profile_from_report(root, {
                    'validated_json': report.model_dump(mode='json'), 'registration_reference': canonical,
                    'source_directory': directory.as_posix(), 'manifest_sha256': digest(manifest_path.read_bytes()),
                })
                self.assertIsNone(profile.registration_chain_id)
                self.assertEqual(profile.execution_chain_ids, [8453])
                self.assertEqual(profile.execution_accounts, [plan['owner']])
                self.assertIn('公共服务目录', profile.boundary)
                self.assertIn('UNKNOWN', profile.boundary)
                self.assertIn('报价', profile.boundary)

                key = source['tasks'][0]['task_key']
                view = repository_view(imported, key)
                self.assertEqual(len(view.actions), 1)
                action = view.actions[0]
                self.assertEqual(action.action, 'swap')
                self.assertEqual(action.verdict, Verdict.PASS)
                self.assertEqual(action.chain_id, 8453)
                self.assertEqual(action.block_number, 53211263)
                self.assertEqual(action.transaction_hash,
                    '0xb120835b32623e9d64f71a826e25eaa11d3ebcffdf8c9373b069b5d41a9f0e4d')
                self.assertEqual(action.target, plan['protocol_binding']['settlement'])
                self.assertNotEqual(action.executor, plan['owner'])  # solver is not the buyer
                self.assertIn('0xbbf8b16dc9736e3d469e064dc5440dcfaf6659d2cf7ce46fd8afee64ffd6f9c6176501c795dbc31259bb86a49eb8a88ff2298b856ae240eb', action.summary)
                self.assertIn(plan['owner'], action.summary)
                self.assertIn('USDC 0.1', action.summary)
                self.assertIn('WETH 0.000041856540788113', action.summary)
                self.assertIn('WETH 0.000041629291989146', action.summary)
                self.assertIn('91 块', action.summary)
                self.assertIn('64 块', action.summary)
                self.assertIn('VaultRelayer 剩余授权为 0', action.summary)
                self.assertIn('ERC-8004 chain_registration', ' '.join(view.limitations))
                self.assertEqual(build_report_chain_evidence(root, report, hashes,
                    plan['tasks'][1]['task_key']).actions, [])
                with self.assertRaisesRegex(ValueError, 'differs from replay'):
                    verify_shared_report_sources(root, report.model_copy(update={'scope': 'tampered'}), hashes)
                with self.assertRaisesRegex(ValueError, 'Conflicting CoW'):
                    verify_shared_report_sources(root, report, dict(hashes,
                        **{'runtime/control/unsigned-swap-report-origin.json': '0' * 64}))

                missing = copy.deepcopy(source)
                execution = missing['tasks'][0]['execution']
                execution['rpc_observations'] = [name for name in execution['rpc_observations']
                    if json.loads(json.loads((root / name).read_bytes())['request_json'])['method']
                    != 'eth_getTransactionByHash']
                missing_source = Path('runtime/cow-integration/missing-transaction-source.json')
                save(missing_source, missing)
                unknown_dir = Path('runtime/cow-integration/missing-transaction-report')
                unknown = adapter.build_cow_swap_report(root, missing_source, unknown_dir)
                loaded_unknown = repository._load_report(unknown_dir)
                outcomes = [item.verdict for item in unknown.shared_assessment.observations
                            if item.task_key == key and item.criterion_id == 'onchain-fulfillment']
                self.assertTrue(outcomes)
                self.assertTrue(all(item == Verdict.UNKNOWN for item in outcomes))
                unknown_view = repository_view(loaded_unknown, key)
                self.assertEqual(unknown_view.actions, [])
                self.assertIsNone(unknown.scores.behavioral.value)
                self.assertIsNone(unknown.scores.overall)

                manifest_raw = manifest_path.read_bytes()
                manifest_path.write_bytes(manifest_raw + b' ')
                with self.assertRaises(EvidenceIntegrityError):
                    repository_view(imported, key)
                manifest_path.write_bytes(manifest_raw)

                # A byte change in a real original is rejected at Repository's
                # retained-input boundary, without opening a database connection.
                original = root / source['tasks'][0]['task_intent']
                original.write_bytes(original.read_bytes() + b' ')
                with self.assertRaises(EvidenceIntegrityError):
                    repository._load_report(directory)


if __name__ == '__main__':
    unittest.main()
