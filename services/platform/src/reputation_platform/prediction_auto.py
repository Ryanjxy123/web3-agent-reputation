"""Attach the existing prediction policy to authenticated protocol evidence."""

from datetime import datetime, timezone
from collections import Counter
import hashlib
import json
from pathlib import Path
import secrets
import sys

from reputation_core.application import normalize_reference
from reputation_platform.evaluation_report import render_evaluation_report
from reputation_platform.mech_task_collection import _LeasedEvidenceStore
from reputation_platform.model_analysis import prediction_tool_descriptors
from reputation_core.planning import prediction_tool_supported
from reputation_platform.prediction_evidence import collect_history, file_reference, EvidenceUnavailable
from reputation_platform.prediction_report import build_prediction_report, RetainedEvidence, load_history_profile
from reputation_platform.question_translation import load_verified_translations

POLICY = 'docs/adr/0013-automatic-prediction-attachment.md'
ERRATUM = 'docs/adr/0014-prediction-binding-verification-erratum.md'
SUPPLEMENT_POLICY = 'docs/adr/0015-registration-date-supplement.md'
ORIGIN = 'prediction-auto-origin.json'


def _save(path: Path, value) -> None:
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)


def _run(root: Path, prefix: str) -> Path:
    path = root / 'runtime' / f'{prefix}-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}-{secrets.token_hex(4)}'
    path.mkdir()
    return path


def _qualification_gap(registration: dict, evidence, history: Path, bundle: dict) -> None:
    """Retain why a recognized specialty could not form an evaluable cohort."""
    reasons = Counter(item['reason'] for item in bundle['qualifications'])
    looked = len(bundle['qualifications'])
    qualified = bundle['plan']['qualified_market_count']
    explanation = (f'已识别历史预测声明；本轮检查{looked}条历史候选，仅{qualified}个市场符合固定取样条件。'
                   '未形成可自动评价的任务材料，因此不生成预测分；缺少原件或明确市场标识不等于Agent业务失败。')
    assessment = evidence.run/'prediction-qualification-summary.json'
    labels = {'http_status_not_success': '公开原始请求文件未成功读取，具体HTTP状态见保留观测',
              'Original task lacks an explicit supported market identifier': '原始请求没有明确的受支持市场标识，无法独立对应结算结果',
              'ReadTimeout': '本次原始请求文件读取超时，尚未取得可核对内容'}
    _save(assessment, {'canonical': registration['canonical'], 'status': 'INSUFFICIENT_EVIDENCE',
        'looked_count': looked, 'qualified_market_count': qualified,
        'reason_counts': [{'reason': reason, 'count': count} for reason, count in reasons.most_common()],
        'explanation': explanation, 'sources': [file_reference(history/name, evidence.root)
                                               for name in ('manifest.json', 'bundle.json')],
        'score_effect': 'NONE'})
    registration['limitations'].extend([explanation, *[f'历史候选缺项：{count}条；{labels.get(reason, reason)}'
                                                    for reason, count in reasons.most_common()]])
    for path in (assessment, history/'manifest.json', history/'bundle.json'):
        reference = file_reference(path, evidence.root)
        evidence.inputs[reference['path']] = reference['sha256']


def _report(root: Path, origin: dict):
    translations, translation_refs = {}, []
    supplement_inputs = {}
    identity_run = root/origin['identity_run'] if origin.get('identity_run') else None
    if identity_run:
        from reputation_platform.prediction_registration_supplement import validate_registration_supplement

        supplement_inputs = validate_registration_supplement(root, identity_run, root/origin['history_run'])
    if origin.get('translation_run'):
        translations, translation_refs = load_verified_translations(root / origin['translation_run'])
    report, background, reader = build_prediction_report(
        history_run=root / origin['history_run'], plan_run=root / origin['plan_run'],
        availability_run=root / origin['availability_run'] if origin.get('availability_run') else None,
        translations=translations, identity_run=identity_run,
        verification_revision=origin.get('verification_revision', 1), root=root)
    reader.inputs.update(supplement_inputs)
    if identity_run:
        reader.remember(SUPPLEMENT_POLICY)
        report.scope = '本版补充了ERC-8004登记日期的原始交易证明，历史任务与原分组保持不变。\n' + report.scope
    for item in translation_refs:
        reader.remember(item.path, item.sha256)
    reader.remember(POLICY)
    if origin.get('verification_revision', 1) in (2, 3, 4):
        reader.remember(ERRATUM)
    if origin.get('report_format_revision', 1) == 2:
        from reputation_platform.prediction_presentation import present_prediction_report

        history = root / origin['history_run']
        manifest = reader.manifest(history)
        bundle_ref = next(item for item in manifest['outputs']
                          if item['path'] == (history/'bundle.json').relative_to(root).as_posix())
        bundle = json.loads(reader.remember(bundle_ref['path'], bundle_ref['sha256']).read_bytes())
        descriptor = json.loads(reader.remember(origin['plan_run'] + '/descriptor.json').read_bytes())
        catalog = json.loads(reader.remember(descriptor['metadata_source_file']).read_bytes())
        present_prediction_report(report, bundle, catalog, reader, origin)
    report.source_references = sorted(reader.inputs)
    return report, background, reader


