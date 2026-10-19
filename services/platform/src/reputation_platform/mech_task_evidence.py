"""Verify frozen Mech deliveries and resume absent files on a new evaluation."""

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from reputation_core import CapabilityCoverage, MeasurementPurpose, ReportFinding, SampleExplanation, ScoredSample, Verdict
from reputation_core.application import normalize_reference
from reputation_core.prediction_chain import extract_task_anchors, verify_prediction_chain
from reputation_core.reporting import EvaluationReport
from reputation_platform.mech_task_identity import verify_mech_identity
from reputation_platform.prediction_report import AuthenticatedJsonError, OutputViolation, RetainedEvidence

POLICY = 'docs/adr/0011-shared-task-delivery-evidence.md'
PLAN_NAME = 'generic-mech-task-plan.json'
SCHEMAS = {'prediction-evidence-bundle-v1', 'mech-task-evidence-bundle-v1'}


def _reference(reader: RetainedEvidence, name: str, expected: str | None = None) -> dict:
    path = reader.remember(name, expected)
    key = path.relative_to(reader.root).as_posix()
    return {'path': key, 'sha256': reader.inputs[key]}


def _source(reader: RetainedEvidence, path: Path) -> dict:
    manifest_path = path.parent / ('mech-source-manifest.json' if (path.parent / 'mech-source-manifest.json').is_file() else 'manifest.json')
    manifest_ref = _reference(reader, manifest_path.relative_to(reader.root).as_posix())
    manifest = json.loads(manifest_path.read_bytes())
    completed = datetime.fromisoformat(manifest['completed_at'])
    if completed.tzinfo is None or manifest.get('outcome', {}).get('status') in {'UNKNOWN', 'INTERRUPTED', 'INCOMPLETE'}:
        raise ValueError('Source collection has no valid completed timestamp or outcome')
    references = {item['path']: item['sha256'] for item in [*manifest.get('inputs', []), *manifest.get('outputs', [])]}
    name = path.relative_to(reader.root).as_posix()
    if name not in references:
        raise ValueError('Completed source manifest does not authenticate its bundle')
    bundle_ref = _reference(reader, name, references[name])
    bundle = json.loads(path.read_bytes())
    if bundle.get('schema_version') not in SCHEMAS:
        raise ValueError('Unsupported completed task bundle')
    if bundle.get('resume_of'):
        previous = bundle['resume_of']
        parent = _source(reader, reader.path(previous['bundle']['path']))
        for name, digest in parent['references'].items():
            reader.remember(name, digest)
        if (any(parent[key] != previous[key] for key in ('bundle', 'manifest', 'plan'))
            or bundle['profile'] != parent['data']['profile'] or bundle['identity'] != parent['data']['identity']
            or bundle['plan_reference'] != parent['data']['plan_reference']
            or bundle['plan'] != parent['data']['plan'] or len(bundle['tasks']) != len(parent['data']['tasks'])):
            raise ValueError('Resumed source changed its frozen identity or task cohort')
        resume_ref = bundle['resume_plan']
        if references.get(resume_ref['path']) != resume_ref['sha256']:
            raise ValueError('Completed resumed source has no authenticated recovery plan')
        reader.remember(resume_ref['path'], resume_ref['sha256'])
        for old, new in zip(parent['data']['tasks'], bundle['tasks']):
            if any(old.get(key) != new.get(key) for key in ('slot', 'purpose', 'request_id', 'task_key')):
                raise ValueError('Resumed source replaced an original task')
            if any(old.get(key) is not None and old[key] != new.get(key) for key in ('chain_evidence', 'input', 'output')):
                raise ValueError('Recovery must preserve every original retained task component')
    profile, plan_ref = bundle['profile'], bundle['plan_reference']
    canonical = normalize_reference(f"eip155:{profile['chain_id']}:{profile['registry']}:{profile['agent_id']}")
    if not canonical or references.get(plan_ref['path']) != plan_ref['sha256']:
        raise ValueError('Original task plan or identity is not bound by the completed source')
    original = json.loads(reader.remember(plan_ref['path'], plan_ref['sha256']).read_bytes())
    if original != bundle['plan'] or original.get('pilot_only') is True:
        raise ValueError('Original frozen plan differs or is an excluded pilot')
    if bundle['schema_version'] == 'prediction-evidence-bundle-v1' and original.get('pilot_only') is not False:
        raise ValueError('Legacy source is not a formal frozen cohort')
    slots = [slot for slot in original['slots'] if slot['purpose'] == 'behavioral']
    ids = [slot['request_id'] for slot in original['slots'] if slot.get('request_id')]
    if (len(slots) != 7 or len(set(ids)) != len(ids)
        or bundle['schema_version'] == 'mech-task-evidence-bundle-v1' and len(original['slots']) != 7):
        raise ValueError('Source must retain seven distinct original behavioral slots')
    tasks = []
    for slot in slots:
        matches = [task for task in bundle['tasks'] if task['slot'] == slot['slot'] and task['purpose'] == 'behavioral']
        if len(matches) != 1 or any(matches[0].get(key) != slot.get(key) for key in ('request_id', 'task_key')):
            raise ValueError('Task copy differs from its original behavioral slot')
        tasks.append(matches[0])
    return {'manifest': manifest_ref, 'bundle': bundle_ref, 'plan': plan_ref, 'data': bundle,
            'canonical': canonical, 'completed_at': completed, 'slots': slots, 'tasks': tasks, 'references': references}


