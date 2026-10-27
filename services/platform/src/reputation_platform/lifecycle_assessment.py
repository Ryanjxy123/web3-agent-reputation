"""Append source-replayed lifecycle tasks to a retained shared assessment."""
from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path

from reputation_core.admission import MeasurementPurpose, Verdict
from reputation_core.reporting import (CapabilityCoverage, ReportFinding, SampleExplanation,
                                       parse_evaluation_report)
from reputation_core.scoring import MULTICAP_POLICY_VERSION, POINT_POLICY_VERSION, ScoredSample
from reputation_core.shared_scoring import SharedAssessment, SharedDeclarationGroup
from reputation_core.swap import integer
from reputation_platform.swap_report import SwapEvidence

ADAPTER = 'retained-evm-multicapability-v2'
POINT_ADAPTER = 'retained-evm-point-assessment-v3'
ASSESSMENT_SCHEMA = 'shared-task-assessment-v2'
GROUPS = {'native_swap': ('native-v4',),
          'scheduled_cancel': ('create-query', 'cancel-refund', 'asset-permission-fees'),
          'limit_cancel': ('create-query', 'cancel-refund', 'asset-permission-fees')}
A_REASON = '本任务未采集Agent业务HTTP响应；RPC、钱包签名与链确认耗时不能代替A，保留尚未观测。'
TITLES = {'native_swap': '原生资产兑换', 'scheduled_cancel': '定时订单管理', 'limit_cancel': '限价订单管理'}
GROUP_TITLES = {'native-v4': '原生输入与V4执行', 'create-query': '创建与合约查询',
                'cancel-refund': '撤销与完整退款', 'asset-permission-fees': '资产、权限与费用'}


def _check(value, reason):
    if not value:
        raise ValueError(reason)


def _bound_graph(evidence, manifest):
    rows = manifest['inputs']
    hashes = {row['path']: row['sha256'] for row in rows}
    _check(len(hashes) == len(rows), '来源manifest存在重复依赖')
    for name, digest in hashes.items():
        _check(evidence.hashes.get(name) == digest, '扩展报告未绑定原来源图：' + name)
        evidence.raw(name)
    return hashes


def _units(value, decimals):
    whole, tail = divmod(integer(value), 10 ** integer(decimals))
    fraction = f'{tail:0{integer(decimals)}d}'.rstrip('0')
    return str(whole) + ('.' + fraction if fraction else '')


def _criterion_facts(fact, kind, protocol):
    """These values come from the raw replayer, never from supplied summary flags."""
    verified = fact.get('verified') is True
    if not verified:
        return {}, {}, fact.get('reason', '原始链上证据尚未核齐')
    amount = integer(fact['amount_in_raw'])
    native, token = protocol['assets']['native'], protocol['assets']['token']
    fees = sum(integer(fact[key]) for key in ('l2_fee_wei', 'l1_fee_wei', 'operator_fee_wei'))
    conserved = fees == integer(fact['network_fee_wei']) and fees >= 0
    network_text = _units(fees, native['decimals']) + native['symbol']
    if kind == 'native_swap':
        functional = {'native-v4': [
            ('native-input', True,
             f"原生本金{_units(amount, native['decimals'])}{native['symbol']}（{amount}wei）与实际value、资产、调用者和V4状态由原件绑定。"),
            ('minimum-output', integer(fact['output_raw']) >= integer(fact['minimum_raw']),
             f"真实到账{_units(fact['output_raw'], token['decimals'])}{token['symbol']}，最低{_units(fact['minimum_raw'], token['decimals'])}{token['symbol']}。"),
            ('native-fee-conservation', conserved and integer(fact['platform_fee_raw']) >= 0,
             f"平台费{_units(fact['platform_fee_raw'], native['decimals'])}{native['symbol']}已含本金；网络费{network_text}及前后资产变化已独立对平。")]}
        goal = fact['outcome'] == 'Executed'
        goal_text = '本任务目标是即时兑换，真实订单终态Executed、到账及最低接收量对应原意图。'
    else:
        refunded = integer(fact['escrowed_raw']) == integer(fact['refunded_raw']) == amount
        cancelled = fact['outcome'] == 'Cancelled'
        zero_allowance = integer(fact['remaining_allowance_raw']) == 0
        functional = {
            'create-query': [
                ('order-binding', True, f"订单{fact['order_id']}的本人归属、资产、数量与时间/价格参数经原调用和持久状态核对。"),
                ('stored-management-state', cancelled, '读取最终Cancelled状态；没有把模拟中间返回冒称链上中间态。')],
            'cancel-refund': [('exact-principal-refund', refunded,
                f"本金{_units(fact['escrowed_raw'], token['decimals'])}{token['symbol']}已托管并完整退回{_units(fact['refunded_raw'], token['decimals'])}{token['symbol']}（{fact['refunded_raw']}个最小单位），实际两向转账和余额一致。")],
            'asset-permission-fees': [
                ('ending-allowance', zero_allowance, '精确授权已消耗并归零，钱包及合约本金净变化0。'),
                ('management-fee-conservation', conserved and integer(fact['platform_fee_raw']) == 0,
                 f'创建撤销没有执行兑换或收取平台费，原生币只支出实际网络费{network_text}。')]}
        goal = cancelled and refunded and zero_allowance
        goal_text = '本任务目标是创建、查询并撤销订单且完整退款；Cancelled为管理目标完成，不是兑换成交。'
    behavioral = [
        ('accepted-goal', goal, goal_text),
        ('asset-permission-boundary', True, '同链同交易、调用者、目标、原参数、转账、授权和终态均通过原件重放。'),
        ('actual-network-fees', conserved, f"实际网络费{network_text}（{fact['network_fee_wei']}wei），组成与钱包原生资产差额一致。")]
    _check(all(item[1] for rows in functional.values() for item in rows)
           and all(item[1] for item in behavioral), '重放事实与正式判据不一致')
    return functional, behavioral, ''


