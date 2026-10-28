"""Source-replayed shared assessments; no network, wallet or supplied scores."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from reputation_core import MeasurementPurpose, Verdict
from reputation_core.reporting import EvaluationReport, parse_evaluation_report
from reputation_core.scoring import SHARED_POLICY_VERSION, MULTICAP_POLICY_VERSION, POINT_POLICY_VERSION
from reputation_core.shared_scoring import SharedAssessment
from reputation_core.swap import address, verify_swap_execution, verify_swap_function
from reputation_platform.swap_report import (
    CAPABILITY, ORIGIN as SWAP_ORIGIN, PROTOCOLS, SwapEvidence, _check, _decimals,
    _execution, _metadata_tag, _simulation, _task_request, verify_swap_report_sources,
)

ORIGIN = 'shared-report-origin.json'
SCHEMA = 'shared-report-origin-v1'
ADAPTER = 'retained-evm-swap-v1'
ADR = 'docs/adr/0026-scoped-shared-assessment.md'
GROUPS = ('intent-binding', 'execution-effect', 'asset-display')
CRITERION_TITLES = {'complete-response': '完整业务响应', 'intent-binding': '任务参数与授权',
                    'execution-effect': '独立执行效果', 'asset-display': '资产标识一致性',
                    'onchain-fulfillment': '真实链上履约'}
APPROACH = '复用已核原件的回顾性共享任务评价；一任务分别支持响应、声明及链上结果。新功能补测另列，不冒充新采样。'
SHARED_LIMITATIONS = [
    '本结果只对应选定声明组和已测范围；目录中的未测功能不补零、不补满分。',
    '旧传输中断的有效发出与环境尚未证实，A保留UNKNOWN；没有将客户端计数直接当作提供方故障率。',
    '旧B按当时64块确认要求取证；这不等于已取得finalized状态，新最终性补证不伪装成已有结果。']


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _json(path):
    return json.loads(path.read_bytes())


def _write(path, value):
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write('\n')


def _base(root, evidence, origin):
    manifest = evidence.json(origin['source_manifest'])
    _check(manifest['schema_version'] == 'evaluation-input-manifest-v1', 'Unsupported parent manifest')
    parent_hashes = {row['path']: row['sha256'] for row in manifest['inputs']}
    _check(len(parent_hashes) == len(manifest['inputs']), 'Duplicate parent evidence path')
    _check(all(evidence.hashes.get(path) == digest for path, digest in parent_hashes.items()),
           'Shared evidence changed a retained parent source')
    base = parse_evaluation_report(evidence.raw(origin['source_report']))
    verify_swap_report_sources(root, base, parent_hashes)
    return base, parent_hashes


def _assessment(root, evidence, origin):
    """Reuse one verified protocol adapter for any matching registered identity."""
    base, parent_hashes = _base(root, evidence, origin)
    catalog = evidence.json(origin['declarations'])
    _check(catalog['schema_version'] == 'shared-declaration-catalog-v1'
           and catalog['checker_id'] == ADAPTER, 'Unsupported declaration catalog')
    _check(catalog['candidate_key'] == base.candidate_key
           and catalog['registration_reference'] == base.registration_reference,
           'Declaration catalog belongs to a different identity')
    _check(catalog['response_deadline_ms'] > 0, 'A response deadline is required')
    for path in catalog['source_documents']:
        evidence.raw(path)
    capabilities = catalog['capabilities']
    selected = [item for item in capabilities if item['selected']]
    _check(len(selected) == 1 and selected[0]['capability_id'] == CAPABILITY,
           'This source adapter supports only its declared ERC20 swap capability')
    groups = {item['group_id'] for item in selected[0]['declaration_groups'] if item['selected']}
    _check(groups == set(GROUPS), 'The reviewed swap scope requires its three independent declaration groups')
    for capability in capabilities:
        for group in capability['declaration_groups']:
            for path in group['source_references']:
                evidence.raw(path)

    parent = SwapEvidence(root, parent_hashes)
    origins = [name for name in parent_hashes if Path(name).name == SWAP_ORIGIN]
    _check(len(origins) == 1, 'No unique parent protocol origin')
    source = parent.json(origins[0])
    campaign = parent.json(source['campaign'])
    protocol = parent.json(PROTOCOLS)['chains'][str(campaign['execution_chain_id'])]
    entries = {item['slot']: item for item in source['tasks']}
    samples = {item.sample.task_key: item for item in base.samples}
    tasks, observations = [], []
    case_keys = {}
    cases = {}

    def observe(task, direction, dimension, criterion, verdict, reason, sources, *, validity='valid',
                elapsed=None, critical=False, response_complete=None):
        case_id = f'{dimension}:{criterion}:{direction}'
        case_keys.setdefault(case_id, []).append(task)
        cases.setdefault(case_id, {'case_id': case_id, 'capability_id': CAPABILITY,
            'dimension': dimension, 'declaration_group_id': criterion if dimension == 'functional' else None,
            'title': f'{direction} · {CRITERION_TITLES[criterion]}', 'criterion_ids': [criterion],
            'normal_execution': dimension == 'behavioral', 'required_decisive': 1})
        observations.append({'task_key': task, 'case_id': case_id, 'criterion_id': criterion,
            'dimension': dimension, 'verdict': verdict.value, 'reason': reason,
            'evidence': list(dict.fromkeys(sources)), 'measurement_validity': validity,
            'elapsed_ms': elapsed, 'critical': critical, 'response_complete': response_complete})

    for slot in campaign['slots']:
        item = entries[slot['slot']]
        data = parent.json(item['input_file'])
        task_key = slot['task_key']
        explanation = samples[task_key]
        request = _task_request({'input': data}, protocol)
        token_in = protocol['tokens'][address(data['token_in'])]
        token_out = protocol['tokens'][address(data['token_out'])]
        direction = token_in['symbol'] + ' → ' + token_out['symbol']
        sources = [item['frozen_task'], item['input_file'], item['request_file']]
        builder, elapsed, http = None, None, None
        if item.get('response_file'):
            raw = parent.raw(item['response_file'])
            http = parent.json(item['observation_file'])
            sources.extend([item['response_file'], item['observation_file']])
            elapsed = float(http['elapsed_ms'])
            try:
                builder = json.loads(raw)
            except ValueError:
                builder = None
        complete = (http is not None and http['status'] == 200 and isinstance(builder, dict)
                    and builder.get('status') == 'ready'
                    and all(key in builder for key in ('quote', 'transactions', 'execution')))
        if complete:
            verdict = Verdict.PASS if elapsed <= catalog['response_deadline_ms'] else Verdict.FAIL
            reason = f'完整协议响应耗时{elapsed:.2f}ms；本范围时限{catalog["response_deadline_ms"]}ms。'
            observe(task_key, direction, 'availability', 'complete-response', verdict, reason, sources,
                    elapsed=elapsed, response_complete=True)
        elif http is not None:
            observe(task_key, direction, 'availability', 'complete-response', Verdict.FAIL,
                    '已收到完整业务响应，但未交付接口约定的可解析方案。', sources,
                    elapsed=elapsed, response_complete=True)
        else:
            failure_name = item.get('transport_failure') or item.get('preflight_failure')
            if failure_name:
                failure = parent.json(failure_name)
                sources.append(failure_name)
                elapsed = failure.get('elapsed_ms')
            observe(task_key, direction, 'availability', 'complete-response', Verdict.UNKNOWN,
                    '旧原件未取得完整业务响应；不能仅凭客户端开始计时证明有效送达与测量环境，保留未决。',
                    sources, validity='unknown', elapsed=elapsed, response_complete=False)

        result = None
        if complete:
            initial = verify_swap_function(request, builder, None)
            binding = Verdict.PASS if initial.facts else initial.verdict
            observe(task_key, direction, 'functional', 'intent-binding', binding,
                '实际calldata的链、资产、整数金额、收款人、最低到账与精确授权符合冻结请求。' if initial.facts
                else initial.reason, sources, critical=binding == Verdict.FAIL and any(
                    word in initial.reason for word in ('收款人', '额外交易', '原生币转出', '授权不是')))
            labels = []
            missing_label = False
            for key, asset in (('tokenIn', token_in), ('tokenOut', token_out)):
                displayed = builder.get('quote', {}).get(key, {}).get('symbol')
                if not displayed:
                    missing_label = True
                elif displayed != asset['symbol']:
                    labels.append(f'{key}显示{displayed}，实际地址对应{asset["symbol"]}')
            label_verdict = Verdict.FAIL if labels else Verdict.UNKNOWN if missing_label else Verdict.PASS
            observe(task_key, direction, 'functional', 'asset-display', label_verdict,
                    '；'.join(labels) if labels else '缺少可核对的资产显示标识。' if missing_label
                    else '输入、输出资产标识与可信代币地址配置一致。', sources)
            proof_sources = list(sources)
            if slot['purpose'] in ('functional', 'behavioral'):
                records = parent.rpc_records(item['rpc_observations'], set(protocol['rpc_urls']))
                proof_sources.extend(item['rpc_sources'])
                send = parent.json(item['send_intent']) if item.get('send_intent') else None
                if item.get('send_intent'):
                    proof_sources.append(item['send_intent'])
                tag = _metadata_tag(records, request, slot['purpose'], send)
                gap = _decimals(records, request, tag) if tag else '缺固定区块代币核验。'
                if gap:
                    result = (Verdict.UNKNOWN, gap)
                elif slot['purpose'] == 'functional':
                    verified = verify_swap_function(request, builder, _simulation(records, request, builder))
                    result = (verified.verdict, verified.reason)
                else:
                    verified = verify_swap_execution(request, builder, _execution(records, request, builder, send))
                    result = (verified.verdict, verified.reason)
            result = result or (Verdict.UNKNOWN, '本任务只有返回方案，原件没有独立固定块模拟或真实执行，不能推定可执行效果。')
            observe(task_key, direction, 'functional', 'execution-effect', result[0], result[1], proof_sources)
        else:
            for group in GROUPS:
                observe(task_key, direction, 'functional', group, Verdict.UNKNOWN,
                        '未取得完整方案，无法判断这项功能；未交付事实已同时保留在A。', sources)
        if slot['purpose'] == 'behavioral':
            result = result or (Verdict.UNKNOWN, '预定真实执行未取得可判证据，不能用方案或HTTP成功替代。')
            observe(task_key, direction, 'behavioral', 'onchain-fulfillment', result[0], result[1],
                    proof_sources if complete else sources, critical=result[0] == Verdict.FAIL)
        outcome = 'completed' if slot['purpose'] == 'behavioral' and result and result[0] == Verdict.PASS else (
            'failed' if slot['purpose'] == 'behavioral' and result and result[0] == Verdict.FAIL else
            'unknown' if slot['purpose'] == 'behavioral' else 'not_executed')
        tasks.append({'task_key': task_key, 'capability_id': CAPABILITY,
            'input_summary': explanation.input_summary, 'outcome': outcome, 'attribution': 'unknown',
            'observed_at': explanation.observed_at.isoformat() if explanation.observed_at else None,
            'evidence': list(dict.fromkeys(explanation.sample.evidence + sources))})
    for key, case in cases.items():
        case['task_keys'] = case_keys[key]
    assessment = SharedAssessment.model_validate_json(json.dumps({'schema_version': 'shared-task-assessment-v1',
        'capabilities': capabilities, 'cases': list(cases.values()), 'tasks': tasks, 'observations': observations}, ensure_ascii=False))
    return base, catalog, assessment


MULTICAP_ADAPTER = 'retained-evm-multicapability-v2'
POINT_ADAPTER = 'retained-evm-point-assessment-v3'


def _lifecycle_assessment(root, evidence, origin):
    from reputation_platform.lifecycle_assessment import replay_lifecycle_assessment
    return replay_lifecycle_assessment(root, evidence, origin)


SOURCE_ADAPTERS = {ADAPTER: _assessment, MULTICAP_ADAPTER: _lifecycle_assessment, POINT_ADAPTER: _lifecycle_assessment}


def _replay(root, evidence, origin):
    _check(origin['schema_version'] == SCHEMA and origin['adapter'] == ADAPTER
           and origin['analysis_mode'] == 'retrospective-source-reuse',
           'Shared report requires a registered source adapter')
    return SOURCE_ADAPTERS[origin['adapter']](root, evidence, origin)


def verify_shared_report_sources(root, report, hashes):
    if any(Path(name).name == 'unsigned-swap-report-origin.json' for name in hashes):
        from reputation_platform.unsigned_swap_report import verify_unsigned_swap_report_sources
        return verify_unsigned_swap_report_sources(root, report, hashes)
    if report.policy_version in (MULTICAP_POLICY_VERSION, POINT_POLICY_VERSION):
        from reputation_platform.expanded_shared_report import verify_expanded_report_sources
        return verify_expanded_report_sources(root, report, hashes)
    origins = [path for path in hashes if Path(path).name == ORIGIN]
    _check(len(origins) == 1, 'Shared report requires one retained origin')
    evidence = SwapEvidence(root, hashes)
    evidence.raw(ADR)
    base, catalog, assessment = _replay(root, evidence, evidence.json(origins[0]))
    _check(report.policy_version == SHARED_POLICY_VERSION
           and report.registration_reference == base.registration_reference
           and report.candidate_key == base.candidate_key and report.name == base.name,
           'Shared report identity differs from source replay')
    _check(report.shared_assessment is not None
           and report.shared_assessment.model_dump(mode='json') == assessment.model_dump(mode='json'),
           'Shared judgments or computed results differ from original evidence')
    _check(report.scope == catalog['scope'] and report.scope_exclusions == catalog['scope_exclusions']
           and report.evaluation_window == base.evaluation_window and report.approach == APPROACH,
           'Shared report changed its selected scope or observation window')
    _check(report.samples == base.samples and report.capabilities == base.capabilities,
           'Parent sample explanations must remain source-derived')
    _check(all(value in report.limitations for value in base.limitations + SHARED_LIMITATIONS),
           'Shared report omitted identity or shared-method limitations')
    _check(set(report.source_references) == set(hashes), 'Shared report omitted or invented source references')
    return base.registration_reference


def build_shared_report(root: Path, source_directory: Path, declarations: Path, directory: Path) -> EvaluationReport:
    """Append a retrospectively assessed report; never mutate its source report."""
    root = root.resolve()
    source_directory = (root / source_directory).resolve()
    declarations = (root / declarations).resolve()
    directory = (root / directory).resolve()
    _check(source_directory.is_relative_to(root / 'runtime') and directory.is_relative_to(root / 'runtime')
           and declarations.is_relative_to(root / 'configs'), 'Expected retained sources and reviewed configuration')
    _check(not directory.exists(), 'A shared report destination must be new')
    manifest = _json(source_directory / 'manifest.json')
    hashes = {row['path']: row['sha256'] for row in manifest['inputs']}

    def add(path):
        path = path.resolve()
        _check(path.is_relative_to(root) and path.is_file()
               and not any('.private' in part.lower() or part == '.env' for part in path.parts),
               'Only reviewed public inputs can enter a shared report')
        name = path.relative_to(root).as_posix()
        digest = _sha(path.read_bytes())
        _check(name not in hashes or hashes[name] == digest, 'A retained input was modified')
        hashes[name] = digest
        return name

    catalog = _json(declarations)
    if catalog.get('checker_id') in (MULTICAP_ADAPTER, POINT_ADAPTER):
        from reputation_platform.expanded_shared_report import build_expanded_report
        return build_expanded_report(root, source_directory, declarations, directory)
    origin = {'schema_version': SCHEMA, 'adapter': catalog['checker_id'],
        'analysis_mode': 'retrospective-source-reuse',
        'source_report': add(source_directory / 'report.json'),
        'source_manifest': add(source_directory / 'manifest.json'), 'declarations': add(declarations)}
    for path in catalog['source_documents']:
        add(root / path)
    add(root / ADR)
    directory.mkdir(parents=True, exist_ok=False)
    origin_path = directory / ORIGIN
    _write(origin_path, origin)
    add(origin_path)
    evidence = SwapEvidence(root, hashes)
    base, catalog, assessment = _replay(root, evidence, origin)
    report = EvaluationReport(policy_version=SHARED_POLICY_VERSION, candidate_key=base.candidate_key,
        name=base.name, registration_reference=base.registration_reference, generated_at=datetime.now(timezone.utc),
        scope=catalog['scope'], scope_exclusions=catalog['scope_exclusions'], evaluation_window=base.evaluation_window,
        approach=APPROACH,
        samples=base.samples, capabilities=base.capabilities, shared_assessment=assessment,
        source_references=sorted(hashes), limitations=base.limitations + SHARED_LIMITATIONS)
    verify_shared_report_sources(root, report, hashes)
    _write(directory / 'manifest.json', {'schema_version': 'evaluation-input-manifest-v1',
        'implementation_note': {'path': ADR, 'sha256': hashes[ADR]},
        'inputs': [{'path': path, 'sha256': digest} for path, digest in sorted(hashes.items())]})
    _write(directory / 'report.json', report.model_dump(mode='json'))
    from reputation_platform.evaluation_report import render_evaluation_report
    with (directory / 'report.html').open('x', encoding='utf-8') as stream:
        stream.write(render_evaluation_report(report))
    return report