def _catalog(reader: RetainedEvidence, identity: dict, known: dict[str, str], proof: dict | None = None) -> tuple[dict, dict]:
    urls = {item['endpoint'] for item in identity['document'].get('services', [])
            if str(item.get('name', '')).lower() == 'manifest' and isinstance(item.get('endpoint'), str)}
    if proof is None:
        names = {name for name in known if name.endswith('.observation.json')
                 and any(part in Path(name).name for part in ('manifest', 'catalog', 'document'))}
        for pattern in ('runtime/olas-discovery-identities-*/*manifest.observation.json',
                        'runtime/generic-evaluation-*/*manifest*.observation.json',
                        'runtime/generic-evaluation-*/*document.observation.json'):
            names.update(path.relative_to(reader.root).as_posix() for path in reader.root.glob(pattern))
        for name in sorted(names):
            observed_path = reader.path(name)
            obs = json.loads(observed_path.read_bytes())
            if (obs.get('url') in urls and obs.get('method') == 'GET' and obs.get('http_status') == 200
                and obs.get('body_complete') and not obs.get('error_kind') and obs.get('response_file')):
                response_name = (observed_path.parent / obs['response_file']).relative_to(reader.root).as_posix()
                proof = {'url': obs['url'], 'evidence': [_reference(reader, name, known.get(name)),
                         _reference(reader, response_name, obs['response_sha256'])]}
                break
        if proof is None:
            raise ValueError('Registered manifest URL has no retained catalog GET response')
    if proof['url'] not in urls:
        raise ValueError('Tool catalog is not linked by the registered document')
    observation, raw = reader.observation(proof['evidence'], url=proof['url'], method='GET')
    document = json.loads(raw)
    if (observation.request_json is not None or not isinstance(document, dict)
        or not isinstance(document.get('tools'), list) or not all(isinstance(name, str) for name in document['tools'])
        or not isinstance(document.get('toolMetadata'), dict)):
        raise ValueError('Registered catalog lacks the supported tool declarations')
    return document, proof


def _prepare(reader: RetainedEvidence, task: dict, identity: dict, catalog: dict) -> dict:
    try:
        if not task.get('request_id'):
            raise ValueError('Original slot has no authenticated request')
        if not task.get('input'):
            raise ValueError('本槽原始请求文件尚未取得，暂时不能确认实际工具；原任务仍保留在计划中。')
        chain = reader.tree(task['chain_evidence'])
        anchors = extract_task_anchors(chain, mech=identity['mech'], request_id=task['request_id'],
                                       confirmation_head=identity['confirmation_head'])
        original = reader.content(task['input'], anchors['input_digest'], 'metadata.json')
        operation = original.get('tool') if isinstance(original, dict) else None
        if (not isinstance(operation, str) or operation not in catalog['tools']
            or not isinstance(catalog['toolMetadata'].get(operation), dict)):
            raise ValueError('Authenticated input tool is absent from its registered catalog')
        return {'chain': chain, 'anchors': anchors, 'input': original, 'operation': operation}
    except (ValueError, KeyError, TypeError, OSError) as error:
        return {'missing': '原槽位尚缺可认证的请求、工具或链上文件绑定：' + str(error)}