def _assemble(parent, catalog, config, facts, actions, supplement_sources, protocol):
    old = parent.shared_assessment
    _check(old is not None, '父报告没有可复用的共享任务评价')
    data = old.model_dump(mode='json', exclude={'result'})
    capabilities = deepcopy(catalog['capabilities'])
    by_cap = {item['capability_id']: item for item in capabilities}
    _check(len(by_cap) == len(capabilities), '声明能力ID重复')
    for previous in old.capabilities:
        if previous.selected:
            current = by_cap.get(previous.capability_id)
            _check(current and current['selected'], '新范围不能删除旧已选能力')
            selected_groups = {group['group_id'] for group in current['declaration_groups'] if group['selected']}
            _check(all(not group.selected or group.group_id in selected_groups for group in previous.declaration_groups),
                   '新范围不能删除旧已选声明组及其失败/未知')
            current_groups = {item['group_id']: SharedDeclarationGroup.model_validate_json(json.dumps(item))
                              for item in current['declaration_groups']}
            _check(all(not group.selected or current_groups[group.group_id] == group for group in previous.declaration_groups),
                   '旧已选声明组的语义或来源被改写')
    tasks, cases, observations = deepcopy(data['tasks']), deepcopy(data['cases']), deepcopy(data['observations'])
    old_keys = {item['task_key'] for item in tasks}
    fact_map = {item['task_key']: item for item in facts['tasks']}
    _check(len(fact_map) == facts['task_count'] == len(config['tasks']), '来源重放遗漏或重复任务')
    _check(set(fact_map) == {item['task_key'] for item in config['tasks']}, '来源任务清单不符')
    action_map = {item.transaction_hash.lower(): item for item in actions}
    mapping = catalog['lifecycle_supplement']['capability_map']
    new_samples, new_cases = [], {}

    def case(capability, kind, dimension, group, criteria, task_key):
        ident = f'lifecycle:{capability}:{kind}:{dimension}:{group or "delivery"}'
        item = new_cases.setdefault(ident, {'case_id': ident, 'capability_id': capability,
            'dimension': dimension, 'declaration_group_id': group,
            'title': TITLES[kind] + ' · ' + ('业务响应待观测' if dimension == 'availability'
                else GROUP_TITLES[group] if group else '真实任务履约'),
            'criterion_ids': criteria, 'task_keys': [], 'normal_execution': dimension == 'behavioral', 'required_decisive': 1})
        _check(item['criterion_ids'] == criteria and task_key not in item['task_keys'], '场景判据漂移或任务重复')
        item['task_keys'].append(task_key)
        return ident

    def observe(capability, kind, dimension, group, rows, key, sources, verified, reason):
        ident = case(capability, kind, dimension, group, [row[0] for row in rows], key)
        for criterion, _, explanation in rows:
            observations.append({'task_key': key, 'case_id': ident, 'criterion_id': criterion,
                'dimension': dimension, 'verdict': 'PASS' if verified else 'UNKNOWN',
                'reason': explanation if verified else reason, 'evidence': sources,
                'measurement_validity': 'valid' if verified else 'unknown', 'elapsed_ms': None,
                'response_complete': None, 'critical': False})

    for entry in config['tasks']:
        key, kind = entry['task_key'], entry['kind']
        _check(key not in old_keys and kind in GROUPS and kind in mapping, '补测任务重复旧任务或能力尚未注册')
        old_keys.add(key)
        capability = mapping[kind]
        selected = by_cap.get(capability)
        _check(selected and selected['selected'] and selected['write_operation'], '补测能力未明确纳入范围')
        groups = {item['group_id'] for item in selected['declaration_groups'] if item['selected']}
        _check(set(GROUPS[kind]).issubset(groups), '补测声明组缺失或未选')
        fact = fact_map[key]
        verified = fact.get('verified') is True
        action = action_map.get(entry['transaction_hash'].lower())
        _check(not verified or action is not None and action.verdict == Verdict.PASS
               and fact['transaction_hash'].lower() == action.transaction_hash.lower(), '事实与真实动作索引不符')
        sources = list(dict.fromkeys([*supplement_sources, *(action.evidence if action else fact.get('evidence', []))]))
        observed_at = datetime.fromtimestamp(fact['timestamp'], timezone.utc) if verified else None
        if verified:
            native, token, wrapped = (protocol['assets'][item] for item in ('native', 'token', 'wrapped_native'))
            asset = native if kind == 'native_swap' else token
            amount_text = _units(fact['amount_in_raw'], asset['decimals']) + asset['symbol']
            input_text = (f"{amount_text}换{token['symbol']}，最低{_units(fact['minimum_raw'], token['decimals'])}{token['symbol']}。"
                if kind == 'native_swap' else f"使用{amount_text}创建目标为{wrapped['symbol']}的{TITLES[kind]}任务，随后查询、撤销并全额退款，不触发成交。")
        else:
            input_text = f"{TITLES[kind]}；{fact.get('reason','原始证据待核')}"
        tasks.append({'task_key': key, 'capability_id': capability, 'input_summary': input_text,
            'outcome': 'completed' if verified else 'unknown', 'attribution': 'operator' if verified else 'unknown',
            'observed_at': observed_at.isoformat() if observed_at else None, 'evidence': sources})
        # There was no Agent HTTP observation: retain a planned case, never invent an UNKNOWN request.
        case(capability, kind, 'availability', None, ['lifecycle-business-delivery'], key)
        functional, behavioral, reason = _criterion_facts(fact, kind, protocol)
        if not verified:
            template = {'native-v4': ['native-input', 'minimum-output', 'native-fee-conservation']} if kind == 'native_swap' else {
                'create-query': ['order-binding', 'stored-management-state'], 'cancel-refund': ['exact-principal-refund'],
                'asset-permission-fees': ['ending-allowance', 'management-fee-conservation']}
            functional = {group: [(criterion, False, reason) for criterion in criteria] for group, criteria in template.items()}
            behavioral = [(criterion, False, reason) for criterion in ('accepted-goal', 'asset-permission-boundary', 'actual-network-fees')]
        for group, rows in functional.items():
            observe(capability, kind, 'functional', group, rows, key, sources, verified, reason)
        observe(capability, kind, 'behavioral', None, behavioral, key, sources, verified, reason)
        sample_checks = [ReportFinding(label='A · 业务服务可用性', verdict=Verdict.UNKNOWN, explanation=A_REASON),
            ReportFinding(label='F · 本次声明与参数', verdict=Verdict.PASS if verified else Verdict.UNKNOWN,
                explanation='原意图、链上调用、真实资产/订单状态和费用由来源重放核对。' if verified else reason),
            ReportFinding(label='B · 本次任务履约', verdict=Verdict.PASS if verified else Verdict.UNKNOWN,
                explanation=action.summary if verified else reason)]
        new_samples.append(SampleExplanation(sample=ScoredSample(sample_id='lifecycle:' + key, task_key=key,
            purpose=MeasurementPurpose.BEHAVIORAL, verdict=Verdict.PASS if verified else Verdict.UNKNOWN,
            elapsed_ms=None, reason=sample_checks[-1].explanation, evidence=sources), observed_at=observed_at,
            title=action.title if verified else selected['title'] + '（来源待核）', input_summary=input_text,
            claimed_output='完成即时兑换并满足最低到账。' if kind == 'native_swap' else '创建、查询并撤销订单，本金完整退回，不要求触发成交。',
            independent_result=action.summary if verified else reason, checks=sample_checks, capability_id=capability))
    schema = 'shared-task-assessment-v3' if catalog['policy_version'] == POINT_POLICY_VERSION else ASSESSMENT_SCHEMA
    assessment = SharedAssessment.model_validate_json(json.dumps({'schema_version': schema,
        'capabilities': capabilities, 'cases': [*cases, *new_cases.values()], 'tasks': tasks,
        'observations': observations}, ensure_ascii=False))
    coverage = []
    previous_coverage = {item.capability_id: item for item in parent.capabilities}
    for capability in capabilities:
        ident = capability['capability_id']
        additions = [sample for sample in new_samples if sample.capability_id == ident]
        previous = previous_coverage.get(ident)
        if not additions:
            if previous is not None:
                coverage.append(previous)
            continue
        selected_groups = [group['title'] for group in capability['declaration_groups'] if group['selected']]
        missing = [group.get('selection_reason') or group['title'] for group in capability['declaration_groups'] if not group['selected']]
        coverage.append(CapabilityCoverage(capability_id=ident, operation=capability['title'],
            description=capability.get('description', ''), protocol='evm.contract-lifecycle',
            tested_scope='；'.join(selected_groups),
            sample_ids=[*(previous.sample_ids if previous else []), *(sample.sample.sample_id for sample in additions)],
            findings=[*(previous.findings if previous else []), *(check for sample in additions for check in sample.checks)],
            missing_evidence=[A_REASON, *missing], capability_type='asset-operation', checker_id=catalog['checker_id'],
            checker_version='v' + catalog['policy_version'].rsplit('-v', 1)[1]))
    projected = parent.model_copy(update={'samples': [*parent.samples, *new_samples], 'capabilities': coverage})
    return projected, assessment


