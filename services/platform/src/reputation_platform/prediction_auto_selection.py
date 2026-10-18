"""Build the existing prediction selection contract from authenticated local sources."""

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re

from reputation_core.admission import AdmissionCheck, AdmissionReport, CandidateRecord, CheckCode, Verdict, assess_candidate
from reputation_core.application import normalize_reference
from reputation_core.claims import BusinessClaim, ClaimCitation, DeclarationAnalysis, SourceDocument, validate_analysis
from reputation_core.planning import PredictionHistoryDescriptor, prediction_tool_supported, select_prediction_plan
from reputation_platform.mech_task_evidence import _catalog
from reputation_platform.mech_task_identity import verify_mech_identity
from reputation_platform.model_analysis import prediction_tool_descriptors
from reputation_platform.prediction_evidence import PredictionProfile
from reputation_platform.prediction_report import RetainedEvidence


def _business_quote(tool, text: str) -> str | None:
    # A JSON escape is not the literal description text required by source citations.
    for fragment in re.findall(r'[^"\\\r\n]+', tool.description):
        for quote in [*re.split(r'(?<=[.!?])\s+', fragment), fragment]:
            quote = quote.strip()
            if quote and quote in text and prediction_tool_supported(tool.model_copy(update={'description': quote})):
                return quote
    return None


def _history_source(reader: RetainedEvidence, bundle: dict, operations: set[str]):
    for qualification in bundle.get('qualifications', []):
        content = qualification.get('input')
        if not isinstance(content, dict):
            continue
        try:
            digest = qualification['hint']['request']['marketplaceRequest']['ipfsHashBytes']
            actual = reader.content(content, digest, 'metadata.json')
            context = actual.get('request_context') if isinstance(actual, dict) else None
            if (not isinstance(context, dict) or context.get('type') != 'omen'
                or not isinstance(context.get('market_id'), str) or not context['market_id'].strip()
                or actual.get('tool') not in operations or not isinstance(actual.get('prompt'), str)
                or not all(field in actual['prompt'] for field in ('p_yes', 'p_no'))):
                continue
            return content['response_file'], actual
        except (ValueError, KeyError, TypeError, AttributeError, OSError):
            continue
    return None


