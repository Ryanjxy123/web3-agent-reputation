"""Source-bound capability coverage and explicit errata for new prediction reports."""

import hashlib
import json

from reputation_core import MeasurementPurpose, Verdict
from reputation_core.application import normalize_reference
from reputation_core.reporting import CapabilityCoverage, EvaluationReport, ReportFinding
from reputation_platform.mech_task_evidence import _catalog, _prepare
from reputation_platform.mech_task_identity import verify_mech_identity
from reputation_platform.model_analysis import prediction_tool_descriptors
from reputation_core.planning import prediction_tool_supported


def _correction(report: EvaluationReport, reader, origin: dict) -> None:
    correction = origin.get('correction_of')
    if correction is None:
        return
    if origin.get('verification_revision') != 2:
        raise ValueError('A verification erratum requires explicit revision 2')
    report_ref, origin_ref = correction['report'], correction['origin']
    report_path = reader.remember(report_ref['path'], report_ref['sha256'])
    origin_path = reader.remember(origin_ref['path'], origin_ref['sha256'])
    old_origin = json.loads(origin_path.read_bytes())
    manifest_name = (report_path.parent / 'manifest.json').relative_to(reader.root).as_posix()
    manifest = reader.json(manifest_name)
    report_bindings = [item for item in manifest['outputs'] if item['path'] == report_ref['path']]
    origin_bindings = [item for item in manifest['inputs'] if item['path'] == origin_ref['path']]
    if report_bindings != [report_ref] or origin_bindings != [origin_ref]:
        raise ValueError('The previous report and origin are not uniquely bound to its retained manifest')
    payload = json.loads(report_path.read_bytes())
    original_scores = payload.pop('scores')
    previous = EvaluationReport.model_validate_json(json.dumps(payload, ensure_ascii=False))
    canonical = normalize_reference(report.registration_reference)
    if (previous.scores.model_dump(mode='json') != original_scores
        or previous.candidate_key != report.candidate_key or previous.policy_version != report.policy_version
        or normalize_reference(previous.registration_reference) != canonical
        or normalize_reference(old_origin['canonical']) != canonical
        or origin_ref['path'] not in previous.source_references):
        raise ValueError('The correction does not identify the same authenticated previous report')
    for field in ('history_run', 'plan_run', 'availability_run', 'translation_run'):
        if old_origin.get(field) != origin.get(field):
            raise ValueError('A no-resampling correction must retain the same ' + field)
    for reference in old_origin['sources']:
        reader.remember(reference['path'], reference['sha256'])
    old_score, new_score = previous.scores.overall, report.scores.overall
    before = f'{old_score:.2f}' if old_score is not None else '待评价'
    after = f'{new_score:.2f}' if new_score is not None else '待评价'
    unchanged = '原历史任务、原始证据及10次访问均未重采。' if origin.get('availability_run') else '原计划与已有历史证据均未重采，本次未新增访问采样。'
    report.scope = (f'本版更正：综合{before}→{after}。修复JSON对话转义造成的原题误判，以及行为维度对内部prompt回显的错误门禁。'
                    + unchanged + '\n' + report.scope)
    report.limitations.extend([
        '本版纠正平台核验实现：功能题干按正规JSON对话解码后精确核对；行为仍独立核验链上请求、交付、任务号、工具和CID，不因内部prompt未再次回显原题而判失败。',
        f'更正前版本综合分为{before}，原报告与原件继续保留：' + report_ref['path'] + '；这次更正没有选择新样本或重新测量访问。',
    ])


