"""Selective public export and deterministic replay of a frozen swap campaign."""
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
from math import isfinite
from pathlib import Path
from urllib.parse import urlsplit
from uuid import UUID

from reputation_core import CapabilityCoverage, MeasurementPurpose, ReportFinding, SampleExplanation, ScoredSample, Verdict
from reputation_core.application import normalize_reference
from reputation_core.prediction_chain import calldata
from reputation_core.reporting import EvaluationReport
from reputation_core.scoring import SWAP_EVIDENCE_POLICY_VERSION, SWAP_POLICY_VERSION, SWAP_POLICY_VERSIONS
from reputation_core.swap import (SwapRequest, SwapVerification, address, integer, plan_facts,
                                  verify_swap_execution, verify_swap_function)
from reputation_platform.prediction_report import RetainedEvidence
from reputation_platform.evaluation_report import render_evaluation_report

PLAN = 'configs/swap-task-plan-v1.json'
EXPANDED_PLAN = 'configs/swap-task-plan-v2.json'
PROTOCOLS = 'configs/swap-protocols-v1.json'
ADR = 'docs/adr/0022-evm-swap-builder-scoring.md'
REASSESSMENT_ADR = 'docs/adr/0023-swap-dimension-reassessment.md'
EXPANDED_ADR = 'docs/adr/0024-swap-evidence-coverage-v2.md'
ORIGIN = 'swap-report-origin.json'
CHECKER = 'evm.uniswap-v3-exact-input-single'
CAPABILITY = 'erc20-swap-builder'
SCOPE = '仅评价ERC20精确输入兑换方案及其本人授权执行的三维表现；不代表全部功能、策略收益或自主资产管理。'
EXCLUSIONS = ['其它登记身份及ACP品牌能力不共享本报告分数。', '批量支付、任意交易路由、AI计算与收益表现未评价。']
APPROACH = '预先冻结24个互斥任务；A真实业务访问，F独立固定块完整模拟，B另外七个真实任务独立核链与资产。提供方构造，操作者签名。'
READ_METHODS = {'eth_chainId', 'eth_blockNumber', 'eth_getBlockByNumber', 'eth_getTransactionByHash',
                'eth_getTransactionReceipt', 'eth_getCode', 'eth_getBalance', 'eth_getTransactionCount',
                'eth_call', 'eth_estimateGas', 'eth_gasPrice'}


def _check(value, message):
    if not value:
        raise ValueError(message)


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write('\n')


def _normalized(value):
    if isinstance(value, str) and value.startswith('0x'):
        return value.lower()
    if isinstance(value, list):
        return [_normalized(item) for item in value]
    if isinstance(value, dict):
        return {key: _normalized(item) for key, item in value.items()}
    return value


class SwapEvidence:
    def __init__(self, root, hashes):
        self.root, self.hashes = root.resolve(), hashes
        self.retained = RetainedEvidence(self.root)

    def raw(self, name):
        _check(name in self.hashes, 'Swap source is absent from verified manifest')
        return self.retained.remember(name, self.hashes[name]).read_bytes()

    def json(self, name):
        return json.loads(self.raw(name))

    def observed(self, name):
        obs = self.json(name)
        raw_name = (Path(name).parent / obs['response_file']).as_posix() if obs.get('response_file') else None
        raw = self.raw(raw_name) if raw_name else None
        if raw is not None:
            _check(_sha(raw) == obs.get('response_sha256'), 'Original RPC response hash differs')
        return obs, raw

    def rpc_records(self, observations, urls):
        records = []
        for name in observations:
            obs, raw = self.observed(name)
            _check(obs['url'] in urls and obs['method'] == 'POST', 'RPC endpoint is not the reviewed operator endpoint')
            request = json.loads(obs['request_json'])
            _check(request.get('jsonrpc') == '2.0' and request.get('method') in READ_METHODS,
                   'Published RPC is not an allowed read')
            complete = bool(raw and not obs.get('error_kind') and obs.get('body_complete') and obs.get('http_status') == 200)
            try:
                response = json.loads(raw) if complete else {}
            except ValueError:
                response, complete = {}, False
            if not isinstance(response, dict):
                response, complete = {}, False
            if complete:
                _check(response.get('jsonrpc') == '2.0' and response.get('id') == request.get('id'),
                       'Original RPC request/response envelope differs')
            records.append({'method': request['method'], 'params': request['params'],
                            'value': response.get('result'),
                            'error': response.get('error') or obs.get('error_kind') or (None if complete else 'incomplete_rpc_response'),
                            'observation': name})
        return records


def _lookup(records, method, params):
    matches = [item for item in records if item['method'] == method
               and _normalized(item['params']) == _normalized(params) and item['value'] is not None
               and not item['error']]
    if not matches:
        return None
    if method == 'eth_blockNumber':
        return max(matches, key=lambda item: integer(item['value']))['value']
    values = {_canonical(item['value']) for item in matches}
    _check(len(values) == 1, 'Conflicting retained RPC results for one fixed request')
    return matches[0]['value']


def _canonical(value):
    return json.dumps(_normalized(value), sort_keys=True, separators=(',', ':'))


