"""Offline, manifest-bound contract lifecycle facts; never an HTTP score or wallet."""
from datetime import datetime, timezone
import hashlib
from pathlib import Path

from eth_hash.auto import keccak

from reputation_core.admission import Verdict
from reputation_core.chain_view import ChainAction
from reputation_core.prediction_chain import calldata
from reputation_core.reporting import ReportFinding, parse_evaluation_report
from reputation_core.swap import (TRANSFER_TOPIC, SWAP_TOPIC, address, decode_batch,
                                  encode_batch, hex_bytes, integer, words)
from reputation_platform.swap_report import SwapEvidence, _lookup
from reputation_platform.shared_report import verify_shared_report_sources

ZERO = '0x' + '0' * 40
EXECUTED = '0x' + keccak(b'SwapExecuted(uint256,address,uint256)').hex()


def _check(value, reason):
    if not value:
        raise ValueError(reason)


def _topic(value):
    return '0x' + address(value)[2:].rjust(64, '0')


def _units(value, decimals):
    whole, tail = divmod(value, 10 ** decimals)
    fraction = f'{tail:0{decimals}d}'.rstrip('0')
    return str(whole) + ('.' + fraction if fraction else '')


class _Reads:
    def __init__(self, evidence, task, protocol):
        self.records = evidence.rpc_records(task['rpc_observations'], set(protocol['rpc_urls']))

    def get(self, method, params):
        value = _lookup(self.records, method, params)
        _check(value is not None, '缺少完整、同参数的独立RPC原件：' + method)
        return value

    def call(self, to, signature, *args, tag):
        return self.get('eth_call', [{'to': to, 'data': calldata(signature, *args)}, tag])

    def number(self, to, signature, *args, tag):
        return integer(self.call(to, signature, *args, tag=tag))


def _transfers(logs, token, sender=None, recipient=None):
    result = []
    for log in logs:
        topics = [value.lower() for value in log.get('topics', [])]
        if address(log['address']) != token or len(topics) != 3 or topics[0] != TRANSFER_TOPIC:
            continue
        if sender is not None and topics[1] != _topic(sender):
            continue
        if recipient is not None and topics[2] != _topic(recipient):
            continue
        result.append(words(log['data'], 1)[0])
    return result


def _balance(reads, token, owner, tag):
    return reads.number(token, 'balanceOf(address)', owner, tag=tag)


def _source_names(evidence, task, common):
    names = set(common) | {task['intent_path'], task['task_path'], task['unsigned_transaction']}
    for name in task['rpc_observations']:
        names.add(name)
        obs = evidence.json(name)
        if obs.get('response_file'):
            names.add((Path(name).parent / obs['response_file']).as_posix())
    return sorted(names)


