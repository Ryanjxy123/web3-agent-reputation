import copy
import json
from pathlib import Path
import unittest

from reputation_platform.unsigned_swap_protocol import (
    UnsignedSwapMismatch,
    UnsupportedUnsignedSwap,
    decode_unsigned_swap,
    verify_unsigned_swap_intent,
)


FIXTURE = Path(__file__).parent / "fixtures" / "unsigned_swap_protocol_cases.json"


class UnsignedSwapProtocolTests(unittest.TestCase):
    def test_real_calldata_binding_and_nested_deadline_boundaries(self):
        cases = json.loads(FIXTURE.read_text(encoding="utf-8"))
        self.assertEqual(len(cases), 2)
        protocols = ("kyber-metaaggregation-v2", "hydrex-multirouter")
        fields = ("token_in", "token_out", "amount_in", "recipient", "minimum_out")
        required = {
            "protocol", "spender", *fields, "deadlines", "earliest_known_deadline",
            "fees", "actions", "opaque_payloads", "unsupported_actions", "calldata_hash",
        }
        original_cases = copy.deepcopy(cases)

        for case, protocol in zip(cases, protocols):
            with self.subTest(protocol=protocol):
                self.assertEqual(
                    set(case),
                    {"transaction", "chain_id", "expected", "source_history_sha256"},
                )
                self.assertEqual(set(case["transaction"]), {"to", "data", "value"})
                self.assertEqual(set(case["expected"]), set(fields))
                self.assertRegex(case["source_history_sha256"], r"^[0-9a-f]{64}$")
                transaction, expected = case["transaction"], case["expected"]
                decoded = decode_unsigned_swap(transaction, chain_id=case["chain_id"])
                self.assertTrue(required.issubset(decoded))
                self.assertEqual(decoded["protocol"], protocol)
                self.assertNotIn("calldata_binding_verified", decoded)
                self.assertRegex(decoded["spender"], r"^0x[0-9a-fA-F]{40}$")
                self.assertRegex(decoded["calldata_hash"], r"^0x[0-9a-fA-F]{64}$")
                for field in fields:
                    actual = decoded[field]
                    if field in ("amount_in", "minimum_out"):
                        self.assertIs(type(actual), int)
                        self.assertEqual(actual, expected[field])
                    else:
                        self.assertEqual(actual.lower(), expected[field].lower())
                self.assertIsInstance(decoded["deadlines"], list)
                for deadline in decoded["deadlines"]:
                    self.assertIsInstance(deadline["kind"], str)
                    self.assertTrue(deadline["kind"])
                    self.assertIs(type(deadline["timestamp"]), int)

                bound = verify_unsigned_swap_intent(
                    transaction, expected, chain_id=case["chain_id"],
                )
                self.assertIs(bound["calldata_binding_verified"], True)
                self.assertEqual(bound["calldata_hash"], decoded["calldata_hash"])
                for field in fields:
                    self.assertEqual(bound[field], decoded[field])
                for missing in ("amount_in", "minimum_out"):
                    incomplete = {key: value for key, value in expected.items() if key != missing}
                    with self.assertRaises(ValueError):
                        verify_unsigned_swap_intent(transaction, incomplete, chain_id=case["chain_id"])

                # These expectations contain no calldata hash or provider verdict.
                # Each mismatch must therefore be rejected using decoded intent.
                for field in fields:
                    wrong = dict(expected)
                    wrong[field] = (
                        expected[field] + 1
                        if field in ("amount_in", "minimum_out")
                        else "0x0000000000000000000000000000000000000001"
                    )
                    with self.subTest(mismatched_field=field):
                        with self.assertRaises(UnsignedSwapMismatch):
                            verify_unsigned_swap_intent(
                                transaction, wrong, chain_id=case["chain_id"],
                            )

                unknown = dict(transaction)
                unknown["data"] = "0xdeadbeef" + transaction["data"][10:]
                with self.assertRaises(UnsupportedUnsignedSwap):
                    decode_unsigned_swap(unknown, chain_id=case["chain_id"])
                with self.assertRaises(ValueError):
                    decode_unsigned_swap(dict(transaction, chainId=8453), chain_id=1)

        kyber = cases[0]
        decoded_kyber = decode_unsigned_swap(kyber["transaction"], chain_id=8453)
        self.assertTrue(decoded_kyber["opaque_payloads"])
        self.assertIsNone(decoded_kyber["earliest_known_deadline"])
        quote_deadline = 1793171895
        with_quote = decode_unsigned_swap(
            kyber["transaction"], chain_id=8453, quote_deadline=quote_deadline,
        )
        self.assertEqual(with_quote["earliest_known_deadline"], quote_deadline)
        self.assertIn(quote_deadline, [d["timestamp"] for d in with_quote["deadlines"]])

        hydrex = cases[1]
        raw = bytes.fromhex(hydrex["transaction"]["data"][2:])

        def word(offset):
            return int.from_bytes(raw[offset:offset + 32], "big")

        # Locate the first SwapData tuple through its ABI array offsets, then
        # alter only its recipient word. The resulting call remains ABI-valid.
        array_start = 4 + word(4)
        self.assertEqual(word(array_start), 1)
        array_elements = array_start + 32
        swap_start = array_elements + word(array_elements)
        recipient_offset = swap_start + 6 * 32
        self.assertEqual(
            "0x" + raw[recipient_offset + 12:recipient_offset + 32].hex(),
            hydrex["expected"]["recipient"],
        )
        wrong_recipient = "0x0000000000000000000000000000000000000001"
        changed = bytearray(raw)
        changed[recipient_offset:recipient_offset + 32] = bytes.fromhex(
            wrong_recipient[2:].rjust(64, "0"),
        )
        wrong_transaction = dict(hydrex["transaction"], data="0x" + changed.hex())
        wrong_decoded = decode_unsigned_swap(wrong_transaction, chain_id=8453)
        self.assertEqual(wrong_decoded["recipient"].lower(), wrong_recipient)
        with self.assertRaises(UnsignedSwapMismatch):
            verify_unsigned_swap_intent(
                wrong_transaction, hydrex["expected"], chain_id=8453,
            )

        outer_deadline = word(4 + 32)
        self.assertEqual(outer_deadline, 1793172998)
        transfer_from_selector = bytes.fromhex("c1fb425e")
        self.assertEqual(raw.count(transfer_from_selector), 1)
        permit_deadline_offset = raw.index(transfer_from_selector) + 4 + 4 * 32
        original_permit_deadline = word(permit_deadline_offset)
        self.assertEqual(original_permit_deadline, 1793172098)
        decoded_hydrex = decode_unsigned_swap(hydrex["transaction"], chain_id=8453)
        self.assertEqual(
            decoded_hydrex["earliest_known_deadline"], original_permit_deadline,
        )
        self.assertIn(
            outer_deadline, [d["timestamp"] for d in decoded_hydrex["deadlines"]],
        )

        # The original nested permit is already earlier than the outer deadline.
        # Replacing it with outer-60 still proves that the nested limit is used
        # without passing a quote_deadline to supply the answer.
        nested_deadline = outer_deadline - 60
        changed = bytearray(raw)
        changed[permit_deadline_offset:permit_deadline_offset + 32] = (
            nested_deadline.to_bytes(32, "big")
        )
        shorter_transaction = dict(hydrex["transaction"], data="0x" + changed.hex())
        with_nested = decode_unsigned_swap(shorter_transaction, chain_id=8453)
        self.assertEqual(with_nested["earliest_known_deadline"], nested_deadline)
        self.assertIn(nested_deadline, [d["timestamp"] for d in with_nested["deadlines"]])
        self.assertEqual(cases, original_cases)