def _campaign_times(evidence, campaign, visited=()):
    """Validate original freezes, retaining entire F/B groups in a refresh."""
    for item in campaign.get('inputs', []):
        _check(evidence.hashes.get(item['path']) == item['sha256'], 'Frozen campaign dependency changed')
        evidence.raw(item['path'])
    if campaign['policy_version'] == SWAP_EVIDENCE_POLICY_VERSION:
        return _union_campaign_times(evidence, campaign, visited)
    _check(campaign['policy_version'] == SWAP_POLICY_VERSION and campaign.get('preregistered') is True,
           'Campaign was not preregistered under the supported policy')
    plan = evidence.json(PLAN)
    _check([(item['slot'], item['purpose']) for item in campaign['slots']] ==
           [(item['slot'], item['purpose']) for item in plan['slots']], 'Campaign slot structure changed')
    for slot in campaign['slots']:
        _check(str(UUID(slot['request_id'])).lower() == slot['request_id'].lower()
               and UUID(slot['request_id']).version == 4, 'Task identifier is not a CSPRNG UUIDv4')
    created = datetime.fromisoformat(campaign['created_at'])
    times = {slot['slot']: created for slot in campaign['slots']}
    refresh = campaign.get('reassessment')
    if refresh is None:
        return times
    _check(refresh['kind'] == 'dimension-window-refresh-v1' and refresh['policy_note'] == REASSESSMENT_ADR,
           'Unsupported reassessment scope')
    evidence.raw(REASSESSMENT_ADR)
    parent_name = refresh['parent_campaign']
    _check(parent_name not in visited and evidence.hashes.get(parent_name) == refresh['parent_campaign_sha256'],
           'Parent campaign hash changed or reassessment contains a cycle')
    parent = evidence.json(parent_name)
    for key in ('candidate_key', 'registration_reference', 'identity', 'execution_chain_id', 'buyer', 'policy_version'):
        _check(campaign[key] == parent[key], 'Reassessment changed identity or execution scope')
    _check(created > datetime.fromisoformat(parent['created_at']), 'Reassessment must be frozen after its parent')
    renewed = set(refresh['renewed_purposes'])
    retained_purposes = set(refresh['retained_purposes'])
    _check(renewed and renewed.isdisjoint(retained_purposes)
           and renewed | retained_purposes == {'availability', 'functional', 'behavioral'}
           and len(renewed) == len(refresh['renewed_purposes'])
           and len(retained_purposes) == len(refresh['retained_purposes']), 'Reassessment dimensions are not a disjoint partition')
    retained = [slot for slot in campaign['slots'] if slot['purpose'] in retained_purposes]
    _check(retained == [slot for slot in parent['slots'] if slot['purpose'] in retained_purposes],
           'Reassessment must retain entire original dimension groups without selection')
    old_ids = {slot['request_id'] for slot in parent['slots']}
    _check(not any(slot['request_id'] in old_ids for slot in campaign['slots'] if slot['purpose'] in renewed),
           'A renewed dimension window reuses an old task')
    parent_times = _campaign_times(evidence, parent, (*visited, parent_name))
    times.update({slot['slot']: parent_times[slot['slot']] for slot in retained})
    return times


def _union_campaign_times(evidence, campaign, visited):
    """Bind whole source groups; aliases never replace the original tasks."""
    _check(campaign.get('schema_version') == 'swap-campaign-v2' and campaign.get('preregistered') is True,
           'Expanded campaign was not preregistered')
    dependency_names = {item['path'] for item in campaign['inputs']}
    _check({EXPANDED_PLAN, EXPANDED_ADR, PROTOCOLS}.issubset(dependency_names),
           'Expanded campaign did not freeze its v2 policy inputs')
    plan = evidence.json(EXPANDED_PLAN)
    evidence.raw(EXPANDED_ADR)
    _check(plan['policy_version'] == campaign['policy_version'], 'Expanded plan policy differs')
    union = campaign['aggregation']
    _check(union['kind'] == plan['aggregation_kind'] and union['policy_note'] == EXPANDED_ADR,
           'Unsupported source aggregation')
    parents = union['parents']
    names = [item['path'] for item in parents]
    _check(len(names) >= 2 and len(set(names)) == len(names), 'Source aggregation needs distinct complete parent windows')
    sources, parent_times = {}, {}
    created = datetime.fromisoformat(campaign['created_at'])
    previous_time = None
    for index, entry in enumerate(parents):
        name = entry['path']
        _check(name not in visited and evidence.hashes.get(name) == entry['sha256'],
               'Expanded campaign parent changed or contains a cycle')
        parent = evidence.json(name)
        _check(parent['policy_version'] == SWAP_POLICY_VERSION, 'Whole source groups require original v1 windows')
        for key in ('candidate_key', 'registration_reference', 'identity', 'execution_chain_id', 'buyer'):
            _check(parent[key] == campaign[key], 'Source union changed identity or execution scope')
        frozen = datetime.fromisoformat(parent['created_at'])
        _check(created > frozen and (previous_time is None or frozen > previous_time),
               'Source windows must precede their union in chronological order')
        if index:
            _check(parent.get('reassessment', {}).get('parent_campaign') == names[index - 1]
                   and 'functional' in parent['reassessment']['renewed_purposes'],
                   'Functional union must retain complete successive independent windows')
        previous_time = frozen
        sources[name] = parent
        parent_times[name] = _campaign_times(evidence, parent, (*visited, name))
    _check(union['availability_source'] == names[-1] and union['functional_sources'] == names
           and union['behavioral_source'] == names[0],
           'Source selection must keep latest A, every F window and original B')
    expected, times = [], {}
    for purpose, source_names, prefix in (
            ('availability', [names[-1]], 'A'), ('functional', names, 'F'), ('behavioral', [names[0]], 'B')):
        number = 0
        for name in source_names:
            for original in sources[name]['slots']:
                if original['purpose'] != purpose:
                    continue
                number += 1
                slot_name = f'{prefix}{number:02d}'
                expected.append({**original, 'slot': slot_name, 'source_campaign': name,
                                 'source_slot': original['slot']})
                times[slot_name] = parent_times[name][original['slot']]
    _check(campaign['slots'] == expected, 'Source union must retain every original group field and task without selection')
    pending = union['pending_request_ids']
    _check(len(set(pending)) == len(pending), 'Pending request identifiers repeat')
    latest_functional = {item['request_id'] for item in expected
                         if item['purpose'] == 'functional' and item['source_campaign'] == names[-1]}
    _check(set(pending).issubset(latest_functional), 'Pending requests must belong to the complete latest functional group')
    for slot in expected:
        if slot['request_id'] in pending:
            times[slot['slot']] = created
    return times


def _approach(campaign):
    if campaign['policy_version'] == SWAP_EVIDENCE_POLICY_VERSION:
        count = sum(item['purpose'] == 'functional' for item in campaign['slots'])
        return (f'A沿用最新完整10槽，F合并已冻结来源的全部{count}槽，B沿用最初完整7槽；'
                'FAIL、UNKNOWN与未执行槽全部保留。F至少7个确定结果且覆盖率至少80%才出分；'
                '待补任务在v2冻结后执行，历史任务保留各自原时间窗口。提供方构造，操作者签名。')
    refresh = campaign.get('reassessment')
    if not refresh:
        return APPROACH
    names = {'availability': 'A可用性', 'functional': 'F功能', 'behavioral': 'B交易'}
    renewed = '、'.join(names[name] for name in refresh['renewed_purposes'])
    retained = '、'.join(names[name] for name in refresh['retained_purposes']) or '无'
    return f'{renewed}是本次新做的完整检查；{retained}沿用上次已固定的整组正式样本并复核原始证据，未挑选成功样本或改变用途。提供方构造，操作者签名。'


