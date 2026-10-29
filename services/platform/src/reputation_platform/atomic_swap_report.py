"""Version-isolated, offline replay of prospective atomic ERC20 swap evidence.

HTTP fields are mapped by a frozen JSON-pointer configuration; judgments follow
the generic call protocol and independent chain evidence, never an Agent name.
"""
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import json
from math import ceil, isfinite
from pathlib import Path
import re
from urllib.parse import urlsplit
from uuid import UUID

from eth_hash.auto import keccak

from reputation_core import MeasurementPurpose, ReportFinding, SampleExplanation, ScoredSample, Verdict
from reputation_core.application import normalize_reference
from reputation_core.prediction_chain import calldata
from reputation_core.reporting import EvaluationReport
from reputation_core.scoring import POINT_POLICY_VERSION
from reputation_core.shared_scoring import SharedAssessment
from reputation_core.swap import address, encode_batch, hex_bytes, integer
from reputation_platform.atomic_swap_protocol import normalize_atomic_swap, verify_atomic_swap_intent
from reputation_platform.registration_discovery import verify_registration_proof
from reputation_platform.public_service_identity import verify_service_identity, identity_limitations
from reputation_platform.swap_report import SwapEvidence, _check, _lookup, _normalized, _sha, _write
from reputation_platform.unsigned_swap_protocol import UnsupportedUnsignedSwap, UnsignedSwapMismatch
from reputation_platform import unsigned_swap_report as retained

ADAPTER = 'retained-atomic-swap-campaign-v1'
ORIGIN = 'atomic-swap-report-origin.json'
ADR = 'docs/adr/0032-atomic-swap-campaign-replay.md'
CLOCK_ADR = 'docs/adr/0036-deadline-default-request-interval.md'
METRICS = {'complete-response', 'intent-binding', 'default-contract', 'call-safety',
           'execution-effect', 'safe-rejection', 'onchain-fulfillment'}
UNKNOWN = (Verdict.UNKNOWN, '缺少本任务可独立核验的原件；保留冻结槽位。', {})
LIMITATIONS = [
    '只评价前瞻选择的ERC20原子兑换范围，未测能力另列；不强制测全声明才能评价已测范围。',
    '同一经济任务的报价、构建、模拟、实际执行共享task_key；多个HTTP请求不是多个任务。',
    '没有公开SLA时只展示实测HTTP耗时，不臆造延迟扣分门槛。',
    '方案和固定块模拟不等于真实成交；服务费、保护退出不补正常履约B。',
    'SWEEP约束Router总余额，不直接保证收款净增；独立效果扣除Router旧输出余额并核三类授权清零。',
    'B使用完整原子交易、可信canonical回执、ERC20净事件与前后余额、64块确认距离；不声称finalized。',
]


def _time(value):
    result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    _check(result.tzinfo is not None, 'Evidence time needs an explicit timezone')
    return result


def _pointer(value, pointer):
    _check(isinstance(pointer, str) and (not pointer or pointer.startswith('/')), 'Expected a JSON pointer')
    for part in pointer.split('/')[1:]:
        part = part.replace('~1', '/').replace('~0', '~')
        value = value[int(part)] if isinstance(value, list) else value[part]
    return value


def _origin(url):
    parsed = urlsplit(url)
    _check(parsed.scheme == 'https' and parsed.hostname and not parsed.username and not parsed.password
           and not parsed.fragment and parsed.port in (None, 443), 'Expected a fixed public HTTPS service')
    return parsed.scheme, parsed.hostname.lower(), parsed.port or 443


def _fingerprint(value):
    return '0x' + keccak(hex_bytes(value)).hex()


def predict_slipstream_pool(factory, implementation, token_a, token_b, tick_spacing):
    """ERC1167 CREATE2 address from the verified router's actual pool formula."""
    tokens = sorted([address(token_a), address(token_b)])
    spacing = integer(tick_spacing)
    _check(tokens[0] != tokens[1] and 0 < spacing < 2**23, 'Invalid explicit CL pool key')
    salt = keccak(b''.join(int(value, 16).to_bytes(32, 'big') for value in tokens) + spacing.to_bytes(32, 'big'))
    init = bytes.fromhex('3d602d80600a3d3981f3363d3d373d3d3d363d73' + address(implementation)[2:]
                         + '5af43d82803e903d91602b57fd5bf3')
    return '0x' + keccak(b'\xff' + bytes.fromhex(address(factory)[2:]) + salt + keccak(init))[-20:].hex()


def atomic_evidence_calls(plan):
    """Exact sixteen-CALL measurement envelope, usable before root signs anything.

    Its central seven calls are provider output. Getter calls surround the same
    atomic batch and are never represented as extra tasks or execution trades.
    """
    fact = normalize_atomic_swap(plan)
    owner, router, permit2 = fact['required_executor'], fact['router'], fact['permit2']
    token, output = fact['token_in'], fact['token_out']
    balances = [
        {'target': token, 'value': '0', 'data': calldata('balanceOf(address)', owner)},
        {'target': output, 'value': '0', 'data': calldata('balanceOf(address)', owner)},
        {'target': output, 'value': '0', 'data': calldata('balanceOf(address)', router)},
    ]
    approvals = [
        {'target': token, 'value': '0', 'data': calldata('allowance(address,address)', owner, permit2)},
        {'target': token, 'value': '0', 'data': calldata('allowance(address,address)', owner, router)},
        {'target': permit2, 'value': '0', 'data': calldata('allowance(address,address,address)', owner, token, router)},
    ]
    calls = [{'target': row['to'], 'value': '0', 'data': row['data']} for row in fact['calls']]
    return [*balances, *calls, *balances, *approvals]


def atomic_post_calls(plan):
    """Six independent post-receipt balance/allowance getters, in fixed order."""
    return atomic_evidence_calls(plan)[10:]


def _snapshot(evidence, value):
    _check(evidence.hashes.get(value['path']) == value['sha256'], 'Frozen snapshot changed')
    evidence.raw(value['path'])


