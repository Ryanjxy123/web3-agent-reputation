"""Offline shared-task reports from ACP delivery and unsigned ERC20 route evidence.

The adapter is protocol based: provider identity and business parameters are inputs;
neither provider claims nor retained operator summary verdicts are scoring evidence.
"""
from datetime import datetime, timezone
import json
from pathlib import Path

from eth_hash.auto import keccak

from reputation_core import MeasurementPurpose, ReportFinding, SampleExplanation, ScoredSample, Verdict
from reputation_core.application import AgentProfile, normalize_reference
from reputation_core.prediction_chain import calldata
from reputation_core.reporting import EvaluationReport
from reputation_core.scoring import POINT_POLICY_VERSION
from reputation_core.shared_scoring import SharedAssessment
from reputation_core.swap import address, encode_batch, hex_bytes, integer
from reputation_platform.registration_discovery import _configuration, verify_registration_proof
from reputation_platform.swap_report import SwapEvidence, _check, _lookup, _normalized, _sha, _write
from reputation_platform.unsigned_swap_protocol import (
    _ABI, decode_unsigned_swap, verify_unsigned_swap_intent, UnsignedSwapMismatch,
)

ORIGIN = 'unsigned-swap-report-origin.json'
ADAPTER = 'retained-unsigned-swap-v1'
ADR = 'docs/adr/0029-single-score-and-report-scope.md'
SOURCE_ADR = 'docs/adr/0030-unsigned-swap-source-replay.md'
CAPABILITY = 'erc20-swap-routing'
APPROACH = '独立重放公开身份、ACP原始需求与链上交付、协议calldata、固定块模拟及真实兑换；同一任务共享三维证据，沿用单分规则。'
LIMITATIONS = [
    '仅评价明确选择的ERC20精确输入兑换范围；少量任务不能证明全部资产、路由或长期可靠性。',
    '服务生成方案，买方钱包签名执行；服务费及报价服务结算不是资产兑换履约。',
    'A从链上资金就绪到链上提交交付的区块时间计算，不包含此前等待买方付款的时间，也不是HTTP延迟。',
    'F固定区块模拟不是实际成交；B只使用已核真实兑换。未执行的旧过期报价不算提供方交易失败。',
    '按64块确认距离核验，未声称finalized；块末余额属于整个区块窗口，逐交易到账以代币事件独立核对。',
    '注册正文自报字段可能不符合登记格式；身份依据可信registry的ownerOf/tokenURI及原始正文服务链接核实。',
]
FUNDED = '0xe3fbcc1ea1bdc559ec7f0347efde7655e58b5f45a30b0e4470a583c3ef5496b3'
SUBMITTED = '0x80c17db79857f338a6a6df68a6883ecc0ce78e2202fe61ed979733573f40538e'
TRANSFER = '0x' + keccak(b'Transfer(address,address,uint256)').hex()
IMPLEMENTATION_SLOT = '0x360894a13ba1a3210667c828492db98dca3e2076cc3735a920a3ca505d382bbc'
# Verified proxy/implementation runtime for the ABI version supported by the decoder.
# These bind a protocol implementation, not an Agent or its registration identity.
HYDREX_PROXY_HASH = '0fd29b47a89ab717d1653f7e091ec20c409ccee39c8cfbce5b61580ab5798fbc'
HYDREX_IMPLEMENTATION_HASH = '48f4283f2f63da1ea0910b5a950150e2f457c7d0bdc51a7a5256ef8f255c0a81'
READS = {'eth_chainId', 'eth_blockNumber', 'eth_getBlockByNumber', 'eth_getTransactionByHash',
         'eth_getTransactionReceipt', 'eth_getCode', 'eth_getStorageAt', 'eth_getLogs',
         'eth_getBalance', 'eth_getTransactionCount', 'eth_call', 'eth_estimateGas', 'eth_gasPrice'}


def _topic(value):
    return '0x' + address(value)[2:].zfill(64)


def _uint(value):
    return integer(value)


def _results(value):
    abi = _ABI(hex_bytes(value))
    return [abi.blob_at(at) for at in abi.array(0, 0, 1, dynamic=True)]


def _word(value):
    _check(len(value) == 32, 'Expected one canonical uint256 result')
    return int.from_bytes(value, 'big')