def _replay_task(evidence, entry, protocol, signatures, plan_path):
    p = protocol
    wallet, contract, token, wrapped = (address(p[key]) for key in ('wallet', 'contract', 'token', 'wrapped_native'))
    plan_raw, intent = evidence.raw(plan_path), evidence.json(entry['intent_path'])
    plan, task, unsigned = evidence.json(plan_path), evidence.json(entry['task_path']), evidence.json(entry['unsigned_transaction'])
    _check(intent['plan_sha256'] == hashlib.sha256(plan_raw).hexdigest(), '意图未绑定原冻结计划字节')
    plan_tasks = plan.get('cases')
    if plan_tasks is None and isinstance(plan.get('task'), dict):
        plan_tasks = [plan['task']]
    _check(isinstance(plan_tasks, list) and task in plan_tasks
           and task['request_id'] == intent['request_id'] == entry['task_key'], '任务不属于原冻结计划')
    _check(all(integer(item['chain_id']) == integer(p['chain_id']) and address(item['buyer']) == wallet
               and address(item['contract']) == contract for item in (plan, intent)), '计划、意图与配置链/角色不符')
    _check(intent['transaction'] == unsigned, '原意图与保留的未签名交易不符')
    reads = _Reads(evidence, entry, p)
    _check(integer(reads.get('eth_chainId', [])) == integer(p['chain_id']), '原RPC链号不符')
    fixed = hex(integer(intent['fixed_block']))
    planning = reads.get('eth_getBlockByNumber', [fixed, False])
    _check(integer(planning['number']) == integer(intent['fixed_block'])
           and planning['hash'].lower() == intent['fixed_block_hash'].lower()
           and integer(planning['timestamp']) == integer(intent['block_timestamp']), '准备区块与原意图不符')
    _check(reads.get('eth_getCode', [wallet, fixed]).lower() == '0xef0100' + address(p['expected_delegate'])[2:],
           '准备时执行账户不属于已约定委托')
    code = reads.get('eth_getCode', [contract, fixed])
    _check(hashlib.sha256(hex_bytes(code)).hexdigest() == p['contract_runtime_hash'], '部署代码与已审协议字节码不符')
    tx_hash = entry['transaction_hash'].lower()
    receipt = reads.get('eth_getTransactionReceipt', [tx_hash])
    height = integer(receipt['blockNumber']); tag, before_tag = hex(height), hex(height - 1)
    block = reads.get('eth_getBlockByNumber', [tag, False])
    tx = reads.get('eth_getTransactionByHash', [tx_hash])
    _check(integer(receipt['status']) == 1 and receipt['transactionHash'].lower() == tx_hash
           and tx['hash'].lower() == tx_hash and integer(block['number']) == height
           and integer(tx['blockNumber']) == height
           and tx['blockHash'].lower() == receipt['blockHash'].lower() == block['hash'].lower()
           and tx_hash in [value.lower() for value in block['transactions']], '交易/回执未位于同一canonical区块')
    for key in ('from', 'to'):
        _check(address(tx[key]) == address(unsigned[key]) == address(receipt[key]) == wallet, '实际调用者/外层目标不符')
    for key in ('chainId', 'nonce', 'value', 'gas', 'maxFeePerGas', 'maxPriorityFeePerGas'):
        _check(integer(tx[key]) == integer(unsigned[key]), '实际签发参数与原意图不符：' + key)
    _check(integer(tx['chainId']) == integer(p['chain_id']) and integer(tx['value']) == 0
           and not tx.get('authorizationList'), '执行链/value或新增委托不在约定范围')
    calls = decode_batch(tx['input'])
    _check(tx['input'].lower() == unsigned['data'].lower() == encode_batch(intent['calls']), '实际内层调用与原意图不符')
    logs = receipt['logs']
    for log in logs:
        _check(log['transactionHash'].lower() == tx_hash and log['blockHash'].lower() == block['hash'].lower()
               and integer(log['blockNumber']) == height and not log.get('removed', False), '事件不属于本交易/区块')
    _check(len({integer(log['logIndex']) for log in logs}) == len(logs), '交易日志索引重复')
    kind, amount = entry['kind'], integer(task['amount_raw'])
    minimum = integer(intent.get('minimum_output_raw', 0))
    _check(amount > 0 and (kind == 'limit_cancel' or minimum > 0), '缺少合法的原任务整数金额/最低到账')
    order_id = integer(intent['predicted_limit_id'] if kind == 'limit_cancel' else intent['predicted_swap_id'])
    method = 'getLimitOrder(uint256)' if kind == 'limit_cancel' else 'getSwap(uint256)'
    stored = words(reads.call(contract, method, order_id, tag=tag), 8)
    _check(stored[:4] == [int(wallet, 16), int(task['token_in'], 16), int(task['token_out'], 16), amount],
           '持久订单归属、资产或输入不符')
    def call(target, signature, *args, value=0):
        _check(signature in signatures, '已审ABI不支持该方法：' + signature)
        return {'target': target, 'value': str(value), 'data': calldata(signature, *args)}
    allowed_reads = [call(contract, method, order_id), call(token, 'balanceOf(address)', wallet),
                     call(token, 'balanceOf(address)', contract), call(token, 'allowance(address,address)', wallet, contract)]
    # ERC20 methods belong to their token ABI rather than the lifecycle ABI.
    body_time = integer(block['timestamp'])
    _check(datetime.fromisoformat(plan['created_at']).timestamp() <= body_time
           and datetime.fromisoformat(intent['checked_at']).timestamp() <= body_time, '意图/计划时间晚于交易')
    if kind == 'native_swap':
        _check(integer(task['route_fee_tier']) == integer(p['fee_tier']) == integer(intent['fee_tier']), '路由费率不符原任务')
        fee_bps = reads.number(contract, 'platformFee()', tag=fixed)
        _check(0 <= fee_bps <= 500 and fee_bps == integer(intent['platform_fee_bps']), '平台费与原约定不符')
        fee, after_fee = amount * fee_bps // 10000, amount - amount * fee_bps // 10000
        _check(address(task['token_in']) == ZERO and address(task['token_out']) == token, '原生输入任务资产不符')
        prefix = [call(contract, 'instantSwap(address,address,uint256,uint256)', ZERO, token, amount, minimum, value=amount)]
        _check(stored[4] == minimum and stored[5] == body_time and stored[6] == 1, '原生兑换未保存为本次Executed任务')
        output = stored[7]
        _check(output >= minimum, '真实到账低于约定最低值')
        pool = address('0x' + f"{reads.number(address(p['factory']), 'getPool(address,address,uint24)', wrapped, token, integer(p['fee_tier']), tag=tag):040x}")
        _check(pool != ZERO and _transfers(logs, token, pool, wallet) == [output]
               and _transfers(logs, token, recipient=wallet) == [output]
               and not _transfers(logs, token, sender=wallet)
               and _transfers(logs, wrapped, address(p['router']), pool) == [after_fee]
               and not _transfers(logs, wrapped, sender=wallet), '实际池/代币转账不符原生任务')
        events = [log for log in logs if address(log['address']) == contract
                  and [value.lower() for value in log['topics']] == [EXECUTED, '0x' + f'{order_id:064x}', _topic(wallet)]]
        _check(len(events) == 1 and words(events[0]['data'], 1) == [output], 'V4执行事件与订单/到账不符')
        pool_events = [log for log in logs if address(log['address']) == pool
                       and [value.lower() for value in log['topics']] == [SWAP_TOPIC, _topic(address(p['router'])), _topic(wallet)]]
        _check(len(pool_events) == 1, '缺少同交易官方池Swap')
        raw = hex_bytes(pool_events[0]['data']); _check(len(raw) == 160, '池Swap ABI不完整')
        deltas = [int.from_bytes(raw[i:i + 32], 'big', signed=True) for i in (0, 32)]
        _check(deltas == [after_fee if asset == wrapped else -output for asset in sorted((wrapped, token))], '池实际输入输出不符')
        decimals = reads.number(token, 'decimals()', tag=tag)
        _check(decimals == integer(p['assets']['token']['decimals']), '原始代币精度与配置不符')
        _check(_balance(reads, token, wallet, tag) - _balance(reads, token, wallet, before_tag) == output,
               '实际代币余额增量不符')
        _check(integer(reads.get('eth_getBalance', [contract, tag])) - integer(reads.get('eth_getBalance', [contract, before_tag])) == fee
               and reads.number(contract, 'fees()', tag=tag) - reads.number(contract, 'fees()', tag=before_tag) == fee,
               '平台实际原生费/计数不符')
        result = {'outcome': 'Executed', 'output_raw': str(output), 'minimum_raw': str(minimum), 'platform_fee_raw': str(fee)}
        title, action = '原生资产即时兑换', 'native_swap'
        native, asset = p['assets']['native'], p['assets']['token']
        summary = (f"使用{_units(amount, integer(native['decimals']))}{native['symbol']}，实际收到"
                   f"{_units(output, decimals)}{asset['symbol']}，最低{_units(minimum, decimals)}{asset['symbol']}；"
                   f"平台费{_units(fee, integer(native['decimals']))}{native['symbol']}已含本金。")
    elif kind in ('scheduled_cancel', 'limit_cancel'):
        _check(address(task['token_in']) == token and address(task['token_out']) == wrapped, '取消任务资产不符')
        limit = kind == 'limit_cancel'
        if limit:
            price, when = integer(intent['target_price_raw']), integer(intent['expiry_time'])
            _check(price > 0 and amount * price < 2 ** 256 and price == integer(task['target_price_raw'])
                   and when == integer(planning['timestamp']) + integer(task['expiry_offset_seconds']),
                   '限价价格/到期条件与原任务不符')
            create = call(contract, 'createLimitOrder(address,address,uint256,uint256,uint256)', token, wrapped, amount, price, when)
            cancel = call(contract, 'cancelLimitOrder(uint256)', order_id)
        else:
            price, when = minimum, integer(intent['execution_time'])
            _check(when == integer(planning['timestamp']) + integer(task['execution_time_offset_seconds']), '定时条件与原任务不符')
            create = call(contract, 'scheduleSwap(address,address,uint256,uint256,uint256)', token, wrapped, amount, minimum, when)
            cancel = call(contract, 'cancelSwap(uint256)', order_id)
        _check(when == 0 or when > body_time, '订单已经到期，不属于预定创建取消实验')
        prefix = [call(token, 'approve(address,uint256)', contract, amount), create, cancel]
        _check(stored[4:] == [price, when, 2, 0], '订单不是原任务的Cancelled/零成交终态')
        _check(_transfers(logs, token, wallet, contract) == [amount] and _transfers(logs, token, contract, wallet) == [amount]
               and _transfers(logs, token, sender=wallet) == [amount] and _transfers(logs, token, recipient=wallet) == [amount]
               and _transfers(logs, token, sender=contract) == [amount] and _transfers(logs, token, recipient=contract) == [amount],
               '本金转账/退款未按原约定精确托管并全退')
        for owner in (wallet, contract):
            _check(_balance(reads, token, owner, tag) == _balance(reads, token, owner, before_tag), '取消后出现代币净支出/托管残留变化')
        _check(reads.number(token, 'allowance(address,address)', wallet, contract, tag=tag) == 0
               and reads.number(token, 'allowance(address,address)', wallet, contract, tag=before_tag) == 0, '任务结束授权未归零或原授权不明')
        history_method = 'getUserLimitOrders(address)' if limit else 'getUserSwaps(address)'
        history = hex_bytes(reads.call(contract, history_method, wallet, tag=tag))
        ids = words('0x' + history.hex(), len(history) // 32)
        _check(len(ids) >= 2 and ids[0] == 32 and len(ids) == ids[1] + 2 and order_id in ids[2:], '订单不在本人链上历史')
        result = {'outcome': 'Cancelled', 'escrowed_raw': str(amount), 'refunded_raw': str(amount),
                  'remaining_allowance_raw': '0', 'platform_fee_raw': '0'}
        title, action = ('限价订单创建并撤销', 'limit_order_cancel') if limit else ('定时订单创建并撤销', 'scheduled_order_cancel')
        asset = p['assets']['token']
        summary = f"同笔创建并撤销订单{order_id}，{_units(amount, integer(asset['decimals']))}{asset['symbol']}全退，结束授权0；没有触发兑换。"
    else:
        raise ValueError('尚未适配该合约生命周期')
    _check([item for item in calls if item not in allowed_reads] == prefix, '批调用含未约定写入、value或写入顺序')
    _check(_balance(reads, wrapped, wallet, before_tag) == _balance(reads, wrapped, wallet, tag)
           and not _transfers(logs, wrapped, sender=wallet) and not _transfers(logs, wrapped, recipient=wallet),
           '已有封装原生资产被改变或发生未约定转账')
    l2, l1 = integer(receipt['gasUsed']) * integer(receipt['effectiveGasPrice']), integer(receipt['l1Fee'])
    operator = integer(receipt['operatorFee']) if receipt.get('operatorFee') is not None else reads.number(
        address(p['gas_oracle']), 'getOperatorFee(uint256)', integer(receipt['gasUsed']), tag=tag)
    network = l2 + l1 + operator
    native_delta = integer(reads.get('eth_getBalance', [wallet, before_tag])) - integer(reads.get('eth_getBalance', [wallet, tag]))
    _check(native_delta == network + (amount if kind == 'native_swap' else 0), '原生资产变化不等于本金/实际全部网络费')
    head = integer(reads.get('eth_blockNumber', []))
    _check(head - height >= integer(p['minimum_confirmations']), '尚未达到已配置确认距离')
    result.update(task_key=entry['task_key'], kind=kind, transaction_hash=tx_hash, verified=True, block=height,
        order_id=order_id, timestamp=body_time, confirmation_distance=head - height,
        amount_in_raw=str(amount), network_fee_wei=str(network), l2_fee_wei=str(l2), l1_fee_wei=str(l1), operator_fee_wei=str(operator))
    native = p['assets']['native']
    summary += f" 实际网络费{_units(network, integer(native['decimals']))}{native['symbol']}。"
    return result, title, action, summary


def replay_contract_lifecycle(root: Path, config: dict, hashes: dict[str, str]):
    """Return protocol facts, findings and actions; absent/mismatched facts stay UNKNOWN."""
    _check(config['schema_version'] == 'contract-lifecycle-supplement-v1'
           and config['checker_id'] == 'evm.contract-lifecycle-v1', '不支持的补测来源格式')
    evidence = SwapEvidence(root, hashes)
    identity_manifest = evidence.json(config['identity_manifest'])
    _check(identity_manifest['schema_version'] == 'evaluation-input-manifest-v1', '身份报告来源manifest格式不符')
    identity_hashes = {item['path']: item['sha256'] for item in identity_manifest['inputs']}
    for name, digest in identity_hashes.items():
        _check(hashes.get(name) == digest, '身份报告的原依赖未绑定或已改变')
        evidence.raw(name)
    identity = parse_evaluation_report(evidence.raw(config['identity_report']))
    verify_shared_report_sources(root, identity, identity_hashes)
    _check(identity.candidate_key == config['candidate_key'] and identity.registration_reference == config['registration_reference']
           and identity.name == config['name'], '补测身份与已重放登记/声明报告不一致')
    protocol = evidence.json(config['protocol_config'])
    _check(protocol['schema_version'] == 'evm-contract-lifecycle-protocol-v1', '未审阅协议配置')
    abi = evidence.json(protocol['abi_path'])
    signatures = {item['name'] + '(' + ','.join(value['type'] for value in item['inputs']) + ')'
                  for item in abi if item.get('type') == 'function'}
    signatures.update({'approve(address,uint256)', 'balanceOf(address)', 'allowance(address,address)'})
    common = [config['protocol_config'], protocol['abi_path'], *config.get('additional_sources', [])]
    for name in common:
        evidence.raw(name)
    checks = [ReportFinding(label='A · 业务服务可用性', verdict=Verdict.UNKNOWN,
        explanation='未取得本次V4任务的Agent HTTP业务交付观测；RPC、钱包签名与合约成功均不替代，A观测数为0。')]
    actions, tasks, times = [], [], []
    _check(len({item['task_key'] for item in config['tasks']}) == len(config['tasks']), '任务标识重复')
    for entry in config['tasks']:
        plan_path = entry.get('plan_path', config['plan_path'])
        sources = sorted(set([*common, plan_path, entry['intent_path'], entry['task_path'],
                              entry['unsigned_transaction'], *entry['rpc_observations']]))
        try:
            result, title, action, summary = _replay_task(evidence, entry, protocol, signatures, plan_path)
            sources = _source_names(evidence, entry, [*common, plan_path])
            tasks.append(result); times.append(result['timestamp'])
            checks.extend([ReportFinding(label=f'F · {title}', verdict=Verdict.PASS,
                explanation=f"任务{entry['task_key']}的原计划、实际调用、资产/订单终态及整数参数对应；仅支持该条已测声明。"),
                ReportFinding(label=f'B · {title}', verdict=Verdict.PASS, explanation=summary + f" 实际网络费{result['network_fee_wei']}wei；确认距离{result['confirmation_distance']}块。")])
            actions.append(ChainAction(sample_id='contract:' + entry['task_key'], chain_id=integer(protocol['chain_id']),
                action=action, title=title, transaction_hash=entry['transaction_hash'], block_number=result['block'],
                executor=address(protocol['wallet']), target=address(protocol['contract']),
                method='executeBatch → ' + ('instantSwap' if entry['kind'] == 'native_swap' else 'create → cancel'),
                summary=summary, verdict=Verdict.PASS, evidence=sources))
        except (OSError, KeyError, ValueError, TypeError, OverflowError) as error:
            reason = ('缺少公开字段：' + str(error)) if isinstance(error, KeyError) else (
                str(error) if isinstance(error, ValueError) else type(error).__name__)
            tasks.append({'task_key': entry['task_key'], 'kind': entry['kind'], 'transaction_hash': entry['transaction_hash'],
                          'verified': False, 'reason': reason, 'evidence': sources})
            checks.append(ReportFinding(label='F/B · 原件尚未核齐', verdict=Verdict.UNKNOWN,
                explanation=f"任务{entry['task_key']}保留未决：{reason}。未把summary布尔、缺源或平台问题补成通过/Agent违约。"))
    window = '—'.join(datetime.fromtimestamp(value, timezone.utc).isoformat() for value in (min(times), max(times))) if times else '执行时间尚未核齐'
    facts = {key: getattr(identity, key) for key in ('candidate_key', 'registration_reference', 'name')}
    facts.update(chain_id=integer(protocol['chain_id']), buyer=address(protocol['wallet']), contract=address(protocol['contract']),
        task_count=len(config['tasks']), verified_task_count=len(actions), tasks=tasks, window_summary=window,
        availability_observed=0, availability_verdict='UNKNOWN',
        functional_summary=f'{len(actions)}/{len(config["tasks"])}项任务的调用与实际效果由原件对应；不是全声明评价。',
        behavioral_summary='只核已接受任务的真实执行/退款、授权及费用；取消不是成交，未产生数值或综合分。',
        confirmation_limitations=['区块确认距离不等于Base finalized或L1最终性。'],
        limitations=[*config.get('limitations', []), '本快照不进入既有范围评分，A没有业务HTTP观测；原网站评分保持。',
                     '源码风险须按独立来源说明，不能由未发生的损失或未观测Failed状态伪造实验结论。'])
    return facts, checks, actions
