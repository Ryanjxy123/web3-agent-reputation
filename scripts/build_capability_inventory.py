"""Rebuild capability-analysis inputs from retained, cited declaration assets; offline only."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import secrets
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'packages/core/src'), str(ROOT / 'services/platform/src')]

from analyze_declarations import sources_from_review
from reputation_core import DeclarationAnalysis, ProbeObservation, SourceDocument, validate_analysis
from reputation_platform.model_analysis import ENDPOINT, catalog_operations, parse_declarations

PAIRS = [
    ('runtime/model-review-20261017T182601Z-ccb0ed3d', 'runtime/model-reviewed-20261018T045116Z-10a85dc4'),
    ('runtime/model-review-20261018T065247Z-d2d75c1a', 'runtime/model-analysis-20261018T065302Z-e234ef65'),
    ('runtime/model-review-20261018T065549Z-7efbdf07', 'runtime/model-analysis-20261018T065605Z-293a4039'),
    ('runtime/model-review-20261018T070719Z-920e0463', 'runtime/model-analysis-20261018T070738Z-6217d1b6'),
]
ADMISSIONS = [
    'runtime/admission-report-20261017T182038Z-f504c54e/admission-report.json',
    'runtime/admission-report-20261018T063130Z-e7ee947b/admission-report.json',
    'runtime/admission-report-20261018T071049Z-f95cbda3/admission-report.json',
]
REPORTS = [
    'runtime/evaluation-report-20261018T060340Z-4c27cea3',
    'runtime/evaluation-report-20261018T074802Z-2378ca3d',
    'runtime/evaluation-report-20261018T074803Z-c4f9fbe0',
]
INPUTS = {}


def retain(value: str | Path, expected: str | None = None) -> Path:
    path = (ROOT / value).resolve()
    if (not any(path.is_relative_to(ROOT / base) for base in ('runtime', 'configs'))
        or not path.is_file() or any(part.lower() in {'secrets', 'platform-config'}
                                    or '.private' in part.lower() for part in path.parts)):
        raise ValueError('Inventory inputs must be retained public source files')
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if expected is not None and digest != expected:
        raise ValueError('Retained source changed: ' + str(value))
    INPUTS[path.relative_to(ROOT).as_posix()] = digest
    return path


def load(value: str | Path, expected: str | None = None):
    return json.loads(retain(value, expected).read_bytes())


def reference(path: Path) -> dict:
    retain(path)
    name = path.relative_to(ROOT).as_posix()
    return {'path': name, 'sha256': INPUTS[name]}


def observation(value: str | Path, *, url: str | None = None) -> tuple[ProbeObservation, Path]:
    path = retain(value)
    observed = ProbeObservation.model_validate_json(path.read_bytes())
    if (observed.http_status != 200 or observed.error_kind or not observed.body_complete
        or not observed.response_file or (url is not None and observed.url != url)):
        raise ValueError('Source observation is incomplete or identifies another document')
    response = (path.parent / observed.response_file).resolve()
    if response.parent != path.parent:
        raise ValueError('Source response escaped its retained observation directory')
    retain(response, observed.response_sha256)
    return observed, response


def manifest(directory: Path) -> dict:
    value = load(directory / 'manifest.json')
    for item in value.get('inputs', []):
        if 'path' in item:
            retain(item['path'], item['sha256'])
    return value


def source_details(review_run: Path, key: str, source: SourceDocument) -> tuple[dict, dict | None]:
    review = load(review_run / 'review.json')
    item = next(item for item in review['documents'] if item['candidate'] == key)
    raw_file = retain(item['raw_file'], source.raw_sha256)
    projected = retain(review_run / item['projection_file'], source.projection_sha256)
    observed_path = raw_file.with_name(raw_file.name.removesuffix('.response.bin') + '.observation.json')
    observed, response = observation(observed_path, url=source.url)
    if response != raw_file:
        raise ValueError('Review raw document differs from its observation response')
    document = None
    try:
        document = json.loads(source.text)
    except ValueError:
        semantic_projection = 'REVIEWED_TEXT_PROJECTION_HASH_BOUND; raw HTML retained, omissions not independently re-reviewed here'
    else:
        if document != json.loads(raw_file.read_bytes()):
            raise ValueError('JSON projection changed the source document content')
        semantic_projection = 'FULL_JSON_SEMANTIC_EQUALITY'
    return {
        'source_id': source.source_id, 'url': source.url,
        'raw_path': raw_file.relative_to(ROOT).as_posix(), 'raw_sha256': source.raw_sha256,
        'projection_path': projected.relative_to(ROOT).as_posix(), 'projection_sha256': source.projection_sha256,
        'observation_path': observed_path.relative_to(ROOT).as_posix(), 'observed_at': observed.observed_at.isoformat(),
        'body_complete': True, 'projection_integrity': semantic_projection,
        'source_authentication': 'HTTP_OBSERVATION_AND_DIGEST; this inventory does not newly verify IPFS DAG or business truth',
    }, document


def validated_asset(review_run: Path, analysis_run: Path, key: str, expected_sources: list[SourceDocument]):
    analyzed_manifest = manifest(analysis_run)
    original_run = ROOT / analyzed_manifest.get('source_run', analysis_run.relative_to(ROOT).as_posix())
    original_manifest = manifest(original_run)
    if (ROOT / original_manifest['material_directory']).resolve() != review_run:
        raise ValueError('Model run refers to a different source review')
    saved_sources = [SourceDocument.model_validate(item) for item in load(original_run / f'{key}.sources.json')]
    if saved_sources != expected_sources:
        raise ValueError('Model inputs differ from digest-bound source review')
    observed, response = observation(original_run / f'analysis-{key}.observation.json', url=ENDPOINT)
    request = json.loads(observed.request_json)
    if (observed.method != 'POST' or request.get('tools') != [] or request.get('tool_choice') != 'none'
        or json.loads(request['input']) != {'sources': [source.model_dump() for source in expected_sources]}):
        raise ValueError('Retained declaration request did not use these exact source documents without tools')
    derived, rejected = parse_declarations(load(response), expected_sources)
    stored = validate_analysis(DeclarationAnalysis.model_validate(load(analysis_run / f'{key}.analysis.json')), expected_sources)
    if derived != stored:
        raise ValueError('Accepted analysis differs from its retained provider response: ' + key)
    return stored, rejected


def identity(key: str, admissions: dict) -> tuple[str, dict, list[dict]]:
    entry = admissions[key]
    registration = next(item for item in entry['checks'] if item['code'] == 'registration')
    references, bridge_mappings = [], []
    for name in registration['evidence']:
        if name.startswith('runtime/'):
            path = retain(name)
            references.append(reference(path))
            if path.name.endswith('.observation.json'):
                observed, response = observation(path)
                references.append(reference(response))
                if observed.method == 'POST':
                    request, body = json.loads(observed.request_json), load(response)
                    if (body.get('jsonrpc') != '2.0' or body.get('id') != request['id']
                        or body.get('error') or body.get('result') is None):
                        raise ValueError('Identity source has no matching successful original RPC envelope')
                    if request['method'] == 'eth_call':
                        call = request['params'][0]
                        if (call.get('to', '').lower() == '0x6e8f740f23f07ce129daa59786926feca8c2d2f3'
                            and call.get('data', '').startswith('0xe0e3e127')):
                            bridge_mappings.append((int(call['data'][10:], 16), int(body['result'], 16)))
    if key == 'degenai':
        catalog = load('runtime/candidate-check-20261017T175652Z-f876ebbc/catalog-degen.response.bin')
        canonical = f"eip155:{int(catalog['chain_id'])}:{catalog['contract_address'].lower()}:{int(catalog['token_id'])}"
    elif key == 'brain-defi':
        profile = load('configs/pilots/brain-defi-liquidity-v1.json')
        canonical = f"eip155:{profile['chain_id']}:{profile['registry'].lower()}:{profile['agent_id']}"
    else:
        canonical = entry['registration_reference']
    if not re.fullmatch(r'eip155:[0-9]+:0x[0-9a-f]{40}:[0-9]+', canonical):
        raise ValueError('A canonical registration reference is required: ' + key)
    if key.startswith('olas-'):
        ids = {(service, agent) for service, agent in bridge_mappings}
        if len(ids) != 1 or next(iter(ids))[1] != int(canonical.rsplit(':', 1)[1]):
            raise ValueError('Actual bridge mapping differs from the canonical Agent identity')
    return canonical, registration, references


def schema_for(document: dict | None, operation: str) -> tuple[dict | None, str | None, str | None]:
    if not isinstance(document, dict):
        return None, None, None
    tools = document.get('toolMetadata', {})
    if isinstance(tools, dict) and operation in tools:
        return tools[operation], '/toolMetadata/' + operation.replace('~', '~0').replace('/', '~1'), 'tool'
    for index, item in enumerate(document.get('capabilities', [])):
        if isinstance(item, dict) and item.get('id') == operation:
            return item, f'/capabilities/{index}', 'capability'
    return None, None, None


def existing_scopes() -> dict:
    by_key = {}
    for name in REPORTS:
        run = ROOT / name
        report, retained_manifest = load(run / 'report.json'), load(run / 'manifest.json')
        if report['scores']['status'] != 'COMPLETE':
            raise ValueError('Expected an actually completed retained report')
        scope = {'policy_id': report.get('policy_version', 'liquidity-history-v1'), 'scope': report['scope'],
                 'report_file': (run / 'report.json').relative_to(ROOT).as_posix(),
                 'coverage_status': 'EXISTING_COMPLETE_SCOPED_REPORT', 'functional_operations': [], 'behavioral_operations': []}
        if scope['policy_id'] == 'prediction-history-v1':
            bundle_file = ROOT / retained_manifest['history_run'] / 'bundle.json'
            expected = next(item['sha256'] for item in retained_manifest['inputs']
                            if item['path'] == bundle_file.relative_to(ROOT).as_posix())
            bundle = load(bundle_file, expected)
            scope['functional_operations'] = sorted({task['input']['payload']['tool'] for task in bundle['tasks']
                                                     if task['purpose'] == 'functional'})
            scope['behavioral_operations'] = sorted({task['input']['payload']['tool'] for task in bundle['tasks']
                                                     if task['purpose'] == 'behavioral'})
        else:
            scope['functional_operations'] = ['Increase']
            scope['behavioral_operations'] = ['Increase']
        scope['limitation'] = 'Only this report scope and sampled operations are evidenced; other claims do not inherit COMPLETE.'
        by_key.setdefault(report['candidate_key'], []).append(scope)
    return by_key


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-pair', nargs=2, action='append', metavar=('REVIEW_RUN', 'ANALYSIS_RUN'))
    args = parser.parse_args()
    admissions = {}
    for name in ADMISSIONS:
        for candidate in load(name)['candidates']:
            admissions[candidate['key']] = {**candidate, 'snapshot_path': name}
    scopes = existing_scopes()
    records, links = [], []
    for review_name, analysis_name in args.source_pair or PAIRS:
        review_run, analysis_run = (ROOT / review_name).resolve(), (ROOT / analysis_name).resolve()
        retain(review_run / 'review.json')
        if (review_run / 'manifest.json').is_file():
            manifest(review_run)
        for key, sources in sources_from_review(review_run, None):
            analysis, rejected = validated_asset(review_run, analysis_run, key, sources)
            documents, parsed = [], {}
            for source in sources:
                document, content = source_details(review_run, key, source)
                documents.append(document)
                parsed[source.source_id] = content
            canonical, registration, identity_refs = identity(key, admissions)
            provider = {'status': 'UNKNOWN', 'name': None, 'evidence': [], 'claimed_names': []}
            for source in sources:
                doc = parsed[source.source_id]
                operator = doc.get('operator') if isinstance(doc, dict) else None
                if isinstance(operator, dict) and isinstance(operator.get('name'), str) and operator['name'].strip():
                    provider = {'status': 'DECLARED', 'name': operator['name'], 'claimed_names': [operator['name']],
                                'evidence': [{'source_id': source.source_id, 'json_pointer': '/operator/name',
                                              'quote': operator['name'], 'raw_sha256': source.raw_sha256}],
                                'limitation': 'Source-declared operator name; not independent company or historical executor verification.'}
            catalog = catalog_operations(sources)
            claims = []
            for claim in analysis.claims:
                citations, business_text, source_schema, pointer = [], [], None, None
                for citation in claim.citations:
                    source = next(item for item in sources if item.source_id == citation.source_id)
                    info = next(item for item in documents if item['source_id'] == source.source_id)
                    schema, location, _ = schema_for(parsed[source.source_id], claim.operation)
                    source_schema, pointer = schema or source_schema, location or pointer
                    citations.append({**citation.model_dump(), 'url': source.url, 'json_pointer': location,
                        'raw_sha256': source.raw_sha256, 'projection_sha256': source.projection_sha256,
                        'raw_path': info['raw_path'], 'projection_path': info['projection_path'],
                        'observation_path': info['observation_path']})
                    business_text.append(schema['description'] if schema and isinstance(schema.get('description'), str)
                                         else citation.quote)
                semantic_text = '\n'.join(dict.fromkeys(business_text))
                covered = [item for item in scopes.get(key, []) if claim.operation in item['functional_operations']]
                behavior_covered = [item for item in scopes.get(key, []) if claim.operation in item['behavioral_operations']]
                claim_record = {**claim.model_dump(exclude={'citations'}), 'source_citations': citations,
                    'validation': 'REPARSED_PROVIDER_RESPONSE_AND_EXACT_SOURCE_CITATIONS_AND_CATALOG',
                    'semantic_review': 'SOURCE_BACKED_ANALYSIS_INPUT; modeled summaries and draft clusters are not independent business verification',
                    'business_original': semantic_text, 'source_schema': source_schema, 'schema_json_pointer': pointer,
                    'feasibility': {
                        'input_output': {'status': 'DECLARED' if claim.inputs and claim.outputs else 'UNKNOWN',
                                         'formal_schema_present': source_schema is not None,
                                         'gaps': [] if source_schema else ['只保留声明中的输入输出文字；未取得机器接口完整schema。']},
                        'authorization': {'status': 'DECLARED' if claim.access != 'unknown' else 'UNKNOWN',
                                          'declared_access': claim.access, 'constraints': claim.constraints,
                                          'gaps': ['声明价格/授权不等于平台已获调用许可；本清单不发起业务、签名或付款。']},
                        'independent_oracle': {'status': 'KNOWN_IN_EVALUATED_SCOPE' if covered else 'UNKNOWN',
                            'existing_reports': [item['report_file'] for item in covered],
                            'gaps': [] if covered else ['尚未为本项能力绑定真实输入与独立结果判据；不能借用其他工具已通过的报告。']},
                        'transaction_history': {'status': 'KNOWN_IN_EVALUATED_SCOPE' if behavior_covered else 'UNKNOWN',
                            'existing_reports': [item['report_file'] for item in behavior_covered],
                            'gaps': [] if behavior_covered else ['本项能力尚无已核对的任务级输入输出、交易及历史执行控制；当前登记映射不代表历史。']},
                    }}
                claims.append(claim_record)
                links.append({'registration_reference': canonical, 'candidate_key': key, 'claim_id': claim.claim_id,
                              'operation': claim.operation})
            content_urls = [parsed[source.source_id].get('url') for source in sources
                            if isinstance(parsed[source.source_id], dict) and parsed[source.source_id].get('url')]
            records.append({'candidate_key': key, 'registration_reference': canonical,
                'identity_status': 'REGISTERED_SNAPSHOT_VERIFIED' if registration['status'] == 'PASS' else 'INDEXED_NOT_CHAIN_VERIFIED',
                'identity_evidence': identity_refs, 'identity_limitation': registration['explanation'],
                'provider': provider, 'source_documents': documents, 'claims': claims, 'declarations': [],
                'quality': {'description_present': True, 'specific_function': 'YES',
                    'reason': '有原始业务资料、provider原始响应和逐条可回查引用；不等同于业务正确或可评分。',
                    'explicit_catalog_operations': catalog,
                    'missing_catalog_operations': sorted(set(catalog or []) - {claim.operation for claim in analysis.claims}),
                    'rejected_model_claims': rejected, 'analysis_gaps': analysis.gaps,
                    'source_complete': {'raw_http_complete': all(item['body_complete'] for item in documents),
                        'json_projection_semantically_equal': all(item['projection_integrity'] == 'FULL_JSON_SEMANTIC_EQUALITY' for item in documents),
                        'catalog_extraction_complete': (set(catalog) == {claim.operation for claim in analysis.claims}) if catalog is not None else None,
                        'limitation': 'Raw HTTP completion does not establish every business capability or implication was extracted; HTML omissions have not been independently re-reviewed here.'},
                    'full_raw_retained': True, 'declared_urls_not_probed': content_urls},
                'feasibility': {'existing_evaluation_scopes': scopes.get(key, []),
                    'prior_admission_snapshot': {'path': admissions[key]['snapshot_path'], 'checks': admissions[key]['checks']},
                    'gaps': ['早期准入是时间点快照，后续限定范围报告单列；不同能力不互相继承通过。',
                             '尚未统一验证所有业务接口、授权和独立判据；实际可测覆盖由后续分析确定。']},
                'source_runs': [review_run.relative_to(ROOT).as_posix(), analysis_run.relative_to(ROOT).as_posix()]})
    canonical_ids = [record['registration_reference'] for record in records]
    if len(canonical_ids) != len(set(canonical_ids)):
        raise ValueError('One registered Agent must occur once, regardless of claim count')
    operations = {}
    for link in links:
        operations.setdefault(link['operation'], []).append(link)
    now = datetime.now(timezone.utc)
    run = ROOT / 'runtime' / f'capability-inventory-{now:%Y%m%dT%H%M%SZ}-{secrets.token_hex(4)}'
    run.mkdir()
    output = {'schema_version': 'capability-inventory-v1', 'created_at': now.isoformat(),
        'purpose': 'Capability coverage analysis inputs; not evaluation selection or new scores', 'records': records}
    index = {'schema_version': 'capability-links-v1', 'links': links, 'exact_operations': operations,
             'limitation': 'Exact operation text is not semantic classification. Use separately source-bound semantic review; deprecated keyword drafts are not recommendation inputs.'}
    for name, value in (('records.json', output), ('capability-links.json', index)):
        with (run / name).open('x', encoding='utf-8') as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
    retained_manifest = {'created_at': now.isoformat(), 'network_requests': 0, 'model_requests': 0, 'scores_computed': False,
        'agent_count': len(records), 'claim_count': len(links), 'exact_operation_count': len(operations),
        'inputs': [{'path': name, 'sha256': digest} for name, digest in sorted(INPUTS.items())],
        'outputs': [{'path': path.relative_to(ROOT).as_posix(), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
                    for path in (run / 'records.json', run / 'capability-links.json')],
        'builder_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    with (run / 'manifest.json').open('x', encoding='utf-8') as stream:
        json.dump(retained_manifest, stream, ensure_ascii=False, indent=2)
    print(json.dumps({key: retained_manifest[key] for key in ('agent_count', 'claim_count', 'exact_operation_count',
        'network_requests', 'model_requests', 'scores_computed')}
        | {'evidence_directory': run.relative_to(ROOT).as_posix()}, ensure_ascii=False))


if __name__ == '__main__':
    main()
