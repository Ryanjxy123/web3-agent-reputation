"""One offline rule regression using retained public responses, never an evaluation sample."""

from copy import deepcopy
from datetime import datetime
import json
from pathlib import Path
import unittest

from reputation_core.admission import Verdict
from reputation_core.behavior import verify_behavior

FIXTURES = Path(__file__).parent / "fixtures/behavior-98"


class BehaviorVerificationTests(unittest.TestCase):
    def test_retained_sequence_and_decisive_or_missing_evidence(self) -> None:
        def load(name: str) -> object:
            return json.loads((FIXTURES / (name + ".json")).read_bytes())["result"]

        steps = {role: {kind: load(f"{role}-{kind}") for kind in ("transaction", "receipt", "block")}
                 for role in ("wrap", "swap", "increase")}
        expected = {
            "expected_tx_hashes": {
                "wrap": "0x5bf1da56f29171157dff8a02290b6970aaa04444729694f87094dfac397176f6",
                "swap": "0x924dffad3ba851e9c104176f2d0584315f1bea29f9a59ed2496e5134945d6da3",
                "increase": "0x90231e98bae020ed77a7aba631f70b8efc62f3add338ea4f03ebb71ac358328c",
            },
            "expected_sender": "0xbfaa69233741924ed5b9d5daa9b4bf7b84567f0a",
            "token_id": 7575224,
            # This unit test injects the trusted context. The live caller must independently read the factory.
            "trusted_pool": "0xafb2da14056725e3ba3a30dd846b6bbbd7886c56",
            "trusted_pool_block": int(steps["swap"]["receipt"]["blockNumber"], 16),
            "confirmation_head": int(load("confirmation-head"), 16),
            "task_started_at": datetime.fromisoformat("2026-10-05T09:00:38.978+00:00").timestamp(),
        }
        result = verify_behavior(steps, **expected)
        self.assertEqual(result.verdict, Verdict.PASS, result.model_dump_json())
        self.assertEqual(result.elapsed_seconds, 3)
        self.assertGreater(int(result.swap.amount_out), 2**53)
        self.assertIsInstance(json.loads(result.model_dump_json())["increase"]["liquidity_delta"], str)

        for mutation, verdict in (("recipient", Verdict.FAIL), ("sender", Verdict.FAIL),
                                  ("direction", Verdict.FAIL), ("reverted", Verdict.FAIL),
                                  ("missing_log", Verdict.UNKNOWN), ("unknown_path", Verdict.UNKNOWN),
                                  ("price_limit", Verdict.UNKNOWN), ("missing_pool", Verdict.UNKNOWN)):
            with self.subTest(mutation=mutation):
                evidence, parameters = deepcopy(steps), dict(expected)
                swap = evidence["swap"]
                if mutation in ("recipient", "price_limit"):
                    data = swap["transaction"]["input"]
                    word = 3 if mutation == "recipient" else 7
                    value = int("11" * 20, 16) if mutation == "recipient" else 1
                    swap["transaction"]["input"] = data[:10 + word * 64] + f"{value:064x}" + data[10 + (word + 1) * 64:]
                elif mutation == "sender":
                    swap["transaction"]["from"] = "0x" + "11" * 20
                elif mutation == "direction":
                    data = swap["receipt"]["logs"][-1]["data"]
                    positive = int(data[2:66], 16) - 2**256
                    swap["receipt"]["logs"][-1]["data"] = "0x" + f"{-positive:064x}" + data[66:]
                elif mutation == "reverted":
                    swap["receipt"]["status"] = "0x0"
                elif mutation == "missing_log":
                    swap["receipt"]["logs"].pop()
                elif mutation == "unknown_path":
                    data = swap["transaction"]["input"]
                    swap["transaction"]["input"] = "0xdeadbeef" + data[10:]
                else:
                    parameters["trusted_pool"] = None
                actual = verify_behavior(evidence, **parameters)
                self.assertEqual(actual.verdict, verdict, actual.model_dump_json())


if __name__ == "__main__":
    unittest.main()
