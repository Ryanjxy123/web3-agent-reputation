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


def _read_chain_observation(root: Path, path: str, permitted: dict[str, str]) -> object:
    observation = _read_json(root, path, permitted)
    if not isinstance(observation, dict):
        raise ValueError('Chain RPC observation must be an object')
    request_json = observation.get('request_json')
    if request_json is None:
        return None
    request = json.loads(request_json)
    methods = {'eth_getTransactionByHash', 'eth_getTransactionReceipt', 'eth_getBlockByNumber'}
    if not isinstance(request, dict) or request.get('method') not in methods:
        return None
    if (request.get('jsonrpc') != '2.0' or observation.get('method') != 'POST'
        or observation.get('http_status') != 200 or observation.get('body_complete') is not True
        or observation.get('error_kind') is not None):
        raise ValueError('Chain RPC observation is not a complete successful original')
    name = observation.get('response_file')
    if (not isinstance(name, str) or name in ('', '.', '..') or '/' in name or '\\' in name
        or Path(name).name != name):
        raise ValueError('Chain RPC response must be a sibling basename')
    response_path = (Path(path).parent / name).as_posix()
    if permitted.get(response_path) != observation.get('response_sha256') or response_path not in permitted:
        raise ValueError('Chain RPC response SHA256 differs from the permitted source')
    response = _read_json(root, response_path, permitted)
    if (not isinstance(response, dict) or response.get('jsonrpc') != '2.0'
        or response.get('id') != request.get('id') or response.get('error') is not None):
        raise ValueError('Chain RPC response differs from its successful request')
    value = response.get('result')
    if value is None:
        return None
    params = request.get('params')
    if not isinstance(value, dict) or not isinstance(params, list):
        raise ValueError('Chain RPC result or parameters have an invalid shape')
    method = request['method']
    if method in {'eth_getTransactionByHash', 'eth_getTransactionReceipt'}:
        field = 'hash' if method == 'eth_getTransactionByHash' else 'transactionHash'
        actual = value.get(field)
        if (len(params) != 1 or not isinstance(params[0], str) or not isinstance(actual, str)
            or actual.lower() != params[0].lower()):
            raise ValueError('Chain RPC transaction result differs from its requested hash')
    elif (len(params) != 2 or type(params[1]) is not bool or not isinstance(params[0], str)
          or (params[0].startswith('0x') and int(value['number'], 16) != int(params[0], 16))):
        raise ValueError('Chain RPC block result differs from its requested block')
    return value


def _unsigned_execution_transactions(root: Path, permitted: dict[str, str]) -> dict[str, str | None]:
    origins = [name for name in permitted if Path(name).name == 'unsigned-swap-report-origin.json']
    if not origins:
        return {}
    if len(origins) != 1:
        raise ValueError('No unique unsigned swap chain-view origin')
    origin = _read_json(root, origins[0], permitted)
    source = _read_json(root, origin['source'], permitted)
    transactions = {}
    for task in source.get('tasks', []):
        if task.get('retained_source'):
            continue  # Retained source pointers keep their original body-path behavior.
        key = task['task_key']
        if key in transactions:
            raise ValueError('Duplicate unsigned campaign task in chain-view source')
        execution = task.get('execution')
        tx_hash = execution.get('transaction_hash') if execution else None
        if tx_hash is not None and (not isinstance(tx_hash, str) or not re.fullmatch(r'0x[0-9a-fA-F]{64}', tx_hash)):
            raise ValueError('Invalid unsigned campaign execution transaction hash')
        transactions[key] = tx_hash.lower() if tx_hash else None
    return transactions


def _describe_unsigned_swap(transaction, receipt, action, *, batch_call=None):
    """Explain the actual asset movements of a previously source-verified route."""
    from reputation_core.chain_view import _asset, _transfers
    from reputation_platform.unsigned_swap_protocol import decode_unsigned_swap, UnsupportedUnsignedSwap

    chain = int(transaction['chainId'], 16)
    sender = transaction['from'].lower()
    calls = ([batch_call] if batch_call is not None else decode_batch(transaction['input']) if sender == transaction['to'].lower()
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
        'method': ('executeBatch → ' if batch_call is None and sender == transaction['to'].lower() else '') + methods[route['protocol']],
        'summary': f"买方钱包执行服务生成的兑换方案，实际支付 {_asset(chain, route['token_in'], paid)}，"
                   f"收款账户 {route['recipient']} 实收 {_asset(chain, route['token_out'], received)}；"
                   f"方案最低到账为 {_asset(chain, route['token_out'], route['minimum_out'])}。"})


