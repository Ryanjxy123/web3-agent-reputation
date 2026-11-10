"""Offline CoW/MCP source replay. Service tool/host/fee policies are frozen data."""
from datetime import datetime, timezone
import json
import re
from math import ceil, floor
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from uuid import UUID

from eth_hash.auto import keccak
from reputation_core import MeasurementPurpose, ReportFinding, SampleExplanation, ScoredSample, Verdict
from reputation_core.application import normalize_reference
from reputation_core.prediction_chain import calldata
from reputation_core.reporting import EvaluationReport
from reputation_core.scoring import POINT_POLICY_VERSION
from reputation_core.shared_scoring import SharedAssessment
from reputation_core.swap import address, hex_bytes, integer
from reputation_platform.cow_swap_protocol import (ORDER_FIELDS, CowSwapMismatch, UnsupportedCowSwap,
    decode_trade, derive_cow_argument, inspect_cow_order, normalize_order, order_uid_key, pointer, transfer_net, uint)
from reputation_platform.public_service_identity import identity_limitations, verify_service_identity
from reputation_platform.swap_report import SwapEvidence, _check, _lookup, _normalized, _sha, _write

ADAPTER = 'retained-cow-swap-campaign-v1'
ORIGIN = 'cow-swap-report-origin.json'
ADR = 'docs/adr/0035-cow-source-protocol.md'
LINEAGE_ADR = 'docs/adr/0040-cow-append-only-campaign-lineage.md'
DIAGNOSTICS_ADR = 'docs/adr/0041-cow-declared-diagnostics-calibration.md'
METRICS = ('complete-response', 'quote-binding', 'order-binding', 'appdata-policy',
    'validation-binding', 'balance-binding', 'fee-binding', 'surplus-binding',
    'safe-rejection', 'onchain-fulfillment', 'submit-binding')
UNKNOWN = (Verdict.UNKNOWN, '缺少该任务可独立核验的公开原件；保留任务槽位。', {})
LIMITATIONS = [
    '仅核冻结的ERC20精确输入CoW FOK订单范围；报价、构建、格式验证和模拟均不等于成交。',
    '同一经济任务的MCP阶段共享task_key；正常B按chain_id+UID去重，同一settlement tx可包含多个独立UID。',
    '服务host、tool、费用和appData来源策略在冻结数据中，协议不按对象名或固定partner费率给分。',
    'signed feeAmount为零不表示无网络/平台/solver费用；以冻结总输入、签入最低值和实际本人净资产为准。',
    '已有pilot回顾映射明确标注，不能称本次case在pilot之前前瞻冻结；旧失败与UNKNOWN不删除。',
    'A/F required_decisive是覆盖目标；使用现共享v3单分，不增加全部声明可判的总分门槛。',
    'B正常目标为双方向各4个真实UID，保护退出不补正常B；64块距离不声称finalized。',
    '原生submit私有签名请求不发布；没有认证公开原件时该工具判据保持UNKNOWN。',
]


def _time(value):
    result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    _check(result.tzinfo is not None, 'Explicit evidence timezone required')
    return result


def _snapshot(evidence, ref):
    _check(evidence.hashes.get(ref['path']) == ref['sha256'], 'Frozen CoW reference SHA differs')
    return evidence.raw(ref['path'])


def _public_path(root, name):
    path = (root / name).resolve()
    _check(path.is_relative_to(root) and not any('.private' in part.lower() or part.lower() in
        {'secrets', 'platform-config', '.env'} for part in path.relative_to(root).parts), 'Private input cannot enter CoW sources')
    _check(not path.name.upper().startswith(('SIGNED_', 'SIGNING_', 'SEND_', 'SUBMIT_INTENT')),
           'Private signing/send material cannot enter CoW sources')
    return path


def _campaign_lineage(evidence, current_path):
    """Verify original bytes and prospective append-only task/case revisions."""
    versions, seen = [], set()
    path, expected = current_path, None
    while path:
        _check(path not in seen, 'CoW campaign lineage cycle')
        seen.add(path)
        _check(_public_path(evidence.root, path).is_relative_to(evidence.root / 'runtime'), 'CoW plans must be public runtime originals')
        raw = evidence.raw(path)
        _check(expected is None or _sha(raw) == expected, 'CoW previous plan SHA differs')
        plan = json.loads(raw)
        _check(plan.get('schema_version') == 'cow-swap-campaign-v1' and plan.get('status') == 'FROZEN'
               and plan.get('frozen_at'), 'CoW DRAFT is review data, not a frozen scoring plan')
        versions.append({'path': path, 'sha256': _sha(raw), 'plan': plan, 'frozen_at': _time(plan['frozen_at'])})
        previous = plan.get('previous_plan')
        if previous:
            _check(isinstance(previous, dict) and set(previous) == {'path', 'sha256'}, 'Invalid CoW previous plan reference')
            path, expected = previous['path'], previous['sha256']
        else:
            path = None
    versions.reverse()
    immutable = ('schema_version', 'candidate_key', 'name', 'registration_reference', 'registered_service',
        'registration_proof', 'owner', 'chain_id', 'scoring_contract', 'source_snapshot', 'protocol_binding',
        'app_data_policy', 'operator_policy', 'capability', 'response_mapping',
        'deadline_clock_tolerance_seconds', 'scope', 'scope_exclusions')
    for before, after in zip(versions, versions[1:]):
        old, new = before['plan'], after['plan']
        _check(before['frozen_at'] <= after['frozen_at'], 'CoW revision predates previous freeze')
        _check(all(old.get(key) == new.get(key) for key in immutable), 'CoW revision changed frozen identity/service/policy')
        original = old['tasks']
        _check(new['tasks'][:len(original)] == original, 'CoW revision changed or removed an original task')
        labels = [task['task_id'] for task in new['tasks']]
        keys = [task['task_key'] for task in new['tasks']]
        _check(len(labels) == len(set(labels)) and len(keys) == len(set(keys)), 'CoW revision duplicated task identity')
        added = new['tasks'][len(original):]
        _check(all(task['selection_mode'] == 'prospective' for task in added), 'Appended CoW task must be prospective')
        fresh_ids = {task['task_id'] for task in added}
        _check([case['case_id'] for case in old['cases']] == [case['case_id'] for case in new['cases']],
               'CoW revision changed original case identities/order')
        for prior, case in zip(old['cases'], new['cases'], strict=True):
            _check({key: value for key, value in prior.items() if key != 'planned_task_ids'}
                   == {key: value for key, value in case.items() if key != 'planned_task_ids'},
                   'CoW revision changed original case rules or required_decisive')
            members, prefix = case['planned_task_ids'], prior['planned_task_ids']
            _check(members[:len(prefix)] == prefix and set(members[len(prefix):]) <= fresh_ids
                   and len(members) == len(set(members)) and set(members) <= set(labels),
                   'CoW revision changed original case assignments')
    return versions


