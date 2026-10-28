"""One retained-evidence view check and its integrity failure boundary."""

from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from reputation_core.admission import MeasurementPurpose, Verdict
from reputation_core.chain_view import ChainAction
from reputation_core.behavior import TRANSFER
from reputation_core.prediction_chain import calldata
from reputation_core.reporting import EvaluationReport, SampleExplanation
from reputation_core.scoring import ScoredSample
from reputation_core.swap import encode_batch
from reputation_platform.report_chain_view import _describe_unsigned_swap, _expand_task_calls, build_report_chain_evidence


FIXTURES = Path(__file__).parent / "fixtures/behavior-98"


class ReportChainViewTests(unittest.TestCase):
    def test_unsigned_batch_keeps_swap_amounts_and_rejects_mismatched_transfers(self) -> None:
        case = json.loads((FIXTURES.parent / 'unsigned_swap_protocol_cases.json').read_bytes())[1]
        expected, unsigned = case['expected'], case['transaction']
        payer = expected['recipient']
        calls = [
            {'target': expected['token_in'], 'value': '0', 'data': calldata('balanceOf(address)', payer)},
            {'target': expected['token_in'], 'value': '0', 'data': calldata('approve(address,uint256)', unsigned['to'], expected['amount_in'])},
            {'target': unsigned['to'], 'value': unsigned['value'], 'data': unsigned['data']},
            {'target': expected['token_in'], 'value': '0', 'data': calldata('approve(address,uint256)', unsigned['to'], 0)},
        ]
        transaction = {'chainId': hex(case['chain_id']), 'from': payer, 'to': payer, 'input': encode_batch(calls), 'value': '0x0'}
        # Synthetic receipt events exercise the view; they are not retained chain evidence.
        def transfer(token, sender, recipient, amount):
            return {'address': token, 'topics': [TRANSFER, '0x' + sender[2:].rjust(64, '0'), '0x' + recipient[2:].rjust(64, '0')],
                    'data': '0x' + format(amount, '064x')}

        receipt = {'logs': [transfer(expected['token_in'], payer, unsigned['to'], expected['amount_in']),
                            transfer(expected['token_out'], unsigned['to'], payer, expected['minimum_out'] + 1)]}
        action = ChainAction(sample_id='synthetic-batch', chain_id=case['chain_id'], action='contract_call', title='Test batch',
                             transaction_hash='0x' + '2' * 64, block_number=10, executor=payer, target=payer,
                             method='executeBatch', summary='Synthetic test only', verdict=Verdict.PASS, evidence=[])
        aggregate = _describe_unsigned_swap(transaction, receipt, action)
        self.assertEqual(aggregate.action, 'swap')
        self.assertIn('executeBatch → executeSwaps', aggregate.method)
        with tempfile.TemporaryDirectory() as directory:
            operations = _expand_task_calls(Path(directory), action, transaction, [], {}, receipt=receipt)
            self.assertEqual(len(operations), len(calls))
            swaps = [item for item in operations if item.action == 'swap']
            self.assertEqual(len(swaps), 1)
            self.assertEqual(swaps[0].transaction_hash, action.transaction_hash)
            self.assertEqual(swaps[0].target, unsigned['to'].lower())
            self.assertEqual(swaps[0].method, 'executeSwaps(...)')
            self.assertIn('实际支付 USDC 0.1', swaps[0].summary)
            self.assertIn('实收 WETH 0.000042202735617549', swaps[0].summary)
            self.assertIn('最低到账为 WETH 0.000042202735617548', swaps[0].summary)
            receipt['logs'][1] = transfer(expected['token_out'], unsigned['to'], payer, expected['minimum_out'] - 1)
            with self.assertRaisesRegex(ValueError, 'contradict'):
                _expand_task_calls(Path(directory), action, transaction, [], {}, receipt=receipt)

    def test_actual_batch_reads_and_writes_share_transaction(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            abi_path = 'contract/contract-abi.json'
            (root / 'contract').mkdir()
            raw = json.dumps([{'type': 'function', 'name': 'getOrder', 'stateMutability': 'view',
                               'inputs': [{'name': 'orderId', 'type': 'uint256'}]}]).encode()
            (root / abi_path).write_bytes(raw)
            target = '0x' + '1' * 40
            calls = [{'target': target, 'value': '0', 'data': calldata('approve(address,uint256)', target, 20000)},
                     {'target': target, 'value': '0', 'data': calldata('getOrder(uint256)', 2)}]
            action = ChainAction(sample_id='sample', chain_id=8453, action='contract_call', title='Task',
                                 transaction_hash='0x' + '2' * 64, block_number=10, executor=target, target=target,
                                 method='executeBatch', summary='Retained', verdict=Verdict.PASS, evidence=['tx', 'receipt', 'block'])
            operations = _expand_task_calls(root, action, {'input': encode_batch(calls)}, [abi_path],
                                            {abi_path: hashlib.sha256(raw).hexdigest()})
            self.assertEqual([item.action for item in operations], ['contract_call', 'contract_read'])
            self.assertEqual([item.transaction_hash for item in operations], [action.transaction_hash] * 2)
            self.assertIn('20000', operations[0].summary)
            self.assertIn('不是一笔独立交易', operations[1].summary)
            with self.assertRaisesRegex(ValueError, 'SHA256'):
                _expand_task_calls(root, action, {'input': encode_batch(calls)}, [abi_path], {abi_path: 'incorrect'})

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
            scoped = build_report_chain_evidence(root, report, permitted, "retained:98")
            self.assertEqual(len(scoped.actions), 3)
            self.assertEqual(len({action.transaction_hash for action in scoped.actions}), 3)
            self.assertEqual(build_report_chain_evidence(root, report, permitted, "other-report-task").actions, [])
            quote = report.model_copy(deep=True)
            quote.samples[0].sample.purpose = MeasurementPurpose.FUNCTIONAL
            self.assertEqual(build_report_chain_evidence(root, quote, permitted, "retained:98").actions, [])
            damaged = root / "history-98-swap-receipt.response.bin"
            original = json.loads(damaged.read_bytes())
            original["result"]["status"] = "0x0"
            damaged.write_text(json.dumps(original), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "SHA256"):
                build_report_chain_evidence(root, report, permitted)


if __name__ == "__main__":
    unittest.main()