def _window(samples):
    names = {'availability': 'A服务可用性', 'functional': 'F功能任务', 'behavioral': 'B真实交易'}
    parts = []
    for purpose, label in names.items():
        times = [item.observed_at for item in samples if item.sample.purpose == purpose and item.observed_at is not None]
        parts.append(f"{label}：{min(times).isoformat()} 至 {max(times).isoformat()}" if times else f"{label}：尚无实际业务响应")
    return '；'.join(parts)


def verify_swap_identity(evidence, summary_name, canonical, endpoint):
    """Rebuild chain identity and explicitly declared gateway association."""
    summary = evidence.json(summary_name)
    _check(summary.get('schema_version') == 'registered-agent-identity-attribution-v1', 'Unsupported identity evidence')
    _check(normalize_reference(canonical) == canonical, 'Report must retain the real canonical registration')
    _, chain, registry, token = canonical.split(':')
    registered = [item for item in summary['registered'] if item['canonical'] == canonical]
    _check(len(registered) == 1 and integer(chain) == summary['chain_id'], 'Identity summary does not contain this registration')
    selected = registered[0]
    names = []
    for item in summary['sources']:
        _check(evidence.hashes.get(item['path']) == item['sha256'], 'Identity source digest differs')
        evidence.raw(item['path'])
        observed = item['path'].removesuffix('.response.bin') + '.observation.json'
        if observed in evidence.hashes:
            names.append(observed)
    records = evidence.rpc_records([name for name in names if evidence.json(name).get('method') == 'POST'
                                    and evidence.json(name).get('url') == 'https://ethereum.reth.rs/rpc'],
                                   {'https://ethereum.reth.rs/rpc'})
    _check(_lookup(records, 'eth_chainId', []) is not None
           and integer(_lookup(records, 'eth_chainId', [])) == integer(chain), 'Registered chain was not independently read')
    block = hex(integer(selected['block']))
    owner = _lookup(records, 'eth_call', [{'to': registry, 'data': calldata('ownerOf(uint256)', integer(token))}, block])
    uri = _lookup(records, 'eth_call', [{'to': registry, 'data': calldata('tokenURI(uint256)', integer(token))}, block])
    _check(isinstance(owner, str) and len(owner) == 66 and 0 < integer(owner) < 2**160,
           'Original registered owner is absent')
    owner = '0x' + owner[-40:].lower()
    _check(owner == address(selected['owner']) and isinstance(uri, str), 'Registered owner/URI differs')
    from reputation_platform.registration_discovery import _abi_string
    _check(_abi_string(uri) == selected['token_uri'], 'Original tokenURI differs from retained identity')
    card_name = summary['current_card_source']
    card_obs, card_raw = evidence.observed(card_name.removesuffix('.response.bin') + '.observation.json')
    card_url = urlsplit(card_obs['url'])
    _check(card_obs['method'] == 'GET' and card_obs['http_status'] == 200 and card_obs['body_complete']
           and not card_obs['error_kind'] and card_url.scheme == 'https'
           and card_url.path in ('/.well-known/agent-card.json', '/.well-known/agent.json'),
           'Missing complete published well-known service card')
    card = json.loads(card_raw)
    chain_names = {1: 'ethereum', 8453: 'base', 56: 'bsc', 100: 'gnosis'}
    group = card.get('erc8004', {}).get(chain_names.get(integer(chain), str(chain)), {})
    declared = [value for value in group.values() if isinstance(value, dict)]
    _check(any(integer(item.get('agentId', -1)) == integer(token)
               and address(item.get('registry')) == registry for item in declared),
           'Official card does not explicitly name this registered identity')
    _check(address(card['xmtp']['agentAddress']) == owner, 'Service-card account does not match registered owner')
    base = card['url'].rstrip('/')
    _check(endpoint.startswith(base + '/') and urlsplit(endpoint).scheme == 'https', 'Business endpoint is not declared by this card')
    return {'canonical': canonical, 'owner': owner, 'token_uri': selected['token_uri'],
            'registration_chain': integer(chain), 'endpoint_association': 'PROVIDER_DECLARED',
            'ipfs_authenticated': False, 'card': card, 'source_summary': summary_name}


def _unknown(reason):
    return SwapVerification(Verdict.UNKNOWN, reason, [ReportFinding(label='证据尚不充分', verdict=Verdict.UNKNOWN, explanation=reason)])


def _units(raw, decimals):
    digits = str(integer(raw)).zfill(decimals + 1)
    return (digits if decimals == 0 else (digits[:-decimals] + '.' + digits[-decimals:]).rstrip('0').rstrip('.'))


def _task_request(task, protocol):
    data = task['input']
    return SwapRequest(chain_id=data['chain_id'], token_in=data['token_in'], token_out=data['token_out'],
        amount_in=integer(data['amount_raw']), recipient=data['recipient'], executor=data['executor'],
        router=protocol['router'], factory=protocol['factory'], slippage_bps=data['slippage_bps'],
        input_decimals=protocol['tokens'][address(data['token_in'])]['decimals'],
        output_decimals=protocol['tokens'][address(data['token_out'])]['decimals'],
        expected_account_code=protocol.get('execution_account_code'))


def _simulation(records, request, builder):
    facts = plan_facts(request, builder)
    calls = [item for item in records if item['method'] == 'eth_call' and len(item['params']) == 2
             and isinstance(item['params'][0], dict)
             and address(item['params'][0].get('to')) == address(request.executor)
             and item['params'][0].get('data', '').lower() == facts['batch_data']]
    if not calls:
        return None
    _check(len({_canonical(item['params']) for item in calls}) == 1, 'Simulation records use different frozen calls or blocks')
    successful = [item for item in calls if not item['error'] and item['value'] is not None]
    _check(len({_canonical(item['value']) for item in successful}) <= 1, 'Same fixed simulation returned conflicting results')
    item = successful[0] if successful else calls[0]
    block = _lookup(records, 'eth_getBlockByNumber', [item['params'][1], False])
    if block is None:
        return None
    code = _lookup(records, 'eth_getCode', [request.executor, item['params'][1]])
    return {'chain_id': request.chain_id, 'block_number': integer(block['number']),
            'block_hash': block['hash'], 'block_timestamp': integer(block['timestamp']),
            'account_code': code,
            'call': item['params'][0], 'result': item['value'], 'error': item['error']}


def _decimals(records, request, tag):
    for token, expected in ((request.token_in, request.input_decimals), (request.token_out, request.output_decimals)):
        value = _lookup(records, 'eth_call', [{'to': token, 'data': calldata('decimals()')}, tag])
        if value is None:
            return '尚缺该固定区块的独立token decimals原件。'
        if integer(value) != expected:
            return '可信协议配置与链上token decimals不一致，属于平台核验缺项，不能归责Agent。'
    return None