def _task_plan_version(task, intent, versions):
    """Bind a real task intent to its exact selected frozen lineage node."""
    first = next(v for v in versions if any(t['task_key'] == task['task_key'] for t in v['plan']['tasks']))
    matching = [v for v in versions if v['path'] == intent.get('campaign_plan')]
    _check(len(matching) == 1, 'Task intent plan is absent from CoW lineage')
    version = matching[0]
    _check(intent.get('campaign_plan_sha256') == version['sha256']
           and version['frozen_at'] >= first['frozen_at']
           and any(t == task for t in version['plan']['tasks']), 'Task intent selected the wrong plan SHA/task version')
    plan = version['plan']
    expected = {'task_key': task['task_key'], 'task_id': task['task_id'], 'chain_id': plan['chain_id'],
                'owner': plan['owner'], 'expected': task['expected'], 'requests': task['requests']}
    _check(all(intent.get(key) == value for key, value in expected.items()), 'Task intent differs from its frozen lineage task')
    _check(intent.get('created_at') and _time(intent['created_at']) >= version['frozen_at'],
           'Task intent predates its selected frozen plan version')
    return version


def _measurement_contract(evidence, reference, plan_path, plan):
    """An explicit, source-backed retrospective measurement policy, never remote code."""
    _check(isinstance(reference, dict) and set(reference) == {'path', 'sha256'}, 'Invalid measurement contract reference')
    contract = json.loads(_snapshot(evidence, reference))
    _check(contract.get('schema_version') == 'cow-declared-diagnostics-contract-v1'
           and contract.get('selection_mode') == 'retrospective-measurement-calibration'
           and contract.get('campaign_plan') == {'path': plan_path, 'sha256': _sha(evidence.raw(plan_path))}
           and contract.get('declaration_snapshot') == plan['source_snapshot'], 'Measurement contract changed its frozen scope')
    _time(contract['created_at'])
    evidence.raw(DIAGNOSTICS_ADR)
    for ref in contract['source_refs']:
        _snapshot(evidence, ref)
    primary = set()
    for source in contract['primary_sources']:
        obs, raw = evidence.observed(source['observation'])
        _check(obs['method'] == 'GET' and obs['url'] == source['url'] and obs['http_status'] == 200
               and obs['body_complete'] and not obs['error_kind'] and raw
               and (Path(source['observation']).parent / obs['response_file']).as_posix() == source['response'],
               'Measurement rule lacks its complete primary-source original')
        primary.add(source['response'])
    rules = [contract['lifetime_protection'], *contract['warning_fields']]
    for rule in rules:
        _check(rule['tool'] in {r['tool'] for task in plan['tasks'] for r in task['requests']}, 'Unbound diagnostic tool')
        for fact in rule['source_facts']:
            _check(fact['path'] in primary, 'Diagnostic fact is not backed by a primary original')
            raw = _snapshot(evidence, {'path': fact['path'], 'sha256': fact['sha256']})
            lines = raw.decode('utf-8').splitlines()
            _check(1 <= fact['line_start'] <= fact['line_end'] <= len(lines)
                   and '\n'.join(lines[fact['line_start'] - 1:fact['line_end']]) == fact['text'],
                   'Declared diagnostic source excerpt differs')
    lifetime = contract['lifetime_protection']
    _check(isinstance(lifetime['minimum_remaining_seconds'], int) and lifetime['minimum_remaining_seconds'] > 0
           and lifetime['timestamp_precision_seconds'] == 1
           and all(lifetime['error_template'].count('{' + key + '}') == 1 for key in ('valid_to', 'remaining', 'minimum')),
           'Unsupported lifetime diagnostic rule')
    fields = set()
    for rule in contract['warning_fields']:
        # Only non-executable appData attribution is supported at warning level.
        # Chain, owner, receiver, domain, hash, fees and hooks cannot be downgraded.
        _check(rule['invalid_field'] == 'appCode' and rule['argument'] == 'fullAppData'
               and rule['pointer'] == '/appCode' and rule['invalid_field'] not in fields
               and plan['app_data_policy']['required_values'].get(rule['pointer']) == rule['expected_value']
               and all(rule['message_template'].count('{' + key + '}') == 1 for key in ('actual_json', 'expected')),
               'Unsupported or fatal warning-level field')
        fields.add(rule['invalid_field'])
    return contract


def _order_expectations(plan, task, quote, build):
    fields = {key: pointer(quote['payload'], path) for key, path in plan['response_mapping']['quote'].items()}
    bps = uint(task['expected']['slippage_bps'])
    _check(bps < 10000, 'Invalid frozen slippage')
    minimum = (uint(fields['buy_amount']) * (10000 - bps) + 9999) // 10000
    elapsed, lifetime = ceil(float(build['obs']['elapsed_ms']) / 1000), uint(task['expected']['valid_for_seconds'])
    tolerance = uint(plan['deadline_clock_tolerance_seconds'])
    return dict(task['expected'], recipient=task['expected']['owner'], minimum_out=str(minimum),
        valid_to_min=floor(build['when'].timestamp()) - elapsed + lifetime - tolerance,
        valid_to_max=ceil(build['when'].timestamp()) + elapsed + lifetime + tolerance), fields


def _warning_diagnostic(plan, task, rows):
    contract = plan.get('_measurement_contract')
    rule = next((r for r in contract['warning_fields'] if r['invalid_field'] == task['expected']['invalid_field']), None) if contract else None
    if not rule:
        return None
    stages = {row['stage']: row for row in rows}
    quote, build = stages.get('quote'), stages.get('build')
    native = next((row for row in rows if row['payload'] is not None
                   and next(s for s in task['requests'] if s['stage'] == row['stage'])['tool'] == rule['tool']), None)
    if not quote or not build or not native or quote['payload'] is None or build['payload'] is None:
        return UNKNOWN
    try:
        expected, _ = _order_expectations(plan, task, quote, build)
        material = _material(plan, build)
        facts = inspect_cow_order(material, expected, plan['protocol_binding'], plan['app_data_policy'])
        args, value = native['arguments'], native['payload']
        original, changed = json.loads(material['full_app_data']), json.loads(args[rule['argument']])
        actual = pointer(changed, rule['pointer'])
        restored = dict(changed, appCode=rule['expected_value'])
        _check(actual != rule['expected_value'] and restored == original, 'Warning task is not one isolated attribution mutation')
        order = dict(args['order'], appData=facts['app_data_hash'])
        _check(normalize_order(order) == facts['order']
               and args['signingDomain'] == material['domain'] and args['orderbookUrl'] == material['orderbook_url']
               and args['order']['appData'].lower() == '0x' + keccak(args[rule['argument']].encode()).hex(),
               'Warning diagnostic changed an executable or cryptographic constraint')
    except (ValueError, KeyError, TypeError):
        return Verdict.UNKNOWN, '告警检查的独立单字段前置条件未证实；不降低致命约束。', {}
    message = rule['message_template'].replace('{actual_json}', json.dumps(actual, ensure_ascii=False, separators=(',', ':'))).replace('{expected}', str(rule['expected_value']))
    good = value.get('valid') is True and value.get('errors') == [] and isinstance(value.get('warnings'), list) and message in value['warnings']
    return (Verdict.PASS if good else Verdict.FAIL,
        '原生工具按声明明确告警该独立归因字段；未将告警称为拒绝或成交。' if good else '独立归因字段缺少声明要求的明确告警或返回值不符合声明诊断等级。',
        {'diagnostic_severity': 'warning', 'invalid_field': rule['invalid_field']})


