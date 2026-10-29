"""One offline real-originals combination for explicit diagnostic calibration."""
import base64
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

from reputation_platform import cow_swap_report as adapter
from reputation_platform.swap_report import SwapEvidence

ROOT = Path(__file__).resolve().parents[1]


class CowDeclaredDiagnosticsAcceptance(unittest.TestCase):
    def test_originals_legacy_calibration_and_fatal_guards(self):
        fixture = json.loads((ROOT / 'tests/fixtures/cow_declared_diagnostics_case.json').read_bytes())
        with tempfile.TemporaryDirectory(prefix='cow-diagnostics-offline-') as temporary:
            root = Path(temporary)
            for row in fixture['files']:
                name = Path(row['path'])
                self.assertFalse(name.is_absolute())
                self.assertNotIn('..', name.parts)
                self.assertNotIn('.private', row['path'])
                raw = base64.b64decode(row['base64'], validate=True)
                self.assertEqual(hashlib.sha256(raw).hexdigest(), row['sha256'])
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(raw)
            for note in (adapter.ADR, adapter.LINEAGE_ADR, adapter.DIAGNOSTICS_ADR):
                path = root / note
                if not path.exists():
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes((ROOT / note).read_bytes())
            plan_path = fixture['plan_path']
            original_raw = (root / plan_path).read_bytes()
            self.assertEqual(hashlib.sha256(original_raw).hexdigest(), fixture['plan_sha256'])
            original = json.loads(original_raw)
            items = fixture['items']
            by_item = {item['task_id']: item for item in items}
            tasks = {task['task_id']: task for task in original['tasks']}
            self.assertEqual(set(by_item), {'C16', 'C24', 'C25'})

            def collect(reference=None):
                source = adapter.collect_cow_originals(root, plan_path, items, measurement_contract=reference)
                hashes = {row['path']: row['sha256'] for row in source['sources']}
                hashes[adapter.ADR] = hashlib.sha256((root / adapter.ADR).read_bytes()).hexdigest()
                evidence = SwapEvidence(root, hashes)
                plan, clocks, _ = adapter._plan(evidence, source)
                return source, evidence, plan, clocks

            def evaluate(plan, evidence, clocks, label, rows=None):
                task, item = tasks[label], by_item[label]
                if rows is None:
                    rows = adapter._http_task(evidence, plan, task, item, clocks[task['task_key']])
                metrics, _ = adapter._metrics(evidence, plan, task, item, rows, clocks[task['task_key']])
                return metrics, rows

            legacy_source, legacy_ev, legacy, legacy_clocks = collect()
            self.assertNotIn('measurement_contract', legacy_source)
            self.assertNotIn('_measurement_contract', legacy)
            self.assertEqual(legacy, original)
            for label, criterion in [('C16', 'validation-binding'), ('C24', 'safe-rejection')]:
                metrics, _ = evaluate(legacy, legacy_ev, legacy_clocks, label)
                self.assertEqual(metrics[criterion][0].value, 'FAIL')

            reference = fixture['measurement_contract']
            source, evidence, plan, clocks = collect(reference)
            self.assertEqual(source['measurement_contract'], reference)
            self.assertEqual(clocks, legacy_clocks)
            self.assertEqual(plan['tasks'], legacy['tasks'])
            self.assertEqual(plan['cases'], legacy['cases'])
            results, originals = {}, {}
            for label in by_item:
                results[label], originals[label] = evaluate(plan, evidence, clocks, label)
            protected = results['C16']['validation-binding']
            self.assertEqual(protected[0].value, 'UNKNOWN')
            self.assertIs(protected[2]['protected'], True)
            warning = results['C24']['safe-rejection']
            self.assertEqual(warning[0].value, 'PASS')
            self.assertEqual(warning[2]['diagnostic_severity'], 'warning')
            self.assertEqual(results['C25']['safe-rejection'][0].value, 'PASS')

            # A missing attribution warning is not silently accepted.
            rows = deepcopy(originals['C24'])
            next(row for row in rows if row['stage'] == 'validate')['payload']['warnings'] = []
            metrics, _ = evaluate(plan, evidence, clocks, 'C24', rows)
            self.assertEqual(metrics['safe-rejection'][0].value, 'FAIL')
            # An unrelated warning cannot downgrade a fatal receiver mismatch.
            rows = deepcopy(originals['C25'])
            native = next(row for row in rows if row['stage'] == 'validate')['payload']
            native.update(valid=True, errors=[], warnings=deepcopy(
                next(row for row in originals['C24'] if row['stage'] == 'validate')['payload']['warnings']))
            metrics, _ = evaluate(plan, evidence, clocks, 'C25', rows)
            self.assertEqual(metrics['safe-rejection'][0].value, 'FAIL')
            # Timing protection cannot hide an additional fatal domain error.
            rows = deepcopy(originals['C16'])
            native = next(row for row in rows if row['stage'] == 'validate')['payload']
            native['errors'].append('signingDomain.verifyingContract is invalid')
            metrics, _ = evaluate(plan, evidence, clocks, 'C16', rows)
            self.assertEqual(metrics['validation-binding'][0].value, 'FAIL')

            spec = importlib.util.spec_from_file_location(
                'cow_diagnostics_assembler_test', ROOT / 'scripts/assemble_cow_task_items.py')
            assembler = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(assembler)
            assembled, summary = assembler.assemble(
                root, plan_path, fixture['plan_sha256'], measurement_contract=reference)
            self.assertEqual({item['task_key'] for item in assembled}, {item['task_key'] for item in items})
            self.assertEqual(summary['observed_tasks'], 3)
            self.assertEqual(summary['measurement_contract'], reference)

            when = datetime(2026, 10, 29, 4, 0, tzinfo=timezone.utc)
            old_report = adapter.replay_cow_swap_sources(root, legacy_ev, legacy_source, when)
            new_report = adapter.replay_cow_swap_sources(root, evidence, source, when)
            old = old_report.shared_assessment.model_dump(mode='json')
            new = new_report.shared_assessment.model_dump(mode='json')
            old_cases = {case['case_id']: case for case in old['cases']}
            new_cases = {case['case_id']: case for case in new['cases']}
            self.assertNotEqual(old_cases['F-invalid-appCode']['title'], new_cases['F-invalid-appCode']['title'])
            for key, case in old_cases.items():
                self.assertEqual(case['task_keys'], new_cases[key]['task_keys'])
                self.assertEqual(case['required_decisive'], new_cases[key]['required_decisive'])
            outcomes = {task['task_key']: task['outcome'] for task in new['tasks']}
            self.assertEqual(outcomes[tasks['C16']['task_key']], 'protected_exit')
            self.assertEqual(outcomes[tasks['C24']['task_key']], 'completed')
            self.assertEqual(next(task['outcome'] for task in old['tasks']
                                  if task['task_key'] == tasks['C24']['task_key']), 'failed')
            with self.assertRaises(ValueError):
                collect(dict(reference, sha256='0' * 64))
            self.assertEqual((root / plan_path).read_bytes(), original_raw)


if __name__ == '__main__':
    unittest.main()