def _campaign_lineage(evidence, path):
    versions, visited = [], set()
    while path:
        _check(path not in visited, 'Atomic campaign lineage contains a cycle')
        visited.add(path)
        plan = evidence.json(path)
        _check(plan.get('schema_version') == 'atomic-swap-campaign-v1' and plan.get('status') == 'FROZEN'
               and plan.get('frozen_at'), 'Atomic campaign must be frozen before real requests')
        versions.append(plan)
        previous = plan.get('previous_plan')
        if previous:
            _snapshot(evidence, previous)
        path = previous['path'] if previous else None
    versions.reverse()
    clocks, previous = {}, None
    for plan in versions:
        when = _time(plan['frozen_at'])
        if previous:
            _check(when >= _time(previous['frozen_at']), 'Atomic append predates its predecessor')
            for field in ('schema_version', 'candidate_key', 'name', 'registration_reference', 'registered_service',
                          'chain_id', 'executor', 'response_mapping', 'source_snapshot', 'identity_declaration_snapshot',
                          'protocol_binding', 'scoring_contract', 'capability', 'scope_exclusions'):
                _check(plan.get(field) == previous.get(field), 'Atomic append changed frozen ' + field)
            _check(plan['scope'].startswith(previous['scope']), 'Atomic append rewrote its original scope')
            if previous.get('deadline_default_clock_policy'):
                _check(plan.get('deadline_default_clock_policy') == previous['deadline_default_clock_policy'],
                       'Atomic append changed its frozen deadline clock policy')
            old_tasks = {row['task_key']: row for row in previous['tasks']}
            new_tasks = {row['task_key']: row for row in plan['tasks']}
            _check(all(new_tasks.get(key) == row for key, row in old_tasks.items()),
                   'Atomic append changed or removed an original task')
            current_cases = {row['case_id']: row for row in plan['cases']}
            for old in previous['cases']:
                new = current_cases.get(old['case_id'])
                _check(new and {k: v for k, v in new.items() if k != 'planned_task_ids'}
                       == {k: v for k, v in old.items() if k != 'planned_task_ids'}
                       and new['planned_task_ids'][:len(old['planned_task_ids'])] == old['planned_task_ids'],
                       'Atomic append rewrote frozen case rules or removed members')
        for task in plan['tasks']:
            clocks.setdefault(task['task_key'], when)
        previous = plan
    return versions[-1], clocks


def _frozen_plan(evidence, source):
    plan, clocks = _campaign_lineage(evidence, source['campaign_plan'])
    _check(plan.get('deadline_default_clock_policy') in (None, 'request-interval-v1'),
           'Unsupported deadline default clock measurement version')
    if plan.get('deadline_default_clock_policy') == 'request-interval-v1':
        evidence.raw(CLOCK_ADR)
    _check(plan.get('schema_version') == 'atomic-swap-campaign-v1' and plan.get('status') == 'FROZEN'
           and plan.get('frozen_at'), 'Atomic campaign must be frozen before real requests')
    _time(plan['frozen_at'])
    for field in ('candidate_key', 'name', 'registration_reference', 'registered_service'):
        _check(source[field] == plan[field], 'Source differs from frozen ' + field)
    if 'response_mapping' in source:
        _check(source['response_mapping'] == plan['response_mapping'], 'Response mapping changed after freeze')
    scoring = plan['scoring_contract']
    _check(scoring['policy'] == POINT_POLICY_VERSION and scoring['shared_schema'] == 'shared-task-assessment-v3'
           and scoring['weights'] == {'availability': 30, 'functional': 40, 'behavioral': 30}
           and scoring['minimum_confirmation_distance'] == 64 and scoring.get('response_sla_ms') is None,
           'Atomic source cannot change the shared v3 contract or invent an SLA')
    _check(plan['tasks'] and len({x['task_key'] for x in plan['tasks']}) == len(plan['tasks'])
           and len({x['task_id'] for x in plan['tasks']}) == len(plan['tasks']), 'Duplicated campaign task')
    for task in plan['tasks']:
        _check(UUID(task['task_key']).version == 4, 'A new task must use a persisted UUIDv4')
        _check(task['requests'] and len({x['stage'] for x in task['requests']}) == len(task['requests']),
               'Missing or repeated task stage')
        _check(all(_origin(x['url']) == _origin(plan['registered_service']) and x['method'] in ('GET', 'POST')
                   for x in task['requests']), 'Requests are outside the registered service origin')
        _check(not task['planned_actual_execution'] or not task['expected']['safe_rejection'],
               'An invalid-input task must not plan an asset execution')
    _snapshot(evidence, plan['source_snapshot'])
    observation, raw = evidence.observed(plan['source_snapshot']['observation'])
    _check(raw and _sha(raw) == plan['source_snapshot']['sha256'] and observation['http_status'] == 200
           and observation['body_complete'] and not observation['error_kind']
           and observation['method'] == 'GET' and _origin(observation['url']) == _origin(plan['registered_service']),
           'Declaration snapshot lacks its original public service response')
    if plan.get('identity_declaration_snapshot'):
        _snapshot(evidence, plan['identity_declaration_snapshot'])
    binding = plan.get('protocol_binding')
    if isinstance(binding, dict) and set(binding) == {'path', 'sha256'}:
        _snapshot(evidence, binding)
        binding = evidence.json(binding['path'])
    if binding is not None:
        roles = ('router', 'permit2', 'cl_factory', 'cl_implementation', 'executor')
        commitments = binding.get('runtime_keccak', {})
        _check(not str(binding.get('status', '')).startswith('PREPARATION')
               and all(isinstance(commitments.get(role), str) and len(commitments[role]) == 66
                       and commitments[role].startswith('0x')
                       and all(char in '0123456789abcdefABCDEF' for char in commitments[role][2:])
                       for role in roles),
               'Frozen deployment binding has unfilled or unreviewed runtime commitments')
    return plan, binding, clocks


def _identity(evidence, source, plan):
    canonical = normalize_reference(source['registration_reference'])
    _check(canonical == source['registration_reference'], 'Expected a canonical registered identity')
    proof = evidence.json(source['registration_proof'])
    for ref in proof['source_refs']:
        _snapshot(evidence, ref)
    identity = verify_service_identity(evidence.root, source['registration_proof'], canonical,
                                       chain_verifier=verify_registration_proof)
    _check(identity['public_registry_verified'], 'Identity lacks authenticated retained public registration evidence')
    endpoints = [x.get('endpoint') for x in (identity.get('document') or {}).get('services', [])]
    _check(plan['registered_service'] in endpoints, 'Registered document does not bind the selected service')
    # Registry owner is not compared to the separate buyer/executor wallet.
    return canonical


def _http_task(evidence, planned, item, frozen_at):
    names = item.get('http_observations', [])
    _check(len(names) <= len(planned['requests']), 'Unplanned extra HTTP stage')
    rows = []
    last_when = None
    for request, name in zip(planned['requests'], names):
        obs, raw = evidence.observed(name)
        _check(obs['url'] == request['url'] and obs['method'] == request['method']
               and (json.loads(obs['request_json']) if obs.get('request_json') is not None else None) == request.get('json'),
               'Actual HTTP stage differs from frozen request')
        when = _time(obs['observed_at'])
        _check(when >= frozen_at and (last_when is None or when >= last_when), 'Business request predates its freeze or stage')
        last_when = when
        complete = bool(raw and obs.get('body_complete')
                        and obs.get('error_kind') in (None, 'http_status_not_success'))
        try:
            body = json.loads(raw) if complete else None
        except (ValueError, UnicodeDecodeError):
            body = None
        rows.append({'stage': request['stage'], 'observation': name, 'obs': obs, 'raw': raw,
                     'body': body, 'complete': complete and isinstance(body, dict), 'when': when})
    return rows