def _lifetime_protection(plan, task, build, native, facts):
    contract = plan.get('_measurement_contract')
    if not contract:
        return None
    rule, value = contract['lifetime_protection'], native['payload']
    spec = next(s for s in task['requests'] if s['stage'] == native['stage'])
    if spec['tool'] != rule['tool'] or value.get('valid') is not False or value.get('warnings') != []:
        return None
    errors = value.get('errors')
    if not isinstance(errors, list) or len(errors) != 1 or not isinstance(errors[0], str):
        return None
    minimum, deadline = rule['minimum_remaining_seconds'], facts['valid_to']
    template = rule['error_template'].replace('{valid_to}', str(deadline)).replace('{minimum}', str(minimum))
    match = re.fullmatch(re.escape(template).replace(re.escape('{remaining}'), r'([0-9]+)'), errors[0])
    if not match or not 0 < int(match[1]) < minimum:
        return None
    remaining, precision = int(match[1]), rule['timestamp_precision_seconds']
    def window(row):
        start = row['when'].timestamp()
        return floor(start) - precision, ceil(start + float(row['obs']['elapsed_ms']) / 1000) + precision
    before, after = window(build), window(native)
    created = deadline - uint(task['expected']['valid_for_seconds'])
    reported_now = deadline - remaining
    matched = before[0] <= created <= before[1] and after[0] <= reported_now <= after[1]
    return Verdict.UNKNOWN, ('原build绑定有效；验证时落入已声明的剩余有效期保护，未满足正常校验时效前置条件。'
        if matched else '原生工具报告已声明时效保护，但创建/验证时钟窗口不足以独立比较；保留UNKNOWN。'), {
        'protected': matched, 'reported_remaining_seconds': remaining, 'minimum_remaining_seconds': minimum}


def _plan(evidence, source):
    versions = _campaign_lineage(evidence, source['campaign_plan'])
    plan = versions[-1]['plan']
    frozen = versions[-1]['frozen_at']
    first_versions = {}
    for version in versions:
        for task in version['plan']['tasks']:
            first_versions.setdefault(task['task_key'], version)
    if len(versions) > 1:
        evidence.raw(LINEAGE_ADR)
        by_key = {task['task_key']: task for task in plan['tasks']}
        for item in source['tasks']:
            task = by_key.get(item['task_key'])
            _check(task is not None, 'Unknown CoW lineage task')
            if task['selection_mode'] == 'prospective':
                _check(item.get('task_intent'), 'CoW lineage task requires its original task intent')
                version = _task_plan_version(task, evidence.json(item['task_intent']), versions)
                _http_task(evidence, plan, task, item, version['frozen_at'])
    for key in ('candidate_key', 'name', 'registration_reference', 'registered_service', 'registration_proof'):
        _check(source[key] == plan[key], 'Source changed frozen ' + key)
    scoring = plan['scoring_contract']
    _check(scoring['policy'] == POINT_POLICY_VERSION and scoring['shared_schema'] == 'shared-task-assessment-v3'
           and scoring['weights'] == {'availability': 30, 'functional': 40, 'behavioral': 30}
           and scoring['minimum_confirmation_distance'] == 64 and scoring.get('response_sla_ms') is None,
           'CoW must preserve shared v3 scoring and canonical confirmation rules')
    _check(plan['chain_id'] == 8453 and plan['protocol_binding']['chain_id'] == 8453,
           'This evidence reader currently supports reviewed public Base RPC originals')
    _check(len({t['task_id'] for t in plan['tasks']}) == len(plan['tasks'])
           and len({t['task_key'] for t in plan['tasks']}) == len(plan['tasks']), 'Duplicated frozen CoW task')
    _snapshot(evidence, plan['source_snapshot'])
    obs, raw = evidence.observed(plan['source_snapshot']['observation'])
    request = json.loads(obs['request_json'])
    _check(obs['url'] == plan['registered_service'] and obs['method'] == 'POST'
           and request.get('method') == 'tools/list' and obs['http_status'] == 200 and obs['body_complete']
           and not obs['error_kind'] and raw and _sha(raw) == plan['source_snapshot']['sha256'],
           'Declaration needs its exact registered MCP tools/list original')
    listed = json.loads(raw)
    _check(listed.get('id') == request.get('id') and listed.get('jsonrpc') == '2.0', 'MCP declaration envelope differs')
    names = {tool['name'] for tool in listed['result']['tools']}
    for ref in [*plan['protocol_binding']['source_refs'], *plan['app_data_policy']['source_refs'],
                *plan.get('operator_policy', {}).get('source_refs', [])]:
        _snapshot(evidence, ref)
    clocks = {}
    for task in plan['tasks']:
        _check(UUID(task['task_key']).version == 4 and task['requests']
               and len({r['stage'] for r in task['requests']}) == len(task['requests']), 'Missing or duplicated task stage')
        _check(all(r['tool'] in names for r in task['requests']), 'Task tool is not in the frozen MCP declaration')
        _check(not task['planned_actual_execution'] or not task['expected']['safe_rejection'], 'Invalid task cannot plan a trade')
        _check(address(task['expected']['owner']) == address(plan['owner']), 'Task owner differs from selected own account')
        if task['selection_mode'] == 'retained-retrospective':
            origin = json.loads(_snapshot(evidence, task['retained_intent']))
            _check(origin['task_key'] == task['task_key'] and _time(origin['frozen_at']) <= frozen,
                   'Retained task lacks its exact original economic intent clock')
            for key, path in task['retained_intent_mapping'].items():
                actual = pointer(origin, path)
                expected = plan['chain_id'] if key == 'chain_id' else task['expected'][key]
                _check(address(actual) == address(expected) if key in {'owner', 'token_in', 'token_out'}
                       else uint(actual) == uint(expected), 'Retrospective mapping changed original ' + key)
            clocks[task['task_key']] = _time(origin['frozen_at'])
        else:
            _check(task['selection_mode'] == 'prospective', 'Explicit retrospective/prospective selection required')
            clocks[task['task_key']] = first_versions[task['task_key']]['frozen_at']
    canonical = normalize_reference(source['registration_reference'])
    _check(canonical == source['registration_reference'], 'Expected a canonical public service identity')
    identity_proof = evidence.json(source['registration_proof'])
    for ref in identity_proof['source_refs']:
        _snapshot(evidence, ref)
    identity = verify_service_identity(evidence.root, source['registration_proof'], canonical)
    _check(identity['public_registry_verified'] and plan['registered_service'] in
           [r.get('endpoint') for r in identity['document']['services']], 'Official identity does not bind this remote')
    if source.get('measurement_contract'):
        plan = dict(plan, _measurement_contract=_measurement_contract(evidence, source['measurement_contract'], source['campaign_plan'], plan))
    return plan, clocks, canonical


def _derived(spec, prior):
    return derive_cow_argument(spec, prior)