def replay_lifecycle_assessment(root: Path, evidence: SwapEvidence, origin: dict):
    """Static source-adapter shape: return projected parent, reviewed catalog, assessment."""
    from reputation_platform.contract_lifecycle_evidence import replay_contract_lifecycle
    from reputation_platform.contract_lifecycle_snapshot import verify_snapshot
    from reputation_platform.shared_report import verify_shared_report_sources

    parent_manifest = evidence.json(origin['source_manifest'])
    _check(parent_manifest['schema_version'] == 'evaluation-input-manifest-v1', '父报告来源格式不符')
    parent_hashes = _bound_graph(evidence, parent_manifest)
    parent = parse_evaluation_report(evidence.raw(origin['source_report']))
    verify_shared_report_sources(root, parent, parent_hashes)
    catalog = evidence.json(origin['declarations'])
    versions = {ADAPTER: MULTICAP_POLICY_VERSION, POINT_ADAPTER: POINT_POLICY_VERSION}
    _check(catalog['schema_version'] == 'shared-declaration-catalog-v1' and catalog['checker_id'] in versions
           and catalog['policy_version'] == versions[catalog['checker_id']],
           '尚未注册此正式补测评价目录')
    _check(catalog['candidate_key'] == parent.candidate_key
           and catalog['registration_reference'] == parent.registration_reference, '新目录与原登记身份不同')
    for name in catalog['source_documents']:
        evidence.raw(name)
    for capability in catalog['capabilities']:
        for group in capability['declaration_groups']:
            for name in group['source_references']:
                evidence.raw(name)
    supplement = catalog['lifecycle_supplement']
    snapshot_manifest = evidence.json(supplement['snapshot_manifest'])
    snapshot_hashes = _bound_graph(evidence, snapshot_manifest)
    _check(snapshot_manifest['configuration'] == supplement['snapshot_config'], '补测配置与冻结快照不符')
    snapshot_name = snapshot_manifest['snapshot']['path']
    _check(evidence.hashes.get(snapshot_name) == snapshot_manifest['snapshot']['sha256'], '快照正文未按原字节绑定')
    evidence.raw(snapshot_name)
    snapshot, verified_hashes, config = verify_snapshot(root, Path(supplement['snapshot_manifest']).parent)
    _check(verified_hashes == snapshot_hashes, '快照重放的来源图不符')
    facts, _, actions = replay_contract_lifecycle(root, config, snapshot_hashes)
    _check(snapshot.candidate_key == parent.candidate_key and snapshot.registration_reference == parent.registration_reference,
           '补测快照不属于父报告登记身份')
    _check(facts['candidate_key'] == parent.candidate_key and facts['registration_reference'] == parent.registration_reference
           and facts['name'] == parent.name, '原件重放身份与父报告不符')
    projected, assessment = _assemble(parent, catalog, config, facts, actions,
        [supplement['snapshot_manifest'], snapshot_name, supplement['snapshot_config']],
        evidence.json(config['protocol_config']))
    return projected, catalog, assessment