def _slots(reader: RetainedEvidence, source: dict, identity: dict, catalog: dict) -> tuple[list[dict], list[dict]]:
    slots, prepared = [], []
    for slot, task in zip(source['slots'], source['tasks']):
        item = _prepare(reader, task, identity, catalog)
        operation, rid = item.get('operation'), slot.get('request_id')
        capability = 'mech-task-' + hashlib.sha256((identity['canonical'] + '\0' + operation).encode()).hexdigest()[:20] if operation else None
        slots.append({'source_slot': slot, 'purpose': 'behavioral', 'request_id': rid,
            'task_key': f"eip155:100:mech:{identity['mech']}:request:{rid.lower()}" if rid else None,
            'sample_id': f"mech-task:{source['bundle']['sha256'][:16]}:{slot['slot']:02d}",
            'operation': operation, 'capability_id': capability})
        prepared.append(item)
    return slots, prepared


def _proof_paths(value):
    if isinstance(value, dict):
        if set(value) == {'path', 'sha256'}:
            yield value['path']
        else:
            for item in value.values():
                yield from _proof_paths(item)
    elif isinstance(value, list):
        for item in value:
            yield from _proof_paths(item)


def _samples(reader: RetainedEvidence, source: dict, identity: dict, catalog: dict,
             slots: list[dict], prepared: list[dict], plan_name: str) -> tuple[list[CapabilityCoverage], list[SampleExplanation], list[str]]:
    capabilities, samples, missing = {}, [], []
    for slot, task, original in zip(slots, source['tasks'], prepared):
        operation = slot['operation']
        if operation is None:
            missing.append(f"原行为槽位 {slot['source_slot']['slot']}：{original['missing']}；原槽保留在计划，不虚构业务功能。")
            continue
        metadata = catalog['toolMetadata'][operation]
        verification = verify_prediction_chain(original['chain'], mech=identity['mech'], service_id=identity['service_id'],
            request_id=slot['request_id'], confirmation_head=identity['confirmation_head'])
        verdict, reason, output = verification.verdict, verification.reason, None
        checks = list(verification.checks)
        try:
            if not task.get('output'):
                raise ValueError('本槽交付文件尚未取得，暂不能核对任务号与交付内容。')
            output = reader.content(task['output'], original['anchors']['output_digest'], str(int(slot['request_id'], 16)))
            if not isinstance(output, dict) or str(output.get('requestId')) != str(int(slot['request_id'], 16)):
                raise OutputViolation('已认证交付文件未提供与实际任务一致的requestId。')
            if 'tool' in output and output['tool'] != operation:
                raise OutputViolation('已认证交付工具与原始请求工具不一致。')
            required = metadata.get('output', {}).get('schema', {}).get('required', [])
            if 'prompt' in required and not isinstance(output.get('prompt'), str):
                raise OutputViolation('登记输出约定要求prompt，但已认证交付中缺少该文本。')
            checks.append(ReportFinding(label='任务文件与声明工具', verdict=Verdict.PASS,
                explanation='请求metadata.json与交付任务文件均通过链上CID及CAR逐块认证，任务号、实际工具及声明必备prompt已对应；未评价业务正确性。'))
        except (OutputViolation, AuthenticatedJsonError) as error:
            verdict, reason = Verdict.FAIL, str(error)
            checks.append(ReportFinding(label='已认证交付的任务绑定', verdict=Verdict.FAIL, explanation=reason))
        except (ValueError, KeyError, TypeError, OSError) as error:
            if verdict != Verdict.FAIL:
                verdict, reason = Verdict.UNKNOWN, '交付文件原件或绑定证据尚不完整：' + str(error)
            checks.append(ReportFinding(label='交付文件证据完整性', verdict=Verdict.UNKNOWN,
                                       explanation='交付文件原件或绑定证据尚不完整：' + str(error)))
        explanation = ('该次请求到交付的链上履约及文件归属已核验。' if verdict == Verdict.PASS else
                       '该次历史任务存在已核实的履约矛盾。' if verdict == Verdict.FAIL else '该次历史任务证据尚不充分，暂时无法判断。')
        explanation += ' 本项不评价预测概率、业务答案正确性或收益。原始规则说明：' + reason
        prompt = original['input'].get('prompt')
        text = prompt[:1200] if isinstance(prompt, str) else '原始请求未提供可读prompt，完整文件见证据。'
        result = output.get('result') if isinstance(output, dict) else None
        claimed = (f"交付任务号：{output.get('requestId')}；绑定的请求工具：{operation}。结果原文节选：{str(result)[:800]}"
                   if isinstance(output, dict) else '尚未取得与本任务绑定的可信交付文件。')
        references = {plan_name, source['manifest']['path'], source['bundle']['path'], source['plan']['path']}
        references.update(path for path in _proof_paths(task) if path in reader.inputs)
        sample = ScoredSample(sample_id=slot['sample_id'], task_key=slot['task_key'], purpose=MeasurementPurpose.BEHAVIORAL,
            verdict=verdict, elapsed_ms=None, reason=explanation, evidence=sorted(references))
        samples.append(SampleExplanation(sample=sample, capability_id=slot['capability_id'],
            observed_at=datetime.fromtimestamp(original['anchors']['delivery_timestamp'], timezone.utc),
            title='历史任务履约 · ' + operation, input_summary='实际工具：' + operation + '。原始请求节选：' + text,
            claimed_output=claimed, independent_result=explanation, checks=checks))
        if operation not in capabilities:
            capabilities[operation] = CapabilityCoverage(capability_id=slot['capability_id'], operation=operation,
                description='登记工具：' + operation + '。' + str(metadata.get('description', '业务说明见登记目录原件。')),
                protocol='Gnosis Mech Marketplace', tested_scope='冻结的不同历史任务：实际请求、交付及文件归属；功能正确性尚未评分。',
                sample_ids=[], findings=[*identity['checks'], ReportFinding(label='注册工具目录来源', verdict=Verdict.PASS,
                    explanation='实际输入tool位于链上登记文档所链接manifest目录；目录GET原件已核对，未以Schema代替业务正确性。')],
                missing_evidence=['尚缺实际功能任务及适用的业务正确性判据；本轮不生成功能分。'])
        capabilities[operation].sample_ids.append(sample.sample_id)
        if verdict == Verdict.UNKNOWN:
            capabilities[operation].missing_evidence.append('历史履约样本仍有无法判断项，具体原因见关联任务。')
    return list(capabilities.values()), samples, list(dict.fromkeys(missing))