def _http_task(evidence, plan, task, item, frozen):
    names = item.get('http_observations', [])
    _check(len(names) <= len(task['requests']), 'Extra MCP observation outside this task')
    rows, prior = [], {}
    for spec, name in zip(task['requests'], names):
        obs, raw = evidence.observed(name)
        request = json.loads(obs['request_json'])
        arguments = dict(spec['arguments'])
        arguments.update({key: _derived(value, prior) for key, value in spec.get('derived_arguments', {}).items()})
        _check(obs['url'] == plan['registered_service'] and obs['method'] == 'POST'
               and request.get('jsonrpc') == '2.0' and request.get('method') == 'tools/call'
               and request.get('params') == {'name': spec['tool'], 'arguments': arguments},
               'Original native MCP request differs from frozen task or prior-stage binding')
        when = _time(obs['observed_at'])
        _check(when >= frozen and (not rows or when >= rows[-1]['when']), 'MCP request predates its true intent or stage order')
        complete = bool(raw and obs['body_complete'] and obs['http_status'] == 200 and not obs['error_kind'])
        payload, tool_error = None, False
        if complete:
            response = json.loads(raw)
            _check(response.get('jsonrpc') == '2.0' and response.get('id') == request.get('id'), 'Native MCP response envelope differs')
            result = response.get('result')
            tool_error = bool(response.get('error') or isinstance(result, dict) and result.get('isError'))
            if not tool_error:
                _check(isinstance(result, dict), 'MCP result object absent')
                content = result.get('content', [])
                _check(len(content) == 1 and content[0].get('type') == 'text', 'Unadapted MCP structured response shape')
                payload = json.loads(content[0]['text'])
        row = {'stage': spec['stage'], 'obs': obs, 'raw': raw, 'when': when, 'complete': complete,
               'payload': payload, 'tool_error': tool_error, 'arguments': arguments, 'observation': name}
        rows.append(row)
        prior[spec['stage']] = row
    return rows


def _material(plan, row):
    return {key: pointer(row['payload'], path) for key, path in plan['response_mapping']['build'].items()}


def _call(records, target, data, tag):
    matches = [r['value'] for r in records if r['method'] == 'eth_call' and not r['error'] and r['value'] is not None
        and len(r['params']) == 2 and r['params'][1] == tag and address(r['params'][0]['to']) == address(target)
        and r['params'][0]['data'].lower() == data.lower()
        and set(r['params'][0]) <= {'to', 'from', 'data', 'value', 'gas', 'gasPrice'}
        and integer(r['params'][0].get('value', 0)) == 0]
    _check(len(set(matches)) <= 1, 'Conflicting fixed-block RPC values')
    if not matches:
        return None
    raw = hex_bytes(matches[0])
    _check(len(raw) == 32, 'Expected one canonical 32-byte getter result')
    return int.from_bytes(raw, 'big')


def _rpc(evidence, names):
    return evidence.rpc_records(names, {'https://mainnet.base.org'})


def _api(evidence, name, url):
    obs, raw = evidence.observed(name)
    _check(obs['url'] == url and obs['method'] == 'GET' and obs.get('request_json') is None,
           'Independent order API request differs')
    if not raw or not obs['body_complete'] or obs['http_status'] != 200 or obs['error_kind']:
        return None
    return json.loads(raw)


def _api_trades(evidence, names, binding, uid):
    rows, offset, finished = [], 0, False
    for name in names:
        obs = evidence.json(name)
        url = urlsplit(obs['url'])
        base = urlsplit(binding['orderbook_url'])
        query = parse_qs(url.query)
        _check((url.scheme, url.netloc, url.path) == (base.scheme, base.netloc, base.path + '/api/v2/trades')
               and set(query) == {'orderUid', 'offset', 'limit'} and query['orderUid'] == [uid]
               and query['offset'] == [str(offset)] and len(query['limit']) == 1 and not finished,
               'Trade pages are not complete ordered pages for this UID')
        limit = uint(query['limit'][0])
        _check(0 < limit <= 1000, 'Unreviewed trade page size')
        page = _api(evidence, name, obs['url'])
        if page is None:
            return None
        _check(isinstance(page, list) and len(page) <= limit, 'Invalid trade page body')
        rows.extend(page)
        offset += len(page)
        finished = len(page) < limit
    return rows if finished else None


def _indexed_order(evidence, name, binding, facts):
    order = _api(evidence, name, binding['orderbook_url'] + '/api/v1/orders/' + facts['uid'])
    if order is None:
        return None
    _check(order['uid'].lower() == facts['uid'] and address(order['owner']) == facts['owner']
           and address(order['settlementContract']) == facts['settlement'], 'Indexed UID/owner/settlement differs')
    signed = {key: order[key] for key, _ in ORDER_FIELDS}
    _check(normalize_order(signed) == facts['order']
           and '0x' + keccak(order['fullAppData'].encode()).hex() == facts['app_data_hash'], 'Indexed signed order differs from build')
    return order