def _metadata_tag(records, request, purpose, send):
    if purpose == 'behavioral' and send:
        receipt = _lookup(records, 'eth_getTransactionReceipt', [send['transactionHash']])
        return hex(integer(receipt['blockNumber'])) if receipt else None
    tags = {item['params'][1] for item in records if item['method'] == 'eth_call'
            and len(item['params']) == 2 and isinstance(item['params'][0], dict)
            and item['params'][0].get('to', '').lower() == request.executor.lower()
            and item['params'][0].get('data', '').lower().startswith('0x34fcd5be')}
    _check(len(tags) <= 1, 'Task simulations use more than one frozen block')
    return next(iter(tags), None)


def _execution(records, request, builder, send):
    if not send:
        return None
    tx_hash = send['transactionHash']
    receipt = _lookup(records, 'eth_getTransactionReceipt', [tx_hash])
    tx = _lookup(records, 'eth_getTransactionByHash', [tx_hash])
    if receipt is None or tx is None:
        return None
    _check(integer(tx['nonce']) == integer(send['nonce']), 'Mined nonce differs from persisted send intent')
    number = integer(receipt['blockNumber']); tag = hex(number)
    block = _lookup(records, 'eth_getBlockByNumber', [tag, False])
    head = _lookup(records, 'eth_blockNumber', [])
    tier = plan_facts(request, builder)['fee_tier']
    pool_word = _lookup(records, 'eth_call', [{'to': request.factory,
        'data': calldata('getPool(address,address,uint24)', request.token_in, request.token_out, tier)}, tag])
    allowance = _lookup(records, 'eth_call', [{'to': request.token_in,
        'data': calldata('allowance(address,address)', request.executor, request.router)}, tag])
    before = _lookup(records, 'eth_getCode', [request.executor, hex(number - 1)])
    after = _lookup(records, 'eth_getCode', [request.executor, tag])
    if any(value is None for value in (block, head, pool_word, allowance, before, after)):
        return None
    _check(isinstance(pool_word, str) and len(pool_word) == 66, 'Factory pool response is malformed')
    return {'expected_transaction_hash': tx_hash, 'transaction': tx, 'receipt': receipt, 'block': block,
            'head': integer(head), 'pool': '0x' + pool_word[-40:], 'allowance_after': integer(allowance),
            'account_code_before': before, 'account_code_after': after}


def _execution_diagnostics(result, records, request, proof):
    """Explain existing independent money facts, without a new scoring weight."""
    if proof is None or result.verdict != Verdict.PASS:
        return
    receipt = proof['receipt']; number = integer(receipt['blockNumber']); tag = hex(number)
    actual = integer(result.facts['actual_out_raw'])
    deltas = []
    for token in (request.token_in, request.token_out):
        subject = request.executor if token == request.token_in else request.recipient
        snapshots = [_lookup(records, 'eth_call', [{'to': token,
            'data': calldata('balanceOf(address)', subject)}, hex(height)]) for height in (number - 1, number)]
        deltas.append(integer(snapshots[1]) - integer(snapshots[0]) if all(v is not None for v in snapshots) else None)
    matched = deltas == [-request.amount_in, actual]
    result.checks.append(ReportFinding(label='资产余额交叉对照', verdict=Verdict.PASS if matched else Verdict.UNKNOWN,
        explanation=(f'账户区块前后输入/输出资产变化为{deltas}整数单位，与同笔事件一致；归属仍以本笔Swap/Transfer为主。'
                     if matched else '块窗口余额不足或存在其它活动，未把整个区块变化强行归于本笔；本笔资产事实依据已核事件。')))
    l2 = integer(receipt['gasUsed']) * integer(receipt['effectiveGasPrice'])
    l1 = integer(receipt['l1Fee']) if receipt.get('l1Fee') is not None else None
    operator = integer(receipt['operatorFee']) if receipt.get('operatorFee') is not None else None
    if operator is None and request.chain_id == 8453:
        value = _lookup(records, 'eth_call', [{'to': '0x420000000000000000000000000000000000000f',
            'data': calldata('getOperatorFee(uint256)', integer(receipt['gasUsed']))}, tag])
        operator = integer(value) if value is not None else None
    if l1 is None or operator is None:
        result.checks.append(ReportFinding(label='本笔网络费用', verdict=Verdict.UNKNOWN,
            explanation=f'已核L2费用{l2}wei；L1或operator分量仍缺来源，未将未知费用当0。'))
        return
    total = l2 + l1 + operator
    result.facts['network_fee_wei'] = str(total)
    before = _lookup(records, 'eth_getBalance', [request.executor, hex(number - 1)])
    after = _lookup(records, 'eth_getBalance', [request.executor, tag])
    agreed = before is not None and after is not None and integer(before) - integer(after) == total
    result.checks.append(ReportFinding(label='本笔网络费用', verdict=Verdict.PASS,
        explanation=f'原收据L2={l2}wei，L1={l1}wei，同块operator={operator}wei；合计{_units(total, 18)} ETH。'
                    + ('与账户ETH区块差额完全一致。' if agreed else '账户块窗口差额另作对照，不据此伪造单笔费用。')))