def _http(evidence, name, url):
    observation, raw = evidence.observed(name)
    _check(observation['url'] == url and observation['method'] == 'GET'
           and observation.get('request_json') is None and observation.get('http_status') == 200
           and observation.get('body_complete') and not observation.get('error_kind') and raw,
           'Original public ACP response is incomplete or from a different endpoint')
    return json.loads(raw)


def _records(evidence, names):
    urls = {item['rpc_url'] for item in _configuration(evidence.root)['chains'].values()}
    urls.add('https://mainnet.base.org')
    records = []
    for name in names:
        obs, raw = evidence.observed(name)
        _check(obs['url'] in urls and obs['method'] == 'POST', 'Unreviewed operator RPC source')
        request = json.loads(obs['request_json'])
        _check(request.get('jsonrpc') == '2.0' and request.get('method') in READS, 'Not a retained readonly RPC')
        complete = bool(raw and obs.get('body_complete') and obs.get('http_status') == 200 and not obs.get('error_kind'))
        response = json.loads(raw) if complete else {}
        if complete:
            _check(response.get('jsonrpc') == '2.0' and response.get('id') == request.get('id'), 'RPC envelope mismatch')
        records.append({'method': request['method'], 'params': request['params'], 'value': response.get('result'),
            'error': response.get('error') or obs.get('error_kind') or (None if complete else 'incomplete'), 'observation': name})
    return records


def _call_value(records, payer, target, data, tag):
    matches = []
    for row in records:
        if (row['method'] != 'eth_call' or row['error'] or row['value'] is None
            or len(row['params']) != 2 or row['params'][1] != tag):
            continue
        call = row['params'][0]
        if (set(call) <= {'from', 'to', 'data', 'value', 'gas', 'gasPrice'} and address(call['from']) == payer
            and address(call['to']) == target and _uint(call.get('value', '0x0')) == 0 and call['data'].lower() == data.lower()):
            matches.append(row['value'])
    _check(len(set(matches)) <= 1, 'Conflicting fixed-block call results')
    return matches[0] if matches else None


def _canonical(records, value):
    header = _lookup(records, 'eth_getBlockByNumber', [value['blockNumber'], False])
    _check(header is not None and header['hash'].lower() == value['blockHash'].lower()
           and _uint(header['number']) == _uint(value['blockNumber']), 'Missing or conflicting canonical block')
    tx_hash = value.get('transactionHash')
    if tx_hash:
        _check(tx_hash.lower() in [row.lower() if isinstance(row, str) else row['hash'].lower()
                                 for row in header['transactions']], 'Transaction is absent from canonical block')
    return header


def _event(records, contract, topic, job_id, actor):
    logs = []
    for row in records:
        if row['error']:
            continue
        if row['method'] == 'eth_getTransactionReceipt' and row['value']:
            receipt = row['value']
            _check(_uint(receipt['status']) == 1, 'ACP event receipt reverted')
            logs.extend(receipt['logs'])
        elif row['method'] == 'eth_getLogs':
            logs.extend(row['value'] or [])
    matching = {log['transactionHash'].lower() + ':' + log['logIndex']: log for log in logs
        if address(log['address']) == contract and len(log['topics']) == 3
        and log['topics'][0].lower() == topic and _uint(log['topics'][1]) == int(job_id)
        and log['topics'][2].lower() == _topic(actor)}
    _check(len(matching) == 1, 'Expected one identity-bound ACP event')
    log = next(iter(matching.values()))
    _check(not log.get('removed'), 'ACP event was removed')
    return log, _canonical(records, log)