def _execution(evidence, plan, task, item, facts, clock):
    supplied = item.get('execution')
    if not supplied or not facts:
        return UNKNOWN
    _check(task['planned_actual_execution'], 'Unplanned execution cannot enter normal B')
    binding, owner, order = plan['protocol_binding'], facts['owner'], facts['order']
    indexed = _indexed_order(evidence, supplied['order_observation'], binding, facts)
    trades = _api_trades(evidence, supplied['trades_observations'], binding, facts['uid'])
    if indexed is None or trades is None or indexed.get('status') != 'fulfilled' or not trades:
        return Verdict.UNKNOWN, '独立订单未证实fulfilled/完整trades；过期或保护退出不补正常B。', {}
    _check(len(trades) == 1 and trades[0]['orderUid'].lower() == facts['uid']
           and address(trades[0]['owner']) == owner, 'FOK order requires one UID-specific trade')
    trade_index = trades[0]
    tx_hash = trade_index['txHash'].lower()
    records = _rpc(evidence, supplied['rpc_observations'])
    chain = _lookup(records, 'eth_chainId', [])
    tx = _lookup(records, 'eth_getTransactionByHash', [tx_hash])
    receipt = _lookup(records, 'eth_getTransactionReceipt', [tx_hash])
    if chain is None or not tx or not receipt:
        return UNKNOWN
    _check(integer(chain) == facts['chain_id'] == integer(tx['chainId']) and integer(receipt['status']) == 1,
           'Settlement chain differs or canonical receipt reverted')
    header = _lookup(records, 'eth_getBlockByNumber', [receipt['blockNumber'], False])
    if not header:
        return UNKNOWN
    _check(tx['hash'].lower() == receipt['transactionHash'].lower() == tx_hash
           and tx['blockHash'].lower() == receipt['blockHash'].lower() == header['hash'].lower()
           and tx['blockNumber'] == receipt['blockNumber'] == header['number']
           and tx['transactionIndex'] == receipt['transactionIndex']
           and header['transactions'][integer(receipt['transactionIndex'])].lower() == tx_hash
           and address(tx['to']) == facts['settlement']
           and clock.timestamp() <= integer(header['timestamp']) <= facts['valid_to'],
           'Settlement canonical inclusion/target/window differs')
    for log in receipt['logs']:
        _check(not log.get('removed') and log['transactionHash'].lower() == tx_hash
               and log['blockHash'].lower() == header['hash'].lower()
               and log['blockNumber'] == receipt['blockNumber'], 'Canonical log inclusion differs')
    decoded = [(log, decode_trade(log, facts['settlement'])) for log in receipt['logs']]
    owned = [(log, trade) for log, trade in decoded if trade and trade['owner'] == owner]
    matched = [(log, trade) for log, trade in owned if trade['uid'] == facts['uid']]
    _check(len(matched) == 1, 'Exactly one canonical Settlement Trade for this UID required')
    log, trade = matched[0]
    _check(integer(log['logIndex']) == integer(trade_index['logIndex'])
           and integer(log['blockNumber']) == integer(trade_index['blockNumber'])
           and trade['token_in'] == order['sellToken'] and trade['token_out'] == order['buyToken']
           and trade['sell_amount'] == order['sellAmount'] and trade['buy_amount'] >= order['buyAmount']
           and trade['fee_amount'] == order['feeAmount'], 'UID Trade assets/amount/minimum/fee differ')
    # Nonzero legacy signed fees need an independently reviewed net-amount rule.
    if any(value['fee_amount'] != 0 for _, value in owned):
        return Verdict.UNKNOWN, '非零legacy签入fee的事件净额规则未适配，保留UNKNOWN。', {}
    related = supplied.get('related_order_observations', {})
    aggregate = {order['sellToken']: 0, order['buyToken']: 0}
    seen = set()
    for _, value in owned:
        _check(value['uid'] not in seen, 'Repeated FOK UID in one settlement receipt')
        seen.add(value['uid'])
        if value['uid'] != facts['uid']:
            if value['uid'] not in related:
                return Verdict.UNKNOWN, '同钱包同tx有其它UID，缺其独立收款订单原件，未分摊净资产。', {}
            other = _api(evidence, related[value['uid']], binding['orderbook_url'] + '/api/v1/orders/' + value['uid'])
            if other is None:
                return UNKNOWN
            _check(other['uid'].lower() == value['uid'] and address(other['owner']) == owner
                   and address(other['receiver']) == owner and other['partiallyFillable'] is False
                   and address(other['sellToken']) == value['token_in'] and address(other['buyToken']) == value['token_out']
                   and uint(other['sellAmount']) == value['sell_amount'] and uint(other['feeAmount']) == 0
                   and value['buy_amount'] >= uint(other['buyAmount']), 'Related UID cannot support owner net attribution')
            other_order = {key: other[key] for key, _ in ORDER_FIELDS}
            other_material = {'order': other_order, 'owner': other['owner'], 'domain': binding['domain'],
                'chain_id': binding['chain_id'], 'orderbook_url': binding['orderbook_url'], 'primary_type': 'Order',
                'types': {'Order': [{'name': key, 'type': kind} for key, kind in ORDER_FIELDS]},
                'full_app_data': other['fullAppData'], 'app_data_hash': other['appData']}
            other_expected = {'owner': owner, 'recipient': owner, 'token_in': other['sellToken'], 'token_out': other['buyToken'],
                'amount_in': str(uint(other['sellAmount']) + uint(other['feeAmount'])), 'minimum_out': other['buyAmount'],
                'valid_to_min': other['validTo'], 'valid_to_max': other['validTo']}
            try:
                other_facts = inspect_cow_order(other_material, other_expected, binding, {'required_values': {}})
            except UnsupportedCowSwap:
                return Verdict.UNKNOWN, '同钱包其它UID含未适配订单模式，无法分摊净资产。', {}
            _check(other_facts['uid'] == value['uid'], 'Related order fields do not cryptographically bind its Trade UID')
        if value['token_in'] in aggregate:
            aggregate[value['token_in']] -= value['sell_amount']
        if value['token_out'] in aggregate:
            aggregate[value['token_out']] += value['buy_amount']
    observed_net = {token: transfer_net(receipt, token, owner) for token in aggregate}
    if observed_net != aggregate:
        return Verdict.UNKNOWN, '同tx本人ERC20净事件含未绑定变化，未将全tx输出重复分配到UID。', {'measurement_validity': 'invalid'}
    pre = supplied.get('prestate')
    if not pre:
        return UNKNOWN
    snapshot = evidence.json(pre['snapshot'])
    prepared = evidence.json(item['prepared_order'])
    intent = evidence.json(item['task_intent'])
    _check(snapshot['task_key'] == prepared['task_key'] == task['task_key']
           and snapshot['plan_sha256'] == prepared['plan_sha256'] == _sha(evidence.raw(item['task_intent']))
           and snapshot['prepared_order_sha256'] == _sha(evidence.raw(item['prepared_order']))
           and snapshot['uid'].lower() == facts['uid'], 'Public prestate does not bind task intent and unsigned build')
    if task['selection_mode'] == 'retained-retrospective':
        _check(item['task_intent'] == task['retained_intent']['path'], 'Retained task intent path differs')
    _check(intent.get('task_key') == task['task_key'] or item['task_intent'] == plan.get('_path'), 'Root intent task differs')
    for name in item['http_observations']:
        observation = evidence.json(name)
        body = (Path(name).parent / observation['response_file']).as_posix()
        _check(any((Path(item['prepared_order']).parent / ref['path']).as_posix() == body
                   and ref['sha256'] == _sha(evidence.raw(body)) for ref in prepared['inputs']),
               'Public prepared snapshot lacks an exact quote/build/validate source SHA')
    before_records = _rpc(evidence, pre['rpc_observations'])
    pretag = hex(uint(snapshot['fixed_block']))
    preheader = _lookup(before_records, 'eth_getBlockByNumber', [pretag, False])
    prechain = _lookup(before_records, 'eth_chainId', [])
    if not preheader or prechain is None:
        return UNKNOWN
    _check(integer(prechain) == facts['chain_id'] and preheader['hash'].lower() == snapshot['block_hash'].lower()
           and integer(preheader['number']) == integer(pretag) < integer(receipt['blockNumber'])
           and clock.timestamp() <= integer(preheader['timestamp']) <= integer(header['timestamp']), 'Prestate block/chain/window differs')
    for role, target in [('settlement', facts['settlement']), ('vault_relayer', facts['vault_relayer'])]:
        code = _lookup(before_records, 'eth_getCode', [target, pretag])
        if code is None or not binding.get('runtime_keccak', {}).get(role):
            return UNKNOWN
        _check('0x' + keccak(hex_bytes(code)).hex() == binding['runtime_keccak'][role], 'Reviewed CoW runtime differs')
    relayer = _call(before_records, facts['settlement'], calldata('vaultRelayer()'), pretag)
    separator = _call(before_records, facts['settlement'], calldata('domainSeparator()'), pretag)
    if relayer is None or separator is None:
        return UNKNOWN
    _check(relayer == int(facts['vault_relayer'], 16) and separator == int(facts['domain_separator'], 16), 'Onchain relayer/domain differs')
    for token, net in aggregate.items():
        before = _call(before_records, token, calldata('balanceOf(address)', owner), pretag)
        after = _call(records, token, calldata('balanceOf(address)', owner), receipt['blockNumber'])
        if before is None or after is None:
            return UNKNOWN
        if after - before != net:
            return Verdict.UNKNOWN, '公开前快照至回执块存在其它资产变化，余额窗口不可独立归属。', {'measurement_validity': 'invalid'}
    allowance = _call(records, order['sellToken'], calldata('allowance(address,address)', owner, facts['vault_relayer']), receipt['blockNumber'])
    uid_bytes = bytes.fromhex(facts['uid'][2:])
    data = calldata('filledAmount(bytes)', 32) + len(uid_bytes).to_bytes(32, 'big').hex() + uid_bytes.hex().ljust(128, '0')
    filled = _call(records, facts['settlement'], data, receipt['blockNumber'])
    head = _lookup(records, 'eth_blockNumber', [])
    if allowance is None or filled is None or head is None:
        return UNKNOWN
    _check(filled == order['sellAmount'], 'Onchain UID filledAmount differs')
    depth = integer(head) - integer(receipt['blockNumber'])
    if allowance != 0 or depth < 64:
        return Verdict.UNKNOWN, '原UID已成交；尚缺64块距离或原授权清零，保留原件继续对账。', {}
    return Verdict.PASS, '真实UID、canonical Settlement Trade、本人收款与净资产、期限、64块距离及allowance清零均核验。', {
        'uid': facts['uid'], 'transaction_hash': tx_hash, 'block': integer(receipt['blockNumber']),
        'block_hash': header['hash'], 'timestamp': integer(header['timestamp']), 'confirmation_distance': depth,
        'input_debit_raw': str(trade['sell_amount']), 'output_credit_raw': str(trade['buy_amount']),
        'owner_transaction_net_raw': {token: str(net) for token, net in aggregate.items()}, 'remaining_allowance_raw': '0'}