def _replay(evidence, origin):
    campaign = evidence.json(origin['campaign'])
    policy = campaign['policy_version']
    plan = evidence.json(EXPANDED_PLAN if policy == SWAP_EVIDENCE_POLICY_VERSION else PLAN)
    protocols = evidence.json(PROTOCOLS)
    evidence.raw(ADR)
    evidence.raw(REASSESSMENT_ADR)
    _check(policy == origin['policy_version'] and policy in SWAP_POLICY_VERSIONS,
           'Frozen campaign policy differs')
    slots = campaign['slots']
    ids = [item['request_id'] for item in slots]
    _check(len(set(ids)) == len(ids) and all(item['task_key'] == item['request_id'] for item in slots), 'Task purposes are not disjoint')
    freeze_times = _campaign_times(evidence, campaign)
    identity = verify_swap_identity(evidence, origin['identity_summary'], campaign['registration_reference'], campaign['identity']['endpoint'])
    endpoint = campaign['identity']['endpoint']
    protocol = protocols['chains'][str(campaign['execution_chain_id'])]
    tasks = {item['slot']: item for item in origin['tasks']}
    _check(set(tasks) == {item['slot'] for item in slots}, 'Published task slots differ from campaign')
    explanations, a_times, times = [], [], []
    for slot in slots:
        task = tasks[slot['slot']]
        frozen_raw = evidence.raw(task['frozen_task'])
        _check(_sha(frozen_raw) == slot['task_sha256'], 'Frozen task file changed')
        frozen = json.loads(frozen_raw)
        data = evidence.json(task['input_file'])
        _check(data['request_id'] == frozen['request_id'] == slot['request_id']
               and data['purpose'] == frozen['measurement_purpose'] == slot['purpose'], 'Task purpose or identity changed')
        asset = next((key for key, value in protocol['tokens'].items() if value['symbol'] == frozen['token_in']), None)
        _check(asset is not None and address(data['token_in']) == asset
               and Decimal(frozen['amount']) * 10 ** protocol['tokens'][asset]['decimals'] == integer(data['amount_raw'])
               and data['slippage_bps'] == frozen['slippage_bps'], 'Task input differs from frozen integer amount')
        request = _task_request({'input': data}, protocol)
        body = evidence.json(task['request_file'])
        _check(body == {'url': endpoint, 'method': 'POST', 'body': {
            'tokenIn': data['token_in'], 'tokenOut': data['token_out'], 'amountIn': frozen['amount'],
            'recipient': data['recipient'], 'slippageBps': data['slippage_bps']}}, 'Published business request differs from the frozen task')
        sources = [task['frozen_task'], task['input_file'], task['request_file']]
        observed, elapsed, builder = None, None, None
        result = _unknown('本槽尚无完整业务响应，原位保留，不替换样本。')
        _check(not (task.get('transport_failure') and task.get('response_file')), 'One business attempt has conflicting complete/failure receipts')
        if task.get('transport_failure'):
            failure = evidence.json(task['transport_failure'])
            _check(failure['request_id'] == data['request_id'] and failure['response_complete'] is False,
                   'Transport failure belongs to another business task')
            observed = datetime.fromisoformat(failure['started_at'])
            elapsed = float(failure['elapsed_ms'])
            _check(freeze_times[slot['slot']] <= observed and isfinite(elapsed) and elapsed >= 0
                   and datetime.fromisoformat(failure['failed_at']) >= observed, 'Original transport timing is invalid')
            sources.append(task['transport_failure']); times.append(observed)
            if slot['purpose'] == 'availability':
                a_times.append(observed)
            result = _unknown(f"客户端业务传输未完整返回（{failure.get('cause_code') or failure.get('error_kind') or 'transport error'}）；保留真实失败计时，不推定Agent失败。")
        if task.get('preflight_failure'):
            failure = evidence.json(task['preflight_failure'])
            _check(failure['request_id'] == data['request_id'] and failure['kind'] == 'operator-rpc-transport',
                   'Sanitized operator failure belongs to another task')
            sources.append(task['preflight_failure'])
            result = _unknown(f"操作者前置核验发生{failure['errors'][-1]['error_kind']}，未取得该槽业务交付；保留UNKNOWN，不归责Agent。")
        for failure in task.get('failure_observations', []):
            obs = evidence.json(failure)
            request_body = json.loads(obs['request_json'])
            _check(obs['url'] in protocol['rpc_urls'] and obs['method'] == 'POST'
                   and request_body['method'] in {'eth_chainId', 'eth_blockNumber', 'eth_getBlockByNumber',
                                                  'eth_getCode', 'eth_getBalance'}
                   and obs.get('error_kind'), 'Failure evidence must be an actual signature-free RPC transport failure')
            sources.append(failure)
            result = _unknown(f"操作者前置只读核验发生{obs['error_kind']}，本任务未取得业务交付；属于UNKNOWN，不归责Agent。")
        if task.get('response_file'):
            sources.extend([task['response_file'], task['observation_file']])
            raw = evidence.raw(task['response_file']); http = evidence.json(task['observation_file'])
            _check(http['request_id'] == data['request_id'] and http['response_sha256'] == _sha(raw)
                   and http['url'] == endpoint and http['method'] == 'POST', 'Business observation binding differs')
            observed = datetime.fromisoformat(http['started_at'])
            _check(freeze_times[slot['slot']] <= observed and datetime.fromisoformat(http['received_at']) >= observed,
                   'Business task predates its original frozen campaign')
            elapsed = float(http['elapsed_ms'])
            _check(isfinite(elapsed) and elapsed >= 0, 'Business timing is not finite')
            times.append(observed)
            try:
                builder = json.loads(raw)
            except ValueError:
                builder = None
            if http['status'] == 200 and isinstance(builder, dict):
                if slot['purpose'] == 'availability':
                    if builder.get('status') == 'ready' and all(key in builder for key in ('quote', 'transactions', 'execution')):
                        result = SwapVerification(Verdict.PASS, '真实付费业务完整返回可用兑换方案；未把付款挑战当业务成功。')
                    else:
                        result = SwapVerification(Verdict.FAIL, '完整业务响应未提供契约要求的兑换方案。')
                else:
                    records = evidence.rpc_records(task['rpc_observations'], set(protocol['rpc_urls']))
                    sources.extend(task['rpc_sources'])
                    chain_read = _lookup(records, 'eth_chainId', [])
                    if chain_read is not None:
                        _check(integer(chain_read) == request.chain_id, 'Business proof belongs to another execution chain')
                    send = evidence.json(task['send_intent']) if task.get('send_intent') else None
                    if task.get('send_intent'):
                        sources.append(task['send_intent'])
                        _check(send['requestId'] == data['request_id'] and send['chainId'] == request.chain_id
                               and address(send['buyer']) == address(request.executor) and send['maxAttempts'] == 1,
                               'Broadcast belongs to another task or execution scope')
                    tag = _metadata_tag(records, request, slot['purpose'], send)
                    gap = _decimals(records, request, tag) if tag else '尚无用于独立decimals核验的固定区块。'
                    initial = verify_swap_function(request, builder, None)
                    if gap:
                        result = _unknown(gap)
                    elif not initial.facts:
                        result = initial
                    elif chain_read is None:
                        result = _unknown('尚无独立执行链号证明。')
                    elif slot['purpose'] == 'functional':
                        sim = _simulation(records, request, builder)
                        result = verify_swap_function(request, builder, sim)
                    else:
                        proof = _execution(records, request, builder, send)
                        result = verify_swap_execution(request, builder, proof, plan['confirmation_distance'])
                        _execution_diagnostics(result, records, request, proof)
            else:
                result = _unknown(f"业务HTTP状态为{http['status']}或响应不完整；尚无独立归责证据，不扣Agent分。")
            if slot['purpose'] == 'availability':
                a_times.append(observed)
        purpose = MeasurementPurpose(slot['purpose'])
        sample = ScoredSample(sample_id=f"{policy}:{slot['slot']}:{data['request_id']}",
            task_key=data['request_id'], purpose=purpose, verdict=result.verdict,
            elapsed_ms=elapsed if purpose == MeasurementPurpose.AVAILABILITY else None,
            reason=result.reason, evidence=list(dict.fromkeys(sources)))
        minimum = result.facts.get('minimum_out_raw', '尚无')
        actual = result.facts.get('actual_out_raw', result.facts.get('simulated_out_raw', '尚无'))
        output_asset = protocol['tokens'][address(data['token_out'])]
        claimed = '尚无完整可解析的实际业务交付。'
        if isinstance(builder, dict) and isinstance(builder.get('quote'), dict):
            output = builder['quote'].get('tokenOut', {})
            if output.get('estimatedAmountRaw') is not None and output.get('minimumAmountRaw') is not None:
                try:
                    claimed = (f"服务报价{_units(output['estimatedAmountRaw'], output_asset['decimals'])} {output_asset['symbol']}，"
                               f"最低{_units(output['minimumAmountRaw'], output_asset['decimals'])} {output_asset['symbol']}；报价不是实际成交结果。")
                except (ValueError, TypeError):
                    claimed = '服务已返回报价字段，但无法按契约整数单位解析；原响应完整保留。'
                if output.get('symbol') and output['symbol'] != output_asset['symbol']:
                    result.checks.append(ReportFinding(label='展示名称与真实资产的区别', verdict=Verdict.FAIL,
                        explanation=f"服务显示{output['symbol']}，真实token地址对应{output_asset['symbol']}。本政策资金约束按地址及整数单位判定，这项标签问题单列保留。"))
        independent = result.reason
        if actual != '尚无':
            independent += (f" {'真实到账' if purpose == MeasurementPurpose.BEHAVIORAL else '独立模拟输出'}"
                            f"{_units(actual, output_asset['decimals'])} {output_asset['symbol']}，最低"
                            f"{_units(minimum, output_asset['decimals'])} {output_asset['symbol']}。")
        if result.facts.get('network_fee_wei') is not None:
            independent += f" 本笔网络费{_units(result.facts['network_fee_wei'], 18)} ETH，服务费和兑换本金另计。"
        explanations.append(SampleExplanation(sample=sample, observed_at=observed,
            title=f"{slot['slot']} · {protocol['tokens'][address(data['token_in'])]['symbol']} → {protocol['tokens'][address(data['token_out'])]['symbol']}",
            input_summary=f"{frozen['amount']} {frozen['token_in']}；执行链{data['chain_id']}；收款人{data['recipient']}；滑点{data['slippage_bps']}bps。",
            claimed_output=claimed,
            independent_result=independent,
            checks=result.checks or [ReportFinding(label='业务入口与响应', verdict=result.verdict, explanation=result.reason)],
            capability_id=CAPABILITY))
    _check(all((later - earlier).total_seconds() >= plan['availability_interval_seconds']
               for earlier, later in zip(a_times, a_times[1:])), 'Availability requests did not preserve the frozen interval')
    missing = ['仅覆盖ERC20兑换方案及其本人授权执行；批量支付、其它协议、策略收益和ACP六项服务不由本报告外推。',
               '提供方与注册身份的端点关联来自公开卡显式声明及匹配链上owner；未取得tokenURI对应IPFS内容，不称其已认证。']
    if campaign.get('reassessment') or campaign.get('aggregation'):
        missing.append(_approach(campaign) + '原PARTIAL报告保留，不声称全部样本同时新执行。')
    coverage = CapabilityCoverage(capability_id=CAPABILITY, operation='ERC20兑换方案与真实兑换履约',
        description='接收资产、金额和滑点，构造授权及兑换calldata；操作者自行签名，独立核验真实链上结果。',
        protocol=CHECKER, tested_scope='Base上的受支持Uniswap V3精确输入单池路径，公开注册链与执行链分别取证。',
        sample_ids=[item.sample.sample_id for item in explanations],
        findings=[ReportFinding(label='执行角色', verdict=Verdict.PASS, explanation='Agent提供方案；操作者控制的账户签名和执行，不冒充Agent自主交易。')],
        missing_evidence=missing, capability_type='asset-swap-builder', checker_id=CHECKER, checker_version='v1')
    return campaign, identity, explanations, coverage, missing, times