def verify_auto_prediction_report(root: Path, report, hashes: dict[str, str]) -> str:
    """Rebuild new automatic reports before accepting them into PostgreSQL."""
    from reputation_platform.mech_task_evidence import _catalog
    from reputation_platform.mech_task_identity import verify_mech_identity

    reader = RetainedEvidence(root)
    origins = {name: json.loads(reader.remember(name, hashes[name]).read_bytes())
               for name in hashes if Path(name).name == ORIGIN}
    previous = {item['correction_of']['origin']['path'] for item in origins.values() if item.get('correction_of')}
    names = [name for name in origins if name not in previous]
    if len(names) != 1:
        raise ValueError('An automatic prediction report requires one retained origin')
    origin = origins[names[0]]
    if origin.get('schema_version') != 'prediction-auto-report-v1':
        raise ValueError('Unsupported automatic prediction report origin')
    for item in origin['sources']:
        reader.remember(item['path'], item['sha256'])
    history = root / origin['history_run']
    manifest = reader.manifest(history)
    bundle_ref = next(item for item in manifest['outputs'] if item['path'] == (history/'bundle.json').relative_to(root).as_posix())
    bundle = json.loads(reader.remember(bundle_ref['path'], bundle_ref['sha256']).read_bytes())
    profile = load_history_profile(reader, manifest, bundle)
    identity = verify_mech_identity(reader, bundle, profile.registration_reference)
    catalog, _ = _catalog(reader, identity, hashes, origin['catalog'])
    descriptor = json.loads(reader.remember(origin['plan_run'] + '/descriptor.json').read_bytes())
    if json.loads(reader.remember(descriptor['metadata_source_file']).read_bytes()) != catalog:
        raise ValueError('The selected tool catalog is not the registered service catalog')
    supported = sorted(tool.operation for tool in prediction_tool_descriptors(catalog) if prediction_tool_supported(tool))
    if bundle['plan'].get('supported_operations') != supported:
        raise ValueError('Historical eligibility did not use the registered prediction operations')
    expected, _, rebuilt = _report(root, origin)
    expected.source_references = sorted(set(expected.source_references) | {names[0]})
    expected.generated_at = report.generated_at
    if expected.model_dump(mode='json') != report.model_dump(mode='json'):
        raise ValueError('Automatic report differs from its actual task, selection or probability evidence')
    reader.inputs.update(rebuilt.inputs)
    if any(hashes.get(name) != digest for name, digest in reader.inputs.items()):
        raise ValueError('Automatic prediction dependencies are absent from the report manifest')
    return profile.registration_reference


def _retained_history(root: Path, canonical: str, catalog: dict, policy_version: str = 'prediction-history-v1'):
    for path in sorted((root/'runtime').glob('prediction-auto-history-*/manifest.json'), reverse=True):
        try:
            if json.loads(path.read_bytes()).get('canonical') != canonical:
                continue
            reader = RetainedEvidence(root)
            manifest = reader.manifest(path.parent)
            if manifest.get('canonical') != canonical or not manifest.get('selection_run'):
                continue
            ref = next(item for item in manifest['outputs'] if item['path'].endswith('/bundle.json'))
            bundle = json.loads(reader.remember(ref['path'], ref['sha256']).read_bytes())
            profile = load_history_profile(reader, manifest, bundle)
            if (profile.registration_reference != canonical or profile.policy_version != policy_version
                or bundle['plan']['status'] != 'READY'
                or not all(task.get('input') and task.get('output') and task.get('chain_evidence') for task in bundle['tasks'])):
                continue
            from reputation_platform.mech_task_identity import verify_mech_identity
            from reputation_platform.mech_task_evidence import _catalog

            identity = verify_mech_identity(reader, bundle, canonical)
            previous, proof = _catalog(reader, identity, reader.inputs, manifest['catalog'])
            if previous == catalog:
                return path.parent, root/manifest['selection_run'], bundle, proof
        except (ValueError, KeyError, TypeError, OSError, StopIteration):
            continue
    return None