def collect_mech_tasks(registration: dict, evidence) -> tuple[list[CapabilityCoverage], list[SampleExplanation], list[str]]:
    canonical = normalize_reference(registration.get('canonical') or registration.get('registration_reference') or '')
    if canonical is None or canonical.split(':')[1] != '100':
        return [], [], []
    candidates, failures = [], []
    for pattern in ('runtime/prediction-history-*/bundle.json', 'runtime/generic-evaluation-*/mech-task-bundle.json'):
        for path in evidence.root.glob(pattern):
            try:
                # Route by the cheap hint first; matching sources still undergo full authentication.
                hint = json.loads(path.read_bytes())['profile']
                reference = normalize_reference(f"eip155:{hint['chain_id']}:{hint['registry']}:{hint['agent_id']}")
                if reference != canonical:
                    continue
                reader = RetainedEvidence(evidence.root)
                source = _source(reader, path)
                if source['canonical'] == canonical:
                    candidates.append((source['completed_at'], path.as_posix(), reader, source))
            except (ValueError, KeyError, TypeError, OSError):
                continue
    for _, _, reader, source in sorted(candidates, key=lambda item: (item[0], item[1]), reverse=True):
        try:
            identity = verify_mech_identity(reader, source['data'], canonical)
            catalog, catalog_proof = _catalog(reader, identity, {**source['references'], **reader.inputs, **evidence.inputs})
        except (ValueError, KeyError, TypeError, OSError) as error:
            failures.append('已有来源的身份或声明目录尚不能完整复核：' + str(error))
            continue
        if source['data']['schema_version'] == 'mech-task-evidence-bundle-v1':
            from reputation_platform.mech_task_resume import resume_mech_source

            recovered = resume_mech_source(reader, source, identity, evidence)
            if recovered is not None:
                source = _source(reader, recovered)
                identity = verify_mech_identity(reader, source['data'], canonical)
        slots, prepared = _slots(reader, source, identity, catalog)
        policy_ref = _reference(reader, POLICY)
        plan = {'schema_version': 'generic-mech-task-plan-v1', 'policy_version': 'service-contract-v1',
            'created_at': datetime.now(timezone.utc).isoformat(), 'canonical': canonical, 'purpose': 'behavioral',
            'source_bundle': source['bundle'], 'source_manifest': source['manifest'], 'source_plan': source['plan'],
            'policy': policy_ref, 'catalog': catalog_proof, 'slots': slots,
            'selection': '沿完成来源原始七个行为槽位，不挪用功能任务、不按交付结果筛选。'}
        plan_path = evidence.run / PLAN_NAME
        with plan_path.open('x', encoding='utf-8') as stream:
            json.dump(plan, stream, ensure_ascii=False, indent=2)
        plan_name = _reference(reader, plan_path.relative_to(evidence.root).as_posix())['path']
        capabilities, samples, missing = _samples(reader, source, identity, catalog, slots, prepared, plan_name)
        evidence.inputs.update(reader.inputs)
        return capabilities, samples, [*missing, '本项基于归档的历史任务原件核验，没有创建新业务任务或调用模型；业务答案正确性仍待评价。',
            '工具目录按登记URL与保留GET原件核对，本轮未新增该声明文件的CID/DAG认证。']
    return [], [], list(dict.fromkeys(failures or ['尚无与本注册身份对应的完整历史Mech行为证据来源，交易维度保留缺项。']))