def _task_delivery(evidence, source, item):
    plan = evidence.json(item['plan'])
    tasks = [row for row in plan['tasks'] if row['task_key'] == item['task_key']]
    _check(len(tasks) == 1, 'Task does not bind to a unique frozen request')
    frozen, acp = tasks[0], item['acp']
    provider, buyer = address(acp['provider_wallet']), address(plan['buyer'])
    _check(frozen['provider_id'] == acp['provider_id'] and address(frozen['provider_wallet']) == provider,
           'Provider identity differs from frozen request')
    base = 'https://api.acp.virtuals.io'
    detail = _http(evidence, acp['detail_observation'], base + '/agents/' + acp['provider_id'])['data']
    job = _http(evidence, acp['job_observation'], f'{base}/jobs/{plan["chain_id"]}/{acp["job_id"]}')['data']
    _check(detail['id'] == acp['provider_id'] and address(detail['walletAddress']) == provider
           and job['providerId'] == acp['provider_id'] and address(job['providerAddress']) == provider
           and address(job['clientAddress']) == buyer and str(job['onChainJobId']) == str(acp['job_id'])
           and job['chainId'] == plan['chain_id'] and job['description'] == frozen['offering'], 'ACP participant or offering mismatch')
    history = _http(evidence, acp['history_observation'], f'{base}/chats/{plan["chain_id"]}/{acp["job_id"]}/history')['entries']
    _check(all(str(row['onChainJobId']) == str(acp['job_id']) and row['chainId'] == plan['chain_id'] for row in history), 'History contains another job')
    requests = [row for row in history if row['kind'] == 'message' and row.get('contentType') == 'requirement'
                and address(row['from']) == buyer]
    _check(len(requests) == 1 and json.loads(requests[0]['content']) == frozen['requirement'], 'Delivered requirement differs from frozen input')
    deliveries = [row['event'] for row in history if row['kind'] == 'system' and row['event']['type'] == 'job.submitted']
    _check(len(deliveries) == 1 and address(deliveries[0]['provider']) == provider, 'Missing unique provider delivery')
    delivery = deliveries[0]
    digest = '0x' + keccak(delivery['deliverable'].encode('utf-8')).hex()
    _check(digest.lower() == delivery['deliverableHash'].lower(), 'Original deliverable hash mismatch')
    records = _records(evidence, acp['rpc_observations'])
    fund, funded_block = _event(records, address(plan['contract']), FUNDED, acp['job_id'], buyer)
    submitted, submitted_block = _event(records, address(plan['contract']), SUBMITTED, acp['job_id'], provider)
    _check(submitted['data'].lower() == digest.lower() and _uint(fund['data']) > 0, 'Onchain delivery or funded amount mismatch')
    elapsed = (_uint(submitted_block['timestamp']) - _uint(funded_block['timestamp'])) * 1000
    _check(elapsed >= 0, 'Delivery predates funded service request')
    return plan, frozen, json.loads(delivery['deliverable']), elapsed, submitted_block, provider


def _intent(plan, frozen, delivered):
    request = frozen['requirement']
    if {'fromTokenAddress', 'toTokenAddress', 'amount', 'taker', 'slippage'} <= request.keys():
        expected = {'token_in': address(request['fromTokenAddress']), 'token_out': address(request['toTokenAddress']),
            'amount_in': _uint(request['amount']), 'recipient': address(request['taker'])}
        slippage = _uint(request['slippage'])
    elif {'sellToken', 'buyToken', 'amountIn', 'buyer', 'slippageBps'} <= request.keys():
        expected = {'token_in': address(request['sellToken']), 'token_out': address(request['buyToken']),
            'amount_in': _uint(request['amountIn']), 'recipient': address(request['buyer'])}
        slippage = _uint(request['slippageBps'])
    else:
        raise ValueError('Unsupported exact-input requirement format')
    _check(0 <= slippage < 10000 and expected['recipient'] == address(plan['asset_recipient']), 'Frozen recipient or slippage mismatch')
    if 'quote' in delivered:
        route = delivered['quote']
        transaction = {'to': route['routerContract'], 'data': route['calldata'], 'value': route['value']}
        quoted, minimum = _uint(route['amountOut']), _uint(route['minOutputAmount'])
        deadline = None
    elif 'route' in delivered:
        route = delivered['route']
        transaction = {'to': route['target'], 'data': route['calldata'], 'value': route['valueToSend']}
        quoted, minimum = _uint(route['quotedOut']), _uint(route['minOut'])
        deadline = delivered.get('validUntil')
    else:
        raise ValueError('No unsigned protocol route in provider delivery')
    expected['minimum_out'] = minimum
    _check(quoted > 0, 'Quote has no positive reference output')
    issues = []
    if minimum < quoted * (10000 - slippage) // 10000:
        issues.append('交付的最低到账低于本次请求允许的滑点下限。')
    try:
        decoded = verify_unsigned_swap_intent(transaction, expected, chain_id=plan['chain_id'], quote_deadline=deadline)
    except UnsignedSwapMismatch as error:
        # An authentic but nonconforming provider plan is an F failure, not corrupt evidence.
        decoded = decode_unsigned_swap(transaction, chain_id=plan['chain_id'], quote_deadline=deadline)
        issues.append(str(error))
    decoded['intent_binding_issues'] = issues
    return expected, decoded, transaction


