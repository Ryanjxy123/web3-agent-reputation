"""Build a small chain evidence view from hash-bound, published sample sources."""

import hashlib
import json
from pathlib import Path
import re

from reputation_core.admission import MeasurementPurpose
from reputation_core.chain_view import (
    ChainAction, ReportChainEvidence, describe_chain_action, has_chain_action_description,
)
from reputation_core.reporting import EvaluationReport
from reputation_core.swap import decode_batch
from eth_hash.auto import keccak


_RPC_SOURCE = re.compile(r"(?:^|[-_/])(transaction|receipt|block)(?:[-_.]|$)")


def _read_json(root: Path, path: str, permitted: dict[str, str]) -> object:
    expected = permitted.get(path)
    resolved = (root / path).resolve()
    if expected is None or not resolved.is_relative_to(root.resolve()):
        raise ValueError("Chain evidence is outside the report's permitted sources")
    raw = resolved.read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected:
        raise ValueError("Chain evidence SHA256 does not match the published source")
    return json.loads(raw)


def _read_source(root: Path, path: str, permitted: dict[str, str]) -> object:
    value = _read_json(root, path, permitted)
    return value.get("result") if isinstance(value, dict) else None


def _call_methods(root: Path, evidence: list[str], permitted: dict[str, str]) -> dict[str, tuple[str, bool]]:
    """Names describe observed calldata, never an Agent's internal tool log."""
    methods = {}
    signatures = [('approve(address,uint256)', False), ('balanceOf(address)', True),
                  ('allowance(address,address)', True),
                  ('exactInputSingle((address,address,uint24,address,uint256,uint256,uint160))', False)]
    for path in evidence:
        if not path.endswith('/contract-abi.json'):
            continue
        abi = _read_json(root, path, permitted)
        if not isinstance(abi, list):
            continue
        for entry in abi:
            if not isinstance(entry, dict) or entry.get('type') != 'function':
                continue
            signature = entry['name'] + '(' + ','.join(_abi_type(item) for item in entry['inputs']) + ')'
            signatures.append((signature, entry.get('stateMutability') in ('view', 'pure')))
    for signature, read_only in signatures:
        methods['0x' + keccak(signature.encode()).hex()[:8]] = (signature, read_only)
    return methods


def _abi_type(item: dict) -> str:
    kind = item['type']
    if kind.startswith('tuple'):
        return '(' + ','.join(_abi_type(part) for part in item['components']) + ')' + kind[5:]
    return kind


def _argument_summary(method: str, data: str) -> str:
    """Only flat ABI words are formatted; complex inputs retain their source reference."""
    if method.count('(') != 1:
        return ''
    kinds = method.split('(', 1)[1][:-1].split(',')
    payload = data[10:]
    if len(payload) != len(kinds) * 64 or any(kind not in ('address', 'uint256', 'uint24', 'uint160') for kind in kinds):
        return ''
    values = []
    for index, kind in enumerate(kinds):
        word = payload[index * 64:(index + 1) * 64]
        value = '0x' + word[-40:] if kind == 'address' else str(int(word, 16))
        values.append(f'参数{index + 1}（{kind}）={value}')
    return '；'.join(values) + '（数量均为原始整数单位）。'


def _expand_task_calls(root: Path, action: ChainAction, transaction: dict, evidence: list[str], permitted: dict[str, str]) -> list[ChainAction]:
    try:
        calls = decode_batch(transaction['input'])
    except (ValueError, KeyError, TypeError):
        return [action]
    methods = _call_methods(root, evidence, permitted)
    result = []
    for index, call in enumerate(calls):
        selector = call['data'][:10].lower()
        method, read_only = methods.get(selector, (selector, False))
        result.append(action.model_copy(update={
            'action': 'contract_read' if read_only else 'contract_call',
            'title': ('合约查询' if read_only else '合约调用') + ' · ' + method.split('(')[0],
            'target': call['target'].lower(), 'method': method,
            'summary': f"同一笔 executeBatch 交易内第 {index + 1}/{len(calls)} 项调用；value={call['value']} wei。"
                       + _argument_summary(method, call['data'])
                       + ('这是同笔合约读取，不是一笔独立交易。' if read_only else ''),
        }))
    return result


def build_report_chain_evidence(
    root: Path, report: EvaluationReport, permitted: dict[str, str], task_key: str | None = None,
) -> ReportChainEvidence:
    """Explain retained operations; task selection expands all its cited transactions.

    Without task_key, retain the first-sample, three-operation summary. Filenames
    limit I/O; actual JSON structure and transaction/block hashes determine pairing.
    Neither background summaries nor Agent names are trusted.
    Integrity failures propagate to the existing report/attachment boundary.
    """
    collected, transaction_hashes = [], set()
    for explanation in report.samples:
        if task_key is not None and explanation.sample.task_key != task_key:
            continue
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
        selected = sorted(complete if task_key is not None else described or complete, key=lambda item: (
            int(item[0]["blockNumber"], 16), int(item[0]["transactionIndex"], 16),
        ))
        if task_key is None:
            selected = selected[:3]
        if not selected:
            continue
        actions = []
        for transaction, path in selected:
            if task_key is not None and transaction['hash'].lower() in transaction_hashes:
                continue
            receipt, receipt_path = receipts[transaction["hash"].lower()]
            block, block_path = blocks[transaction["blockHash"].lower()]
            action = describe_chain_action(
                transaction, receipt, block, sample_id=explanation.sample.sample_id,
                verdict=explanation.sample.verdict, evidence=[path, receipt_path, block_path],
            )
            actions.extend(_expand_task_calls(root, action, transaction, explanation.sample.evidence, permitted)
                           if task_key is not None else [action])
            transaction_hashes.add(transaction['hash'].lower())
        if task_key is not None:
            collected.extend(actions)
            continue
        return ReportChainEvidence(
            actions=actions,
            summary=f"从「{explanation.title}」已引用的原始交易、收据和区块中，展开 {len(selected)} 笔交易、{len(actions)} 项操作。",
            limitations=[
                "沿用已发布样本的整体核验结论；此视图只解读已核对SHA256的原件，不新增评分或重新评价Agent。",
                "执行地址来自实际交易from；Agent归属及历史授权沿用原样本的核验范围，不能由收款钱包或当前权限推定。",
                "资产转移和合约事件不代表策略最优、未来收益或当前服务在线；完整任务约束与确认检查见对应样本。",
            ],
        )
    if collected:
        return ReportChainEvidence(
            actions=collected,
            summary=f"从本报告任务已引用且校验摘要的交易、收据和区块中，展开 {len(transaction_hashes)} 笔交易、{len(collected)} 项操作。",
            limitations=[
                "执行账户与合约方法来自保留交易；同笔内部合约查询与独立交易分别标明。",
                "操作沿用样本结论，不单独产生新的评分；原始调用次序不代表Agent内部工具或推理日志。",
            ],
        )
    return ReportChainEvidence(
        actions=[], summary="这份报告尚无可展开为交易、收据、区块三者绑定的链上操作原件。",
        limitations=["现有研究交付或查询结果不能据此解释为Agent执行了资产交易。"],
    )
