"""Versioned, offline replay of a prospective ERC20 routing campaign.

The frozen plan supplies slots, never verdicts. Missing/unsupported evidence stays in
those slots. v1 replay is deliberately kept in unsigned_swap_report unchanged.
"""
from datetime import datetime, timezone
import json
from pathlib import Path
import re
from uuid import UUID

from eth_hash.auto import keccak

from reputation_core import MeasurementPurpose, ReportFinding, SampleExplanation, ScoredSample, Verdict
from reputation_core.application import AgentProfile, normalize_reference
from reputation_core.reporting import EvaluationReport
from reputation_core.scoring import POINT_POLICY_VERSION
from reputation_core.shared_scoring import SharedAssessment
from reputation_core.swap import address, hex_bytes
from reputation_platform import unsigned_swap_report as old
from reputation_platform.registration_discovery import verify_registration_proof
from reputation_platform.public_service_identity import verify_service_identity, identity_limitations
from reputation_platform.unsigned_swap_protocol import UnsupportedUnsignedSwap, decode_unsigned_swap

ADAPTER = 'retained-unsigned-swap-campaign-v2'
ADR = 'docs/adr/0031-prospective-unsigned-swap-campaign.md'
REASSESSMENT_ADR = 'docs/adr/0033-independent-campaign-assessment.md'
METRICS = {'complete-response', 'intent-binding', 'deliverable-schema', 'execution-effect',
           'route-filter', 'default-slippage', 'undocumented-taker-default', 'explicit-slippage',
           'candidate-coverage', 'net-best-selection', 'safe-validation', 'safe-source-validation',
           'onchain-fulfillment'}
UNKNOWN = (Verdict.UNKNOWN, '缺少本案例可独立核验的原件；保留计划槽位，不补分。')


class _MalformedQuote(ValueError):
    pass


def _time(value):
    result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    old._check(result.tzinfo is not None, 'Campaign time must include a timezone')
    return result