def verify_swap_report_sources(root, report, hashes):
    origins = [name for name in hashes if Path(name).name == ORIGIN]
    _check(len(origins) == 1, 'Swap report requires one authenticated origin')
    evidence = SwapEvidence(root, hashes)
    origin = evidence.json(origins[0])
    campaign, identity, samples, coverage, limitations, _ = _replay(evidence, origin)
    _check(report.policy_version == campaign['policy_version'] and report.registration_reference == identity['canonical']
           and report.candidate_key == campaign['candidate_key'] and report.name == campaign['identity']['name'],
           'Report identity differs from its verified sources')
    _check(report.scope == SCOPE and report.scope_exclusions == EXCLUSIONS and report.approach == _approach(campaign)
           and report.evaluation_window == _window(samples),
           'Report claims a scope different from the frozen policy')
    _check([value.model_dump(mode='json') for value in report.samples] == [value.model_dump(mode='json') for value in samples]
           and [value.model_dump(mode='json') for value in report.capabilities] == [coverage.model_dump(mode='json')],
           'Report verdicts or capability coverage differ from original evidence replay')
    _check(all(value in report.limitations for value in limitations), 'Report omitted the identity/scope limitations')
    return identity['canonical']


def export_swap_campaign(root: Path, campaign_file: Path, directory: Path) -> Path:
    """Copy a strict allowlist; never read wallet signatures or payment headers."""
    root, campaign_file, directory = root.resolve(), campaign_file.resolve(), directory.resolve()
    _check(campaign_file.is_relative_to(root / 'runtime') and directory.is_relative_to(root / 'runtime')
           and not any('.private' in part.lower() for part in directory.parts), 'Public export must be a new runtime directory')
    directory.mkdir(parents=True, exist_ok=False)
    inputs = {}

    def remember(path):
        path = path.resolve()
        _check(path.is_relative_to(root) and path.is_file()
               and not any('.private' in part.lower() for part in path.parts), 'Only public selected sources enter the report')
        name = path.relative_to(root).as_posix()
        inputs[name] = _sha(path.read_bytes())
        return name

    def save(name, value):
        path = directory / name
        _write(path, value)
        return remember(path)

    def copy(source, name):
        target = directory / name
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open('xb') as stream:
            stream.write(source.read_bytes())
        return remember(target)

    campaign = json.loads(campaign_file.read_bytes())
    expanded = campaign.get('policy_version') == SWAP_EVIDENCE_POLICY_VERSION
    _check(campaign.get('schema_version') == ('swap-campaign-v2' if expanded else 'swap-campaign-v1')
           and campaign['policy_version'] in SWAP_POLICY_VERSIONS,
           'Expected a pre-frozen swap campaign')
    for name in (PLAN, PROTOCOLS, ADR, REASSESSMENT_ADR, *((EXPANDED_PLAN, EXPANDED_ADR) if expanded else ())):
        remember(root / name)
    _check('candidate_key' in campaign, 'Frozen campaign needs a stable candidate key')
    campaign_name = copy(campaign_file, 'campaign.json')

    def campaign_dependencies(value, seen=()):
        for entry in value.get('inputs', []):
            path = root / entry['path']
            _check(_sha(path.read_bytes()) == entry['sha256'], 'Frozen campaign dependency changed before export')
            remember(path)
        refresh = value.get('reassessment')
        if refresh:
            _check(refresh['parent_campaign'] not in seen, 'Cyclic reassessment parent')
            remember(root / REASSESSMENT_ADR)
            parent = root / refresh['parent_campaign']
            _check(_sha(parent.read_bytes()) == refresh['parent_campaign_sha256'], 'Reassessment parent changed before export')
            remember(parent)
            campaign_dependencies(json.loads(parent.read_bytes()), (*seen, refresh['parent_campaign']))
        for entry in value.get('aggregation', {}).get('parents', []):
            _check(entry['path'] not in seen, 'Cyclic source aggregation parent')
            parent = root / entry['path']
            _check(_sha(parent.read_bytes()) == entry['sha256'], 'Source aggregation parent changed before export')
            remember(parent)
            campaign_dependencies(json.loads(parent.read_bytes()), (*seen, entry['path']))

    campaign_dependencies(campaign)
    identity_name = campaign['identity']['source_summary']
    identity_path = root / identity_name
    identity = json.loads(identity_path.read_bytes())
    remember(identity_path)
    for item in identity['sources']:
        source = root / item['path']
        _check(_sha(source.read_bytes()) == item['sha256'], 'Retained identity source changed')
        remember(source)
        observation = source.with_name(source.name.removesuffix('.response.bin') + '.observation.json')
        if observation.is_file():
            remember(observation)
    protocol = json.loads((root / PROTOCOLS).read_bytes())['chains'][str(campaign['execution_chain_id'])]
    tokens = protocol['tokens']
    items = []
    for slot in campaign['slots']:
        task_path = (root / slot['task_path']).resolve()
        _check(task_path.is_relative_to(root / 'runtime') and task_path.parent.name == 'tasks'
               and task_path.name == slot['request_id'] + '.json'
               and _sha(task_path.read_bytes()) == slot['task_sha256'], 'Frozen task source changed')
        task = json.loads(task_path.read_bytes())
        token_in = next((key for key, value in tokens.items() if value['symbol'] == task['token_in']), None)
        _check(token_in is not None, 'Frozen task asset is not in trusted protocol configuration')
        token_out = next((key for key in tokens if key != token_in), None)
        runs_root = task_path.parent.parent / 'runs'
        _check(runs_root.is_relative_to(root / 'runtime'), 'Task run directory must remain in runtime')
        run = runs_root / task['request_id']
        input_data = {'request_id': task['request_id'], 'purpose': task['measurement_purpose'],
            'chain_id': campaign['execution_chain_id'], 'executor': campaign['buyer'], 'recipient': campaign['buyer'],
            'token_in': token_in, 'token_out': token_out,
            'amount_raw': str(int(Decimal(task['amount']) * 10 ** tokens[token_in]['decimals'])),
            'slippage_bps': task['slippage_bps']}
        body = {'tokenIn': token_in, 'tokenOut': token_out, 'amountIn': task['amount'],
                'recipient': campaign['buyer'], 'slippageBps': task['slippage_bps']}
        if (run / 'RUN_INTENT.private.json').is_file():
            # This file contains no wallet signature; select only these business
            # fields, never copy its fee authorization or source/config fields.
            actual = json.loads((run / 'RUN_INTENT.private.json').read_bytes())
            _check(actual['requestId'] == task['request_id'] and actual['purpose'] == task['measurement_purpose']
                   and actual['chainId'] == input_data['chain_id'] and address(actual['buyer']) == address(campaign['buyer'])
                   and address(actual['tokenIn']) == token_in and address(actual['tokenOut']) == token_out
                   and actual['amountRaw'] == input_data['amount_raw']
                   and _normalized(actual['body']) == _normalized(body), 'Actual invocation differs from frozen task')
            body = actual['body']
            input_data.update(token_in=actual['tokenIn'], token_out=actual['tokenOut'])
        prefix = 'sources/' + slot['slot']
        business_request = {'url': campaign['identity']['endpoint'], 'method': 'POST', 'body': body}
        captured_request = run / 'paid-builder.request.private.json'
        if captured_request.is_file():
            captured_raw = captured_request.read_bytes()
            captured = json.loads(captured_raw)
            # Extract exactly the three noncredential fields; payment headers
            # never enter a public object, log, manifest input or attachment.
            actual_request = {key: captured[key] for key in ('url', 'method', 'body')}
            _check(_normalized(actual_request) == _normalized(business_request), 'Actual sent business body differs from the frozen request')
            business_request = actual_request
        item = {'slot': slot['slot'], 'frozen_task': copy(task_path, prefix + '/task.json'),
            'input_file': save(prefix + '/input.json', input_data),
            'request_file': save(prefix + '/business-request.json', business_request),
            'rpc_observations': [], 'rpc_sources': []}
        response, receipt = run / 'paid-builder.response.private.json', run / 'paid-builder.receipt.json'
        value = json.loads(receipt.read_bytes()) if receipt.is_file() else None
        if (response.is_file() and captured_request.is_file() and value is not None
            and value.get('responseComplete', True) and value.get('receivedAt')):
            item['response_file'] = copy(response, prefix + '/business-response.json')
            item['observation_file'] = save(prefix + '/business-observation.json', {
                'request_id': task['request_id'], 'url': campaign['identity']['endpoint'], 'method': 'POST',
                'status': value['status'], 'started_at': value['startedAt'], 'received_at': value['receivedAt'],
                'elapsed_ms': value['elapsedMs'], 'response_sha256': _sha(response.read_bytes()),
                'measurement_purpose': task['measurement_purpose'], 'timing': 'paid-business-post-send-to-complete-response'})
        elif value is not None and value.get('responseComplete') is False:
            item['transport_failure'] = save(prefix + '/business-transport-failure.json', {
                'request_id': task['request_id'], 'status': value.get('status'),
                'started_at': value['startedAt'], 'failed_at': value['failedAt'], 'elapsed_ms': value['elapsedMs'],
                'response_complete': False, 'error_kind': value.get('errorKind'), 'error_code': value.get('errorCode'),
                'cause_kind': value.get('causeKind'), 'cause_code': value.get('causeCode')})
        elif (run / 'fee-rpc.private').is_dir():
            item['failure_observations'] = []
            errors = []
            for path in sorted((run / 'fee-rpc.private').glob('*.observation.json')):
                value = json.loads(path.read_bytes())
                request = json.loads(value['request_json'])
                if value.get('error_kind'):
                    # Some failures contain an EIP1271/payment signature in
                    # request_json. Only these observation metadata are public.
                    errors.append({key: value.get(key) for key in
                        ('request_key', 'observed_at', 'http_status', 'elapsed_ms', 'error_kind')})
                if value.get('error_kind') and request.get('method') in {
                        'eth_chainId', 'eth_blockNumber', 'eth_getBlockByNumber', 'eth_getCode', 'eth_getBalance'}:
                    item['failure_observations'].append(copy(path, prefix + '/failed-preflight/' + path.name))
            if errors:
                item['preflight_failure'] = save(prefix + '/preflight-failure.json', {
                    'request_id': task['request_id'], 'kind': 'operator-rpc-transport', 'errors': errors})
        if (run / 'SEND_INTENT.private.json').is_file():
            send = json.loads((run / 'SEND_INTENT.private.json').read_bytes())
            item['send_intent'] = save(prefix + '/send-intent.json', {key: send[key] for key in
                ('requestId', 'transactionHash', 'chainId', 'buyer', 'nonce', 'maxAttempts', 'createdAt')})
        rpc_dirs = ([run / 'swap-rpc.private'] if (run / 'swap-rpc.private').is_dir() else [])
        rpc_dirs.extend(sorted(run.glob('independent-proof-*')))
        rpc_dirs.extend(sorted(run.glob('decimals-proof-*')))
        for rpc_dir in rpc_dirs:
            # Only transaction-free RPC observations from these explicit phases.
            # fee-rpc, send-rpc, Privy and signed transaction files are excluded.
            for obs_path in sorted(rpc_dir.glob('*.observation.json')):
                obs = json.loads(obs_path.read_bytes())
                request = json.loads(obs['request_json'])
                _check(obs['url'] in protocol['rpc_urls'] and obs['method'] == 'POST'
                       and request.get('method') in READ_METHODS, 'Public export found an unexpected RPC scope')
                if request['method'] == 'eth_call':
                    data = request['params'][0].get('data', '')
                    from reputation_core.prediction_chain import selector
                    signatures = ('balanceOf(address)', 'allowance(address,address)', 'decimals()',
                        'getPool(address,address,uint24)', 'quoteExactInputSingle((address,address,uint256,uint24,uint160))',
                        'executeBatch((address,uint256,bytes)[])', 'getL1FeeUpperBound(uint256)', 'getOperatorFee(uint256)')
                    _check(data[:10].lower() in {selector(value) for value in signatures},
                           'Only reviewed signature-free business RPC calls may enter public report')
                sub = prefix + '/rpc/' + rpc_dir.name.replace('.private', '')
                item['rpc_observations'].append(copy(obs_path, sub + '/' + obs_path.name))
                item['rpc_sources'].append(item['rpc_observations'][-1])
                if obs.get('response_file'):
                    raw = rpc_dir / obs['response_file']
                    _check(raw.parent == rpc_dir and _sha(raw.read_bytes()) == obs['response_sha256'], 'Original RPC bytes changed')
                    item['rpc_sources'].append(copy(raw, sub + '/' + raw.name))
                original_plan = obs_path.with_name(obs_path.name.removesuffix('.observation.json') + '.request-plan.json')
                if original_plan.is_file():
                    item['rpc_sources'].append(copy(original_plan, sub + '/' + original_plan.name))
        items.append(item)
    origin = {'schema_version': 'evm-swap-report-origin-v2' if expanded else 'evm-swap-report-origin-v1',
              'policy_version': campaign['policy_version'],
              'campaign': campaign_name, 'identity_summary': identity_name, 'tasks': items}
    save(ORIGIN, origin)
    _write(directory / 'manifest.json', {'schema_version': 'evaluation-input-manifest-v1',
        'implementation_note': {'path': EXPANDED_ADR if expanded else REASSESSMENT_ADR,
                                'sha256': inputs[EXPANDED_ADR if expanded else REASSESSMENT_ADR]},
        'inputs': [{'path': name, 'sha256': digest} for name, digest in sorted(inputs.items())]})
    return directory


def build_swap_report(root: Path, directory: Path) -> EvaluationReport:
    root, directory = root.resolve(), directory.resolve()
    manifest = json.loads((directory / 'manifest.json').read_bytes())
    hashes = {item['path']: item['sha256'] for item in manifest['inputs']}
    evidence = SwapEvidence(root, hashes)
    origin_name = (directory / ORIGIN).relative_to(root).as_posix()
    origin = evidence.json(origin_name)
    campaign, identity, samples, coverage, limitations, times = _replay(evidence, origin)
    report = EvaluationReport(policy_version=campaign['policy_version'], candidate_key=campaign['candidate_key'],
        name=campaign['identity']['name'], registration_reference=identity['canonical'],
        generated_at=datetime.now(timezone.utc),
        scope=SCOPE,
        scope_exclusions=EXCLUSIONS,
        evaluation_window=_window(samples),
        approach=_approach(campaign),
        samples=samples, capabilities=[coverage], source_references=sorted(hashes), limitations=limitations)
    verify_swap_report_sources(root, report, hashes)
    _write(directory / 'report.json', report.model_dump(mode='json'))
    with (directory / 'report.html').open('x', encoding='utf-8') as stream:
        stream.write(render_evaluation_report(report))
    return report
