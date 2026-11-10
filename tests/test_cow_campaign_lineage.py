"""One offline append-only acceptance using actual frozen v1 and old MCP originals."""
import base64
from copy import deepcopy
from datetime import timedelta
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from uuid import uuid4

from reputation_platform import cow_swap_report as adapter
from reputation_platform.swap_report import SwapEvidence

ROOT = Path(__file__).resolve().parents[1]


class CowCampaignLineageAcceptance(unittest.TestCase):
    def test_old_v1_append_clock_intent_and_tamper_guards(self):
        fixture = json.loads((ROOT / 'tests/fixtures/cow_campaign_lineage_case.json').read_bytes())
        with tempfile.TemporaryDirectory(prefix='cow-lineage-offline-') as temporary:
            root = Path(temporary)
            for row in fixture['files']:
                raw = base64.b64decode(row['base64'], validate=True)
                self.assertEqual(hashlib.sha256(raw).hexdigest(), row['sha256'])
                self.assertNotIn('.private', row['path'])
                path = root / row['path']
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(raw)
            note = root / adapter.LINEAGE_ADR
            note.parent.mkdir(parents=True, exist_ok=True)
            note.write_bytes((ROOT / adapter.LINEAGE_ADR).read_bytes())
            old_path = fixture['plan_path']
            old_raw = (root / old_path).read_bytes()
            self.assertEqual(hashlib.sha256(old_raw).hexdigest(), fixture['plan_sha256'])
            original = json.loads(old_raw)

            def collect(path, items):
                source = adapter.collect_cow_originals(root, path, items)
                evidence = SwapEvidence(root, {r['path']: r['sha256'] for r in source['sources']})
                return source, evidence

            source, evidence = collect(old_path, [fixture['old_item']])
            legacy, clocks, canonical = adapter._plan(evidence, source)
            self.assertEqual(legacy, original)
            self.assertEqual(canonical, original['registration_reference'])
            self.assertEqual(clocks[next(t['task_key'] for t in original['tasks'] if t['task_id'] == 'C02')],
                             adapter._time(original['frozen_at']))
            self.assertNotIn(adapter.LINEAGE_ADR, evidence.hashes)

            revised = deepcopy(original)
            revised['previous_plan'] = {'path': old_path, 'sha256': fixture['plan_sha256']}
            revised['frozen_at'] = (adapter._time(original['frozen_at']) + timedelta(hours=1)).isoformat()
            fresh = deepcopy(next(t for t in original['tasks'] if t['task_id'] == 'C02'))
            fresh.update(task_id='C31', task_key=str(uuid4()), input_summary='Controlled temporary prospective retry, not a business sample')
            revised['tasks'].append(fresh)
            for case in revised['cases']:
                if 'C02' in case['planned_task_ids']:
                    case['planned_task_ids'].append('C31')
            new_path = str(Path(old_path).with_name('plan-v2-controlled-offline.json')).replace('\\', '/')

            def put(value):
                (root / new_path).write_text(json.dumps(value), encoding='utf-8')

            put(revised)
            source2, evidence2 = collect(new_path, [fixture['old_item']])
            plan2, clocks2, _ = adapter._plan(evidence2, source2)
            versions = adapter._campaign_lineage(evidence2, new_path)
            self.assertEqual(plan2['tasks'][:30], original['tasks'])
            self.assertEqual(evidence2.raw(old_path), old_raw)
            self.assertIn(old_path, evidence2.hashes)
            self.assertIn(adapter.LINEAGE_ADR, evidence2.hashes)
            self.assertEqual(len(versions), 2)
            self.assertEqual(clocks2[fresh['task_key']], adapter._time(revised['frozen_at']))
            for task in original['tasks']:
                self.assertEqual(clocks2[task['task_key']], clocks[task['task_key']])
            pilot = next(t for t in original['tasks'] if t['task_id'] == 'C01')
            self.assertEqual(clocks2[pilot['task_key']], adapter._time(evidence2.json(pilot['retained_intent']['path'])['frozen_at']))
            old_task = next(t for t in original['tasks'] if t['task_id'] == 'C09')
            old_intent = evidence2.json(fixture['old_item']['task_intent'])
            self.assertEqual(adapter._task_plan_version(old_task, old_intent, versions)['path'], old_path)
            later_intent = dict(old_intent, campaign_plan=new_path, campaign_plan_sha256=versions[-1]['sha256'],
                                created_at=(adapter._time(revised['frozen_at']) + timedelta(seconds=1)).isoformat())
            self.assertEqual(adapter._task_plan_version(old_task, later_intent, versions)['path'], new_path)
            # A later plan intent cannot relabel original earlier HTTP as a new-node request.
            intent_path = root / fixture['old_item']['task_intent']
            original_intent = intent_path.read_bytes()
            intent_path.write_text(json.dumps(later_intent), encoding='utf-8')
            bad_source, bad_evidence = collect(new_path, [fixture['old_item']])
            with self.assertRaisesRegex(ValueError, 'predates'):
                adapter._plan(bad_evidence, bad_source)
            intent_path.write_bytes(original_intent)
            for bad in (dict(later_intent, campaign_plan_sha256='0' * 64),
                        dict(later_intent, created_at=original['frozen_at'])):
                with self.assertRaises(ValueError):
                    adapter._task_plan_version(old_task, bad, versions)
            impostor = dict(old_intent, task_id='C31', task_key=fresh['task_key'], expected=fresh['expected'], requests=fresh['requests'])
            with self.assertRaisesRegex(ValueError, 'wrong plan SHA/task version'):
                adapter._task_plan_version(fresh, impostor, versions)

            # The actual assembler accepts C09/v1 while collecting a v2 assessment.
            spec = importlib.util.spec_from_file_location('cow_lineage_assembler_test', ROOT / 'scripts/assemble_cow_task_items.py')
            assembler = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(assembler)
            before_items, before_summary = assembler.assemble(root, old_path, fixture['plan_sha256'])
            new_sha = hashlib.sha256((root / new_path).read_bytes()).hexdigest()
            items, summary = assembler.assemble(root, new_path, new_sha)
            self.assertEqual(items, before_items)
            self.assertEqual(summary['observed_tasks'], before_summary['observed_tasks'])
            self.assertEqual(summary['observed_tasks'], 1)
            self.assertEqual(summary['planned_tasks'], 31)
            self.assertIn('C31', summary['missing_task_items'])

            for mutation in ('old-request', 'previous-sha', 'owner', 'required-decisive', 'old-case', 'backdate'):
                changed = deepcopy(revised)
                if mutation == 'old-request':
                    changed['tasks'][1]['requests'][0]['arguments']['amount'] = '1'
                elif mutation == 'previous-sha':
                    changed['previous_plan']['sha256'] = '0' * 64
                elif mutation == 'owner':
                    changed['owner'] = '0x' + '1' * 40
                elif mutation == 'required-decisive':
                    changed['cases'][-2]['required_decisive'] -= 1
                elif mutation == 'old-case':
                    changed['cases'][0]['planned_task_ids'] = changed['cases'][0]['planned_task_ids'][1:]
                else:
                    changed['frozen_at'] = (adapter._time(original['frozen_at']) - timedelta(seconds=1)).isoformat()
                put(changed)
                with self.assertRaises(ValueError, msg=mutation):
                    collect(new_path, [fixture['old_item']])
            put(revised)
            self.assertEqual((root / old_path).read_bytes(), old_raw)


if __name__ == '__main__':
    unittest.main()
