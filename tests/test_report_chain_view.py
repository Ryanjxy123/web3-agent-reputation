"""One retained-evidence view check and its integrity failure boundary."""

from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from reputation_core.admission import MeasurementPurpose, Verdict
from reputation_core.reporting import EvaluationReport, SampleExplanation
from reputation_core.scoring import ScoredSample
from reputation_platform.report_chain_view import build_report_chain_evidence


FIXTURES = Path(__file__).parent / "fixtures/behavior-98"


class ReportChainViewTests(unittest.TestCase):
    def test_retained_actions_and_tampered_source(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root, permitted, paths = Path(directory), {}, []
            for role in ("wrap", "swap", "increase"):
                for kind in ("transaction", "receipt", "block"):
                    path = f"history-98-{role}-{kind}.response.bin"
                    raw = (FIXTURES / f"{role}-{kind}.json").read_bytes()
                    (root / path).write_bytes(raw)
                    permitted[path] = hashlib.sha256(raw).hexdigest()
                    paths.append(path)
            sample = ScoredSample(
                sample_id="retained:98", task_key="retained:98", purpose=MeasurementPurpose.BEHAVIORAL,
                verdict=Verdict.PASS, elapsed_ms=None, reason="Retained published verification", evidence=paths,
            )
            report = EvaluationReport(
                candidate_key="retained-public-case", name="Retained case", registration_reference="retained-reference",
                generated_at=datetime(2026, 10, 23, tzinfo=timezone.utc), scope="Retained historical operations",
                scope_exclusions=[], evaluation_window="Historical", approach="Existing report",
                samples=[SampleExplanation(sample=sample, title="运行记录98", input_summary="Retained task",
                                           claimed_output="Three operations", independent_result="Verified",
                                           checks=[])], source_references=[], limitations=[],
            )
            before = deepcopy(report.model_dump(mode="json"))
            view = build_report_chain_evidence(root, report, permitted)
            self.assertEqual([action.action for action in view.actions], ["wrap", "swap", "increase_liquidity"])
            self.assertEqual(view.actions[0].executor, "0xbfaa69233741924ed5b9d5daa9b4bf7b84567f0a")
            self.assertEqual(view.actions[0].block_number, 125840454)
            self.assertIn("4.084197897928518823", view.actions[1].summary)
            self.assertIn("7575224", view.actions[2].summary)
            self.assertEqual(report.model_dump(mode="json"), before)
            damaged = root / "history-98-swap-receipt.response.bin"
            original = json.loads(damaged.read_bytes())
            original["result"]["status"] = "0x0"
            damaged.write_text(json.dumps(original), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "SHA256"):
                build_report_chain_evidence(root, report, permitted)


if __name__ == "__main__":
    unittest.main()
