"""Synthetic packages exercise explicit report selection without database or network access."""

from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import tarfile
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch
from uuid import UUID

from scripts import public_reports


class PublicReportArchiveTests(unittest.TestCase):
    def test_checked_in_dependencies_match_the_published_mangoswap_package(self):
        root = Path(__file__).resolve().parents[1]
        with tarfile.open(root / 'data/public-reports-single-score-v3.tar.gz') as archive:
            index = next(member for member in archive if public_reports.INDEX.fullmatch(member.name))
            package = json.load(archive.extractfile(index))
            self.assertEqual(len(package['reports']), 1)
            self.assertEqual(package['reports'][0]['candidate_key'], 'mangoswap-26345')
            inventory = package['files']
        frozen = [item for item in inventory if not item['path'].startswith('runtime/')]
        self.assertTrue(frozen)
        for item in frozen:
            with self.subTest(path=item['path']):
                self.assertEqual(hashlib.sha256((root / item['path']).read_bytes()).hexdigest(), item['sha256'])


class PublicReportSelectionTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory(prefix="public-report-selection-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.output = self.root / "selected.tar.gz"
        self.rows, self.imported = [], {}
        self.repo = MagicMock()
        connection = self.repo._connect.return_value.__enter__.return_value
        connection.execute.side_effect = self.execute
        self.repo._load_report.side_effect = self.imported.__getitem__
        self.repo._manifest.return_value = ({}, {})
        for name, value in (("Repository", self.repo), ("load_database_url", "unused")):
            patched = patch.object(public_reports, name, return_value=value)
            patched.start()
            self.addCleanup(patched.stop)

    def execute(self, query, parameters):
        self.assertIn("->>'status'='COMPLETE'", query)
        rows = [row for row in self.rows if row["validated_json"]["scores"]["status"] == "COMPLETE"]
        if parameters:
            self.assertIn("r.id = ANY(%s)", query)
            rows = [row for row in rows if row["id"] in parameters[0]]
        return SimpleNamespace(fetchall=lambda: rows)

    def report(self, number, identity, status="COMPLETE"):
        report_id = UUID(int=number)
        canonical = f"eip155:100:0x8004a169fb4a3325136eb29fa0ceb6d2e539a432:{identity}"
        source = f"runtime/synthetic-public-report/{number}"
        directory = self.root / source
        directory.mkdir(parents=True)
        for name in ("manifest.json", "report.json", "report.html"):
            (directory / name).write_text("synthetic fixture", encoding="utf-8")
        scores = {"status": status}
        report_hash = public_reports.digest(directory / "report.json")
        manifest_hash = public_reports.digest(directory / "manifest.json")
        self.imported[source] = SimpleNamespace(directory=directory, registration_reference=canonical,
            report_hash=report_hash, manifest_hash=manifest_hash,
            report=SimpleNamespace(candidate_key=f"synthetic-{identity}", name="Synthetic fixture",
                generated_at=datetime(2026, 10, 20, tzinfo=timezone.utc),
                scores=SimpleNamespace(model_dump=lambda **_: scores)))
        self.rows.insert(0, {"id": report_id, "registration_reference": canonical,
            "source_directory": source, "report_sha256": report_hash, "manifest_sha256": manifest_hash,
            "validated_json": {"scores": scores}})
        return report_id

    def exported_ids(self, report_ids=None):
        result = public_reports.export_package(self.root, self.output, report_ids)
        with tarfile.open(self.output) as archive:
            index = next(member for member in archive if public_reports.INDEX.fullmatch(member.name))
            reports = json.load(archive.extractfile(index))["reports"]
        self.assertEqual(result["reports"], len(reports))
        return {UUID(item["source_report_id"]) for item in reports}

    def test_exports_only_requested_complete_reports(self):
        first = self.report(1, 1)
        self.report(2, 2)
        third = self.report(3, 3)
        self.assertEqual(self.exported_ids([str(first), third]), {first, third})
        self.assertEqual(self.repo._load_report.call_count, 2)

    def test_default_keeps_latest_complete_report_per_identity(self):
        self.report(1, 1)
        latest = self.report(2, 1)
        complete = self.report(3, 2)
        self.report(4, 2, "PARTIAL")
        self.assertEqual(self.exported_ids(), {latest, complete})

    def test_rejects_missing_incomplete_invalid_or_dropped_ids(self):
        older = self.report(1, 1)
        newer = self.report(2, 1)
        incomplete = self.report(3, 2, "PARTIAL")
        for ids in ([older, UUID(int=999)], [older, incomplete], [older, newer], ["invalid-uuid"], []):
            with self.subTest(ids=ids), self.assertRaises(ValueError):
                public_reports.export_package(self.root, self.output, ids)
            self.assertFalse(self.output.exists())
        self.repo._load_report.assert_not_called()

    def test_cli_accepts_repeated_report_ids(self):
        ids = [UUID(int=1), UUID(int=2)]
        argv = ["public_reports.py", "export", "--root", str(self.root), "--output", str(self.output),
                "--report-id", str(ids[0]), "--report-id", str(ids[1])]
        with patch("sys.argv", argv), patch("sys.stdout", new_callable=io.StringIO), \
             patch.object(public_reports, "export_package", return_value={}) as export:
            self.assertEqual(public_reports.main(), 0)
        export.assert_called_once_with(self.root, self.output, ids)


if __name__ == "__main__":
    unittest.main()
