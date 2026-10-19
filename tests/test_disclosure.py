"""Offline public fixtures; synthetic mutations are not real evaluation samples."""

from copy import deepcopy
import json
from pathlib import Path
import unittest

from reputation_core.admission import Verdict
from reputation_core.disclosure import DECREASE_TOPIC, verify_disclosure

FIXTURES = Path(__file__).parent / "fixtures"


class DisclosureVerificationTests(unittest.TestCase):
    def test_exact_disclosures_ordered_reconstruction_and_evidence_gaps(self) -> None:
        transaction = json.loads((FIXTURES / "increase-transaction.json").read_bytes())["result"]
        receipt = json.loads((FIXTURES / "increase-receipt.json").read_bytes())["result"]
        # Verbatim positions from runtime/liquidity-state-20261018T051558Z-2222c99c.
        # The single receipt event reconciles these fixed states in this offline case;
        # production callers must independently collect the complete block log set.
        before = json.loads((FIXTURES / "positions-before.json").read_bytes())["result"]
        after = json.loads((FIXTURES / "positions-after.json").read_bytes())["result"]
        logs = [log for log in receipt["logs"] if log["address"].lower() == receipt["to"].lower()]
        self.assertEqual(len(logs), 1)
        parameters = dict(
            chain_id=56, expected_sender="0xbfaa69233741924ed5b9d5daa9b4bf7b84567f0a",
            manager="0x46a15b0b27311cedf172ab29e4f4766fbe7f4364", token_id=7637521,
            expected_tx_hash=transaction["hash"], block_timestamp=int("0x6ad36809", 16),
            positions_before=before, positions_after=after, block_logs=logs,
            declared_liquidity_after="220953851191452895995",
            declared_amount0="1.991646278553218044", declared_amount1="0.011100197378023839",
            decimals0=18, decimals1=18,
            expected_token0="0x0e09fabb73bd3ade0a17ecc321fd13a19e81ce82",
            expected_token1="0xbb4cdb9cbd36b01bd1cbaebf2de08d9173bc095c",
        )
        result = verify_disclosure(transaction, receipt, **parameters)
        self.assertEqual(result.verdict, Verdict.PASS)
        self.assertEqual(result.actual_liquidity_after, parameters["declared_liquidity_after"])
        self.assertEqual(result.actual_amount0_base_units, "1991646278553218044")
        self.assertEqual(result.actual_amount0_base_units, result.declared_amount0_base_units)
        self.assertIsInstance(json.loads(result.model_dump_json())["actual_liquidity_after"], str)
        for label, changes, expected in (
            ("amount", {"declared_amount0": "1.991646278553218045"}, Verdict.FAIL),
            ("after", {"declared_liquidity_after": "220953851191452895996"}, Verdict.FAIL),
            ("missing", {"block_logs": []}, Verdict.UNKNOWN),
            ("duplicate", {"block_logs": logs + deepcopy(logs)}, Verdict.UNKNOWN),
            ("precision", {"decimals0": 17}, Verdict.UNKNOWN),
            ("uint256", {"declared_amount0": str(2**256)}, Verdict.UNKNOWN),
            ("token mapping", {"expected_token0": parameters["expected_token1"]}, Verdict.UNKNOWN),
            ("state gap", {"positions_after": before}, Verdict.UNKNOWN),
        ):
            with self.subTest(label=label):
                self.assertEqual(verify_disclosure(transaction, receipt, **(parameters | changes)).verdict, expected)

        # Synthetic cancelling changes before/after the target leave block-end L
        # unchanged, while the target transaction's own post-state differs by one.
        prior, later = deepcopy(logs[0]), deepcopy(logs[0])
        for item, offset, byte in ((prior, -1, "11"), (later, 1, "22")):
            item["transactionHash"] = "0x" + byte * 32
            item["transactionIndex"] = hex(int(item["transactionIndex"], 16) + offset)
            item["logIndex"] = hex(int(item["logIndex"], 16) + offset)
            item["data"] = "0x" + f"{1:064x}{0:064x}{0:064x}"
        prior["topics"][0] = DECREASE_TOPIC
        ordered = parameters | {"block_logs": [later, *logs, prior]}
        self.assertEqual(verify_disclosure(transaction, receipt, **ordered).verdict, Verdict.FAIL)
        ordered["declared_liquidity_after"] = str(int(parameters["declared_liquidity_after"]) - 1)
        result = verify_disclosure(transaction, receipt, **ordered)
        self.assertEqual(result.verdict, Verdict.PASS)
        self.assertNotEqual(result.actual_liquidity_after, result.block_end_liquidity)
