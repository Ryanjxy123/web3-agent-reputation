"""Offline retained RPC fixtures; these checks are not public evaluation samples."""

from copy import deepcopy
import json
from pathlib import Path
import unittest

from reputation_core import Verdict, verify_increase

# Verbatim public responses from runtime/defi-step-20261017T181209Z-f4925047.
FIXTURES = Path(__file__).parent / "fixtures"


class LiquidityVerificationTests(unittest.TestCase):
    def test_retained_increase_and_invalid_evidence(self) -> None:
        transaction = json.loads((FIXTURES / "increase-transaction.json").read_bytes())["result"]
        receipt = json.loads((FIXTURES / "increase-receipt.json").read_bytes())["result"]
        expected = {
            "chain_id": 56,
            "expected_sender": "0xbFAA69233741924eD5b9d5DAA9B4Bf7B84567F0A",
            "manager": "0x46A15B0b27311cedF172AB29E4f4766fbE7F4364",
            "token_id": 7637521,
            "expected_tx_hash": "0xceda861374ea49e79034c23812c90d6d98b2ce0a7d17ea2f1abfb5aa2881f644",
        }
        result = verify_increase(transaction, receipt, **expected)
        self.assertEqual(result.verdict, Verdict.PASS)
        self.assertGreater(result.liquidity_delta, 0)
        self.assertIn("deadline not independently checked", result.reason)
        self.assertGreater(result.amount0, 2**53)
        wire = json.loads(result.model_dump_json())
        quantities = ("liquidity_delta", "amount0", "amount1")
        self.assertEqual({name: wire[name] for name in quantities},
                         {name: str(getattr(result, name)) for name in quantities})
        self.assertIsInstance(wire["block_number"], int)
        self.assertIsInstance(wire["transaction_index"], int)

        for mutation, verdict in (("token", Verdict.FAIL), ("sender", Verdict.FAIL),
                                   ("reverted", Verdict.FAIL), ("missing", Verdict.UNKNOWN),
                                   ("duplicate", Verdict.UNKNOWN), ("deadline", Verdict.FAIL)):
            with self.subTest(mutation=mutation):
                tx, proof, parameters = deepcopy(transaction), deepcopy(receipt), dict(expected)
                if mutation == "token":
                    parameters["token_id"] += 1
                elif mutation == "sender":
                    tx["from"] = "0x" + "11" * 20
                elif mutation == "reverted":
                    proof["status"] = "0x0"
                elif mutation == "missing":
                    proof.pop("logs")
                elif mutation == "duplicate":
                    proof["logs"].append(deepcopy(proof["logs"][-1]))
                else:
                    parameters["block_timestamp"] = int(tx["input"][-64:], 16) + 1
                self.assertEqual(verify_increase(tx, proof, **parameters).verdict, verdict)