def verify_mech_task_samples(root: Path, report: EvaluationReport, hashes: dict[str, str]) -> set[str]:
    plans = [name for name in hashes if Path(name).name == PLAN_NAME]
    actual = [item for item in report.samples if item.sample.purpose == MeasurementPurpose.BEHAVIORAL]
    if not plans and not actual:
        return set()
    if len(plans) != 1:
        raise ValueError('Mech behavioral samples require one frozen generic task plan')
    reader = RetainedEvidence(root)
    plan = json.loads(reader.remember(plans[0], hashes[plans[0]]).read_bytes())
    if (plan.get('schema_version') != 'generic-mech-task-plan-v1' or plan.get('policy_version') != report.policy_version
        or plan.get('purpose') != 'behavioral' or plan.get('canonical') != report.registration_reference
        or plan['policy']['path'] != POLICY):
        raise ValueError('Generic task plan differs from the report identity or policy')
    reader.remember(plan['policy']['path'], plan['policy']['sha256'])
    source = _source(reader, reader.path(plan['source_bundle']['path']))
    if any(source[key] != plan['source_' + key] for key in ('bundle', 'manifest', 'plan')):
        raise ValueError('Frozen completed source changed')
    identity = verify_mech_identity(reader, source['data'], plan['canonical'])
    catalog, _ = _catalog(reader, identity, hashes, plan['catalog'])
    slots, prepared = _slots(reader, source, identity, catalog)
    if slots != plan['slots']:
        raise ValueError('All seven original behavioral slots and operation bindings must be preserved')
    capabilities, expected, _ = _samples(reader, source, identity, catalog, slots, prepared, plans[0])
    if [item.model_dump(mode='json') for item in actual] != [item.model_dump(mode='json') for item in expected]:
        raise ValueError('Behavioral samples differ from their original task, chain or CID evidence')
    published = {item.capability_id: item for item in report.capabilities}
    for capability in capabilities:
        found = published.get(capability.capability_id)
        if (found is None or found.operation != capability.operation
            or not set(capability.sample_ids).issubset(found.sample_ids)):
            raise ValueError('Behavioral task belongs to a different declared capability')
    if any(hashes.get(name) != digest for name, digest in reader.inputs.items()):
        raise ValueError('Replayed task dependencies are absent from the report input manifest')
    return {item.sample.sample_id for item in expected}