def _batch_binding(calls, expected, transaction, payer):
    token, output, recipient = expected['token_in'], expected['token_out'], expected['recipient']
    spender = address(transaction['to'])
    expected_calls = [
        (token, calldata('balanceOf(address)', payer)),
        (output, calldata('balanceOf(address)', recipient)),
        (token, calldata('approve(address,uint256)', spender, expected['amount_in'])),
        (spender, transaction['data']),
        (token, calldata('approve(address,uint256)', spender, 0)),
        (token, calldata('balanceOf(address)', payer)),
        (output, calldata('balanceOf(address)', recipient)),
        (token, calldata('allowance(address,address)', payer, spender)),
    ]
    _check(len(calls) == 8 and all(address(call['target']) == target and _uint(call['value']) == 0
           and call['data'].lower() == data.lower() for call, (target, data) in zip(calls, expected_calls)),
           'Simulation or execution batch differs from exact approval, delivered route, cleanup and balance queries')


def _simulation(evidence, item, expected, decoded, transaction):
    source = item.get('simulation')
    if not source:
        return Verdict.UNKNOWN, '缺独立固定块完整模拟。', {}
    plan = evidence.json(source['plan'])
    _check(plan['origin_task'] == item['task_key'], 'Simulation belongs to another task')
    if 'source_plan_sha256' in plan:
        _check(source.get('source_plan') and plan['source_plan_sha256'] == _sha(evidence.raw(source['source_plan'])),
               'Simulation source plan digest mismatch')
    payer = address(plan['payer'])
    _batch_binding(plan['calls'], expected, transaction, payer)
    records = _records(evidence, source['rpc_observations'])
    calls = [row for row in records if Path(row['observation']).name == source['call_label'] + '.observation.json']
    _check(len(calls) == 1 and calls[0]['method'] == 'eth_call', 'Missing exact retained simulation request')
    call = calls[0]
    _check(len(call['params']) == 2, 'Scored simulation must not contain state or block overrides')
    actual_call = call['params'][0]
    _check(set(actual_call) <= {'from', 'to', 'data', 'value', 'gas', 'gasPrice'}
           and address(actual_call['from']) == payer == address(actual_call['to'])
           and actual_call['data'].lower() == encode_batch(plan['calls']).lower()
           and _uint(actual_call.get('value', '0x0')) == 0, 'Simulation call differs from frozen batch')
    tag = call['params'][1]
    header = _lookup(records, 'eth_getBlockByNumber', [tag, False])
    _check(header and _uint(header['number']) == _uint(tag), 'Simulation fixed block is not independently retained')
    deadline = decoded['earliest_known_deadline']
    _check(deadline is None or _uint(header['timestamp']) <= deadline, 'Retained simulation was past the effective protocol deadline')
    if decoded['protocol'] == 'hydrex-multirouter':
        proxy = address(transaction['to'])
        proxy_code = _lookup(records, 'eth_getCode', [proxy, tag])
        slot = _lookup(records, 'eth_getStorageAt', [proxy, IMPLEMENTATION_SLOT, tag])
        implementation = address('0x' + slot[-40:]) if slot else None
        implementation_code = _lookup(records, 'eth_getCode', [implementation, tag]) if implementation else None
        _check(proxy_code and implementation_code
               and keccak(hex_bytes(proxy_code)).hex() == HYDREX_PROXY_HASH
               and keccak(hex_bytes(implementation_code)).hex() == HYDREX_IMPLEMENTATION_HASH,
               'Actual proxy or implementation runtime differs from the verified protocol ABI')
    if call['error']:
        return Verdict.UNKNOWN, '固定块模拟未取得可判返回；没有把平台读取失败当提供方违约。', {}
    results = _results(call['value'])
    _check(len(results) == 8, 'Simulation result count differs from full batch')
    debit, credit, allowance = _word(results[0]) - _word(results[5]), _word(results[6]) - _word(results[1]), _word(results[7])
    passed = debit == expected['amount_in'] and credit >= expected['minimum_out'] and allowance == 0
    facts = {'input_debit_raw': str(debit), 'output_credit_raw': str(credit), 'allowance_raw': str(allowance), 'block': _uint(tag),
             'pre_input_raw': str(_word(results[0])), 'pre_output_raw': str(_word(results[1])), 'block_hash': header['hash']}
    return (Verdict.PASS if passed else Verdict.FAIL,
            f'固定块{_uint(tag)}完整模拟：输入减少{debit}最小单位，输出增加{credit}，最低{expected["minimum_out"]}，剩余授权{allowance}。', facts)