def _metrics(evidence, plan, task, item, rows, clock):
    metrics = {key: UNKNOWN for key in METRICS}
    by_stage = {row['stage']: row for row in rows}
    if task['expected']['safe_rejection']:
        diagnostic = _warning_diagnostic(plan, task, rows)
        if diagnostic is not None:
            metrics['safe-rejection'] = diagnostic
            return metrics, None
        # A generic error is not evidence of the specific promised protection.
        for row in rows:
            value = row['payload']
            if isinstance(value, dict) and value.get('valid') is False and value.get('errors'):
                term = task['expected']['invalid_field']
                if any(term.lower() in str(error).lower() for error in value['errors']):
                    metrics['safe-rejection'] = (Verdict.PASS, '已冻结无效字段由原生验证工具明确拒绝，未交付可执行方案。', {})
                break
            if isinstance(value, dict) and value.get('valid') is True:
                metrics['safe-rejection'] = (Verdict.FAIL, '独立已知无效的冻结字段仍被原生validate标为valid。', {})
                break
        return metrics, None
    if len(rows) == len(task['requests']) and all(row['complete'] and row['payload'] is not None for row in rows):
        metrics['complete-response'] = (Verdict.PASS, '该任务全部公开MCP阶段取得完整业务响应；未虚构公开SLA。', {})
    elif any(row['tool_error'] or row['obs'].get('http_status') in (400, 404, 422, 500, 502, 503) for row in rows):
        metrics['complete-response'] = (Verdict.FAIL, '冻结正常业务请求返回明确业务/服务错误，原失败保留。', {})
    expected, facts = task['expected'], None
    quote = by_stage.get('quote')
    if quote and quote['payload'] is not None:
        fields = {key: pointer(quote['payload'], path) for key, path in plan['response_mapping']['quote'].items()}
        good = (address(fields['owner']) == address(fields['recipient']) == address(expected['owner'])
            and address(fields['token_in']) == address(expected['token_in'])
            and address(fields['token_out']) == address(expected['token_out'])
            and uint(fields['sell_amount']) + uint(fields['fee_amount']) == uint(expected['amount_in'])
            and uint(fields['buy_amount']) > 0 and fields['kind'] == 'sell')
        metrics['quote-binding'] = (Verdict.PASS if good else Verdict.FAIL,
            '报价本人/资产/总输入及卖出模式与冻结任务一致。' if good else '报价经济字段违反冻结任务。', {})
    build = by_stage.get('build')
    if build and build['payload'] is not None and metrics['quote-binding'][0] == Verdict.PASS:
        independent, quote_fields = _order_expectations(plan, task, quote, build)
        try:
            facts = inspect_cow_order(_material(plan, build), independent, plan['protocol_binding'], plan['app_data_policy'])
        except UnsupportedCowSwap as error:
            metrics['order-binding'] = (Verdict.UNKNOWN, str(error), {})
        except CowSwapMismatch as error:
            metrics['order-binding'] = (Verdict.FAIL, '可解码订单违反冻结经济/密码绑定：' + str(error), {})
        if facts:
            metrics['order-binding'] = (Verdict.PASS, '签入Order全部字段、domain、总输入、独立最低值、本人receiver与UID均一致。', {})
            metrics['appdata-policy'] = (Verdict.PASS, '精确appData UTF-8哈希及冻结声明的来源/费用策略一致；未将此策略写成通用费率。', {})
            metrics['fee-binding'] = (Verdict.PASS, 'quote卖出量加报价费等于总预算；签入费与appData费用符合本服务冻结声明，零签入费未被称为免费。', {
                'quoted_fee_raw': str(quote_fields['fee_amount']), 'signed_fee_raw': facts['signed_fee_raw']})
    validate = by_stage.get('validate')
    if validate and validate['payload'] is not None and facts:
        result = validate['payload']
        valid = result.get('valid') is True and result.get('errors') == [] and result.get('warnings') == []
        metrics['validation-binding'] = (Verdict.PASS if valid else Verdict.FAIL,
            '原生validate绑定同一build原件，结果与独立协议核验一致。' if valid else '独立有效订单被原生validate拒绝或警告，原件保留。', {})
        protection = _lifetime_protection(plan, task, build, validate, facts)
        if protection is not None:
            metrics['validation-binding'] = protection
    # Balance accuracy and advisory market surplus require a matching independent
    # block/source pair; a number-shaped response alone is deliberately UNKNOWN.
    metrics['onchain-fulfillment'] = _execution(evidence, plan, task, item, facts, clock)
    return metrics, facts


