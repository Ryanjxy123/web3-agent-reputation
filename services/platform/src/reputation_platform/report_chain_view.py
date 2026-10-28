"""Build a small chain evidence view from hash-bound, published sample sources."""

import hashlib
import json
from pathlib import Path
import re

from reputation_core.admission import MeasurementPurpose
from reputation_core.chain_view import (
    ReportChainEvidence, describe_chain_action, has_chain_action_description,
)
from reputation_core.reporting import EvaluationReport


_RPC_SOURCE = re.compile(r"(?:^|[-_/])(transaction|receipt|block)(?:[-_.]|$)")


def _read_source(root: Path, path: str, permitted: dict[str, str]) -> object:
    expected = permitted.get(path)
    resolved = (root / path).resolve()
    if expected is None or not resolved.is_relative_to(root.resolve()):
        raise ValueError("Chain evidence is outside the report's permitted sources")
    raw = resolved.read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected:
        raise ValueError("Chain evidence SHA256 does not match the published source")
    value = json.loads(raw)
    return value.get("result") if isinstance(value, dict) else None


def _describe_unsigned_swap(transaction, receipt, action):
    """Explain the actual asset movements of a previously source-verified route."""
    from reputation_core.chain_view import _asset, _transfers
    from reputation_core.swap import decode_batch
    from reputation_platform.unsigned_swap_protocol import decode_unsigned_swap, UnsupportedUnsignedSwap

    chain = int(transaction['chainId'], 16)
    sender = transaction['from'].lower()
    calls = (decode_batch(transaction['input']) if sender == transaction['to'].lower()
             else [{'target': transaction['to'], 'data': transaction['input'], 'value': transaction['value']}])
    routes = []
    for call in calls:
        try:
            routes.append(decode_unsigned_swap({'to': call['target'], 'data': call['data'], 'value': call['value']}, chain_id=chain))
        except UnsupportedUnsignedSwap:
            continue
    if len(routes) != 1:
        return action
    route = routes[0]
    transfers = _transfers(receipt)
    paid = sum(amount for token, source, _, amount in transfers if token == route['token_in'] and source == sender)
    received = sum(amount for token, _, target, amount in transfers if token == route['token_out'] and target == route['recipient'])
    if paid != route['amount_in'] or received < route['minimum_out']:
        raise ValueError('Published swap transfers contradict the decoded task constraints')
    methods = {'hydrex-multirouter': 'executeSwaps(...)', '0x-allowanceholder-settler': 'exec(...)',
               'kyber-metaaggregation-v2': 'swap(...)'}
    return action.model_copy(update={'action': 'swap', 'title': '兑换资产',
        'method': ('executeBatch → ' if sender == transaction['to'].lower() else '') + methods[route['protocol']],
        'summary': f"买方钱包执行服务生成的兑换方案，实际支付 {_asset(chain, route['token_in'], paid)}，"
                   f"收款账户 {route['recipient']} 实收 {_asset(chain, route['token_out'], received)}；"
                   f"方案最低到账为 {_asset(chain, route['token_out'], route['minimum_out'])}。"})


def build_report_chain_evidence(
    root: Path, report: EvaluationReport, permitted: dict[str, str],
) -> ReportChainEvidence:
    """Explain up to three operations of the first suitable behavioral sample.

    Filenames limit I/O; the actual JSON structure and transaction/block hashes
    determine pairing. Neither background summaries nor Agent names are trusted.
    Integrity failures propagate to the existing report/attachment boundary.
    """
    for explanation in report.samples:
        if explanation.sample.purpose != MeasurementPurpose.BEHAVIORAL:
            continue
        transactions, receipts, blocks = {}, {}, {}
        for path in dict.fromkeys(explanation.sample.evidence):
            if not path.endswith((".response.bin", ".json")) or not _RPC_SOURCE.search(path):
                continue
            if path.endswith(".observation.json"):
                continue
            value = _read_source(root, path, permitted)
            if not isinstance(value, dict):
                continue
            if {"hash", "from", "to", "input", "chainId", "blockHash"} <= value.keys():
                transactions[value["hash"].lower()] = (value, path)
            elif {"transactionHash", "logs", "status", "blockHash"} <= value.keys():
                receipts[value["transactionHash"].lower()] = (value, path)
            elif {"hash", "number", "transactions", "timestamp"} <= value.keys():
                blocks[value["hash"].lower()] = (value, path)
        complete = [(transaction, path) for tx_hash, (transaction, path) in transactions.items()
                    if tx_hash in receipts and transaction["blockHash"].lower() in blocks]
        described = [item for item in complete if has_chain_action_description(item[0])]
        selected = sorted(described or complete, key=lambda item: (
            int(item[0]["blockNumber"], 16), int(item[0]["transactionIndex"], 16),
        ))[:3]
        if not selected:
            continue
        actions = []
        for transaction, path in selected:
            receipt, receipt_path = receipts[transaction["hash"].lower()]
            block, block_path = blocks[transaction["blockHash"].lower()]
            action = describe_chain_action(
                transaction, receipt, block, sample_id=explanation.sample.sample_id,
                verdict=explanation.sample.verdict, evidence=[path, receipt_path, block_path],
            )
            if any(Path(name).name == 'unsigned-swap-report-origin.json' for name in permitted):
                action = _describe_unsigned_swap(transaction, receipt, action)
            actions.append(action)
        return ReportChainEvidence(
            actions=actions,
            summary=f"从「{explanation.title}」已引用的原始交易、收据和区块中，展开 {len(actions)} 笔真实链上操作。",
            limitations=[
                "沿用已发布样本的整体核验结论；此视图只解读已核对SHA256的原件，不新增评分或重新评价Agent。",
                "执行地址来自实际交易from；Agent归属及历史授权沿用原样本的核验范围，不能由收款钱包或当前权限推定。",
                "资产转移和合约事件不代表策略最优、未来收益或当前服务在线；完整任务约束与确认检查见对应样本。",
            ],
        )
    return ReportChainEvidence(
        actions=[], summary="这份报告尚无可展开为交易、收据、区块三者绑定的链上操作原件。",
        limitations=["现有研究交付或查询结果不能据此解释为Agent执行了资产交易。"],
    )