def _public_response(evidence, path, url):
    if not path:
        return None
    observation, raw = evidence.observed(path)
    old._check(observation['url'] == url and observation['method'] == 'GET'
               and observation.get('request_json') is None, 'Campaign ACP endpoint mismatch')
    if (not raw or not observation.get('body_complete') or observation.get('error_kind')
            or observation.get('http_status') != 200):
        return None
    try:
        value = json.loads(raw)
    except (ValueError, UnicodeDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _optional_event(records, contract, topic, job_id, actor):
    matches = [log for row in records if not row['error']
               for log in ((row['value'] or {}).get('logs', []) if row['method'] == 'eth_getTransactionReceipt'
                           else row['value'] or [] if row['method'] == 'eth_getLogs' else [])
               if address(log['address']) == contract and len(log.get('topics', [])) == 3
               and log['topics'][0].lower() == topic and old._uint(log['topics'][1]) == int(job_id)]
    if not matches:
        return None, None
    old._check(all(log['topics'][2].lower() == old._topic(actor) for log in matches),
               'Campaign ACP event actor mismatch')
    fields = ('address', 'topics', 'data', 'transactionHash', 'blockHash', 'blockNumber',
              'transactionIndex', 'logIndex')
    old._check(len({json.dumps(old._normalized({key: log[key] for key in fields}), sort_keys=True)
                   for log in matches}) == 1,
               'Conflicting campaign ACP event originals')
    log = matches[0]
    old._check(all(not candidate.get('removed') for candidate in matches), 'ACP event was removed')
    receipt = old._lookup(records, 'eth_getTransactionReceipt', [log['transactionHash']])
    if receipt:
        old._check(old._uint(receipt['status']) == 1
                   and receipt['transactionHash'].lower() == log['transactionHash'].lower()
                   and receipt['blockHash'].lower() == log['blockHash'].lower()
                   and receipt['blockNumber'] == log['blockNumber'],
                   'Campaign ACP receipt contradicts event inclusion')
    if old._lookup(records, 'eth_getBlockByNumber', [log['blockNumber'], False]) is None:
        # Preserve observed submission presence for timeout logic; it is not yet
        # an authenticated delivery or a usable funding clock without its header.
        return log, None
    return old._event(records, contract, topic, job_id, actor)


def _timeout(evidence, item, request_plan, records, funded, history_path):
    """Only a complete exact event-range observation can prove no delivery by SLA."""
    if (not funded or not history_path
            or old._lookup(records, 'eth_chainId', []) is None):
        return None
    start = old._uint(funded['number'])
    provider = address(item['acp']['provider_wallet'])
    submitted, _ = _optional_event(records, address(request_plan['contract']), old.SUBMITTED,
                                   item['acp']['job_id'], provider)
    if submitted:
        return None  # A cached/incomplete chat cannot erase independently observed delivery.
    topics = [old.SUBMITTED, '0x' + format(int(item['acp']['job_id']), '064x'), old._topic(provider)]
    observed = _time(evidence.json(history_path)['observed_at']).timestamp()
    windows = []
    for row in records:
        if row['method'] != 'eth_getLogs' or row['error'] or row['value'] != []:
            continue
        query = row['params'][0]
        if (set(query) != {'address', 'topics', 'fromBlock', 'toBlock'}
                or old._normalized(query['topics']) != topics
                or address(query['address']) != address(request_plan['contract'])):
            continue
        if query['fromBlock'] in ('latest', 'pending', 'earliest') or query['toBlock'] in ('latest', 'pending', 'earliest'):
            continue
        end = old._lookup(records, 'eth_getBlockByNumber', [query['toBlock'], False])
        if (end and old._uint(end['number']) == old._uint(query['toBlock'])
                and old._uint(query['fromBlock']) <= start <= old._uint(end['number'])
                and observed >= old._uint(end['timestamp'])):
            windows.append((old._uint(end['timestamp']) - old._uint(funded['timestamp'])) * 1000)
    return max(windows) if windows else None


def _delivery(evidence, item, frozen_task, retained):
    plan = evidence.json(item['plan'])
    matches = [row for row in plan['tasks'] if row['task_key'] == item['task_key']]
    old._check(len(matches) == 1, 'Campaign task must bind a unique original request')
    frozen, acp = matches[0], item['acp']
    if not retained:
        old._check(frozen['requirement'] == frozen_task['request'], 'Actual request differs from prospective campaign')
        old._check(plan['chain_id'] == frozen_task['chain_id']
                   and address(plan['buyer']) == address(frozen_task['payer'])
                   and address(plan['asset_recipient']) == address(frozen_task['intended_asset_recipient']),
                   'Actual chain, payer or intended recipient differs from campaign')
    provider, buyer = address(acp['provider_wallet']), address(plan['buyer'])
    old._check(frozen['provider_id'] == acp['provider_id']
               and address(frozen['provider_wallet']) == provider, 'Campaign provider/request mismatch')
    base = 'https://api.acp.virtuals.io'
    detail = _public_response(evidence, acp.get('detail_observation'), base + '/agents/' + acp['provider_id'])
    job = _public_response(evidence, acp.get('job_observation'), f'{base}/jobs/{plan["chain_id"]}/{acp["job_id"]}')
    history = _public_response(evidence, acp.get('history_observation'), f'{base}/chats/{plan["chain_id"]}/{acp["job_id"]}/history')
    result = {'plan': plan, 'frozen': frozen, 'detail': (detail or {}).get('data'), 'provider': provider,
              'delivery': None, 'authenticated': False, 'elapsed_ms': None, 'observed_at': None,
              'reason': '公开业务读取未完整取得；不将平台或网络缺口认定为提供方失败。'}
    if not all((result['detail'], job, history)):
        return result
    if not isinstance(job.get('data'), dict) or not isinstance(history.get('entries'), list):
        return result
    job = job['data']
    result['job_status'] = job.get('jobStatus')
    old._check(result['detail']['id'] == acp['provider_id']
               and address(result['detail']['walletAddress']) == provider
               and job['providerId'] == acp['provider_id'] and address(job['providerAddress']) == provider
               and address(job['clientAddress']) == buyer and str(job['onChainJobId']) == str(acp['job_id'])
               and job['chainId'] == plan['chain_id'] and job['description'] == frozen['offering'],
               'Campaign public participant or offering mismatch')
    entries = history['entries']
    old._check(all(str(row['onChainJobId']) == str(acp['job_id']) and row['chainId'] == plan['chain_id']
                   for row in entries), 'Campaign history contains another job')
    requests = [row for row in entries if row['kind'] == 'message' and row.get('contentType') == 'requirement'
                and address(row['from']) == buyer]
    old._check(len(requests) == 1 and json.loads(requests[0]['content']) == frozen['requirement'],
               'Campaign original requirement differs from frozen payload')
    result['requirement_submitted_at'] = datetime.fromtimestamp(int(requests[0]['timestamp']) / 1000, timezone.utc)
    records = old._records(evidence, [*acp.get('rpc_observations', []),
                                     *acp.get('observation_end_rpc_observations', [])])
    rpc_chain = old._lookup(records, 'eth_chainId', [])
    old._check(rpc_chain is None or old._uint(rpc_chain) == plan['chain_id'], 'Campaign ACP RPC chain mismatch')
    fund, funded = _optional_event(records, address(plan['contract']), old.FUNDED, acp['job_id'], buyer)
    if fund and funded and old._uint(fund['data']) > 0:
        funded = dict(funded, timestamp=hex(max(old._uint(funded['timestamp']), int(requests[0]['timestamp']) // 1000)))
    else:
        funded = None
    deliveries = [row['event'] for row in entries if row['kind'] == 'system'
                  and row['event']['type'] == 'job.submitted']
    old._check(len(deliveries) <= 1, 'Conflicting campaign deliveries')
    if not deliveries:
        result['elapsed_ms'] = _timeout(evidence, item, plan, records, funded, acp.get('history_observation'))
        result['timeout_proven'] = result['elapsed_ms'] is not None
        result['reason'] = '未取得可认证交付；资金/观察窗/完整事件范围不足时保持UNKNOWN。'
        return result
    delivery = deliveries[0]
    old._check(address(delivery['provider']) == provider, 'Campaign delivery provider mismatch')
    digest = '0x' + keccak(delivery['deliverable'].encode('utf-8')).hex()
    old._check(digest.lower() == delivery['deliverableHash'].lower(), 'Campaign deliverable hash mismatch')
    submitted, block = _optional_event(records, address(plan['contract']), old.SUBMITTED, acp['job_id'], provider)
    if submitted:
        old._check(submitted['data'].lower() == digest.lower(), 'Campaign onchain deliverable mismatch')
    if not submitted or not block:
        result['reason'] = '已取得业务交付，但缺独立提交事件或规范区块原件；保持UNKNOWN。'
        return result
    result.update(authenticated=True, observed_at=datetime.fromtimestamp(old._uint(block['timestamp']), timezone.utc))
    if funded:
        result['elapsed_ms'] = (old._uint(block['timestamp']) - old._uint(funded['timestamp'])) * 1000
        old._check(result['elapsed_ms'] >= 0, 'Campaign delivery predates funding')
    try:
        result['delivery'] = json.loads(delivery['deliverable'])
    except (ValueError, UnicodeDecodeError):
        result['reason'] = '提供方链上认证交付不是可解析JSON。'
    return result


def _offering(detail, name):
    return next((row for row in (detail or {}).get('offerings', []) if row['name'] == name), {})


def _requirement_schema(offering):
    value = offering.get('requirements') or {}
    return json.loads(value) if isinstance(value, str) else value


def _request_mapping(facts):
    mapping = facts.get('request_mapping')
    if mapping is None:
        return None
    old._check(isinstance(mapping, dict), 'Invalid frozen request mapping')
    fields = mapping.get('fields', {})
    old._check(set(mapping) <= {'fields', 'source_values', 'default_slippage_bps',
                               'slippage_maximum_bps', 'route_offerings'}
               and isinstance(fields, dict) and fields
               and set(fields) <= {'fromTokenAddress', 'toTokenAddress', 'amount', 'taker', 'slippage', 'source'}
               and all(isinstance(value, str) and value for value in fields.values())
               and len(set(fields.values())) == len(fields), 'Invalid frozen request field mapping')
    values = mapping.get('source_values', {})
    old._check(isinstance(values, dict) and all(isinstance(key, str) and isinstance(value, str)
               and key and value for key, value in values.items())
               and len(set(values.values())) == len(values), 'Invalid frozen source value mapping')
    for key in ('default_slippage_bps', 'slippage_maximum_bps'):
        old._check(key not in mapping or type(mapping[key]) is int and 0 <= mapping[key] < 10000,
                   'Invalid frozen slippage mapping')
    routes = mapping.get('route_offerings')
    old._check(routes is None or isinstance(routes, list) and routes
               and all(isinstance(value, str) and value for value in routes)
               and len(set(routes)) == len(routes), 'Invalid frozen route offering scope')
    return mapping


def _request_view(facts):
    """Project authenticated bytes for rules; never replace the original request."""
    request = dict(facts['frozen']['requirement'])
    offering = _offering(facts.get('contract_detail') or facts['detail'], facts['frozen']['offering'])
    mapping = _request_mapping(facts)
    if mapping is None:
        return request, offering, None
    fields, values = mapping['fields'], mapping.get('source_values', {})
    names = {native: canonical for canonical, native in fields.items()}
    projected = {key: value for key, value in request.items() if key not in names}
    for canonical, native in fields.items():
        old._check(canonical == native or canonical not in request, 'Ambiguous native/canonical request aliases')
        if native in request:
            projected[canonical] = request[native]
    schema = _requirement_schema(offering)
    old._check(set(fields.values()) <= set(schema.get('properties', {})),
               'Request field mapping lacks declared native properties')
    properties = {names.get(key, key): dict(value) for key, value in schema.get('properties', {}).items()}
    if values:
        prop = properties.get('source', {})
        allowed = prop.get('enum') or re.findall(r"['\"]([^'\"]+)['\"]", prop.get('description', ''))
        old._check(allowed and set(values) <= set(allowed), 'Source value mapping lacks declared enum values')
        properties['source'] = dict(prop, enum=[values.get(value, value) for value in allowed])
        if isinstance(projected.get('source'), str):
            projected['source'] = values.get(projected['source'], projected['source'])
    offering = dict(offering, requirements=dict(schema, properties=properties,
        required=[names.get(key, key) for key in schema.get('required', [])]))
    if 'default_slippage_bps' in mapping:
        prop = properties.get('slippage', {})
        match = re.search(r'\bdefault\s*:?\s*(\d+)\s*=', prop.get('description', ''), re.I)
        declared = _default_slippage(offering)
        if declared is None and match:
            declared = int(match[1])
        old._check(declared == mapping['default_slippage_bps'],
                   'Frozen default slippage mapping differs from declaration')
        properties['slippage'] = dict(prop, default=declared)
    if 'slippage_maximum_bps' in mapping:
        prop = properties.get('slippage', {})
        cap = re.search(r'\b(?:hard\s+)?cap\s*:?\s*(\d+)', prop.get('description', ''), re.I)
        maximum = prop.get('maximum', int(cap[1]) if cap else None)
        old._check(maximum == mapping['slippage_maximum_bps'], 'Frozen slippage cap differs from declaration')
    return projected, offering, mapping


def _default_slippage(offering):
    prop = _requirement_schema(offering).get('properties', {}).get('slippage', {})
    if type(prop.get('default')) is int:
        return prop['default']
    match = re.search(r'\bdefault\s*:?\s*(\d+)\s*(?:\(|bps|basis|$)', prop.get('description', ''), re.I)
    return int(match[1]) if match else None


def _invalid_fields(request, offering, mapping=None):
    invalid = set()
    if not isinstance(request.get('amount'), str) or not request['amount'].isdigit() or int(request['amount']) <= 0:
        invalid.add('amount')
    for field in ('fromTokenAddress', 'toTokenAddress', 'taker'):
        if field == 'taker' and field not in request and (not mapping
                or field not in _requirement_schema(offering).get('required', [])):
            continue
        try:
            value = address(request[field])
            if int(value, 16) == 0:
                invalid.add(field)
        except (ValueError, KeyError, TypeError):
            invalid.add(field)
    if 'slippage' in request and (type(request['slippage']) is not int or not 0 <= request['slippage'] < 10000):
        invalid.add('slippage')
    if (mapping and 'slippage' in request and type(request['slippage']) is int
            and request['slippage'] > mapping.get('slippage_maximum_bps', 9999)):
        invalid.add('slippage')
    prop = _requirement_schema(offering).get('properties', {}).get('source', {})
    allowed = prop.get('enum') or re.findall(r'\b[A-Z][A-Z0-9_]{2,}\b', prop.get('description', ''))
    if 'source' in request and allowed and request['source'] not in allowed:
        invalid.add('source')
    return invalid


def _rejection(delivered):
    if not isinstance(delivered, dict) or delivered.get('quote') or delivered.get('route'):
        return None
    text = json.dumps(delivered, ensure_ascii=False)
    if (delivered.get('error') or delivered.get('errors') or delivered.get('reasons') or delivered.get('reason')
            or delivered.get('status') in ('rejected', 'error', 'failed', 'invalid_request', 'no_route', 'no_liquidity', 'unavailable', 'declined')):
        return text
    return None


def _quote_input(facts):
    delivered = facts['delivery']
    if not isinstance(delivered, dict) or not (delivered.get('quote') or delivered.get('route')):
        return None
    request, offering, mapping = _request_view(facts)
    if _invalid_fields(request, offering, mapping):
        return None
    if 'slippage' not in request:
        default = _default_slippage(offering)
        if default is None:
            return None
        request['slippage'] = default
    route = delivered.get('quote') or delivered['route']
    transaction = ({'to': route['routerContract'], 'data': route['calldata'], 'value': route['value']}
                   if 'quote' in delivered else {'to': route['target'], 'data': route['calldata'], 'value': route['valueToSend']})
    if 'taker' not in request:
        decoded = decode_unsigned_swap(transaction, chain_id=facts['plan']['chain_id'])
        # The decoded recipient is an observed fact, never an invented API default.
        if address(decoded['recipient']) != address(facts['plan']['asset_recipient']):
            return None
        request['taker'] = decoded['recipient']
    expected, decoded, transaction = old._intent(facts['plan'], dict(facts['frozen'], requirement=request), delivered)
    return {'expected': expected, 'decoded': decoded, 'transaction': transaction,
            'route': route, 'original_request': facts['frozen']['requirement']}


def _quote(evidence, item, facts, planned):
    try:
        result = _quote_input(facts)
    except UnsupportedUnsignedSwap:
        raise
    except (KeyError, TypeError, ValueError) as error:
        raise _MalformedQuote(str(error)) from error
    if result is None:
        return None
    expected, decoded, transaction = (result[key] for key in ('expected', 'decoded', 'transaction'))
    simulation = (Verdict.UNKNOWN, '缺可判完整模拟，或认证方案已违反请求约束。', {})
    if not decoded['intent_binding_issues']:
        try:
            simulation = old._simulation(evidence, item, expected, decoded, transaction)
        except (KeyError, TypeError):
            simulation = (Verdict.UNKNOWN, '模拟原件缺关键字段，不能据此认定提供方违约。', {})
    if simulation[2] and facts['observed_at']:
        records = old._records(evidence, item['simulation']['rpc_observations'])
        header = old._lookup(records, 'eth_getBlockByNumber', [hex(simulation[2]['block']), False])
        if header and old._uint(header['timestamp']) < int(facts['observed_at'].timestamp()):
            simulation = (Verdict.UNKNOWN, '模拟固定块早于该报价的认证交付，未证明共同有效窗口。', {})
    execution = (Verdict.UNKNOWN, '预定正常真实履约尚无可核执行原件。', {})
    if item.get('execution') and simulation[2]:
        fields = item['execution'].get('pre_balance_fields')
        if fields is not None:
            old._check(set(fields) == {'input', 'output'} and all(isinstance(x, str) for x in fields.values()),
                       'Expected explicit input/output pre-balance field names')
            fields = (fields['input'], fields['output'])
        elif not planned.get('retained'):
            fields = ('pre_input_raw', 'pre_output_raw')
        try:
            execution = old._execution(evidence, item, expected, decoded, transaction, simulation[2], balance_fields=fields)
        except (KeyError, TypeError):
            execution = (Verdict.UNKNOWN, '执行原件缺关键字段或方向余额映射，尚不能独立核齐。', {})
        except ValueError as error:
            if str(error) != 'Execution has not reached the reviewed 64-block confirmation distance':
                raise
            execution = (Verdict.UNKNOWN, '真实交易仍未达到既定64块确认距离，未降低门槛。', {})
    return dict(result, simulation=simulation, execution=execution)


def _route_filter(evidence, source, item, quote, requested):
    bindings = source.get('route_bindings', {}).get(requested, [])
    if not bindings or not quote or not item.get('simulation') or not quote['simulation'][2]:
        return UNKNOWN
    decoded = quote['decoded']
    routes = [row['router'] for row in decoded['actions'] if row.get('kind') == 'hydrex-net-output-transfer']
    if not routes:
        routes = [quote['transaction']['to']]
    records = old._records(evidence, item['simulation']['rpc_observations'])
    tag = hex(quote['simulation'][2]['block'])
    reviewed = set()
    for binding in bindings:
        old._check(binding.get('source_references'), 'Route deployment binding lacks provenance references')
        for reference in binding['source_references']:
            evidence.raw(reference)
        router = address(binding['router'])
        code = old._lookup(records, 'eth_getCode', [router, tag])
        if code and keccak(hex_bytes(code)).hex() == binding['runtime_keccak'].removeprefix('0x').lower():
            reviewed.add(router)
    if not reviewed:
        return UNKNOWN
    if all(address(router) in reviewed for router in routes):
        return Verdict.PASS, '实际内部路由地址及同块运行代码匹配有来源的请求source部署映射。'
    return Verdict.FAIL, '实际内部路由不匹配已独立核定的请求source部署；未用提供方标签替代来源核验。'


def _metrics(evidence, source, item, planned, facts):
    metrics = {name: UNKNOWN for name in METRICS}
    if facts is None:
        return metrics, None
    mapping = _request_mapping(facts)
    if mapping and mapping.get('route_offerings') is not None and facts['frozen']['offering'] not in mapping['route_offerings']:
        # Retain authenticated auxiliary deliveries without pretending their
        # schemas or correctness are adapted as exact-input swap routes.
        return metrics, None
    elapsed = facts['elapsed_ms']
    if facts.get('timeout_proven') and elapsed > source['response_deadline_ms']:
        metrics['complete-response'] = (Verdict.FAIL, '资金已就绪，完整身份绑定事件范围证明交付未在预定SLA内提交。')
    if not facts['authenticated']:
        return metrics, None
    delivered = facts['delivery']
    request, offering, mapping = _request_view(facts)
    rejection = _rejection(delivered)
    invalid = _invalid_fields(request, offering, mapping)
    if elapsed is not None:
        route = delivered.get('quote') if isinstance(delivered, dict) else None
        route_fields = ('amountIn', 'amountOut', 'minOutputAmount', 'routerContract', 'calldata', 'value')
        complete_quote = isinstance(route, dict) and all(isinstance(route.get(name), str) for name in route_fields)
        other_route = delivered.get('route') if isinstance(delivered, dict) else None
        complete_route = isinstance(other_route, dict) and all(name in other_route for name in ('target', 'calldata', 'valueToSend', 'quotedOut', 'minOut'))
        complete = bool(complete_quote or complete_route)
        facts['response_complete'] = complete
        if complete:
            metrics['complete-response'] = (Verdict.PASS if elapsed <= source['response_deadline_ms'] else Verdict.FAIL,
                f'原始链上完整报价交付耗时{elapsed}ms，预定{source["response_deadline_ms"]}ms。')
        elif rejection and (invalid or re.search(r'no[_ -]route|no[_ -]liquidity|insufficient liquidity|slippage|price impact|amount too small|market protection', rejection, re.I)):
            metrics['complete-response'] = (Verdict.UNKNOWN,
                '认证拒绝不冒充完整可用报价；非法输入不计正常A，市场/保护拒绝缺归因时保留UNKNOWN。原文：' + rejection)
        else:
            metrics['complete-response'] = (Verdict.FAIL,
                '正常已就绪请求未取得完整可用报价；认证的内部/上游错误或不完整交付属于本次服务交付失败。原文：' + json.dumps(delivered, ensure_ascii=False))
    if rejection and invalid:
        # A generic upstream/500 error does not prove correct parameter validation.
        validation = bool(re.search(r'invalid|required|positive|validation|unsupported|not supported|must be|out of range', rejection, re.I))
        field_named = any(name.lower() in rejection.lower() for field in invalid
                          for name in (field, (mapping or {}).get('fields', {}).get(field, field)))
        if validation and field_named:
            metric = 'safe-source-validation' if invalid == {'source'} else 'safe-validation'
            metrics[metric] = (Verdict.PASS, '认证交付明确拒绝了实际非法参数；没有产生资产执行或扩大授权。')
    if rejection:
        return metrics, None
    try:
        quote = _quote(evidence, item, facts, planned)
    except UnsupportedUnsignedSwap:
        return metrics, None
    except _MalformedQuote:
        metrics['deliverable-schema'] = (Verdict.FAIL, '认证交付缺少可解析报价必需字段或类型不符。')
        return metrics, None
    if quote is None:
        if not isinstance(delivered, dict) or not (delivered.get('quote') or delivered.get('route')):
            metrics['deliverable-schema'] = (Verdict.FAIL, '认证交付不是可解析的报价/拒绝JSON。')
        return metrics, None
    fields = ('amountIn', 'amountOut', 'minOutputAmount', 'routerContract', 'calldata', 'value')
    if 'quote' in delivered:
        valid = all(isinstance(quote['route'].get(name), str) for name in fields)
        valid = valid and quote['route']['amountIn'] == str(quote['expected']['amount_in'])
        metrics['deliverable-schema'] = (Verdict.PASS if valid else Verdict.FAIL,
                                         '核对声明的六项交付字段、字符串类型及amountIn与实际输入一致。')
    issues = quote['decoded']['intent_binding_issues']
    metrics['intent-binding'] = (Verdict.FAIL if issues else Verdict.PASS,
                                  ' '.join(issues) if issues else '原请求与协议解码的资产、raw金额、收款和最低到账匹配。')
    metrics['execution-effect'] = quote['simulation'][:2]
    metrics['onchain-fulfillment'] = quote['execution'][:2]
    if 'slippage' not in request and _default_slippage(offering) is not None:
        metrics['default-slippage'] = metrics['intent-binding']
    if 'taker' not in request:
        metrics['undocumented-taker-default'] = (Verdict.UNKNOWN, '已记录实际收款人，但接口未声明默认taker语义；不臆造默认规则。')
    if 'slippage' in request:
        metrics['explicit-slippage'] = metrics['intent-binding']
    if 'source' in request:
        metrics['route-filter'] = _route_filter(evidence, source, item, quote, request['source'])
    return metrics, quote


def _comparison(plan, evaluated):
    for group in plan.get('comparison_groups', []):
        rows = [evaluated.get(label) for label in group['task_ids']]
        if not all(rows) or not all(row['quote'] and row['quote']['simulation'][0] == Verdict.PASS for row in rows):
            continue
        quotes = [row['quote'] for row in rows]
        blocks = {(q['simulation'][2]['block'], q['simulation'][2]['block_hash']) for q in quotes}
        parameters = {(q['expected']['token_in'], q['expected']['token_out'], q['expected']['amount_in'], q['expected']['recipient']) for q in quotes}
        if len(blocks) != 1 or len(parameters) != 1:
            continue
        candidates = [row for row in rows if row['label'] != group['omission_task']]
        if not candidates or any(row['metrics']['route-filter'][0] != Verdict.PASS for row in candidates):
            continue
        selected = evaluated[group['omission_task']]
        # Separate filtered calls establish our comparison set, not the omitted-source
        # service's internal queried set. Never turn that unobserved claim into PASS.
        net = int(selected['quote']['simulation'][2]['output_credit_raw'])
        best = max(int(row['quote']['simulation'][2]['output_credit_raw']) for row in candidates)
        selected['metrics']['net-best-selection'] = (Verdict.PASS if net >= best else Verdict.FAIL,
                                                     f'同参数同块自动选择净到账{net}，预定可核source最大净到账{best}；未添加事后价格容差。')


def _campaign_lineage(evidence, current_path):
    """Authenticate append-only revisions; task clocks come from real freezes."""
    versions, visited = [], set()
    path, expected = current_path, None
    while path:
        old._check(path not in visited, 'Campaign plan lineage contains a cycle')
        visited.add(path)
        raw = evidence.raw(path)
        old._check(expected is None or old._sha(raw) == expected, 'Campaign previous plan digest mismatch')
        plan = json.loads(raw)
        old._check(plan['status'] == 'FROZEN' and plan.get('frozen_at'), 'Campaign plan is not frozen')
        frozen_at = _time(plan['frozen_at'])
        tasks = [*plan['new_tasks'], *plan.get('retained_tasks', [])]
        old._check(len({row['task_id'] for row in tasks}) == len(tasks), 'Duplicate campaign task labels')
        old._check(len({row['task_key'] for row in tasks}) == len(tasks), 'Duplicated campaign task identity')
        cases = {row['case_id']: row for row in plan['cases']}
        old._check(len(cases) == len(plan['cases']), 'Duplicate campaign case identity')
        labels = {row['task_id'] for row in tasks}
        for case in cases.values():
            members = case['planned_task_ids']
            old._check(len(set(members)) == len(members) and set(members) <= labels,
                       'Unknown/duplicate planned case task')
        snapshot = plan.get('source_snapshot')
        if snapshot:
            old._check(evidence.hashes.get(snapshot['path']) == snapshot['sha256']
                       and old._sha(evidence.raw(snapshot['path'])) == snapshot['sha256'],
                       'Frozen service declaration source changed')
        versions.append({'path': path, 'plan': plan, 'frozen_at': frozen_at})
        previous = plan.get('previous_plan')
        if previous:
            old._check(set(previous) == {'path', 'sha256'}, 'Invalid previous campaign plan reference')
            path, expected = previous['path'], previous['sha256']
        else:
            path = None
    versions.reverse()
    for before, after in zip(versions, versions[1:]):
        previous, current = before['plan'], after['plan']
        old._check(before['frozen_at'] <= after['frozen_at'], 'Campaign revision predates its previous freeze')
        for field in ('registration_reference', 'candidate_key', 'provider', 'capability',
                      'common_new_task_parameters', 'metric_definitions', 'scoring_contract', 'comparison_groups'):
            old._check(previous.get(field) == current.get(field), 'Campaign revision changed frozen ' + field)
        for field in ('new_tasks', 'retained_tasks'):
            originals = previous.get(field, [])
            old._check(current.get(field, [])[:len(originals)] == originals,
                       'Campaign revision changed or removed an original task')
        old_labels = {row['task_id'] for row in [*previous['new_tasks'], *previous.get('retained_tasks', [])]}
        new_labels = {row['task_id'] for row in [*current['new_tasks'], *current.get('retained_tasks', [])]} - old_labels
        old_cases = {row['case_id']: row for row in previous['cases']}
        new_cases = {row['case_id']: row for row in current['cases']}
        old._check(set(old_cases) <= set(new_cases), 'Campaign revision removed an original case')
        for case_id, case in new_cases.items():
            if case_id in old_cases:
                original = old_cases[case_id]
                old._check({key: value for key, value in case.items() if key != 'planned_task_ids'}
                           == {key: value for key, value in original.items() if key != 'planned_task_ids'},
                           'Campaign revision changed original case rules')
                members = original['planned_task_ids']
                old._check(case['planned_task_ids'][:len(members)] == members
                           and set(case['planned_task_ids'][len(members):]) <= new_labels,
                           'Campaign revision changed original task case assignments')
            else:
                old._check(set(case['planned_task_ids']) <= new_labels,
                           'New campaign case cannot change original task rules')
    return versions


def _task_observed_at(facts, quote=None):
    """Task sampling time is separate from the provider's delivery/SLA clock.

    requirement_submitted_at is set only after exact official job, buyer and
    frozen JSON binding in _delivery; a plan or creation map alone cannot set it.
    """
    when = (facts.get('observed_at') or facts.get('requirement_submitted_at')) if facts else None
    if quote and quote['execution'][2].get('timestamp'):
        executed_at = datetime.fromtimestamp(quote['execution'][2]['timestamp'], timezone.utc)
        when = max(when, executed_at) if when else executed_at
    return when


def campaign_report(root, evidence, source, generated_at):
    old._check(source['schema_version'] == 'unsigned-swap-evidence-v2' and source['adapter'] == ADAPTER,
               'Unsupported unsigned swap campaign source')
    evidence.raw(ADR)
    lineage = _campaign_lineage(evidence, source['campaign_plan'])
    plan = lineage[-1]['plan']
    task_versions = {}
    for version in lineage:
        for task in [*version['plan']['new_tasks'], *version['plan'].get('retained_tasks', [])]:
            task_versions.setdefault(task['task_id'], version)
    mapped = [row for row in plan.get('retained_tasks', []) if row.get('origin_campaign')]
    if mapped:
        evidence.raw(REASSESSMENT_ADR)
    for row in mapped:
        reference = row['origin_campaign']
        old._check(set(reference) == {'path', 'sha256'}
                   and old._sha(evidence.raw(reference['path'])) == reference['sha256'],
                   'Retained campaign digest mismatch')
        history = _campaign_lineage(evidence, reference['path'])
        original = history[-1]['plan']
        old._check(original['registration_reference'] == plan['registration_reference']
                   and original['candidate_key'] == plan['candidate_key']
                   and original.get('provider') == plan.get('provider'), 'Retained campaign identity mismatch')
        matches = [task for task in original['new_tasks'] if task['task_key'] == row['task_key']]
        old._check(len(matches) == 1 and {key: value for key, value in row.items()
                   if key not in ('origin_campaign', 'retention_purpose')} == matches[0]
                   and row.get('retention_purpose') == 'retrospective-case-remap',
                   'Retained campaign task differs from original frozen request')
        first = next(version for version in history
                     if any(task['task_key'] == row['task_key'] for task in version['plan']['new_tasks']))
        task_versions[row['task_id']] = dict(first, origin_lineage=history)
    canonical = normalize_reference(source['registration_reference'])
    old._check(canonical == source['registration_reference'] == plan['registration_reference'], 'Campaign canonical identity mismatch')
    old._check(source['candidate_key'] == plan['candidate_key'], 'Campaign candidate key mismatch')
    if plan.get('common_new_task_parameters'):
        old._check(source['response_deadline_ms'] == plan['common_new_task_parameters']['normal_response_deadline_ms'],
                   'Source response SLA differs from frozen campaign')
    proof = evidence.json(source['registration_proof'])
    for reference in proof['source_refs']:
        old._check(evidence.hashes.get(reference['path']) == reference['sha256'], 'Campaign registration source changed')
        evidence.raw(reference['path'])
    identity = verify_service_identity(root, source['registration_proof'], canonical, chain_verifier=verify_registration_proof)
    old._check(identity['public_registry_verified'], 'Campaign public registration is not independently verified')
    profile = AgentProfile.model_validate_json(json.dumps(source['profile']))
    old._check(profile.registration_chain_id == identity['registration_chain_id'], 'Campaign profile registration chain mismatch')
    by_label = {row['task_id']: dict(row) for row in plan['new_tasks']}
    retained = {row['task_id']: row for row in plan.get('retained_tasks', [])}
    old._check(len(by_label) == len(plan['new_tasks'])
               and len(retained) == len(plan.get('retained_tasks', [])), 'Duplicate campaign task labels')
    old._check(all(UUID(row['task_key']).version == 4 for row in by_label.values()), 'New campaign task is not a UUIDv4')
    for label, row in retained.items():
        old._check(label not in by_label, 'Duplicate retained/new campaign task')
        by_label[label] = dict(row, retained=True)
    old._check(len({row['task_key'] for row in by_label.values()}) == len(by_label), 'Duplicated campaign task identity')
    supplied = {row['task_key']: row for row in source['tasks']}
    old._check(len(supplied) == len(source['tasks']) and set(supplied) <= {row['task_key'] for row in by_label.values()}, 'Unexpected or duplicate source task')
    evaluated, execution_transactions = {}, set()
    for label, planned in by_label.items():
        item = supplied.get(planned['task_key'])
        refs, facts = [source['campaign_plan']], None
        version = task_versions.get(label)
        contract_detail = None
        if version:
            refs.append(version['path'])
            snapshot = version['plan'].get('source_snapshot')
            if snapshot:
                refs.append(snapshot['path'])
                contract_detail = evidence.json(snapshot['path'])['data']
        if item and item.get('retained_source'):
            old._check(planned.get('retained') and item['retained_source'] == retained[label]['source'], 'Unexpected retained source')
            retained_source = evidence.json(item['retained_source'])
            old._check(retained_source['registration_reference'] == canonical, 'Retained source belongs to another identity')
            matches = [row for row in retained_source['tasks'] if row['task_key'] == planned['task_key']]
            old._check(len(matches) == 1, 'Retained task missing or duplicated')
            refs.append(item['retained_source'])
            item = matches[0]
        if item:
            if plan.get('provider'):
                expected_provider = plan['provider']
                old._check(item['acp']['provider_id'] == expected_provider['provider_id']
                           and address(item['acp']['provider_wallet']) == address(expected_provider['provider_wallet']),
                           'Source provider differs from frozen campaign')
            old._check(not item.get('execution') or planned.get('retained') or planned['planned_actual_execution'],
                       'Unplanned actual execution cannot enter this campaign')
            if item.get('execution'):
                execution = item['execution']
                execution_plan = evidence.json(execution['plan'])
                transaction = (old._uint(execution_plan['chain_id']), execution['transaction_hash'].lower())
                # This v2 adapter accepts one swap in an exact eight-call batch.
                # Its transaction cannot supply multiple task samples; adapters
                # for genuine multi-task receipts need their own event binding.
                old._check(transaction not in execution_transactions,
                           'Single-swap campaign execution transaction is reused across tasks')
                execution_transactions.add(transaction)
            refs.extend([item['plan'], *(name for key, name in item['acp'].items() if key.endswith('_observation') and name),
                         *item['acp'].get('rpc_observations', []), *item['acp'].get('observation_end_rpc_observations', [])])
            for stage in ('simulation', 'execution'):
                if item.get(stage):
                    refs.extend([item[stage]['plan'], *item[stage]['rpc_observations']])
                    if stage == 'execution':
                        refs.append(item[stage]['intent_path'])
            inherited_campaign = bool(planned.get('origin_campaign'))
            facts = _delivery(evidence, item, planned, planned.get('retained', False) and not inherited_campaign)
            facts['request_mapping'] = version['plan'].get('request_mapping') if version else None
            if identity.get('provider_wallet'):
                old._check(facts['provider'] == identity['provider_wallet'], 'Actual provider differs from public registry proof')
            # The registry owner controls the verified tokenURI service binding;
            # the service wallet is a separate role. _delivery binds that exact
            # service's official id/wallet to the real job provider independently.
            services = [row.get('endpoint', '') for row in (identity.get('document') or {}).get('services', [])]
            old._check('https://app.virtuals.io/acp/agent/' + item['acp']['provider_id'] in services,
                       'Registration does not bind this campaign service')
            if (not planned.get('retained') or inherited_campaign) and facts.get('requirement_submitted_at'):
                old._check(facts['requirement_submitted_at'] >= version['frozen_at'], 'Actual requirement predates campaign freeze')
                request_campaign = facts['plan'].get('campaign_source')
                if request_campaign:
                    old._check(any(row['path'] == request_campaign['path']
                                   and old._sha(evidence.raw(row['path'])) == request_campaign['sha256']
                                   for row in version.get('origin_lineage', lineage)), 'Actual request campaign is absent from authenticated lineage')
            if contract_detail and (not planned.get('retained') or inherited_campaign):
                old._check(contract_detail['id'] == item['acp']['provider_id']
                           and address(contract_detail['walletAddress']) == facts['provider'], 'Frozen service declaration provider mismatch')
                facts['contract_detail'] = contract_detail
        metrics, quote = _metrics(evidence, source, item, planned, facts)
        evaluated[label] = {'label': label, 'planned': planned, 'item': item, 'facts': facts,
                            'metrics': metrics, 'quote': quote, 'refs': list(dict.fromkeys(refs))}
    _comparison(plan, evaluated)
    capability_id = plan['capability']['capability_id']
    tasks, samples, observations, cases = [], [], [], []
    normal_targets = {label for case in plan['cases'] if case['normal_execution'] for label in case['planned_task_ids']}
    for row in sorted(evaluated.values(), key=lambda value: value['label']):
        planned, facts, quote = row['planned'], row['facts'], row['quote']
        executed = bool(row['item'] and row['item'].get('execution'))
        verdict, reason = row['metrics']['onchain-fulfillment'] if executed else row['metrics']['execution-effect']
        if facts and _rejection(facts['delivery']):
            outcome = 'rejected'
            verdict, reason = next((row['metrics'][name] for name in ('safe-validation', 'safe-source-validation')
                                    if row['metrics'][name][0] != Verdict.UNKNOWN),
                                   (Verdict.UNKNOWN, '已认证业务拒绝：' + _rejection(facts['delivery'])))
        elif facts and facts.get('job_status') in ('REJECTED', 'DECLINED'):
            outcome = 'rejected'
            reason = '公开任务记录为拒绝；缺链上认证交付，不凭状态字段补功能通过或提供方违约。'
        elif executed:
            outcome = 'completed' if verdict == Verdict.PASS else 'failed' if verdict == Verdict.FAIL else 'unknown'
        else:
            outcome = 'completed' if quote else 'unknown'
        refs = row['refs']
        for name in list(refs):
            if name.endswith('.observation.json'):
                observation = evidence.json(name)
                if observation.get('response_file'):
                    raw = (Path(name).parent / observation['response_file']).as_posix()
                    evidence.raw(raw)
                    if raw not in refs:
                        refs.append(raw)
        request = planned.get('request') or (facts['frozen']['requirement'] if facts else {})
        summary = json.dumps(request, ensure_ascii=False, sort_keys=True)
        when = _task_observed_at(facts, quote)
        tasks.append({'task_key': planned['task_key'], 'capability_id': capability_id, 'input_summary': summary,
                      'outcome': outcome, 'attribution': 'unknown', 'observed_at': when, 'evidence': refs})
        samples.append(SampleExplanation(sample=ScoredSample(sample_id='campaign:' + row['label'], task_key=planned['task_key'],
            purpose=MeasurementPurpose.BEHAVIORAL if row['label'] in normal_targets else MeasurementPurpose.FUNCTIONAL,
            verdict=verdict, elapsed_ms=float(facts['elapsed_ms']) if facts and facts['elapsed_ms'] is not None else None,
            reason=reason, evidence=refs), observed_at=when, title=row['label'] + (' 真实兑换任务' if executed else ' 报价/参数任务'),
            input_summary=summary, claimed_output='按冻结请求返回可核方案或明确业务拒绝；预定正常履约须有真实兑换。',
            independent_result=reason, checks=[ReportFinding(label='独立效果', verdict=verdict, explanation=reason)], capability_id=capability_id))
    for frozen_case in plan['cases']:
        old._check(set(frozen_case['criterion_ids']) <= METRICS, 'Unknown campaign criterion')
        labels = frozen_case['planned_task_ids']
        old._check(set(labels) <= set(evaluated) and len(set(labels)) == len(labels), 'Unknown/duplicate planned case task')
        cases.append({'case_id': frozen_case['case_id'], 'capability_id': capability_id, 'dimension': frozen_case['dimension'],
            'declaration_group_id': frozen_case['declaration_group_id'], 'title': frozen_case['case_id'],
            'criterion_ids': frozen_case['criterion_ids'], 'task_keys': [by_label[label]['task_key'] for label in labels],
            'normal_execution': frozen_case['normal_execution'], 'required_decisive': frozen_case['required_decisive']})
        for label in labels:
            row = evaluated[label]
            if row['item'] is None:
                continue  # A missing planned slot is NOT_RUN, not a fabricated observation.
            for criterion in frozen_case['criterion_ids']:
                verdict, reason = row['metrics'][criterion]
                observations.append({'task_key': by_label[label]['task_key'], 'case_id': frozen_case['case_id'],
                    'criterion_id': criterion, 'dimension': frozen_case['dimension'], 'verdict': verdict.value,
                    'reason': reason, 'evidence': row['refs'], 'measurement_validity': 'valid',
                    'elapsed_ms': float(row['facts']['elapsed_ms']) if frozen_case['dimension'] == 'availability' and row['facts'] and row['facts']['elapsed_ms'] is not None else None,
                    'response_complete': bool(row['facts'] and row['facts'].get('response_complete')) if frozen_case['dimension'] == 'availability' else None,
                    'critical': criterion == 'onchain-fulfillment' and verdict == Verdict.FAIL})
    groups = [{'group_id': row['group_id'], 'title': row['group_id'], 'description': row['scope'], 'selected': True,
               'selection_reason': '预先冻结的通用路由声明组。', 'source_references': [row['source']]}
              for row in plan['capability']['declaration_groups']]
    assessment = SharedAssessment.model_validate_json(json.dumps({'schema_version': 'shared-task-assessment-v3',
        'capabilities': [{'capability_id': capability_id, 'title': 'ERC20精确输入路由', 'description': source['scope'],
                          'selected': True, 'write_operation': True, 'declaration_groups': groups}],
        'cases': cases, 'tasks': tasks, 'observations': observations}, ensure_ascii=False, default=lambda value: value.isoformat()))
    return EvaluationReport(policy_version=POINT_POLICY_VERSION, candidate_key=source['candidate_key'], name=source['name'],
        registration_reference=canonical, generated_at=generated_at, scope=source['scope'], scope_exclusions=source['scope_exclusions'],
        evaluation_window=('独立评价冻结于' + plan['frozen_at'] + '；旧任务按明确回顾映射重放，原冻结链、时间与声明快照保持；新任务先冻结再提交。'
            if mapped else '前瞻首版冻结于' + lineage[0]['plan']['frozen_at'] + '；当前追加版冻结于' + plan['frozen_at']
            + '；各任务使用首次纳入的原冻结时间与声明快照，未采槽位保留。'),
        approach='按冻结案例完整重放真实ACP原件；缺省参数、拒绝、缺证据与正常真实履约分别判断，沿用v3单分及30/40/30。',
        samples=samples, capabilities=[], shared_assessment=assessment, source_references=sorted(evidence.hashes),
        limitations=identity_limitations(canonical, [*old.LIMITATIONS, '扩大任务数量不证明长期可靠率；source与最佳价缺独立来源时保留UNKNOWN，不能用标签或重复简单任务补证。']))
