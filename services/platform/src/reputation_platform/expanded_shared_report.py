"""Append a formal multi-capability report from retained, independently replayed sources."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from reputation_core.reporting import EvaluationReport
from reputation_core.scoring import MULTICAP_POLICY_VERSION
from reputation_platform.shared_report import SOURCE_ADAPTERS, MULTICAP_ADAPTER
from reputation_platform.swap_report import SwapEvidence, _check

ORIGIN = 'shared-expanded-origin.json'
SCHEMA = 'shared-expanded-report-origin-v2'
ADR = 'docs/adr/0028-formal-multicapability-assessment.md'
APPROACH = '保留历史任务与已核新交易的原始时间，按统一多能力规则回顾性重评；同一任务共享三维证据，未采响应进入未决范围，不生成新的调用。'
LIMITATIONS = [
    '新增任务已纳入正式判分；每项结论只对应本报告明确选择的声明和案例，不代表全部功能或长期声誉。',
    '未采业务响应保留未采及0–100区间，不用RPC、钱包签名或旧入口响应给新入口的A补分。',
    '评价范围和政策版本已扩大，新旧区间不能直接解释为提供方性能提升或退化。',
    '管理任务完成是创建、合约查询、撤销及退款完成；不等于定时或限价触发成交。',
    '单个新场景样本通过只说明该次任务，不是未来可靠率的统计置信区间。',
]


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _write(path, value):
    with path.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write('\n')


def _origin(evidence, value):
    _check(value.get('schema_version') == SCHEMA and value.get('adapter') == MULTICAP_ADAPTER
           and value.get('analysis_mode') == 'retrospective-expanded-scope', 'Unsupported formal multi-capability source')
    evidence.raw(ADR)
    base, catalog, assessment = SOURCE_ADAPTERS[MULTICAP_ADAPTER](evidence.root, evidence, value)
    _check(catalog.get('policy_version') == MULTICAP_POLICY_VERSION
           and assessment.schema_version == 'shared-task-assessment-v2', 'Formal policy and source structure differ')
    return base, catalog, assessment


def _window(assessment):
    times = [task.observed_at for task in assessment.tasks if task.observed_at is not None]
    return (f'复用任务：{min(times).isoformat()} 至 {max(times).isoformat()}；各任务保留原观察时间，未采入口响应没有虚构时间。'
            if times else '任务时间尚未核齐；不以报告生成时间替代业务观察。')


def _limitations(base):
    return [*('历史来源范围说明：' + item for item in base.limitations), *LIMITATIONS]


def verify_expanded_report_sources(root, report, hashes):
    origins = [name for name in hashes if Path(name).name == ORIGIN]
    _check(len(origins) == 1, 'A formal multi-capability report requires one origin')
    evidence = SwapEvidence(root, hashes)
    base, catalog, assessment = _origin(evidence, evidence.json(origins[0]))
    _check(report.policy_version == MULTICAP_POLICY_VERSION
           and report.candidate_key == base.candidate_key and report.name == base.name
           and report.registration_reference == base.registration_reference,
           'Formal report identity or policy differs from source replay')
    _check(report.shared_assessment is not None
           and report.shared_assessment.model_dump(mode='json') == assessment.model_dump(mode='json'),
           'Formal judgments or calculated scores differ from original evidence')
    _check(report.scope == catalog['scope'] and report.scope_exclusions == catalog['scope_exclusions']
           and report.approach == APPROACH and report.evaluation_window == _window(assessment),
           'Formal scope, provenance or observation window differs')
    _check(report.samples == base.samples and report.capabilities == base.capabilities,
           'Formal sample explanations must remain source-derived')
    _check(report.limitations == _limitations(base), 'Formal report changed or omitted evidence limitations')
    _check(set(report.source_references) == set(hashes), 'Formal report source inventory differs')
    return base.registration_reference


def build_expanded_report(root: Path, source_directory: Path, declarations: Path, directory: Path):
    root, source_directory = root.resolve(), source_directory.resolve()
    declarations, directory = declarations.resolve(), directory.resolve()
    _check(source_directory.is_relative_to(root / 'runtime') and directory.is_relative_to(root / 'runtime')
           and declarations.is_relative_to(root / 'configs') and not directory.exists(),
           'Use reviewed configurations, retained parent sources and a new destination')
    hashes = {}

    def add(path, expected=None):
        path = path.resolve()
        _check(path.is_relative_to(root) and path.is_file()
               and not any('.private' in part.lower() or part in ('.env', 'secrets', 'platform-config')
                           for part in path.relative_to(root).parts), 'Only reviewed public sources can be retained')
        name, digest = path.relative_to(root).as_posix(), _sha(path.read_bytes())
        _check(expected is None or digest == expected, 'A retained source digest changed')
        _check(name not in hashes or hashes[name] == digest, 'Conflicting source bytes')
        hashes[name] = digest
        return name

    parent_manifest = json.loads((source_directory / 'manifest.json').read_bytes())
    _check(parent_manifest['schema_version'] == 'evaluation-input-manifest-v1', 'Unsupported parent report manifest')
    for item in parent_manifest['inputs']:
        add(root / item['path'], item['sha256'])
    catalog = json.loads(declarations.read_bytes())
    _check(catalog.get('checker_id') == MULTICAP_ADAPTER, 'No registered formal source adapter')
    supplement = catalog['lifecycle_supplement']
    snapshot_manifest = json.loads((root / supplement['snapshot_manifest']).read_bytes())
    for item in snapshot_manifest['inputs']:
        add(root / item['path'], item['sha256'])
    add(root / snapshot_manifest['snapshot']['path'], snapshot_manifest['snapshot']['sha256'])
    add(root / supplement['snapshot_manifest'])
    for name in catalog['source_documents']:
        add(root / name)
    for capability in catalog['capabilities']:
        for group in capability['declaration_groups']:
            for name in group['source_references']:
                add(root / name)
    add(root / ADR)
    origin = {'schema_version': SCHEMA, 'adapter': MULTICAP_ADAPTER,
        'analysis_mode': 'retrospective-expanded-scope', 'source_report': add(source_directory / 'report.json'),
        'source_manifest': add(source_directory / 'manifest.json'), 'declarations': add(declarations)}
    directory.mkdir(parents=True, exist_ok=False)
    _write(directory / ORIGIN, origin)
    add(directory / ORIGIN)
    base, catalog, assessment = _origin(SwapEvidence(root, hashes), origin)
    report = EvaluationReport(policy_version=MULTICAP_POLICY_VERSION, candidate_key=base.candidate_key,
        name=base.name, registration_reference=base.registration_reference, generated_at=datetime.now(timezone.utc),
        scope=catalog['scope'], scope_exclusions=catalog['scope_exclusions'], evaluation_window=_window(assessment),
        approach=APPROACH, samples=base.samples, capabilities=base.capabilities, shared_assessment=assessment,
        source_references=sorted(hashes), limitations=_limitations(base))
    _write(directory / 'manifest.json', {'schema_version': 'evaluation-input-manifest-v1',
        'implementation_note': {'path': ADR, 'sha256': hashes[ADR]},
        'inputs': [{'path': name, 'sha256': digest} for name, digest in sorted(hashes.items())]})
    _write(directory / 'report.json', report.model_dump(mode='json'))
    from reputation_platform.evaluation_report import render_evaluation_report
    with (directory / 'report.html').open('x', encoding='utf-8', newline='\n') as stream:
        stream.write(render_evaluation_report(report))
    return report