def replay_cow_swap_sources(root, evidence, source, generated_at):
    _check(source.get('schema_version') == 'cow-swap-evidence-v1' and source.get('adapter') == ADAPTER,
           'Unsupported CoW source version')
    evidence.raw(ADR)
    plan, clocks, canonical = _plan(evidence, source)
    by_key = {item['task_key']: item for item in source['tasks']}
    _check(len(by_key) == len(source['tasks']) and set(by_key) <= {task['task_key'] for task in plan['tasks']},
           'Unexpected or duplicated CoW source task')
    evaluated, samples, shared_tasks, used_http, used_uid = {}, [], [], set(), set()
    capability = plan['capability']['capability_id']
    for task in plan['tasks']:
        item = by_key.get(task['task_key'])
        rows, metrics, facts = [], {name: UNKNOWN for name in METRICS}, None
        refs = [source['campaign_plan'], plan['source_snapshot']['path'], plan['source_snapshot']['observation']]
        if source.get('measurement_contract'):
            refs.extend([source['measurement_contract']['path'], DIAGNOSTICS_ADR])
        if item:
            names = item.get('http_observations', [])
            _check(not used_http.intersection(names), 'One business MCP observation cannot supply two economic tasks')
            used_http.update(names)
            rows = _http_task(evidence, plan, task, item, clocks[task['task_key']])
            refs.extend(names)
            for key in ('task_intent', 'prepared_order'):
                if item.get(key):
                    refs.append(item[key])
            execution = item.get('execution')
            if execution:
                refs.extend([execution['order_observation'], *execution['trades_observations'], *execution['rpc_observations']])
                refs.extend(execution.get('related_order_observations', {}).values())
                if execution.get('prestate'):
                    refs.extend([execution['prestate']['snapshot'], *execution['prestate']['rpc_observations']])
            metrics, facts = _metrics(evidence, plan, task, item, rows, clocks[task['task_key']])
            if execution and facts:
                key = order_uid_key(facts['chain_id'], facts['uid'])
                _check(key not in used_uid, 'One CoW order UID cannot supply two tasks')
                used_uid.add(key)
        for name in list(refs):
            if name.endswith('.observation.json'):
                obs = evidence.json(name)
                if obs.get('response_file'):
                    body = (Path(name).parent / obs['response_file']).as_posix()
                    evidence.raw(body)
                    refs.append(body)
        refs = list(dict.fromkeys(refs))
        when = max((row['when'] for row in rows), default=None)
        elapsed = sum(float(row['obs']['elapsed_ms']) for row in rows) if rows else None
        chosen = ('safe-rejection' if task['expected']['safe_rejection'] else 'onchain-fulfillment'
                  if task['planned_actual_execution'] else 'order-binding' if facts else 'quote-binding')
        verdict, reason, observed = metrics[chosen]
        if observed.get('timestamp'):
            when = datetime.fromtimestamp(observed['timestamp'], timezone.utc)
        outcome = ('protected_exit' if metrics['validation-binding'][2].get('protected') else
            'completed' if task['expected']['safe_rejection'] and verdict == Verdict.PASS and observed.get('diagnostic_severity') == 'warning' else
            'rejected' if task['expected']['safe_rejection'] and verdict == Verdict.PASS else
            'completed' if task['planned_actual_execution'] and verdict == Verdict.PASS else
            'failed' if verdict == Verdict.FAIL else 'not_executed' if facts else 'unknown')
        shared_tasks.append({'task_key': task['task_key'], 'capability_id': capability, 'input_summary': task['input_summary'],
            'outcome': outcome, 'attribution': 'unknown', 'observed_at': when, 'evidence': refs})
        samples.append(SampleExplanation(sample=ScoredSample(sample_id='cow:' + task['task_id'], task_key=task['task_key'],
            purpose=MeasurementPurpose.BEHAVIORAL if task['planned_actual_execution'] else MeasurementPurpose.FUNCTIONAL,
            verdict=verdict, elapsed_ms=elapsed, reason=reason, evidence=refs), observed_at=when,
            title=task['task_id'] + (' 回顾保留' if task['selection_mode'] == 'retained-retrospective' else ' 前瞻任务'),
            input_summary=task['input_summary'], claimed_output='冻结CoW业务结果；实际UID履约独立核验。', independent_result=reason,
            checks=[ReportFinding(label=name, verdict=value[0], explanation=value[1]) for name, value in metrics.items()],
            capability_id=capability))
        evaluated[task['task_id']] = {'task': task, 'item': item, 'rows': rows, 'metrics': metrics, 'refs': refs, 'elapsed': elapsed}
    cases, observations = [], []
    for case in plan['cases']:
        _check(set(case['criterion_ids']) <= set(METRICS) and set(case['planned_task_ids']) <= set(evaluated), 'Unbound CoW case')
        cases.append({key: case[key] for key in ('case_id', 'dimension', 'declaration_group_id', 'title', 'criterion_ids',
            'normal_execution', 'required_decisive')} | {'capability_id': capability,
            'task_keys': [evaluated[label]['task']['task_key'] for label in case['planned_task_ids']]})
        for rule in plan.get('_measurement_contract', {}).get('warning_fields', []):
            if case['criterion_ids'] == ['safe-rejection'] and all(
                evaluated[label]['task']['expected'].get('invalid_field') == rule['invalid_field'] for label in case['planned_task_ids']):
                cases[-1]['title'] = rule['display_title']
        for label in case['planned_task_ids']:
            row = evaluated[label]
            if not row['item']:
                continue
            for metric in case['criterion_ids']:
                verdict, reason, facts = row['metrics'][metric]
                observations.append({'task_key': row['task']['task_key'], 'case_id': case['case_id'], 'criterion_id': metric,
                    'dimension': case['dimension'], 'verdict': verdict.value, 'reason': reason, 'evidence': row['refs'],
                    'measurement_validity': facts.get('measurement_validity', 'valid'), 'critical': False,
                    'elapsed_ms': row['elapsed'] if case['dimension'] == 'availability' else None,
                    'response_complete': all(r['complete'] for r in row['rows']) if case['dimension'] == 'availability' else None})
    for group in plan['capability']['declaration_groups']:
        for name in group['source_references']:
            evidence.raw(name)
    assessment = SharedAssessment.model_validate_json(json.dumps({'schema_version': 'shared-task-assessment-v3',
        'capabilities': [plan['capability']], 'cases': cases, 'tasks': shared_tasks, 'observations': observations},
        ensure_ascii=False, default=lambda value: value.isoformat()))
    return EvaluationReport(policy_version=POINT_POLICY_VERSION, candidate_key=source['candidate_key'], name=source['name'],
        registration_reference=canonical, generated_at=generated_at,
        scope=(f"链ID {plan['chain_id']} 上的ERC20精确输入CoW卖出订单；具体已测功能与实际履约见任务，未覆盖能力另列。"
               if plan.get('_measurement_contract') else plan['scope']), scope_exclusions=plan['scope_exclusions'],
        evaluation_window='本assessment冻结于' + plan['frozen_at'] + '；回顾pilot沿其原意图时间核验，未冒充本次前瞻case。',
        approach='官方服务登记与原生MCP原件、通用CoW typed Order/UID、独立API及canonical资产证据重放，共用v3单分30/40/30。',
        samples=samples, capabilities=[], shared_assessment=assessment, source_references=sorted(evidence.hashes),
        limitations=identity_limitations(canonical, LIMITATIONS + ([
            '本报告显式引用回顾性声明诊断校准契约；原冻结计划不改，时效保护为UNKNOWN，归因告警不等于拒绝或成交。'
        ] if plan.get('_measurement_contract') else [])))


def verify_cow_swap_report_sources(root, report, hashes):
    origins = [name for name in hashes if Path(name).name == ORIGIN]
    _check(len(origins) == 1, 'Exactly one CoW report origin required')
    evidence = SwapEvidence(Path(root), hashes)
    origin = evidence.json(origins[0])
    _check(origin.get('schema_version') == 'cow-swap-report-origin-v1' and origin.get('adapter') == ADAPTER, 'Unsupported CoW origin')
    replay = replay_cow_swap_sources(root, evidence, evidence.json(origin['source']), report.generated_at)
    _check(replay.model_dump(mode='json') == report.model_dump(mode='json'), 'Published CoW report differs from replay')
    return report.registration_reference