def _transfers(receipt, token, sender=None, recipient=None):
    result = []
    for log in receipt['logs']:
        if address(log['address']) != token or len(log['topics']) != 3 or log['topics'][0].lower() != TRANSFER:
            continue
        if sender and log['topics'][1].lower() != _topic(sender):
            continue
        if recipient and log['topics'][2].lower() != _topic(recipient):
            continue
        result.append(_uint(log['data']))
    return sum(result)


def _execution(evidence, item, expected, decoded, transaction, simulation_facts):
    source = item.get('execution')
    if not source:
        return Verdict.UNKNOWN, '本报价任务没有安排真实兑换；不能用报价或模拟补交易分。', {}
    plan, intent = evidence.json(source['plan']), evidence.json(source['intent_path'])
    _check(plan['origin_task'] == item['task_key'] and plan['task_key'] == intent['task_key']
           and intent['plan_sha256'] == _sha(evidence.raw(source['plan'])), 'Actual execution intent does not bind the quoted task')
    payer, tx_hash = address(source['payer']), source['transaction_hash'].lower()
    _check(simulation_facts and str(intent['pre_usdc_raw']) == simulation_facts['pre_input_raw']
           and str(intent['pre_weth_raw']) == simulation_facts['pre_output_raw']
           and intent['fixed_block'] == simulation_facts['block']
           and intent['block_hash'].lower() == simulation_facts['block_hash'].lower(),
           'Persisted execution pre-balances are not backed by the fixed-block raw simulation')
    _batch_binding(plan['calls'], expected, transaction, payer)
    records = _records(evidence, source['rpc_observations'])
    _check(_uint(_lookup(records, 'eth_chainId', [])) == decoded['chain_id'], 'Execution RPC chain mismatch')
    tx = _lookup(records, 'eth_getTransactionByHash', [tx_hash])
    receipt = _lookup(records, 'eth_getTransactionReceipt', [tx_hash])
    _check(tx and receipt and tx['hash'].lower() == tx_hash and receipt['transactionHash'].lower() == tx_hash, 'Missing canonical execution transaction and receipt')
    header = _canonical(records, receipt)
    _check(tx['blockHash'].lower() == receipt['blockHash'].lower() and tx['blockNumber'] == receipt['blockNumber']
           and tx['transactionIndex'] == receipt['transactionIndex'], 'Transaction and receipt block mismatch')
    actual = intent['transaction']
    _check(address(actual['from']) == payer == address(actual['to']) and _uint(actual['chainId']) == decoded['chain_id']
           and _uint(actual['value']) == 0
           and address(tx['from']) == payer == address(tx['to']) and _uint(tx['chainId']) == decoded['chain_id']
           and _uint(tx['value']) == 0 and tx['input'].lower() == actual['data'].lower() == encode_batch(plan['calls']).lower()
           and _uint(tx['nonce']) == _uint(actual['nonce']), 'Actual signed transaction differs from exact planned route')
    _check(decoded['earliest_known_deadline'] is None or _uint(header['timestamp']) <= decoded['earliest_known_deadline'], 'Transaction was included after effective quote deadline')
    heads = [_uint(row['value']) for row in records if row['method'] == 'eth_blockNumber' and row['value'] and not row['error']]
    depth = max(heads, default=-1) - _uint(receipt['blockNumber'])
    _check(depth >= 64, 'Execution has not reached the reviewed 64-block confirmation distance')
    if _uint(receipt['status']) != 1:
        return Verdict.UNKNOWN, '真实交易已回滚，原因及归因尚未核齐；未认定为提供方违约或安全约束违背。', {'transaction_hash': tx_hash, 'block': _uint(receipt['blockNumber'])}
    debit = _transfers(receipt, expected['token_in'], sender=payer) - _transfers(receipt, expected['token_in'], recipient=payer)
    credit = _transfers(receipt, expected['token_out'], recipient=expected['recipient']) - _transfers(receipt, expected['token_out'], sender=expected['recipient'])
    getter_calls = [
        {'target': expected['token_in'], 'value': '0', 'data': calldata('balanceOf(address)', payer)},
        {'target': expected['token_out'], 'value': '0', 'data': calldata('balanceOf(address)', expected['recipient'])},
        {'target': expected['token_in'], 'value': '0', 'data': calldata('allowance(address,address)', payer, address(transaction['to']))},
    ]
    balance = _call_value(records, payer, payer, encode_batch(getter_calls), receipt['blockNumber'])
    _check(balance is not None, 'Missing independent post-execution balances and allowance')
    values = [_word(value) for value in _results(balance)]
    _check(len(values) == 3, 'Post-execution getter count mismatch')
    simulation_records = _records(evidence, item['simulation']['rpc_observations'])
    before_code = _lookup(simulation_records, 'eth_getCode', [payer, hex(intent['fixed_block'])])
    after_code = _lookup(records, 'eth_getCode', [payer, receipt['blockNumber']])
    _check(before_code is not None and after_code is not None and before_code.lower() == after_code.lower(),
           'Execution wallet delegation changed or lacks independent proof')
    passed = debit == expected['amount_in'] and credit >= expected['minimum_out'] and values[2] == 0
    facts = {'transaction_hash': tx_hash, 'block': _uint(receipt['blockNumber']), 'timestamp': _uint(header['timestamp']), 'input_debit_raw': str(debit),
        'output_credit_raw': str(credit), 'allowance_raw': str(values[2]), 'confirmation_distance': depth}
    if passed and (_uint(intent['pre_usdc_raw']) - values[0] != debit or values[1] - _uint(intent['pre_weth_raw']) != credit):
        return Verdict.UNKNOWN, '本交易代币事件符合兑换目标，但前置块至回执块末余额窗口存在额外变化，尚不能独立对平；不推定提供方违约。', facts
    return (Verdict.PASS if passed else Verdict.FAIL,
            f'真实交易输入净减少{debit}，指定收款人输出净增加{credit}最小单位；最低{expected["minimum_out"]}，剩余授权{values[2]}，确认距离{depth}块。', facts)