def present_prediction_report(report: EvaluationReport, bundle: dict, catalog: dict, reader, origin: dict) -> None:
    """Mutate existing presentation fields only; no per-tool score or sample is created."""
    if origin.get('report_format_revision') != 2:
        return
    canonical = normalize_reference(report.registration_reference)
    if (report.policy_version not in ('prediction-history-v1', 'prediction-history-v2')
        or bundle['profile']['policy_version'] != report.policy_version
        or canonical != normalize_reference(origin['canonical'])):
        raise ValueError('Prediction presentation belongs to another policy or registered identity')
    identity = verify_mech_identity(reader, bundle, canonical)
    original_catalog, _ = _catalog(reader, identity, {}, origin['catalog'])
    if original_catalog != catalog:
        raise ValueError('Capability presentation must use the actual registered tool catalog')
    operations = list(dict.fromkeys(catalog['tools']))
    if any(not name.strip() for name in operations):
        raise ValueError('A declared capability requires a nonempty actual operation')
    supported = {tool.operation for tool in prediction_tool_descriptors(catalog) if prediction_tool_supported(tool)}
    metadata = catalog['toolMetadata']
    capabilities = {}
    for operation in operations:
        declaration = metadata.get(operation)
        description = declaration.get('description') if isinstance(declaration, dict) else None
        capabilities[operation] = CapabilityCoverage(
            capability_id='mech-task-' + hashlib.sha256((canonical + '\0' + operation).encode()).hexdigest()[:20],
            operation=operation,
            description=description if isinstance(description, str) and description.strip() else '登记目录列出此操作，但未提供可引用的功能描述。',
            protocol='olas-mech-marketplace', tested_scope='', sample_ids=[],
            findings=[ReportFinding(label='声明来源（不代表业务通过）', verdict=Verdict.UNKNOWN,
                explanation='实际登记服务目录列出此工具；目录存在或格式完整不证明实际业务正确，也不产生工具分。')],
            missing_evidence=[])
    tasks = {f"{report.policy_version}:{report.candidate_key}:{task['slot']}": task for task in bundle['tasks']}
    linked, unbound = set(), []
    for explanation in report.samples:
        if explanation.sample.purpose not in (MeasurementPurpose.FUNCTIONAL, MeasurementPurpose.BEHAVIORAL):
            continue
        explanation.capability_id = None
        sample_id = explanation.sample.sample_id
        task = tasks.get(sample_id)
        if task is None or task.get('purpose') != explanation.sample.purpose.value:
            raise ValueError('A capability sample is not an original frozen task slot')
        prepared = _prepare(reader, task, identity, catalog)
        operation = prepared.get('operation')
        if operation is None:
            unbound.append(sample_id)
            continue
        capability = capabilities[operation]
        if sample_id in linked:
            raise ValueError('A prediction task cannot belong to two tool capabilities')
        explanation.capability_id = capability.capability_id
        capability.sample_ids.append(sample_id)
        linked.add(sample_id)
    samples = {item.sample.sample_id: item for item in report.samples}
    for operation, capability in capabilities.items():
        functional = sum(samples[key].sample.purpose == MeasurementPurpose.FUNCTIONAL for key in capability.sample_ids)
        behavioral = len(capability.sample_ids) - functional
        if capability.sample_ids:
            capability.tested_scope = (f'本轮固定历史样本中，该工具关联{functional}条功能概率评价、{behavioral}条链上履约核验；'
                                       '每条结论见关联样本，不另算工具分，不把其他工具的结果推给本工具。')
            if not functional:
                capability.missing_evidence.append('本轮未抽到该工具的功能维度任务，未评价其概率表现。')
            if not behavioral:
                capability.missing_evidence.append('本轮未抽到该工具的行为维度任务，未据其他工具证明其完整履约。')
            if any(samples[key].sample.verdict == Verdict.UNKNOWN for key in capability.sample_ids):
                capability.missing_evidence.append('部分关联槽位仍有UNKNOWN，具体缺项保留在该样本中。')
        elif operation in supported:
            capability.tested_scope = '声明符合当前预测专项，但本轮固定历史样本未能认证到该工具的任务；当前仅展示声明资料。'
            capability.missing_evidence.append('尚无本轮可绑定的实际任务证据；未抽到或缺少归属证据不记为业务失败。')
        else:
            capability.tested_scope = '此工具的业务语义或输入输出结构尚未匹配当前二元预测专项；本报告未评价它的实际业务结果。'
            capability.missing_evidence.append('缺少可确认匹配当前专项的业务声明与结构，或需要其他适用的实际任务及独立判据；保持UNKNOWN。')
        capability.missing_evidence.append('历史抽样不覆盖该工具全部任务，也未测量其实时推理、收费访问或未抽到的业务能力。')
    published = {item.capability_id: item for item in capabilities.values()}
    if len(published) != len(capabilities):
        raise ValueError('Capability identifiers must be unique')
    if {key for capability in published.values() for key in capability.sample_ids} != linked:
        raise ValueError('Capability sample links are incomplete')
    for sample_id in linked:
        capability = published[samples[sample_id].capability_id]
        if sample_id not in capability.sample_ids:
            raise ValueError('Capability links must agree in both directions')
    report.capabilities = list(capabilities.values())
    report.scope += '\n各工具的已测范围和未覆盖能力分别列明；综合分仅对应本轮固定样本，不是每项工具的单独得分。'
    if unbound:
        report.limitations.append(f'原固定槽位中有{len(unbound)}条任务尚不能从认证请求确认实际工具，已保留原槽与原判定，未虚构功能归属。')
    _correction(report, reader, origin)