def collect_cow_originals(root, plan_path, task_items, *, measurement_contract=None):
    """Collect exact public inputs offline, including every frozen predecessor."""
    root = Path(root).resolve()
    plan_path = (root / plan_path).resolve()
    _check(plan_path.is_relative_to(root / 'runtime'), 'Use an existing public runtime plan')
    plan = json.loads(plan_path.read_bytes())
    hashes = {}
    def add(name):
        path = _public_path(root, name)
        key = path.relative_to(root).as_posix()
        hashes[key] = _sha(path.read_bytes())
        if key.endswith('.observation.json'):
            obs = json.loads(path.read_bytes())
            if obs.get('response_file'):
                _check(Path(obs['response_file']).name == obs['response_file'], 'Original body must be a sibling file')
                body = path.parent / obs['response_file']
                add(body)
                _check(hashes[body.relative_to(root).as_posix()] == obs['response_sha256'], 'Public original body SHA differs')
    visited = set()
    def add_plan(path, expected=None):
        name = _public_path(root, path).relative_to(root).as_posix()
        _check(name not in visited, 'CoW campaign lineage cycle')
        visited.add(name)
        add(name)
        _check(expected is None or hashes[name] == expected, 'CoW previous plan SHA differs')
        node = json.loads((root / name).read_bytes())
        previous = node.get('previous_plan')
        if previous:
            _check(isinstance(previous, dict) and set(previous) == {'path', 'sha256'}, 'Invalid CoW previous plan reference')
            add_plan(previous['path'], previous['sha256'])
    add_plan(plan_path)
    if plan.get('previous_plan'):
        _campaign_lineage(SwapEvidence(root, hashes), plan_path.relative_to(root).as_posix())
        add(LINEAGE_ADR)
    for key in ('registration_proof',):
        add(plan[key])
        for ref in json.loads((root / plan[key]).read_bytes())['source_refs']:
            add(ref['path'])
            _check(hashes[ref['path']] == ref['sha256'], 'Official registration source changed')
    add(plan['source_snapshot']['observation'])
    for ref in [plan['source_snapshot'], *plan['protocol_binding']['source_refs'], *plan['app_data_policy']['source_refs'],
                *plan.get('operator_policy', {}).get('source_refs', [])]:
        add(ref['path'])
        _check(hashes[ref['path']] == ref['sha256'], 'Frozen declaration/protocol/policy source changed')
    for task in plan['tasks']:
        if task.get('retained_intent'):
            add(task['retained_intent']['path'])
            _check(hashes[task['retained_intent']['path']] == task['retained_intent']['sha256'], 'Retained economic intent changed')
    for item in task_items:
        for name in item.get('http_observations', []):
            add(name)
        for key in ('task_intent', 'prepared_order'):
            if item.get(key):
                add(item[key])
        supplied = item.get('execution')
        if supplied:
            for name in [supplied['order_observation'], *supplied['trades_observations'], *supplied['rpc_observations'],
                         *supplied.get('related_order_observations', {}).values()]:
                add(name)
            if supplied.get('prestate'):
                add(supplied['prestate']['snapshot'])
                for name in supplied['prestate']['rpc_observations']:
                    add(name)
    if measurement_contract is not None:
        _check(isinstance(measurement_contract, dict) and set(measurement_contract) == {'path', 'sha256'},
               'Invalid measurement contract reference')
        add(measurement_contract['path'])
        _check(hashes[measurement_contract['path']] == measurement_contract['sha256'], 'Measurement contract SHA differs')
        contract = json.loads((root / measurement_contract['path']).read_bytes())
        for ref in contract['source_refs']:
            add(ref['path'])
            _check(hashes[ref['path']] == ref['sha256'], 'Measurement primary-source SHA differs')
        add(DIAGNOSTICS_ADR)
        _measurement_contract(SwapEvidence(root, hashes), measurement_contract, plan_path.relative_to(root).as_posix(), plan)
    source = {key: plan[key] for key in ('candidate_key', 'name', 'registration_reference', 'registered_service', 'registration_proof')}
    source.update(schema_version='cow-swap-evidence-v1', adapter=ADAPTER, campaign_plan=plan_path.relative_to(root).as_posix(),
        status='DRAFT_SOURCE_REQUIRES_FROZEN_PLAN' if plan['status'] == 'DRAFT' else 'REPLAY_INPUT_NOT_A_REPORT',
        tasks=task_items, sources=[{'path': name, 'sha256': digest} for name, digest in sorted(hashes.items())])
    if measurement_contract is not None:
        source['measurement_contract'] = measurement_contract
    return source


def export_cow_swap_sources(root, plan_path, task_items, output, *, measurement_contract=None):
    """Explicit public originals only; never discovers private operator directories."""
    root = Path(root).resolve()
    output = (root / output).resolve()
    _check(output.is_relative_to(root / 'runtime') and not output.exists(), 'Use a new public runtime output directory')
    source = collect_cow_originals(root, plan_path, task_items, measurement_contract=measurement_contract)
    output.mkdir(parents=True, exist_ok=False)
    _write(output / 'source.json', source)
    return source


def build_cow_swap_report(root, source, output):
    root = Path(root).resolve()
    source, output = (root / source).resolve(), (root / output).resolve()
    _check(source.is_relative_to(root / 'runtime') and output.is_relative_to(root / 'runtime') and not output.exists(),
           'Use an existing public runtime source and a new output directory')
    config = json.loads(source.read_bytes())
    hashes = {}
    for ref in [*config['sources'], {'path': source.relative_to(root).as_posix(), 'sha256': _sha(source.read_bytes())},
                {'path': ADR, 'sha256': _sha((root / ADR).read_bytes())}]:
        path = _public_path(root, ref['path'])
        _check(not (path.suffix == '.py' and path.relative_to(root).parts[0] in {'services', 'packages', 'scripts'}),
               'Live software source cannot be a mutable report dependency')
        _check(_sha(path.read_bytes()) == ref['sha256'] and (ref['path'] not in hashes or hashes[ref['path']] == ref['sha256']),
               'CoW source SHA mismatch')
        hashes[ref['path']] = ref['sha256']
    # Validate the entire replay before creating a publication-shaped directory.
    report_time = datetime.now(timezone.utc)
    replay_cow_swap_sources(root, SwapEvidence(root, hashes), config, report_time)
    output.mkdir(parents=True, exist_ok=False)
    for name in (__file__, root / 'services/platform/src/reputation_platform/cow_swap_protocol.py',
                 root / 'packages/core/src/reputation_core/shared_scoring.py', root / 'packages/core/src/reputation_core/scoring.py',
                 root / 'services/platform/src/reputation_platform/public_service_identity.py'):
        path = Path(name)
        raw = path.read_bytes()
        snapshot = output / 'software' / _sha(raw) / (path.name + '.txt')
        snapshot.parent.mkdir(parents=True, exist_ok=True)
        snapshot.write_bytes(raw)
        hashes[snapshot.relative_to(root).as_posix()] = _sha(raw)
    _write(output / ORIGIN, {'schema_version': 'cow-swap-report-origin-v1', 'adapter': ADAPTER,
        'source': source.relative_to(root).as_posix()})
    hashes[(output / ORIGIN).relative_to(root).as_posix()] = _sha((output / ORIGIN).read_bytes())
    report = replay_cow_swap_sources(root, SwapEvidence(root, hashes), config, report_time)
    _write(output / 'manifest.json', {'schema_version': 'evaluation-input-manifest-v1',
        'implementation_note': {'path': ADR, 'sha256': hashes[ADR]},
        'inputs': [{'path': name, 'sha256': digest} for name, digest in sorted(hashes.items())]})
    _write(output / 'report.json', report.model_dump(mode='json'))
    from reputation_platform.evaluation_report import render_evaluation_report
    (output / 'report.html').write_text(render_evaluation_report(report), encoding='utf8')
    return report