def replay_unsigned_swap_sources(root, evidence, source):
    _check(source['schema_version'] == 'unsigned-swap-evidence-v1' and source['adapter'] == ADAPTER, 'Unsupported unsigned swap evidence source')
    canonical = normalize_reference(source['registration_reference'])
    _check(canonical and canonical == source['registration_reference'], 'Expected a canonical registered identity')
    proof = evidence.json(source['registration_proof'])
    for reference in proof['source_refs']:
        _check(evidence.hashes.get(reference['path']) == reference['sha256'], 'Registration source is absent or changed')
        evidence.raw(reference['path'])
    identity = verify_registration_proof(root, source['registration_proof'], canonical)
    _check(identity['registration_verified'], 'Independent onchain registration is not verified')
    owner = address('0x' + proof['rpc']['owner']['value'][-40:])
    profile = AgentProfile.model_validate_json(json.dumps(source['profile']))
    _check(profile.registration_chain_id == int(canonical.split(':')[1]), 'Profile registration chain differs')
    cases, tasks, observations, samples = {}, [], [], []

    def observe(task_key, dimension, criterion, verdict, reason, refs, elapsed=None):
        case_id = dimension + ':' + criterion
        if case_id not in cases:
            cases[case_id] = {'case_id': case_id, 'capability_id': CAPABILITY, 'dimension': dimension,
                'declaration_group_id': criterion if dimension == 'functional' else None, 'title': criterion,
                'criterion_ids': [criterion], 'task_keys': [], 'normal_execution': dimension == 'behavioral', 'required_decisive': 1}
        cases[case_id]['task_keys'].append(task_key)
        observations.append({'task_key': task_key, 'case_id': case_id, 'criterion_id': criterion, 'dimension': dimension,
            'verdict': verdict.value, 'reason': reason, 'evidence': refs, 'measurement_validity': 'valid',
            'elapsed_ms': elapsed, 'response_complete': True if dimension == 'availability' else None,
            'critical': verdict == Verdict.FAIL and criterion == 'onchain-fulfillment'})

    for index, item in enumerate(source['tasks'], 1):
        plan, frozen, delivered, elapsed, submitted, provider = _task_delivery(evidence, source, item)
        _check(provider == owner, 'Provider wallet is not the independently registered owner')
        services = [row.get('endpoint', '') for row in (identity.get('document') or {}).get('services', [])]
        _check('https://app.virtuals.io/acp/agent/' + item['acp']['provider_id'] in services, 'Registered document does not bind this ACP service identity')
        refs = [item['plan'], item['acp']['history_observation'], item['acp']['job_observation'], item['acp']['detail_observation'], *item['acp']['rpc_observations']]
        expected, decoded, transaction = _intent(plan, frozen, delivered)
        task_key = item['task_key']
        observe(task_key, 'availability', 'complete-response', Verdict.PASS if elapsed <= source['response_deadline_ms'] else Verdict.FAIL,
                f'从资金就绪至该提供方链上提交完整方案耗时{elapsed}ms；预定时限{source["response_deadline_ms"]}ms。', refs, float(elapsed))
        issues = decoded['intent_binding_issues']
        observe(task_key, 'functional', 'intent-binding', Verdict.FAIL if issues else Verdict.PASS,
                ' '.join(issues) if issues else '独立解码原始calldata：输入输出资产、整数金额、指定收款人和滑点最低到账符合冻结需求。', refs)
        sim_verdict, sim_reason, simulation_facts = (_simulation(evidence, item, expected, decoded, transaction)
            if not issues else (Verdict.UNKNOWN, '方案已明确违反任务约束，未用资产执行或补造效果。', {}))
        sim_refs = [*refs, *item['simulation']['rpc_observations'], item['simulation']['plan']] if item.get('simulation') else refs
        observe(task_key, 'functional', 'execution-effect', sim_verdict, sim_reason, sim_refs)
        execution_verdict, execution_reason, execution_facts = _execution(evidence, item, expected, decoded, transaction, simulation_facts)
        execution_refs = [*refs, *item['execution']['rpc_observations'], item['execution']['intent_path'], item['execution']['plan']] if item.get('execution') else refs
        if item.get('execution'):
            observe(task_key, 'behavioral', 'onchain-fulfillment', execution_verdict, execution_reason, execution_refs)
        observed_at = datetime.fromtimestamp(max(_uint(submitted['timestamp']), execution_facts.get('timestamp', 0)), timezone.utc)
        title = 'ERC20兑换方案及真实执行' if item.get('execution') else 'ERC20兑换方案与独立模拟'
        input_summary = f'链{plan["chain_id"]}：{expected["amount_in"]}输入最小单位，{expected["token_in"]} → {expected["token_out"]}，收款人{expected["recipient"]}。'
        all_refs = list(dict.fromkeys([*sim_refs, *execution_refs]))
        for name in list(all_refs):
            if name.endswith('.observation.json'):
                observation = evidence.json(name)
                if observation.get('response_file'):
                    response = (Path(name).parent / observation['response_file']).as_posix()
                    evidence.raw(response)
                    if response not in all_refs:
                        all_refs.append(response)
        tasks.append({'task_key': task_key, 'capability_id': CAPABILITY, 'input_summary': input_summary,
            'outcome': ('completed' if execution_verdict == Verdict.PASS else 'failed' if execution_verdict == Verdict.FAIL else 'unknown') if item.get('execution') else 'completed',
            'attribution': 'unknown', 'observed_at': observed_at.isoformat(), 'evidence': all_refs})
        sample = ScoredSample(sample_id=f'unsigned-swap-{index}', task_key=task_key,
            purpose=MeasurementPurpose.BEHAVIORAL if item.get('execution') else MeasurementPurpose.FUNCTIONAL,
            verdict=execution_verdict if item.get('execution') else sim_verdict, elapsed_ms=float(elapsed),
            reason=execution_reason if item.get('execution') else sim_reason, evidence=all_refs)
        samples.append(SampleExplanation(sample=sample, observed_at=observed_at, title=title, input_summary=input_summary,
            claimed_output=f'提供可由买方签名的兑换方案；最少到账{expected["minimum_out"]}输出最小单位。',
            independent_result=sim_reason + (' ' + execution_reason if item.get('execution') else ''),
            checks=[ReportFinding(label='独立完整模拟', verdict=sim_verdict, explanation=sim_reason),
                    ReportFinding(label='真实链上履约', verdict=execution_verdict, explanation=execution_reason)], capability_id=CAPABILITY))
    _check(tasks and len({row['task_key'] for row in tasks}) == len(tasks), 'Missing or duplicated task identity')
    if 'behavioral:onchain-fulfillment' not in cases:
        cases['behavioral:onchain-fulfillment'] = {'case_id': 'behavioral:onchain-fulfillment', 'capability_id': CAPABILITY,
            'dimension': 'behavioral', 'declaration_group_id': None, 'title': '真实链上履约尚未采集', 'criterion_ids': ['onchain-fulfillment'],
            'task_keys': [row['task_key'] for row in tasks], 'normal_execution': True, 'required_decisive': 1}
    capability = {'capability_id': CAPABILITY, 'title': 'ERC20精确输入兑换', 'description': source['scope'], 'selected': True,
        'write_operation': True, 'declaration_groups': [{'group_id': name, 'title': title, 'description': '', 'selected': True,
        'selection_reason': '本次共同兑换意图范围。', 'source_references': [row['acp']['detail_observation'] for row in source['tasks']]}
        for name, title in [('intent-binding', '兑换参数与收款人'), ('execution-effect', '可执行效果与授权清理')]]}
    assessment = SharedAssessment.model_validate_json(json.dumps({'schema_version': 'shared-task-assessment-v3',
        'capabilities': [capability], 'cases': list(cases.values()), 'tasks': tasks, 'observations': observations}, ensure_ascii=False))
    return assessment, samples


