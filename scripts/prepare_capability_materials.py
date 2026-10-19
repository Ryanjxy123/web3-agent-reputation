"""Prepare deduplicated business text and provenance mappings; no model calls or categories."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import secrets
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'packages/core/src')]
from reputation_core import ProbeObservation


def encoded(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def sha(text: str | bytes) -> str:
    return hashlib.sha256(text.encode('utf-8') if isinstance(text, str) else text).hexdigest()


METRIC_KEYS = {
    'score', 'scores', 'totalscore', 'qualityscore', 'popularityscore', 'activityscore', 'walletscore',
    'freshnessscore', 'healthscore', 'rank', 'networkrank', 'trust', 'trustscore', 'health', 'healthstatus',
    'reputation', 'reputationscore', 'accuracy', 'analytics', 'performancemetrics', 'successrate',
    'capabilityproposals', 'semanticdraftcapabilities', 'existingevaluationscopes', 'quality',
}


def business_value(value):
    """Drop descriptive metadata metrics; retain actual input/output JSON Schema unchanged."""
    if isinstance(value, list):
        return [business_value(item) for item in value]
    if not isinstance(value, dict):
        return value
    return {key: item if key in {'schema', 'inputSchema', 'outputSchema', 'parameters'} else business_value(item)
            for key, item in value.items() if re.sub(r'[^a-z0-9]', '', key.casefold()) not in METRIC_KEYS}


def pointer(value, location: str):
    if location == '':
        return value
    if not location.startswith('/'):
        raise ValueError('A JSON locator must be an RFC 6901 pointer')
    for part in location[1:].split('/'):
        part = part.replace('~1', '/').replace('~0', '~')
        value = value[int(part)] if isinstance(value, list) else value[part]
    return value


def prepare_capability_materials(record_files: list[Path], root: Path = ROOT) -> dict:
    """Return {sources, bindings, agents, summary, inputs} from inventory/corpus records.

    sources are model-ready business text only; bindings retain identity and exact source provenance.
    source_id hashes original business text; projection_sha256 also binds every retained context variant.
    """
    root = root.resolve()
    inputs, raw_cache, units, bindings, agents = {}, {}, {}, [], {}
    counts = {'input_records': 0, 'original_claims': 0, 'original_declarations': 0,
              'unprojected_declarations': 0}

    def retain(name: str | Path, expected: str | None = None) -> Path:
        path = (root / name).resolve()
        if (not any(path.is_relative_to(root / base) for base in ('runtime', 'configs')) or not path.is_file()
            or any(part.lower() in {'secrets', 'platform-config'} or '.private' in part.lower() for part in path.parts)):
            raise ValueError('Only retained public runtime sources and public configuration inputs may be projected')
        if path not in raw_cache:
            raw_cache[path] = path.read_bytes()
        body = raw_cache[path]
        digest = sha(body)
        if expected is not None and digest != expected:
            raise ValueError('A retained projection source changed: ' + str(name))
        inputs[path.relative_to(root).as_posix()] = digest
        return path

    def read(name: str | Path, expected: str | None = None):
        return json.loads(raw_cache[retain(name, expected)])

    def verify_citation(citation: dict) -> dict:
        raw_file = retain(citation['raw_path'], citation['raw_sha256'])
        observation_file = retain(citation['observation_path'])
        observed = ProbeObservation.model_validate_json(raw_cache[observation_file])
        if (observed.url != citation['url'] or observed.http_status != 200 or observed.error_kind
            or not observed.body_complete or observed.response_sha256 != citation['raw_sha256']
            or not observed.response_file or (observation_file.parent / observed.response_file).resolve() != raw_file):
            raise ValueError('Citation differs from its complete retained HTTP source')
        if citation.get('projection_path'):
            projected = retain(citation['projection_path'], citation['projection_sha256'])
            if not isinstance(citation['quote'], str) or citation['quote'] not in raw_cache[projected].decode('utf-8'):
                raise ValueError('Claim citation is absent from the digest-bound model projection')
        elif citation.get('json_pointer') is not None:
            actual = pointer(json.loads(raw_cache[raw_file]), citation['json_pointer'])
            if actual != citation['quote']:
                raise ValueError('Directory declaration differs from its exact source JSON value')
        else:
            raise ValueError('A business citation requires a retained projection or an exact JSON locator')
        return {key: citation.get(key) for key in ('source_id', 'url', 'json_pointer', 'quote', 'raw_path',
            'raw_sha256', 'projection_path', 'projection_sha256', 'observation_path')}

    def add(text: str, context: dict, record: dict, record_ref: dict, location: str,
            citations: list[dict], original_claim: dict | None = None):
        if not text.strip():
            return
        digest = sha(text)
        source_id = 'business-' + digest
        unit = units.setdefault(source_id, {'source_id': source_id, 'original_text': text,
                                           'original_text_sha256': digest, 'contexts': {}})
        context = business_value(context)
        context_hash = sha(encoded(context))
        unit['contexts'][context_hash] = context
        checked = [verify_citation(item) for item in citations]
        if not checked:
            raise ValueError('Business material needs at least one authentic retained source')
        binding = {'source_id': source_id, 'context_sha256': context_hash,
            'registration_reference': record['registration_reference'], 'candidate_key': record.get('candidate_key'),
            'record_source': record_ref, 'record_json_pointer': location, 'source_citations': checked}
        if original_claim is not None:
            binding['previous_validated_extraction'] = {key: original_claim[key] for key in
                ('claim_id', 'operation', 'description', 'inputs', 'outputs', 'constraints', 'access')}
        bindings.append(binding)
        agents[record['registration_reference']]['source_ids'].add(source_id)

    for supplied in record_files:
        record_file = retain(supplied)
        manifest_file = record_file.parent / 'corpus-manifest.json'
        if not manifest_file.is_file():
            manifest_file = record_file.parent / 'manifest.json'
        retained_manifest = read(manifest_file)
        for item in retained_manifest.get('inputs', []):
            retain(item['path'], item['sha256'])
        if retained_manifest.get('request_manifest'):
            retain(retained_manifest['request_manifest']['path'], retained_manifest['request_manifest']['sha256'])
        records_name = record_file.relative_to(root).as_posix()
        output_refs = [item for item in retained_manifest.get('outputs', [])
                       if Path(item['path']).as_posix().replace('\\', '/') == records_name]
        if len(output_refs) != 1:
            raise ValueError('Records must have a unique retained output digest')
        retain(record_file, output_refs[0]['sha256'])
        document = read(record_file)
        if document.get('schema_version') not in {'capability-inventory-v1', 'capability-corpus-v1'}:
            raise ValueError('Use existing capability inventory or public corpus records')
        record_ref = {'path': records_name, 'sha256': inputs[records_name]}
        for index, record in enumerate(document['records']):
            canonical = record['registration_reference']
            if not re.fullmatch(r'eip155:[0-9]+:0x[0-9a-f]{40}:[0-9]+', canonical):
                raise ValueError('Every Agent needs its actual canonical registration identity')
            if document['schema_version'] == 'capability-corpus-v1':
                matched = False
                for source in record['source_documents']:
                    body = read(source['raw_path'], source['raw_sha256'])
                    row = pointer(body, source.get('json_pointer', ''))
                    if isinstance(row, dict) and all(key in row for key in ('chain_id', 'contract_address', 'token_id')):
                        actual = f"eip155:{int(row['chain_id'])}:{row['contract_address'].lower()}:{int(row['token_id'])}"
                        if actual != canonical:
                            raise ValueError('Indexed canonical identity differs from its original source row')
                        matched = True
                if not matched:
                    raise ValueError('Public corpus identity has no exact original directory row')
            agent = agents.setdefault(canonical, {'registration_reference': canonical, 'candidate_keys': set(),
                'identity_statuses': set(), 'record_sources': [], 'source_ids': set()})
            if record.get('candidate_key'):
                agent['candidate_keys'].add(record['candidate_key'])
            agent['identity_statuses'].add(record['identity_status'])
            agent['record_sources'].append({**record_ref, 'json_pointer': f'/records/{index}'})
            counts['input_records'] += 1
            interfaces = business_value({key: record[key] for key in ('services', 'published_interfaces') if record.get(key)})
            interface_citations = record.get('interface_source_citations', [])
            if interfaces and not interface_citations:
                raise ValueError('Declared interfaces require exact retained source citations')
            for number, claim in enumerate(record.get('claims', [])):
                counts['original_claims'] += 1
                schema = claim.get('source_schema')
                context = {'declared_operation': claim['operation'], 'declared_interfaces': interfaces}
                if schema:
                    context['original_tool_schema'] = schema
                else:
                    context['previous_extraction'] = {key: claim[key] for key in ('inputs', 'outputs', 'constraints', 'access')}
                add(claim['business_original'], context, record, record_ref, f'/records/{index}/claims/{number}',
                    claim['source_citations'] + interface_citations, original_claim=claim)
            for number, declaration in enumerate(record.get('declarations', [])):
                counts['original_declarations'] += 1
                if declaration['kind'] not in {'description', 'skills', 'capabilities', 'tools'}:
                    counts['unprojected_declarations'] += 1
                    continue
                original = declaration.get('original_text', declaration.get('original_value'))
                sanitized = business_value(original)
                if sanitized in (None, '', [], {}):
                    counts['unprojected_declarations'] += 1
                    continue
                text = sanitized if isinstance(sanitized, str) else encoded(sanitized)
                add(text, {'declaration_kind': declaration['kind'], 'declared_interfaces': interfaces},
                    record, record_ref, f'/records/{index}/declarations/{number}', declaration['source_citations'] + interface_citations)
    sources = []
    for source_id, unit in sorted(units.items()):
        contexts = [unit['contexts'][digest] for digest in sorted(unit['contexts'])]
        text = json.dumps({'business_original': unit['original_text'], 'declaration_contexts': contexts},
                          ensure_ascii=False, sort_keys=True, indent=2)
        sources.append({'source_id': source_id, 'original_text_sha256': unit['original_text_sha256'],
                        'text': text, 'projection_sha256': sha(text), 'context_count': len(contexts)})
    agent_records = [{**agent, 'candidate_keys': sorted(agent['candidate_keys']),
                      'identity_statuses': sorted(agent['identity_statuses']), 'source_ids': sorted(agent['source_ids'])}
                     for _, agent in sorted(agents.items())]
    summary = {**counts, 'distinct_registered_agents': len(agent_records), 'unique_business_sources': len(sources),
        'business_identity_bindings': len(bindings), 'agents_without_business_sources': sum(not agent['source_ids'] for agent in agent_records),
        'projection_characters': sum(len(source['text']) for source in sources),
        'network_requests': 0, 'model_requests': 0, 'scores_computed': False,
        'classification_performed': False, 'keyword_draft_used': False}
    return {'sources': sources, 'bindings': bindings, 'agents': agent_records, 'summary': summary,
            'inputs': [{'path': path, 'sha256': digest} for path, digest in sorted(inputs.items())]}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--records', type=Path, nargs='+', required=True)
    args = parser.parse_args()
    prepared = prepare_capability_materials(args.records)
    now = datetime.now(timezone.utc)
    run = ROOT / 'runtime' / f'capability-materials-{now:%Y%m%dT%H%M%SZ}-{secrets.token_hex(4)}'
    run.mkdir()
    output_values = {
        'sources.json': {'schema_version': 'capability-business-sources-v1', 'sources': prepared['sources']},
        'bindings.json': {'schema_version': 'capability-business-bindings-v1', 'bindings': prepared['bindings'], 'agents': prepared['agents']},
        'summary.json': prepared['summary'],
    }
    for name, value in output_values.items():
        with (run / name).open('x', encoding='utf-8') as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
    manifest = {'created_at': now.isoformat(), 'purpose': 'Deduplicated business text for later source-backed semantic classification',
        **prepared['summary'], 'inputs': prepared['inputs'],
        'source_id_rule': 'business- + SHA256(exact original business UTF-8 text); context changes also change projection_sha256',
        'excluded': ['keyword capability proposals', 'previous evaluation scopes and values', 'directory scores/rank/trust/health',
                     'Agent names, owners and provider guesses as model capability evidence', 'directory preliminary quality labels'],
        'outputs': [{'path': path.relative_to(ROOT).as_posix(), 'sha256': sha(path.read_bytes())}
                    for path in (run / name for name in output_values)]}
    with (run / 'manifest.json').open('x', encoding='utf-8') as stream:
        json.dump(manifest, stream, ensure_ascii=False, indent=2)
    print(json.dumps({'evidence_directory': run.relative_to(ROOT).as_posix(), **prepared['summary']}, ensure_ascii=False))


if __name__ == '__main__':
    main()