def _delivered(plan, planned, rows):
    builds = [x for x in rows if x['stage'] == 'build' and x['obs'].get('http_status') == 200 and x['complete']]
    if not builds:
        return None
    row = builds[-1]
    mapping, body = plan['response_mapping'], row['body']
    fields = {key: _pointer(body, pointer) for key, pointer in mapping['fields'].items()}
    call_fields = mapping.get('call_fields', {'to': 'to', 'data': 'data', 'value': 'value'})
    _check(set(call_fields) == {'to', 'data', 'value'}, 'Unsupported call field mapping')
    raw_calls = _pointer(body, mapping['calls_pointer'])
    calls = [{field: call[name] for field, name in call_fields.items()} for call in raw_calls]
    actual_plan = {'chain_id': integer(fields.get('chain_id', plan['chain_id'])), 'calls': calls}
    expected = {key: planned['expected'][key] for key in ('token_in', 'token_out', 'amount_in', 'recipient')}
    expected['minimum_out'] = integer(fields['minimum_out'])
    issues = []
    for key in ('token_in', 'token_out', 'recipient'):
        if address(fields[key]) != address(expected[key]):
            issues.append('响应' + key + '与独立任务不符。')
    if integer(fields['amount_in']) != integer(expected['amount_in']) or actual_plan['chain_id'] != integer(plan['chain_id']):
        issues.append('响应链或精确输入数量与独立任务不符。')
    slippage = integer(planned['expected']['slippage_bps'])
    quoted = integer(fields['quoted_out'])
    if not (0 <= slippage < 10000 and quoted > 0 and expected['minimum_out'] > 0
            and expected['minimum_out'] >= quoted * (10000 - slippage) // 10000):
        issues.append('最低到账违反本次请求的滑点下限。')
    if 'slippage_bps' in fields and integer(fields['slippage_bps']) != slippage:
        issues.append('响应滑点与独立请求不符。')
    decoded, safety, safety_reason = None, Verdict.UNKNOWN, '此调用协议尚未适配，不归责提供方。'
    try:
        decoded = verify_atomic_swap_intent(actual_plan, dict(expected, chain_id=plan['chain_id'], executor=plan['executor']))
        safety, safety_reason = Verdict.PASS, '独立解码完整七CALL：精确授权、调用、收款、最低值、期限与零清理相符。'
    except UnsignedSwapMismatch as error:
        decoded = normalize_atomic_swap(actual_plan)
        issues.append(str(error))
        safety, safety_reason = Verdict.FAIL, '真实交付的调用约束违反独立任务：' + str(error)
    except UnsupportedUnsignedSwap as error:
        safety_reason = '调用形状未适配，停止执行并保留UNKNOWN：' + str(error)
    except ValueError as error:
        safety, safety_reason = Verdict.FAIL, '已适配调用的明确安全约束不符：' + str(error)
    execution_blocked = bool(issues or safety != Verdict.PASS)
    quote_mapping = mapping.get('quote_fields', {key: value for key, value in mapping['fields'].items()
        if key not in ('recipient', 'issued_at')})
    for stage in rows:
        if stage['stage'] != 'quote' or not stage['complete'] or stage['obs']['http_status'] != 200:
            continue
        earlier = {key: _pointer(stage['body'], pointer) for key, pointer in quote_mapping.items()}
        for key in ('token_in', 'token_out'):
            if address(earlier[key]) != address(expected[key]):
                issues.append('quote阶段' + key + '与同一任务意图不符。')
        if integer(earlier['amount_in']) != integer(expected['amount_in']):
            issues.append('quote阶段输入单位或数量与同一任务不符。')
        if 'chain_id' in earlier and integer(earlier['chain_id']) != integer(plan['chain_id']):
            issues.append('quote阶段链不符。')
        if (integer(earlier['minimum_out']) <= 0 or integer(earlier['quoted_out']) <= 0
            or integer(earlier['minimum_out']) < integer(earlier['quoted_out']) * (10000 - slippage) // 10000):
            issues.append('quote阶段最低到账不满足同一请求滑点。')
    return {'plan': actual_plan, 'expected': expected, 'decoded': decoded, 'fields': fields,
            'issues': issues, 'execution_blocked': execution_blocked,
            'safety': (safety, safety_reason, {}), 'response': row}


def _call_value(records, payer, target, data, tag, *, require_sender=True):
    matches = []
    for row in records:
        if row['method'] != 'eth_call' or row['error'] or row['value'] is None or len(row['params']) != 2 or row['params'][1] != tag:
            continue
        call = row['params'][0]
        if (set(call) - {'from', 'to', 'data', 'value', 'gas', 'gasPrice'}
            or address(call['to']) != target or call['data'].lower() != data.lower()
            or integer(call.get('value', 0)) != 0):
            continue
        if 'from' in call:
            if address(call['from']) != payer:
                continue
        elif require_sender:
            continue
        matches.append(row['value'])
    _check(len(set(matches)) <= 1, 'Conflicting fixed-block call results')
    return matches[0] if matches else None


def _at(records, payer, target, signature, args, tag):
    return _call_value(records, payer, target, calldata(signature, *args), tag, require_sender=False)


def _deployment(records, binding, decoded, payer, tag):
    if not binding:
        return False, '缺少操作者前瞻固定的协议部署承诺。'
    _check(integer(binding['chain_id']) == decoded['chain_id']
           and address(binding['router']) == decoded['router'] and address(binding['permit2']) == decoded['permit2'],
           'Frozen deployment roles differ from the delivered protocol')
    roles = {'router': decoded['router'], 'permit2': decoded['permit2'], 'executor': payer,
             'cl_factory': address(binding['cl_factory']), 'cl_implementation': address(binding['cl_implementation'])}
    for role, target in roles.items():
        code = _lookup(records, 'eth_getCode', [target, tag])
        if code is None:
            return False, '缺少同固定块' + role + '运行代码。'
        _check(code != '0x' and _fingerprint(code) == binding['runtime_keccak'][role].lower(),
               'Actual runtime differs from frozen reviewed ' + role)
    factory, implementation = roles['cl_factory'], roles['cl_implementation']
    for hop in decoded['path_hops']:
        tokens = sorted([hop['token_in'], hop['token_out']])
        raw = _at(records, payer, factory, 'getPool(address,address,int24)', [*tokens, hop['tick_spacing']], tag)
        if raw is None:
            return False, '缺独立固定块CLFactory.getPool。'
        _check(len(hex_bytes(raw)) == 32 and integer(raw) < 2**160 and integer(raw) != 0, 'Factory did not bind a nonzero pool')
        pool = address('0x' + raw[-40:])
        _check(pool == predict_slipstream_pool(factory, implementation, *tokens, hop['tick_spacing']),
               'Factory pool differs from router ERC1167 CREATE2 prediction')
        for signature, expected in [('token0()', int(tokens[0], 16)), ('token1()', int(tokens[1], 16)),
                                    ('tickSpacing()', hop['tick_spacing'])]:
            value = _at(records, payer, pool, signature, [], tag)
            if value is None:
                return False, '缺池资产或tickSpacing原件。'
            _check(len(hex_bytes(value)) == 32 and integer(value) == expected, 'Independent pool fields differ from path')
        code = _lookup(records, 'eth_getCode', [pool, tag])
        if code is None:
            return False, '缺CL池ERC1167实现绑定。'
        expected_code = '0x363d3d373d3d3d363d73' + implementation[2:] + '5af43d82803e903d91602b57fd5bf3'
        _check(code.lower() == expected_code, 'CL pool clone differs from reviewed implementation')
    return True, '运行代码承诺、CL factory、资产/tickSpacing及clone实现均由同固定块原件核齐。'


def _batch_values(value, count):
    values = retained._results(value)
    _check(len(values) == count, 'Atomic batch result count differs from complete call sequence')
    return values


def _uint(value):
    return retained._word(value)


def _allowances(values):
    _check(len(values) == 3 and len(values[2]) == 96, 'Missing full Permit2 allowance tuple')
    permit = values[2]
    amount, expiration, nonce = (int.from_bytes(permit[i:i + 32], 'big') for i in (0, 32, 64))
    _check(amount < 2**160 and expiration < 2**48 and nonce < 2**48, 'Noncanonical Permit2 allowance widths')
    return [_uint(values[0]), _uint(values[1]), amount]


def _simulation(evidence, planned, item, quote, binding):
    if not quote or not quote['decoded'] or quote.get('execution_blocked') or quote['safety'][0] != Verdict.PASS:
        return UNKNOWN
    supplied = item.get('simulation')
    if not supplied:
        return UNKNOWN
    plan = evidence.json(supplied['plan'])
    _check(plan.get('task_key', plan.get('origin_task')) == planned['task_key']
           and plan['source_response_sha256'] == _sha(quote['response']['raw']), 'Simulation is not bound to this delivered task')
    payer = address(plan['payer'])
    _check(payer == quote['decoded']['required_executor'] and integer(plan['chain_id']) == quote['decoded']['chain_id'],
           'Simulation executor or chain differs')
    calls = atomic_evidence_calls(quote['plan'])
    _check(_normalized(plan['calls']) == _normalized(calls), 'Simulation is not the exact sixteen-call evidence batch')
    records = retained._records(evidence, supplied['rpc_observations'])
    chain = _lookup(records, 'eth_chainId', [])
    if chain is None:
        return Verdict.UNKNOWN, '固定块模拟缺可信chainId原件。', {}
    _check(integer(chain) == quote['decoded']['chain_id'], 'Simulation RPC chain differs')
    rows = [x for x in records if Path(x['observation']).name == supplied['call_label'] + '.observation.json']
    _check(len(rows) == 1 and rows[0]['method'] == 'eth_call' and len(rows[0]['params']) == 2,
           'Scored simulation requires one fixed-block eth_call without overrides')
    row = rows[0]
    tag = row['params'][1]
    _check(isinstance(tag, str) and tag.startswith('0x'), 'Simulation requires an explicit block number')
    request = row['params'][0]
    _check(set(request) <= {'from', 'to', 'data', 'value', 'gas', 'gasPrice'}
           and address(request['from']) == payer == address(request['to'])
           and integer(request.get('value', 0)) == 0 and request['data'].lower() == encode_batch(calls).lower(),
           'Original simulation request differs from complete atomic evidence calls')
    header = _lookup(records, 'eth_getBlockByNumber', [tag, False])
    _check(header and integer(header['number']) == integer(tag), 'Missing fixed canonical simulation header')
    _check(integer(header['timestamp']) <= quote['decoded']['earliest_known_deadline'], 'Simulation occurred after effective deadline')
    deployed, reason = _deployment(records, binding, quote['decoded'], payer, tag)
    if not deployed or row['error'] or row['value'] is None:
        return Verdict.UNKNOWN, reason if not deployed else '固定块模拟回滚或读取错误，尚不能归责提供方。', {}
    values = _batch_values(row['value'], 16)
    before, after = [_uint(x) for x in values[:3]], [_uint(x) for x in values[10:13]]
    allowances = _allowances(values[13:16])
    debit, credit = before[0] - after[0], after[1] - before[1]
    swap_credit = credit - before[2]
    facts = {'block': integer(tag), 'block_hash': header['hash'], 'pre_input_raw': str(before[0]),
        'pre_output_raw': str(before[1]), 'pre_router_output_raw': str(before[2]),
        'input_debit_raw': str(debit), 'output_credit_raw': str(credit), 'swap_only_credit_raw': str(swap_credit),
        'post_router_output_raw': str(after[2]), 'allowances_raw': [str(x) for x in allowances],
        'source_plan_sha256': _sha(evidence.raw(supplied['plan'])), 'deployment_verified': True}
    if before[2] and swap_credit < integer(quote['expected']['minimum_out']):
        return Verdict.UNKNOWN, 'Router旧输出余额污染SWEEP门槛；未用旧余额补本次最低到账。', dict(facts, measurement_validity='invalid')
    passed = (debit == integer(quote['expected']['amount_in']) and swap_credit >= integer(quote['expected']['minimum_out'])
              and after[2] == 0 and allowances == [0, 0, 0])
    return (Verdict.PASS if passed else Verdict.FAIL,
            f'完整固定块模拟：输入净减{debit}，收款净增{credit}，扣旧Router余额后{swap_credit}，三类授权{allowances}。', facts)


def _execution(evidence, planned, item, quote, simulation):
    supplied = item.get('execution')
    if not supplied:
        return UNKNOWN
    _check(planned['planned_actual_execution'], 'Unplanned real execution cannot enter this campaign')
    if simulation[0] != Verdict.PASS or not quote or quote.get('execution_blocked'):
        return Verdict.UNKNOWN, '缺少同方案有效独立模拟；不以费用或保护退出补B。', {}
    plan, intent = evidence.json(supplied['plan']), evidence.json(supplied['intent_path'])
    _check(plan.get('task_key', plan.get('origin_task')) == planned['task_key'] == intent['task_key']
           and intent['plan_sha256'] == _sha(evidence.raw(supplied['plan']))
           and plan['source_response_sha256'] == _sha(quote['response']['raw']), 'Execution plan/intent/source mismatch')
    _check(intent['simulation_plan_sha256'] == simulation[2]['source_plan_sha256']
           and integer(intent['fixed_block']) == simulation[2]['block']
           and intent['block_hash'].lower() == simulation[2]['block_hash'].lower(), 'Execution does not bind original preflight state')
    payer = address(supplied['payer'])
    calls = atomic_evidence_calls(quote['plan'])
    _check(payer == quote['decoded']['required_executor'] == address(plan['payer'])
           and integer(plan['chain_id']) == quote['decoded']['chain_id'] and _normalized(plan['calls']) == _normalized(calls),
           'Execution must retain the exact complete evidence batch and executor')
    records = retained._records(evidence, supplied['rpc_observations'])
    chain_id = quote['decoded']['chain_id']
    chain = _lookup(records, 'eth_chainId', [])
    if chain is None:
        return Verdict.UNKNOWN, '实际交易缺可信chainId原件。', {}
    _check(integer(chain) == chain_id, 'Execution RPC chain differs')
    tx_hash = supplied['transaction_hash'].lower()
    tx = _lookup(records, 'eth_getTransactionByHash', [tx_hash])
    receipt = _lookup(records, 'eth_getTransactionReceipt', [tx_hash])
    if not tx or not receipt:
        return Verdict.UNKNOWN, '实际发送后尚缺可信transaction/receipt；不换hash重复执行。', {}
    _check(tx['hash'].lower() == receipt['transactionHash'].lower() == tx_hash, 'Execution transaction/receipt hash differs')
    header = retained._canonical(records, receipt)
    _check(tx['blockHash'].lower() == receipt['blockHash'].lower() and tx['blockNumber'] == receipt['blockNumber']
           and tx['transactionIndex'] == receipt['transactionIndex'], 'Execution transaction/receipt block differs')
    actual = intent['transaction']
    _check(address(actual['from']) == payer == address(actual['to']) and integer(actual['chainId']) == chain_id
           and integer(actual['value']) == 0 and actual['data'].lower() == encode_batch(calls).lower()
           and address(tx['from']) == payer == address(tx['to']) and integer(tx['chainId']) == chain_id
           and integer(tx['value']) == 0 and tx['input'].lower() == actual['data'].lower()
           and integer(tx['nonce']) == integer(actual['nonce']), 'Actual transaction differs from persisted atomic intent')
    _check(integer(header['timestamp']) <= quote['decoded']['earliest_known_deadline'], 'Actual inclusion missed effective deadline')
    heads = [integer(x['value']) for x in records if x['method'] == 'eth_blockNumber' and not x['error'] and x['value']]
    distance = max(heads, default=-1) - integer(receipt['blockNumber'])
    if distance < 64:
        return Verdict.UNKNOWN, '真实交易尚未达到64块确认距离。', {'transaction_hash': tx_hash, 'confirmation_distance': distance}
    if integer(receipt['status']) != 1:
        return Verdict.UNKNOWN, '真实交易回滚，归因尚未核齐；没有直接认定重大违约。', {'transaction_hash': tx_hash}
    for log in receipt['logs']:
        _check(log['transactionHash'].lower() == tx_hash and log['blockHash'].lower() == receipt['blockHash'].lower()
               and integer(log['blockNumber']) == integer(receipt['blockNumber']) and not log.get('removed'),
               'Receipt contains a removed or differently bound log')
    decoded, expected = quote['decoded'], quote['expected']
    debit = retained._transfers(receipt, decoded['token_in'], sender=payer) - retained._transfers(receipt, decoded['token_in'], recipient=payer)
    credit = retained._transfers(receipt, decoded['token_out'], recipient=payer) - retained._transfers(receipt, decoded['token_out'], sender=payer)
    post = _call_value(records, payer, payer, encode_batch(atomic_post_calls(quote['plan'])), receipt['blockNumber'])
    if post is None:
        return Verdict.UNKNOWN, '缺独立回执块末余额/三授权读取。', {'transaction_hash': tx_hash}
    values = _batch_values(post, 6)
    balances, allowances = [_uint(x) for x in values[:3]], _allowances(values[3:])
    pre = simulation[2]
    sim_records = retained._records(evidence, item['simulation']['rpc_observations'])
    before_code = _lookup(sim_records, 'eth_getCode', [payer, hex(pre['block'])])
    after_code = _lookup(records, 'eth_getCode', [payer, receipt['blockNumber']])
    _check(before_code and after_code and before_code.lower() == after_code.lower(), 'Executor code/delegation changed or lacks evidence')
    swap_credit = credit - integer(pre['pre_router_output_raw'])
    facts = {'transaction_hash': tx_hash, 'block': integer(receipt['blockNumber']), 'timestamp': integer(header['timestamp']),
        'input_debit_raw': str(debit), 'output_credit_raw': str(credit), 'swap_only_credit_raw': str(swap_credit),
        'allowances_raw': [str(x) for x in allowances], 'confirmation_distance': distance}
    if integer(pre['pre_input_raw']) - balances[0] != debit or balances[1] - integer(pre['pre_output_raw']) != credit:
        return Verdict.UNKNOWN, '交易净事件与固定前置块至回执块末余额窗口不能独立对平，保留归因未知。', facts
    if integer(pre['pre_router_output_raw']) and swap_credit < integer(expected['minimum_out']):
        return Verdict.UNKNOWN, 'Router旧余额不能用于本次真实履约最低值，保留未知。', facts
    passed = debit == integer(expected['amount_in']) and swap_credit >= integer(expected['minimum_out']) and balances[2] == 0 and allowances == [0, 0, 0]
    return (Verdict.PASS if passed else Verdict.FAIL,
            f'真实兑换净输入{debit}、净输出{credit}、扣旧Router余额后{swap_credit}，三授权{allowances}，确认距离{distance}块。', facts)


def _schema_accepts(value, schema):
    if 'oneOf' in schema:
        return sum(_schema_accepts(value, x) for x in schema['oneOf']) == 1
    if 'anyOf' in schema:
        return any(_schema_accepts(value, x) for x in schema['anyOf'])
    kind = schema.get('type')
    types = {'string': lambda: isinstance(value, str), 'integer': lambda: type(value) is int,
             'number': lambda: type(value) in (int, float), 'boolean': lambda: type(value) is bool,
             'object': lambda: isinstance(value, dict), 'array': lambda: isinstance(value, list)}
    if kind in types and not types[kind]():
        return False
    if 'enum' in schema and value not in schema['enum']:
        return False
    if type(value) in (int, float):
        if 'minimum' in schema and value < schema['minimum']:
            return False
        if 'maximum' in schema and value > schema['maximum']:
            return False
    return True


def _invalid_input_fields(evidence, plan, planned):
    request = planned['requests'][0]
    snapshot = evidence.json(plan['source_snapshot']['path'])
    operation = snapshot.get('paths', {}).get(urlsplit(request['url']).path, {}).get(request['method'].lower(), {})
    schema = operation.get('requestBody', {}).get('content', {}).get('application/json', {}).get('schema', {})
    body = request.get('json')
    if not isinstance(body, dict):
        return set()
    field = planned['expected'].get('invalid_field')
    invalid = set(schema.get('required', [])) - set(body)
    invalid.update(name for name, value in body.items() if name in schema.get('properties', {})
                   and not _schema_accepts(value, schema['properties'][name]))
    if planned['expected'].get('invalid_kind') == 'evm-address' and field in body:
        try:
            address(body[field])
        except ValueError:
            invalid.add(field)
    for name, value in body.items():
        words = re.sub(r'([a-z])([A-Z])', r'\1 \2', name).lower().split()
        if words and words[-1] == 'amount':
            try:
                number = Decimal(int(value, 16)) if isinstance(value, str) and value.startswith('0x') else Decimal(str(value))
                if not number.is_finite() or number <= 0:
                    invalid.add(name)
            except (ValueError, InvalidOperation):
                invalid.add(name)
    return invalid


def _rejection_error(body, pointer):
    try:
        error = _pointer(body, pointer)
    except (KeyError, IndexError, TypeError):
        error = None
    if isinstance(error, str) and error.strip():
        return error
    if (body.get('kind') == 'error' and 'data' in body and body['data'] is None
            and isinstance(body.get('summary'), str)):
        return body['summary']
    rpc = body.get('error')
    if body.get('jsonrpc') == '2.0' and isinstance(rpc, dict) and isinstance(rpc.get('message'), str):
        return rpc['message']
    return None


def _rejection_matches(error, planned, invalid):
    field = planned['expected'].get('invalid_field')
    if field not in invalid or not isinstance(error, str):
        return False
    text = error.lower()
    validation = re.search(r'invalid|required|missing|positive|uint160|must|range|between|exceed|not.{0,12}(valid|known)|could not resolve|unsupported', text)
    if not validation:
        return False
    compact = re.sub(r'[^a-z0-9]', '', text)
    if re.sub(r'[^a-z0-9]', '', field.lower()) in compact:
        return True
    value = planned['requests'][0].get('json', {}).get(field)
    if isinstance(value, str) and len(value) >= 4 and value.lower() in text:
        return True
    words = re.sub(r'([a-z])([A-Z])', r'\1 \2', field).lower().split()
    return invalid == {field} and words[-1:] == ['amount'] and bool(re.search(r'\bamount\b', text))


def _declared_typed_error(evidence, plan, planned, body):
    if not (isinstance(body, dict) and body.get('kind') == 'error' and 'data' in body
            and body['data'] is None and isinstance(body.get('summary'), str) and body['summary'].strip()):
        return False
    snapshot = evidence.json(plan['source_snapshot']['path'])
    request = planned['requests'][0]
    operation = snapshot.get('paths', {}).get(urlsplit(request['url']).path, {}).get(request['method'].lower(), {})
    for status in planned['expected']['rejection_statuses']:
        schema = operation.get('responses', {}).get(str(status), {}).get('content', {}).get('application/json', {}).get('schema', {})
        visited = set()
        while isinstance(schema, dict) and '$ref' in schema:
            pointer = schema['$ref']
            if not pointer.startswith('#/') or pointer in visited:
                return False
            visited.add(pointer)
            try:
                schema = _pointer(snapshot, pointer[1:])
            except (KeyError, TypeError, IndexError):
                return False
        properties = schema.get('properties', {}) if isinstance(schema, dict) else {}
        if properties.get('kind', {}).get('enum') == ['error'] and properties.get('summary', {}).get('type') == 'string':
            return True
    return False


def _deadline_default_clock(quote, expected_seconds):
    """Compare public timestamps within the observed request's seconds precision."""
    issued = int(_time(quote['fields']['issued_at']).timestamp())
    deadline = integer(quote['decoded']['deadlines'][0]['timestamp'])
    expected = integer(expected_seconds)
    delta = deadline - issued
    observation = quote['response']['obs']
    facts = {'clock_policy': 'request-interval-v1', 'default_seconds': expected,
             'decoded_deadline': deadline, 'provider_timestamp_seconds': issued, 'delta_seconds': delta,
             'request_observed_at': observation.get('observed_at'), 'integer_precision_seconds': 1}
    if delta == expected:
        return Verdict.PASS, '公开缺省TTL与方案和provider时间戳的整数秒差值一致。', facts
    elapsed = observation.get('elapsed_ms')
    if type(elapsed) not in (int, float) or not isfinite(elapsed) or elapsed < 0:
        return Verdict.UNKNOWN, '缺实测请求耗时，不能定位deadline与响应时间戳的生成时点。', dict(facts, measurement_validity='unknown')
    lower, upper = expected - ceil(elapsed / 1000) - 1, expected + 1
    facts.update(elapsed_ms=elapsed, possible_delta_seconds=[lower, upper])
    if lower <= delta <= upper:
        return (Verdict.UNKNOWN, f'缺省TTL差值{delta}秒处于实测请求与整数秒精度窗口[{lower},{upper}]；生成时点不明，未扣提供方分。',
                dict(facts, measurement_validity='unknown'))
    return Verdict.FAIL, f'缺省TTL差值{delta}秒超出实测请求与整数秒精度窗口[{lower},{upper}]，与公开缺省值不符。', facts


def _metrics(evidence, plan, binding, planned, item, rows):
    metrics = {name: UNKNOWN for name in METRICS}
    if planned['expected']['safe_rejection']:
        invalid = _invalid_input_fields(evidence, plan, planned)
        if rows and planned['expected'].get('invalid_field') in invalid:
            row = rows[-1]
            if row['complete'] and row['obs']['http_status'] in planned['expected']['rejection_statuses']:
                try:
                    offered_calls = _pointer(row['body'], plan['response_mapping']['calls_pointer'])
                except (KeyError, IndexError, TypeError):
                    offered_calls = None
                error = _rejection_error(row['body'], plan['response_mapping']['rejection_error_pointer'])
                if _rejection_matches(error, planned, invalid) and not offered_calls:
                    metrics['safe-rejection'] = (Verdict.PASS, '已预设无效的请求由确切业务路由明确拒绝，未交付资产执行方案。', {})
            elif row['complete'] and row['obs']['http_status'] == 200:
                metrics['safe-rejection'] = (Verdict.FAIL, '明确违反冻结输入约束的请求仍被作为正常成功交付。', {})
            elif (row['complete'] and 500 <= (row['obs'].get('http_status') or 0) < 600
                  and row['obs'].get('url') and plan.get('registered_service')
                  and _origin(row['obs']['url']) == _origin(plan['registered_service'])
                  and _declared_typed_error(evidence, plan, planned, row['body'])):
                metrics['safe-rejection'] = (Verdict.FAIL,
                    '独立已知非法输入应按冻结契约返回400/422；绑定服务返回完整已声明错误类型但HTTP为5xx，输入校验处理不符；未推断资金违约或内部根因。', {})
        return metrics, None

    complete = len(rows) == len(planned['requests']) and all(x['complete'] and x['obs']['http_status'] == 200 for x in rows)
    if complete:
        metrics['complete-response'] = (Verdict.PASS, '该任务全部正常业务HTTP阶段完整成功；仅展示耗时，无未经声明的SLA扣分。', {})
    elif any(x['complete'] and x['obs'].get('http_status') is not None and x['obs']['http_status'] >= 400 for x in rows):
        metrics['complete-response'] = (Verdict.FAIL, '已冻结的正常请求取得明确HTTP业务错误，未隐藏失败。', {})
    quote = None
    try:
        quote = _delivered(plan, planned, rows)
    except (KeyError, IndexError, TypeError, ValueError) as error:
        if isinstance(error, (UnsupportedUnsignedSwap, UnsignedSwapMismatch)):
            raise
        metrics['complete-response'] = (Verdict.FAIL, '完整HTTP响应缺少冻结字段映射要求的完整业务方案。', {})
        metrics['intent-binding'] = (Verdict.FAIL, '真实业务方案格式/必要字段不完整：' + str(error), {})
        return metrics, None
    if quote:
        if quote['issues']:
            metrics['intent-binding'] = (Verdict.FAIL, ' '.join(quote['issues']), {})
        elif quote['decoded']:
            metrics['intent-binding'] = (Verdict.PASS, '响应与实际调用资产、整数输入、链、收款与独立滑点下限一致。', {})
        metrics['call-safety'] = quote['safety']
        assertions = planned['expected'].get('default_assertions', {})
        checks = []
        clock = None
        if 'slippage_bps' in assertions and 'slippage_bps' in quote['fields']:
            checks.append(integer(quote['fields']['slippage_bps']) == integer(assertions['slippage_bps']))
        if 'deadline_seconds' in assertions and quote['decoded'] and quote['fields'].get('issued_at'):
            if plan.get('deadline_default_clock_policy') == 'request-interval-v1':
                clock = _deadline_default_clock(quote, assertions['deadline_seconds'])
                checks.append(None if clock[0] == Verdict.UNKNOWN else clock[0] == Verdict.PASS)
            else:
                issued = int(_time(quote['fields']['issued_at']).timestamp())
                checks.append(quote['decoded']['deadlines'][0]['timestamp'] - issued == integer(assertions['deadline_seconds']))
        if assertions and len(checks) == len(assertions):
            if clock and clock[0] == Verdict.UNKNOWN and not any(value is False for value in checks):
                metrics['default-contract'] = clock
            else:
                metrics['default-contract'] = (Verdict.PASS if all(checks) else Verdict.FAIL,
                    '公开缺省值与实际方案内部时间/参数一致。' if all(checks) else '实际方案与冻结公开缺省值不符。', clock[2] if clock else {})
        metrics['execution-effect'] = _simulation(evidence, planned, item, quote, binding)
        metrics['onchain-fulfillment'] = _execution(evidence, planned, item, quote, metrics['execution-effect'])
    return metrics, quote


def replay_atomic_swap_sources(root, evidence, source, generated_at):
    _check(source.get('schema_version') == 'atomic-swap-evidence-v1' and source.get('adapter') == ADAPTER,
           'Unsupported atomic evidence version')
    evidence.raw(ADR)
    plan, binding, task_clocks = _frozen_plan(evidence, source)
    canonical = _identity(evidence, source, plan)
    if binding:
        for ref in binding['source_refs']:
            _snapshot(evidence, ref)
    by_key = {x['task_key']: x for x in source['tasks']}
    tasks_by_key = {x['task_key']: x for x in plan['tasks']}
    _check(len(by_key) == len(source['tasks']) and set(by_key) <= set(tasks_by_key), 'Unexpected or duplicated source task')
    used_http, used_execution, evaluated, samples, tasks = set(), set(), {}, [], []
    capability_id = plan['capability']['capability_id']
    for planned in plan['tasks']:
        key = planned['task_key']
        item, quote, rows = by_key.get(key), None, []
        refs = [source['campaign_plan'], plan['source_snapshot']['path'], plan['source_snapshot']['observation']]
        metrics = {name: UNKNOWN for name in METRICS}
        if item:
            names = item.get('http_observations', [])
            _check(not set(names) & used_http, 'One business HTTP observation cannot supply two tasks')
            used_http.update(names)
            refs.extend(names)
            for stage in ('simulation', 'execution'):
                if item.get(stage):
                    refs.extend([item[stage]['plan'], *item[stage]['rpc_observations']])
                    if stage == 'execution':
                        refs.append(item[stage]['intent_path'])
                        transaction = integer(plan['chain_id']), item[stage]['transaction_hash'].lower()
                        _check(transaction not in used_execution, 'One single-swap transaction cannot supply two tasks')
                        used_execution.add(transaction)
            rows = _http_task(evidence, planned, item, task_clocks[key])
            metrics, quote = _metrics(evidence, plan, binding, planned, item, rows)
        for name in list(refs):
            if name.endswith('.observation.json'):
                obs = evidence.json(name)
                if obs.get('response_file'):
                    response = (Path(name).parent / obs['response_file']).as_posix()
                    evidence.raw(response)
                    refs.append(response)
        refs = list(dict.fromkeys(refs))
        when = max((x['when'] for x in rows), default=None)
        elapsed = sum(float(x['obs']['elapsed_ms']) for x in rows) if rows else None
        chosen = ('safe-rejection' if planned['expected']['safe_rejection'] else
                  'onchain-fulfillment' if planned['planned_actual_execution'] else 'execution-effect')
        verdict, reason, result_facts = metrics[chosen]
        if result_facts.get('timestamp'):
            executed_at = datetime.fromtimestamp(result_facts['timestamp'], timezone.utc)
            when = max(when, executed_at) if when else executed_at
        if planned['expected']['safe_rejection']:
            outcome = 'rejected' if verdict == Verdict.PASS else 'failed' if verdict == Verdict.FAIL else 'unknown'
        elif planned['planned_actual_execution']:
            outcome = ('completed' if verdict == Verdict.PASS else 'failed' if verdict == Verdict.FAIL else
                       'not_executed' if not item or not item.get('execution') else 'unknown')
        else:
            outcome = 'not_executed' if quote else 'unknown'
        tasks.append({'task_key': key, 'capability_id': capability_id, 'input_summary': planned['input_summary'],
            'outcome': outcome, 'attribution': 'unknown', 'observed_at': when, 'evidence': refs})
        samples.append(SampleExplanation(sample=ScoredSample(sample_id='atomic:' + planned['task_id'], task_key=key,
            purpose=MeasurementPurpose.BEHAVIORAL if planned['planned_actual_execution'] else MeasurementPurpose.FUNCTIONAL,
            verdict=verdict, elapsed_ms=elapsed, reason=reason, evidence=refs), observed_at=when,
            title=planned['task_id'] + (' 真实兑换目标' if planned['planned_actual_execution'] else ' 方案或拒绝目标'),
            input_summary=planned['input_summary'], claimed_output='按冻结任务交付原子兑换方案或明确拒绝；真实履约单独核验。',
            independent_result=reason, checks=[ReportFinding(label=name, verdict=metrics[name][0], explanation=metrics[name][1])
                for name in ('complete-response', 'intent-binding', 'call-safety', 'execution-effect', 'onchain-fulfillment')],
            capability_id=capability_id))
        evaluated[planned['task_id']] = {'planned': planned, 'item': item, 'rows': rows, 'quote': quote,
                                       'metrics': metrics, 'refs': refs, 'elapsed_ms': elapsed}
    cases, observations = [], []
    for case in plan['cases']:
        _check(set(case['criterion_ids']) <= METRICS and set(case['planned_task_ids']) <= set(evaluated),
               'Unknown frozen case metric/task')
        cases.append({'case_id': case['case_id'], 'capability_id': capability_id, 'dimension': case['dimension'],
            'declaration_group_id': case['declaration_group_id'], 'title': case['title'],
            'criterion_ids': case['criterion_ids'], 'task_keys': [evaluated[x]['planned']['task_key'] for x in case['planned_task_ids']],
            'normal_execution': case['normal_execution'], 'required_decisive': case['required_decisive']})
        for task_id in case['planned_task_ids']:
            row = evaluated[task_id]
            if row['item'] is None:
                continue
            for criterion in case['criterion_ids']:
                verdict, reason, facts = row['metrics'][criterion]
                observations.append({'task_key': row['planned']['task_key'], 'case_id': case['case_id'],
                    'criterion_id': criterion, 'dimension': case['dimension'], 'verdict': verdict.value,
                    'reason': reason, 'evidence': row['refs'], 'measurement_validity': facts.get('measurement_validity', 'valid'),
                    'elapsed_ms': row['elapsed_ms'] if case['dimension'] == 'availability' else None,
                    'response_complete': all(x['complete'] for x in row['rows']) if case['dimension'] == 'availability' else None,
                    # A revert or unproven cause cannot become a major violation.
                    'critical': False})
    for group in plan['capability']['declaration_groups']:
        for path in group['source_references']:
            evidence.raw(path)
    assessment = SharedAssessment.model_validate_json(json.dumps({'schema_version': 'shared-task-assessment-v3',
        'capabilities': [plan['capability']], 'cases': cases, 'tasks': tasks, 'observations': observations},
        ensure_ascii=False, default=lambda value: value.isoformat()))
    revised_clock = plan.get('deadline_default_clock_policy') == 'request-interval-v1'
    return EvaluationReport(policy_version=POINT_POLICY_VERSION, candidate_key=source['candidate_key'], name=source['name'],
        registration_reference=canonical, generated_at=generated_at, scope=plan['scope'], scope_exclusions=plan['scope_exclusions'],
        evaluation_window=('原任务冻结时钟按追加链保留；缺省deadline于' + plan['frozen_at'] + '作已有证据的回顾性测量校准，未补发业务。'
                           if revised_clock else '前瞻任务冻结于' + plan['frozen_at'] + '；原始HTTP及链时间保留，缺样槽位未删。'),
        approach='从冻结服务与任务、原始HTTP、确定性原子CALL、固定块净效果及实际canonical交易重放，共用v3单分和30/40/30。',
        samples=samples, capabilities=[], shared_assessment=assessment, source_references=sorted(evidence.hashes),
        limitations=identity_limitations(canonical, LIMITATIONS + ([
            '缺省deadline采用request-interval-v1：精确差值可判PASS，请求耗时与秒级精度窗口内的非精确差值保留UNKNOWN；不是SLA。',
            '本次仅重放已有任务作测量校准；旧版报告和原始证据保留，不增加真实业务样本。'] if revised_clock else [])))


def verify_atomic_swap_report_sources(root, report, hashes):
    origins = [name for name in hashes if Path(name).name == ORIGIN]
    _check(len(origins) == 1, 'Expected exactly one atomic report origin')
    evidence = SwapEvidence(root, hashes)
    origin = evidence.json(origins[0])
    _check(origin.get('schema_version') == 'atomic-swap-report-origin-v1' and origin.get('adapter') == ADAPTER,
           'Unsupported atomic origin version')
    source = evidence.json(origin['source'])
    _check(source.get('adapter') == origin['adapter'], 'Atomic source/origin adapter mismatch')
    replay = replay_atomic_swap_sources(Path(root), evidence, source, report.generated_at)
    _check(replay.model_dump(mode='json') == report.model_dump(mode='json'), 'Published atomic report differs from evidence replay')
    return report.registration_reference


def build_atomic_swap_report(root: Path, source: Path, output: Path):
    root = root.resolve()
    source, output = (root / source).resolve(), (root / output).resolve()
    _check(source.is_relative_to(root / 'runtime') and output.is_relative_to(root / 'runtime') and not output.exists(),
           'Use an existing public runtime source and a new output directory')
    config = json.loads(source.read_bytes())
    _check(config.get('schema_version') == 'atomic-swap-evidence-v1' and config.get('adapter') == ADAPTER, 'Unsupported atomic source')
    hashes = {}
    for row in [*config['sources'], {'path': source.relative_to(root).as_posix(), 'sha256': _sha(source.read_bytes())},
                {'path': ADR, 'sha256': _sha((root / ADR).read_bytes())}]:
        path = (root / row['path']).resolve()
        _check(path.is_relative_to(root) and not any('.private' in part.lower() or part.lower() in
            ('secrets', 'platform-config', '.env') for part in path.relative_to(root).parts), 'Private evidence cannot enter a public atomic report')
        _check(not (path.suffix == '.py' and path.relative_to(root).parts[0] in ('services', 'packages', 'scripts')),
               'Live implementation source is not an immutable report input; use an artifact snapshot')
        _check(_sha(path.read_bytes()) == row['sha256'] and (row['path'] not in hashes or hashes[row['path']] == row['sha256']),
               'Atomic source hash mismatch')
        hashes[row['path']] = row['sha256']
    campaign = SwapEvidence(root, hashes).json(config['campaign_plan'])
    if campaign.get('deadline_default_clock_policy') == 'request-interval-v1':
        digest = _sha((root / CLOCK_ADR).read_bytes())
        _check(CLOCK_ADR not in hashes or hashes[CLOCK_ADR] == digest, 'Frozen clock measurement ADR changed')
        hashes[CLOCK_ADR] = digest
    output.mkdir(parents=True, exist_ok=False)
    # These are provenance TEXT, never imported/executed as a replay fallback.
    provenance = [__file__, str(root / 'services/platform/src/reputation_platform/atomic_swap_protocol.py'),
        str(root / 'packages/core/src/reputation_core/shared_scoring.py'),
        str(root / 'packages/core/src/reputation_core/scoring.py'),
        str(root / 'services/platform/src/reputation_platform/swap_report.py'),
        str(root / 'services/platform/src/reputation_platform/registration_discovery.py'),
        str(root / 'services/platform/src/reputation_platform/unsigned_swap_report.py')]
    provenance += [str(root / 'services/platform/src/reputation_platform' / name) for name in (
        'atomic_swap_export.py', 'shared_report.py', 'agent_profiles.py', 'report_chain_view.py', 'evaluation_report.py',
        'public_service_identity.py')]
    software = output / 'software'
    software.mkdir()
    for name in provenance:
        path = Path(name).resolve()
        _check(path.is_relative_to(root), 'Implementation snapshot is outside workspace')
        snapshot = software / (path.name + '.txt')
        snapshot.write_bytes(path.read_bytes())
        hashes[snapshot.relative_to(root).as_posix()] = _sha(snapshot.read_bytes())
    _write(output / ORIGIN, {'schema_version': 'atomic-swap-report-origin-v1', 'adapter': ADAPTER,
                            'source': source.relative_to(root).as_posix()})
    origin = (output / ORIGIN).relative_to(root).as_posix()
    hashes[origin] = _sha((output / ORIGIN).read_bytes())
    report = replay_atomic_swap_sources(root, SwapEvidence(root, hashes), config, datetime.now(timezone.utc))
    _write(output / 'manifest.json', {'schema_version': 'evaluation-input-manifest-v1',
        'implementation_note': {'path': ADR, 'sha256': hashes[ADR]},
        'inputs': [{'path': name, 'sha256': digest} for name, digest in sorted(hashes.items())]})
    _write(output / 'report.json', report.model_dump(mode='json'))
    from reputation_platform.evaluation_report import render_evaluation_report
    (output / 'report.html').write_text(render_evaluation_report(report), encoding='utf8')
    return report