def _report(root, evidence, source, generated_at):
    assessment, samples = replay_unsigned_swap_sources(root, evidence, source)
    times = [row.observed_at for row in assessment.tasks if row.observed_at]
    return EvaluationReport(policy_version=POINT_POLICY_VERSION, candidate_key=source['candidate_key'], name=source['name'],
        registration_reference=source['registration_reference'], generated_at=generated_at, scope=source['scope'],
        scope_exclusions=source['scope_exclusions'], evaluation_window=f'{min(times).isoformat()} 至 {max(times).isoformat()}；保留原任务时间。',
        approach=APPROACH, samples=samples, capabilities=[], shared_assessment=assessment,
        source_references=sorted(evidence.hashes), limitations=LIMITATIONS)


def verify_unsigned_swap_report_sources(root, report, hashes):
    origins = [name for name in hashes if Path(name).name == ORIGIN]
    _check(len(origins) == 1, 'Expected a unique unsigned swap source origin')
    evidence = SwapEvidence(root, hashes)
    origin = evidence.json(origins[0])
    _check(origin['schema_version'] == 'unsigned-swap-report-origin-v1' and origin['adapter'] == ADAPTER, 'Unsupported unsigned swap report origin')
    evidence.raw(ADR)
    evidence.raw(SOURCE_ADR)
    expected = _report(root, evidence, evidence.json(origin['source']), report.generated_at)
    _check(report.model_dump(mode='json') == expected.model_dump(mode='json'), 'Published unsigned swap report differs from original evidence replay')
    return report.registration_reference