def write_auto_selection(registration: dict, evidence, bundle: dict, catalog: dict,
                         catalog_proof: dict, *, run: Path) -> Path | None:
    """Write source-backed selection materials; insufficient declarations/inputs return None."""
    root = evidence.root.resolve()
    run = (root / run).resolve()
    if (not run.is_relative_to(root / 'runtime') or run == root / 'runtime'
        or any(part.lower() in {'secrets', 'platform-config'} or '.private' in part.lower() for part in run.parts)):
        raise ValueError('Automatic selection output must be a public runtime directory')
    profile = PredictionProfile(**bundle['profile'])
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*', profile.candidate_key):
        raise ValueError('Candidate key cannot be used as a local material filename')
    if (registration['candidate_key'] != profile.candidate_key
        or normalize_reference(registration['canonical']) != profile.registration_reference):
        raise ValueError('Automatic selection and history belong to different registered candidates')
    reader = RetainedEvidence(root)
    reader.inputs = evidence.inputs
    for reference in bundle['inputs']:
        reader.remember(reference['path'], reference['sha256'])
    for field in ('plan_reference', 'profile_reference'):
        if bundle.get(field):
            reference = bundle[field]
            reader.remember(reference['path'], reference['sha256'])
    identity = verify_mech_identity(reader, bundle, profile.registration_reference)
    actual_catalog, _ = _catalog(reader, identity, {}, catalog_proof)
    if actual_catalog != catalog:
        raise ValueError('Automatic selection catalog differs from its registered original response')
    observation, raw = reader.observation(catalog_proof['evidence'], url=catalog_proof['url'], method='GET')
    text = raw.decode('utf-8')
    if json.loads(text) != catalog:
        raise ValueError('Tool catalog must be the actual original JSON document')
    observation_name = next(item['path'] for item in catalog_proof['evidence']
                            if item['path'].endswith('.observation.json'))
    response = (reader.path(observation_name).parent / observation.response_file).relative_to(root).as_posix()
    source = SourceDocument(source_id='registered-tool-catalog', url=catalog_proof['url'],
        raw_sha256=hashlib.sha256(raw).hexdigest(), projection_sha256=hashlib.sha256(text.encode('utf-8')).hexdigest(), text=text)
    tools, claims = prediction_tool_descriptors(catalog), []
    for tool in tools:
        if not prediction_tool_supported(tool):
            continue
        quote = _business_quote(tool, text)
        if quote is None:
            continue
        metadata = catalog['toolMetadata'][tool.operation]
        claims.append(BusinessClaim(claim_id='tool-' + hashlib.sha256(tool.operation.encode('utf-8')).hexdigest()[:24],
            operation=tool.operation, description=tool.description,
            inputs=[json.dumps(metadata['input'], ensure_ascii=False)],
            outputs=[json.dumps(metadata['output'], ensure_ascii=False)], constraints=[], access='unknown',
            citations=[ClaimCitation(source_id=source.source_id, quote=quote)]))
    if not claims:
        return None
    analysis = validate_analysis(DeclarationAnalysis(claims=claims,
        gaps=['声明由实际工具目录确定性提取；未调用模型，未据声明证明业务结果、费用或历史履约。']), [source])
    history = _history_source(reader, bundle, {claim.operation for claim in claims})
    if history is None:
        return None
    history_file, actual_input = history
    facts = [profile.registration_source, response, history_file]
    history_count = len({slot['market'] for slot in bundle['plan']['slots'] if slot.get('request_id') and slot.get('market')})
    checks = [
        AdmissionCheck(code=CheckCode.REGISTRATION, status=Verdict.PASS,
            explanation='原始注册表、桥映射和tokenURI文档已绑定当前完整注册身份。', evidence=facts[:1]),
        AdmissionCheck(code=CheckCode.FUNCTIONAL_DECLARATION, status=Verdict.PASS,
            explanation='真实工具描述有连续可核对的预测业务引文，且输入输出字段符合当前方案。', evidence=[response]),
        AdmissionCheck(code=CheckCode.SERVICE_INTERFACE, status=Verdict.UNKNOWN,
            explanation='已取得公开工具目录和历史输入；未执行新的推理任务或核验其访问授权。', evidence=[response, history_file]),
        AdmissionCheck(code=CheckCode.INDEPENDENT_ORACLE, status=Verdict.UNKNOWN,
            explanation='实际Omen输入已定位；各问题的题干、选项和有效最终结算须由报告逐项重验。', evidence=[history_file]),
        AdmissionCheck(code=CheckCode.EXECUTION_BINDING, status=Verdict.PASS,
            explanation='原始固定区块getter核实当前Mech、服务、注册映射及operator；历史执行控制另逐任务核验。',
            evidence=sorted(reader.inputs)),
        AdmissionCheck(code=CheckCode.EXECUTION_HISTORY, status=Verdict.UNKNOWN,
            explanation=f'原计划含{history_count}个非空不同市场槽；不把计划数量、资格副本或声明当成完整履约证明。',
            evidence=[bundle['plan_reference']['path'], history_file]),
    ]
    candidate = CandidateRecord(key=profile.candidate_key, name=registration['name'],
        registration_reference=profile.registration_reference, source_urls=[source.url], checks=checks,
        next_actions=['保留原14槽，分别复核七个功能问题和另外七个履约问题；缺项保持UNKNOWN。',
                      '另采新的十次公开历史文件访问；不足门槛不生成综合分。'])
    descriptor = PredictionHistoryDescriptor(candidate_key=candidate.key,
        claim_ids=[claim.claim_id for claim in claims], tools=tools, chain_id=profile.chain_id,
        protocol='olas-mech-marketplace', metadata_source_id=source.source_id, metadata_source_file=response,
        input_format=catalog.get('inputFormat'), output_format=catalog.get('outputFormat'), published_mech=profile.mech,
        service_id=str(profile.service_id), history_shape='omen-binary-request-v1', history_source_file=history_file,
        history_tool=actual_input['tool'], history_context_type=actual_input['request_context']['type'],
        history_market=actual_input['request_context']['market_id'], history_prompt=actual_input['prompt'])
    selection = select_prediction_plan(analysis, candidate, descriptor)
    if selection.status != 'SELECTED':
        return None
    for name in ('docs/adr/0008-prediction-history-policy.md', 'docs/adr/0013-automatic-prediction-attachment.md'):
        reader.remember(name)
    run.mkdir(parents=True, exist_ok=True)

    def save(name: str, value) -> dict:
        path = run / name
        with path.open('x', encoding='utf-8') as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
        relative = path.relative_to(root).as_posix()
        reader.remember(relative)
        return {'path': relative, 'sha256': reader.inputs[relative]}

    now = datetime.now(timezone.utc)
    save(candidate.key + '.sources.json', [source.model_dump(mode='json')])
    save(candidate.key + '.analysis.json', analysis.model_dump(mode='json'))
    admission = AdmissionReport(assessed_at=now, candidates=[assess_candidate(candidate)])
    save('admission-report.json', admission.model_dump(mode='json'))
    inputs = [{'path': name, 'sha256': digest} for name, digest in sorted(reader.inputs.items())]
    outputs = [save('descriptor.json', descriptor.model_dump(mode='json')),
               save('selection.json', selection.model_dump(mode='json'))]
    save('manifest.json', {'schema_version': 'prediction-auto-selection-v1', 'created_at': now.isoformat(),
        'completed_at': now.isoformat(), 'canonical': profile.registration_reference,
        'policy_id': selection.policy_id, 'network_requests': 0, 'model_calls': 0, 'scores_computed': False,
        'history_evidence_scope': '实际输入结构用于选方案，资格和完整履约仍须从原件复核。',
        'catalog': catalog_proof, 'inputs': inputs, 'outputs': outputs})
    return run