def evaluate_auto_prediction(repo, job: dict, worker: str, registration: dict, evidence) -> bool:
    from reputation_platform.prediction_auto_sources import prepare_prediction_source
    from reputation_platform.prediction_auto_selection import write_auto_selection
    from reputation_platform.worker import execute_child

    canonical = normalize_reference(registration['canonical'])
    if not canonical or canonical.split(':')[1] != '100':
        return False
    root = evidence.root
    history = _run(root, 'prediction-auto-history')
    attempt_run = history
    reuse = [evidence.run, *(root/'runtime').glob('prediction-history-*'),
             *(root/'runtime').glob('input-layout-research-*'),
             *(root/'runtime').glob('prediction-exact-title-chain-research-*'),
             *(root/'runtime').glob('prediction-question-source-research-*'),
             *(root/'runtime').glob('prediction-question-resolution-check-*'),
             *(root/'runtime').glob('direct-question-source-research-*'),
             *(root/'runtime').glob('direct-question-followup-*'),
             *(root/'runtime').glob('prediction-history-tail-discovery-*'),
             *(root/'runtime').glob('prediction-tail-event-probe-*'),
             *(path for path in (root/'runtime').glob('prediction-auto-history-*') if path != history)]
    store = repo.run_with_lease(job['id'], worker, job['fencing_token'], lambda: _LeasedEvidenceStore(
        history, reuse, enabled=evidence.enabled, proxy=evidence.proxy,
        max_requests=1200, parallel_reads=2, root=root, heartbeat=evidence.heartbeat))
    try:
        prepared = repo.run_with_lease(job['id'], worker, job['fencing_token'],
            lambda: prepare_prediction_source(registration, evidence, store))
        if prepared is None:
            return False
        profile, catalog = prepared['profile'], prepared['catalog']
        supported = {tool.operation for tool in prediction_tool_descriptors(catalog) if prediction_tool_supported(tool)}
        if not supported:
            return False
        repo.set_job_stage(job['id'], worker, job['fencing_token'], 'COLLECTING',
            '已自动匹配历史预测判据，正在核实不同市场与原始任务；不发起付费预测或链上交易。')
        retained = _retained_history(root, canonical, catalog, profile.policy_version)
        identity_run = None
        if retained:
            history, plan_run, bundle, catalog_proof = retained
            if not bundle['identity'].get('registration_time') and prepared['identity'].get('registration_time'):
                from reputation_platform.prediction_registration_supplement import write_registration_supplement

                identity_run = _run(root, 'prediction-registration-supplement')
                write_registration_supplement(root, identity_run, history, prepared['identity'])
        else:
            profile_path = history/'prediction-profile.json'
            _save(profile_path, profile.__dict__)
            store._remember([file_reference(profile_path, root), file_reference(root/POLICY, root)])
            if profile.policy_version == 'prediction-history-v2':
                store._remember([file_reference(root/'docs/adr/0016-prediction-evidence-v2.md', root)])
                store._remember([file_reference(root/'docs/adr/0017-prediction-question-and-output-contract.md', root)])
                store._remember([file_reference(root/'docs/adr/0018-marketplace-request-event-versions.md', root)])
                if profile.history_max_deliveries == 512:
                    store._remember([file_reference(root/'docs/adr/0019-prediction-history-bound.md', root)])
            store._remember([{'path': name, 'sha256': digest} for name, digest in prepared['retained_inputs'].items()])
            bundle = collect_history(store, profile, identity=prepared['identity'], supported_operations=supported,
                                     profile_reference=file_reference(profile_path, root))
            plan_run = _run(root, 'prediction-auto-plan')
            selected = write_auto_selection(registration, evidence, bundle, catalog, prepared['catalog_proof'], run=plan_run)
            catalog_proof = prepared['catalog_proof']
            _save(history/'manifest.json', {'schema_version': 'prediction-auto-history-v1',
                'completed_at': datetime.now(timezone.utc).isoformat(), 'canonical': canonical,
                'selection_run': plan_run.relative_to(root).as_posix() if selected else None,
                'catalog': catalog_proof, 'inputs': list(store.inputs.values()),
                'outputs': [file_reference(history/'bundle.json', root)], 'new_request_count': store.sent,
                'mainnet_writes': False, 'model_calls': 0})
            if selected is None:
                _qualification_gap(registration, evidence, history, bundle)
                return False
        log = _run(root, 'prediction-auto-job')
        availability = None
        outputs, source_inputs = [], dict(evidence.inputs)
        reader = RetainedEvidence(root)
        for task in bundle['tasks']:
            if not task.get('output') or not task.get('chain_evidence'):
                continue
            from reputation_core.prediction_chain import extract_task_anchors
            try:
                anchors = extract_task_anchors(reader.tree(task['chain_evidence']), mech=profile.mech,
                    request_id=task['request_id'], confirmation_head=profile.confirmation_head)
                if profile.policy_version == 'prediction-history-v2':
                    reader.content_bytes(task['output'], anchors['output_digest'], str(int(task['request_id'], 16)))
                else:
                    reader.content(task['output'], anchors['output_digest'], str(int(task['request_id'], 16)))
                outputs.append({'request_id': task['request_id'], 'root_digest': anchors['output_digest'],
                    'response_file': task['output']['response_file'], 'sha256': task['output']['sha256']})
                if task['output'].get('layout'):
                    outputs[-1]['layout'] = task['output']['layout']
            except (ValueError, KeyError, TypeError, OSError):
                continue
        source_inputs.update(reader.inputs)
        if len(outputs) >= 10:
            sources_path = log/'availability-sources.json'
            _save(sources_path, {'candidate_key': profile.candidate_key, 'policy_version': profile.policy_version,
                'outputs': outputs[:10],
                'inputs': [{'path': name, 'sha256': digest} for name, digest in sorted(source_inputs.items())]})
            repo.set_job_stage(job['id'], worker, job['fencing_token'], 'COLLECTING',
                '历史任务已冻结，正在测量十次公开交付文件访问；这不代表实时推理可用性。')
            availability = execute_child([sys.executable, str(root/'scripts/sample_prediction_availability.py'),
                '--sources', str(sources_path), '--execute-public-readonly', '--proxy', evidence.proxy],
                log/'availability.log', repo, job, worker)
        translation = None
        if bundle['plan']['status'] == 'READY' and bundle['plan']['qualified_market_count'] == 14:
            translation = execute_child([sys.executable, str(root/'scripts/translate_prediction_questions.py'),
                '--bundles', str(history/'bundle.json'), '--execute', '--proxy', evidence.proxy],
                log/'translation.log', repo, job, worker)
        origin = {'schema_version': 'prediction-auto-report-v1', 'canonical': canonical,
            'verification_revision': 4 if profile.policy_version == 'prediction-history-v2' else 2,
            'report_format_revision': 2,
            'history_run': history.relative_to(root).as_posix(), 'plan_run': plan_run.relative_to(root).as_posix(),
            'availability_run': availability.relative_to(root).as_posix() if availability else None,
            'translation_run': translation.relative_to(root).as_posix() if translation else None,
            'catalog': catalog_proof, 'sources': [file_reference(history/'manifest.json', root),
                file_reference(plan_run/'manifest.json', root), file_reference(root/POLICY, root),
                file_reference(root/ERRATUM, root)]}
        if availability:
            origin['sources'].append(file_reference(availability/'manifest.json', root))
        if translation:
            origin['sources'].append(file_reference(translation/'materials.json', root))
        if identity_run:
            origin['identity_run'] = identity_run.relative_to(root).as_posix()
            origin['sources'].append(file_reference(identity_run/'manifest.json', root))
        repo.set_job_stage(job['id'], worker, job['fencing_token'], 'VERIFYING',
            '正在从概率原文、市场结算、请求交付和执行控制重建三维结果及中文说明。')
        report, background, reader = _report(root, origin)
        destination = _run(root, 'evaluation-report')
        _save(destination/ORIGIN, origin)
        reader.remember((destination/ORIGIN).relative_to(root).as_posix())
        report.source_references = sorted(reader.inputs)
        _save(destination/'report.json', report.model_dump(mode='json'))
        _save(destination/'background.json', background)
        (destination/'report.html').write_text(render_evaluation_report(report), encoding='utf-8')
        _save(destination/'manifest.json', {'policy_version': report.policy_version,
            'completed_at': datetime.now(timezone.utc).isoformat(), 'network_requests': 0,
            'inputs': [{'path': name, 'sha256': digest} for name, digest in sorted(reader.inputs.items())],
            'outputs': [file_reference(destination/name, root) for name in ('report.json', 'report.html')]})
        repo.set_job_stage(job['id'], worker, job['fencing_token'], 'REPORTING', '正在保存本次历史预测报告与逐项证据。')
        repo.finalize_job(job['id'], worker, job['fencing_token'], status='COMPLETE',
            candidate_key=profile.candidate_key, report_directory=destination,
            message=('已按历史预测范围完成三维评分，报告说明概率信用和未覆盖能力。' if report.scores.status == 'COMPLETE'
                     else '已发布历史预测部分报告；不足的样本和证据逐项列出，未计算综合分。'))
        return True
    except EvidenceUnavailable as error:
        _save(attempt_run/'automatic-issue.json', {'status': 'UNKNOWN', 'reason': str(error), 'canonical': canonical})
        registration['limitations'].append('自动历史预测暂无法评价：' + str(error))
        return False
    finally:
        evidence.inputs.update({item['path']: item['sha256'] for item in store.inputs.values()})
        evidence.request_count += store.sent
        store.close()