def _call_methods(root: Path, evidence: list[str], permitted: dict[str, str]) -> dict[str, tuple[str, bool]]:
    """Names describe observed calldata, never an Agent's internal tool log."""
    methods = {}
    signatures = [('approve(address,uint256)', False), ('balanceOf(address)', True),
                  ('allowance(address,address)', True),
                  ('approve(address,address,uint160,uint48)', False),
                  ('allowance(address,address,address)', True),
                  ('execute(bytes,bytes[],uint256)', False), ('execute(bytes,bytes[])', False),
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
    if len(payload) != len(kinds) * 64 or any(kind not in ('address', 'uint256', 'uint24', 'uint48', 'uint160') for kind in kinds):
        return ''
    values = []
    for index, kind in enumerate(kinds):
        word = payload[index * 64:(index + 1) * 64]
        value = '0x' + word[-40:] if kind == 'address' else str(int(word, 16))
        values.append(f'参数{index + 1}（{kind}）={value}')
    return '；'.join(values) + '（数量均为原始整数单位）。'


def _describe_atomic_swap(transaction, receipt, action):
    from reputation_core.chain_view import _asset, _transfers
    from reputation_platform.atomic_swap_protocol import normalize_atomic_swap
    from reputation_platform.atomic_swap_report import atomic_evidence_calls

    if int(receipt['status'], 16) != 1:
        return action
    calls = decode_batch(transaction['input'])
    if len(calls) != 16:
        raise ValueError('Atomic report transaction is not the complete sixteen-call batch')
    provider = {'chain_id': int(transaction['chainId'], 16), 'calls': [
        {'to': row['target'], 'data': row['data'], 'value': row['value']} for row in calls[3:10]]}
    route = normalize_atomic_swap(provider)
    if calls != atomic_evidence_calls(provider) or transaction['from'].lower() != route['required_executor']:
        raise ValueError('Atomic report transaction differs from its evidence envelope')
    sender, recipient = transaction['from'].lower(), route['recipient']
    transfers = _transfers(receipt)
    paid = sum(amount * ((source == sender) - (target == sender))
               for token, source, target, amount in transfers if token == route['token_in'])
    received = sum(amount * ((target == recipient) - (source == recipient))
                   for token, source, target, amount in transfers if token == route['token_out'])
    if paid != route['amount_in'] or received < route['minimum_out']:
        raise ValueError('Published atomic swap transfers contradict task constraints')
    chain = route['chain_id']
    return action.model_copy(update={'action': 'swap', 'title': '兑换资产',
        'method': 'executeBatch → execute(bytes,bytes[],uint256)',
        'summary': f"买方执行完整原子兑换，净支付 {_asset(chain, route['token_in'], paid)}，"
                   f"收款账户 {recipient} 净收到 {_asset(chain, route['token_out'], received)}；"
                   f"方案最低到账 {_asset(chain, route['token_out'], route['minimum_out'])}。余额与授权终态见任务证据。"})


def _expand_task_calls(root: Path, action: ChainAction, transaction: dict, evidence: list[str], permitted: dict[str, str], *, receipt: dict | None = None, atomic_action: ChainAction | None = None) -> list[ChainAction]:
    try:
        calls = decode_batch(transaction['input'])
    except (ValueError, KeyError, TypeError):
        return [action]
    methods = _call_methods(root, evidence, permitted)
    result = []
    for index, call in enumerate(calls):
        selector = call['data'][:10].lower()
        method, read_only = methods.get(selector, (selector, False))
        operation = action.model_copy(update={
            'action': 'contract_read' if read_only else 'contract_call',
            'title': ('合约查询' if read_only else '合约调用') + ' · ' + method.split('(')[0],
            'target': call['target'].lower(), 'method': method,
            'summary': f"同一笔 executeBatch 交易内第 {index + 1}/{len(calls)} 项调用；value={call['value']} wei。"
                       + _argument_summary(method, call['data'])
                       + ('这是同笔合约读取，不是一笔独立交易。' if read_only else ''),
        })
        if atomic_action is not None and index == 7:
            operation = atomic_action.model_copy(update={'target': call['target'].lower(), 'method': 'execute(bytes,bytes[],uint256)'})
        elif receipt is not None:
            operation = _describe_unsigned_swap(transaction, receipt, operation, batch_call=call)
        result.append(operation)
    return result


def _build_cow_chain_evidence(
    root: Path, report: EvaluationReport, permitted: dict[str, str], task_key: str | None,
) -> ReportChainEvidence:
    """Describe fulfilled order UIDs using the existing deterministic CoW reader.

    A solver transaction may settle several UIDs. Its sender remains the chain
    executor, while each action describes only its independently bound order.
    """
    from reputation_core.admission import Verdict
    from reputation_core.chain_view import _asset
    from reputation_platform import cow_swap_report as cow
    from reputation_platform.cow_swap_protocol import order_uid_key
    from reputation_platform.shared_report import verify_shared_report_sources
    from reputation_platform.swap_report import SwapEvidence, _lookup

    verify_shared_report_sources(root, report, permitted)
    evidence = SwapEvidence(root, permitted)
    origin = evidence.json(next(name for name in permitted if Path(name).name == cow.ORIGIN))
    source = evidence.json(origin['source'])
    plan, clocks, _ = cow._plan(evidence, source)
    items = {item['task_key']: item for item in source['tasks']}
    samples = {item.sample.task_key: item.sample for item in report.samples}
    actions, seen, incomplete = [], set(), 0
    selected = [task for task in plan['tasks'] if task_key is None or task['task_key'] == task_key]
    for task in selected:
        item = items.get(task['task_key'])
        if not task['planned_actual_execution'] or not item or not item.get('execution'):
            incomplete += 1
            continue
        rows = cow._http_task(evidence, plan, task, item, clocks[task['task_key']])
        metrics, facts = cow._metrics(evidence, plan, task, item, rows, clocks[task['task_key']])
        verdict, _, observed = metrics['onchain-fulfillment']
        if verdict != Verdict.PASS or not facts:
            incomplete += 1
            continue
        uid_key = order_uid_key(facts['chain_id'], facts['uid'])
        if uid_key in seen:
            continue
        seen.add(uid_key)
        records = cow._rpc(evidence, item['execution']['rpc_observations'])
        transaction = _lookup(records, 'eth_getTransactionByHash', [observed['transaction_hash']])
        receipt = _lookup(records, 'eth_getTransactionReceipt', [observed['transaction_hash']])
        block = _lookup(records, 'eth_getBlockByNumber', [receipt['blockNumber'], False])
        sample = samples[task['task_key']]
        action = describe_chain_action(transaction, receipt, block, sample_id=sample.sample_id,
                                       verdict=verdict, evidence=list(sample.evidence))
        order, chain = facts['order'], facts['chain_id']
        net = '；'.join(
            ('+' if int(amount) >= 0 else '-') + _asset(chain, token, abs(int(amount)))
            for token, amount in sorted(observed['owner_transaction_net_raw'].items())
        )
        actions.append(action.model_copy(update={
            'action': 'swap', 'title': 'CoW 订单兑换', 'method': 'CoW Settlement Trade(bytes orderUid)',
            'summary': (
                f"订单 UID {facts['uid']} 的 canonical Settlement Trade 记录卖出 "
                f"{_asset(chain, order['sellToken'], int(observed['input_debit_raw']))}，买入 "
                f"{_asset(chain, order['buyToken'], int(observed['output_credit_raw']))}；"
                f"订单 owner {facts['owner']} 与收款账户 {facts['recipient']} 为同一本人账户，"
                f"签入最低到账为 {_asset(chain, order['buyToken'], int(facts['minimum_buy_raw']))}。"
                f"整笔 settlement 中本人净资产变化为 {net}；"
                f"交易发送者为 solver {action.executor}。"
                f"履约时间 {observed['timestamp']} 不晚于订单期限 {facts['valid_to']}；"
                f"已观察 {observed['confirmation_distance']} 块距离（要求至少 64 块），"
                f"履约块的 VaultRelayer 剩余授权为 {observed['remaining_allowance_raw']}。"
            ),
        }))
        if task_key is None and len(actions) == 3:
            break
    limitations = [
        '该视图沿用报告的 CoW 来源重放结果，不新增评分；服务登记身份与链上履约归属分别核验。',
        'public_registry 表示已核公开服务登记；仅凭 MCP 登记不能宣称 ERC-8004 chain_registration。',
        '报价、build、validate 或缺少完整 UID/API/回执/净资产/授权/确认原件的任务，不显示为已完成兑换。',
        '同一 settlement 可包含多个 UID；每项对应一个订单，整笔交易的本人净变动不可再次相加。',
    ]
    if actions:
        return ReportChainEvidence(actions=actions,
            summary=f"展示 {len(actions)} 个经独立原件核验的 CoW 订单 UID 履约。"
                    + ('其余未完整核验的任务保留原报告状态。' if incomplete else ''),
            limitations=limitations)
    return ReportChainEvidence(actions=[],
        summary='所选范围尚无完整核验的 CoW UID 链上履约；报价、build、validate 不表示已成交。',
        limitations=limitations)


def build_report_chain_evidence(
    root: Path, report: EvaluationReport, permitted: dict[str, str], task_key: str | None = None,
) -> ReportChainEvidence:
    """Explain retained operations; task selection expands all its cited transactions.

    Without task_key, retain the first-sample, three-operation summary. Bound RPC
    observations or legacy body paths supply transaction/block hash pairing.
    Neither background summaries nor Agent names are trusted.
    Integrity failures propagate to the existing report/attachment boundary.
    """
    if any(Path(name).name == 'cow-swap-report-origin.json' for name in permitted):
        return _build_cow_chain_evidence(root, report, permitted, task_key)
    execution_transactions = _unsigned_execution_transactions(root, permitted)
    collected, transaction_hashes = [], set()
    for explanation in report.samples:
        if task_key is not None and explanation.sample.task_key != task_key:
            continue
        if explanation.sample.purpose != MeasurementPurpose.BEHAVIORAL:
            continue
        key = explanation.sample.task_key
        if key in execution_transactions and execution_transactions[key] is None:
            continue
        transactions, receipts, blocks = {}, {}, {}
        for path in dict.fromkeys(explanation.sample.evidence):
            if path.endswith(".observation.json"):
                value = _read_chain_observation(root, path, permitted)
            elif path.endswith((".response.bin", ".json")) and _RPC_SOURCE.search(path):
                value = _read_source(root, path, permitted)
            else:
                continue
            if not isinstance(value, dict):
                continue
            if {"hash", "from", "to", "input", "chainId", "blockHash"} <= value.keys():
                transactions[value["hash"].lower()] = (value, path)
            elif {"transactionHash", "logs", "status", "blockHash"} <= value.keys():
                receipts[value["transactionHash"].lower()] = (value, path)
            elif {"hash", "number", "transactions", "timestamp"} <= value.keys():
                blocks[value["hash"].lower()] = (value, path)
        complete = [(transaction, path) for tx_hash, (transaction, path) in transactions.items()
                    if tx_hash in receipts and transaction["blockHash"].lower() in blocks
                    and (key not in execution_transactions or tx_hash == execution_transactions[key])]
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
            unsigned_swap = any(Path(name).name == 'unsigned-swap-report-origin.json' for name in permitted)
            atomic_swap = any(Path(name).name == 'atomic-swap-report-origin.json' for name in permitted)
            if unsigned_swap:
                action = _describe_unsigned_swap(transaction, receipt, action)
            if atomic_swap:
                action = _describe_atomic_swap(transaction, receipt, action)
            actions.extend(_expand_task_calls(root, action, transaction, explanation.sample.evidence, permitted,
                                             receipt=receipt if unsigned_swap else None,
                                             atomic_action=action if atomic_swap and action.action == 'swap' else None)
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