def build_unsigned_swap_report(root: Path, source: Path, output: Path):
    root = root.resolve()
    source, output = (root / source).resolve(), (root / output).resolve()
    _check(source.is_relative_to(root / 'runtime') and output.is_relative_to(root / 'runtime') and not output.exists(), 'Use retained public source and a new runtime output directory')
    config = json.loads(source.read_bytes())
    hashes = {}
    for row in [*config['sources'], {'path': source.relative_to(root).as_posix(), 'sha256': _sha(source.read_bytes())},
                *({'path': name, 'sha256': _sha((root / name).read_bytes())} for name in (ADR, SOURCE_ADR))]:
        path = (root / row['path']).resolve()
        _check(path.is_relative_to(root) and not any('.private' in part.lower() or part.lower() in ('secrets', 'platform-config', '.env')
                   for part in path.relative_to(root).parts), 'Private input cannot enter a public unsigned-swap report')
        _check(_sha(path.read_bytes()) == row['sha256'] and (row['path'] not in hashes or hashes[row['path']] == row['sha256']), 'Source hash mismatch')
        hashes[row['path']] = row['sha256']
    output.mkdir(parents=True, exist_ok=False)
    origin = {'schema_version': 'unsigned-swap-report-origin-v1', 'adapter': ADAPTER, 'source': source.relative_to(root).as_posix()}
    _write(output / ORIGIN, origin)
    name = (output / ORIGIN).relative_to(root).as_posix()
    hashes[name] = _sha((output / ORIGIN).read_bytes())
    report = _report(root, SwapEvidence(root, hashes), config, datetime.now(timezone.utc))
    _write(output / 'manifest.json', {'schema_version': 'evaluation-input-manifest-v1',
        'implementation_note': {'path': SOURCE_ADR, 'sha256': hashes[SOURCE_ADR]},
        'inputs': [{'path': name, 'sha256': digest} for name, digest in sorted(hashes.items())]})
    _write(output / 'report.json', report.model_dump(mode='json'))
    from reputation_platform.evaluation_report import render_evaluation_report
    (output / 'report.html').write_text(render_evaluation_report(report), encoding='utf-8')
    return report
