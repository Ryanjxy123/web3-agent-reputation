"""Offline official public-service registration, distinct from onchain ERC8004 identity."""
import json
from pathlib import Path
from urllib.parse import quote, urlsplit
from eth_hash.auto import keccak
from reputation_core.application import normalize_reference
from reputation_core.swap import address
from reputation_platform.registration_discovery import _public_file, _configuration
from reputation_platform.swap_report import SwapEvidence, _check

SCHEMA = 'public-service-registration-proof-v1'
ACP_CONTRACT = '0x238e541bfefd82238730d00a2208e5497f1832e0'


def _https(url):
    value = urlsplit(url)
    _check(value.scheme == 'https' and value.hostname and not value.username and not value.password
           and value.port in (None, 443) and not value.fragment, 'Public service needs an explicit HTTPS URL')
    return url


def verify_public_service_identity(root, proof_path, expected_reference):
    root = Path(root).resolve()
    canonical = normalize_reference(expected_reference)
    _check(canonical == expected_reference and canonical and not canonical.startswith('eip155:'),
           'Expected a canonical official public service reference')
    proof = json.loads(_public_file(root, proof_path).read_bytes())
    _check(proof.get('schema_version') == SCHEMA and proof['canonical'] == canonical,
           'Public service proof identity/schema mismatch')
    hashes = {ref['path']: ref['sha256'] for ref in proof['source_refs']}
    _check(len(hashes) == len(proof['source_refs']), 'Duplicated public identity source')
    evidence = SwapEvidence(root, hashes)
    for path in hashes:
        evidence.raw(path)

    def http(name, url):
        observation, raw = evidence.observed(name)
        _check(observation['url'] == url and observation['method'] == 'GET'
               and observation.get('request_json') is None and observation['http_status'] == 200
               and observation['body_complete'] and not observation['error_kind'] and raw,
               'Identity requires its original complete official HTTPS GET')
        return json.loads(raw)

    endpoint = _https(proof['selected_service'])
    provider, event_verified = None, False
    if canonical.startswith('mcp-registry:'):
        _check(proof['registry_kind'] == 'mcp-registry', 'Public registry kind mismatch')
        name, version = canonical[len('mcp-registry:'):].rsplit('@', 1)
        url = 'https://registry.modelcontextprotocol.io/v0.1/servers/' + quote(name, safe='') + '/versions/' + quote(version, safe='')
        record = http(proof['registry_observation'], url)
        server = record['server']
        official = record['_meta']['io.modelcontextprotocol.registry/official']
        _check(server['name'] == name and server['version'] == version and official['status'] == 'active'
               and official.get('publishedAt') and server.get('$schema', '').startswith('https://static.modelcontextprotocol.io/schemas/'),
               'Official MCP immutable name/version/publisher record mismatch')
        services = [row['url'] for row in server.get('remotes', [])
                    if row.get('type') in ('streamable-http', 'sse')]
        _check(endpoint in services, 'MCP remote is not bound by this official registry version')
        description = server.get('description', '')
    elif canonical.startswith('acp:virtuals:'):
        _check(proof['registry_kind'] == 'virtuals-acp', 'Public registry kind mismatch')
        ident = canonical[len('acp:virtuals:'):]
        base = 'https://api.acp.virtuals.io'
        detail = http(proof['registry_observation'], base + '/agents/' + ident)['data']
        provider = address(detail['walletAddress'])
        _check(detail['id'] == ident and provider != '0x'+'0'*40, 'Official ACP UUID/provider wallet mismatch')
        offering = proof['offering']
        listed = [row for row in detail['offerings'] if row['name'] == offering]
        _check(len(listed) == 1 and listed[0]['agentId'] == ident, 'Official ACP offering is absent or ambiguous')
        services = ['https://app.virtuals.io/acp/agent/' + ident]
        _check(endpoint in services, 'ACP selected service is not its official provider UUID page')
        event = proof.get('provider_event')
        _check(event and event['chain_id'] == 8453 and address(event['contract']) == ACP_CONTRACT,
               'ACP directory alone lacks the required real Base provider event binding')
        job_id = str(event['job_id'])
        job = http(event['job_observation'], base + '/jobs/8453/' + job_id)['data']
        history = http(event['history_observation'], base + '/chats/8453/' + job_id + '/history')['entries']
        _check(job['providerId'] == ident and address(job['providerAddress']) == provider
               and str(job['onChainJobId']) == job_id and job['chainId'] == 8453 and job['description'] == offering,
               'ACP job UUID/wallet/offering differs from official registration')
        _check(all(str(row['onChainJobId']) == job_id and row['chainId'] == 8453 for row in history),
               'Provider event history mixes jobs or chains')
        submissions = [row['event'] for row in history if row.get('kind') == 'system'
                       and row.get('event', {}).get('type') == 'job.submitted']
        _check(len(submissions) == 1 and address(submissions[0]['provider']) == provider,
               'Missing unique official provider submission')
        delivery = submissions[0]
        digest = '0x' + keccak(delivery['deliverable'].encode()).hex()
        _check(digest == delivery['deliverableHash'].lower(), 'Original ACP provider delivery hash mismatch')
        from reputation_platform.unsigned_swap_report import _records, _event, SUBMITTED
        configuration = proof.get('rpc_configuration')
        _check(configuration and configuration['path'] == 'configs/generic-rpc.json'
               and hashes.get(configuration['path']) == configuration['sha256'],
               'ACP provider RPC configuration is not hash-bound operator configuration')
        allowed = {_configuration(root)['chains']['8453']['rpc_url'], 'https://mainnet.base.org'}
        for name in event['rpc_observations']:
            observation, _ = evidence.observed(name)
            _check(observation['url'] in allowed, 'Provider event RPC is not operator-trusted Base')
        records = _records(evidence, event['rpc_observations'])
        chain_reads = [row for row in records if row['method'] == 'eth_chainId' and not row['error'] and row['value']]
        _check(chain_reads and all(int(row['value'], 16) == 8453 for row in chain_reads),
               'Provider event requires successful eth_chainId=8453 evidence')
        log, header = _event(records, ACP_CONTRACT, SUBMITTED, job_id, provider)
        _check(log['data'].lower() == digest and int(header['number'], 16) == int(log['blockNumber'], 16),
               'Real canonical provider event differs from official delivery')
        event_verified = True
        description = detail.get('description', '')
    else:
        raise ValueError('Unsupported public service registry')
    return {'canonical': canonical, 'identity_kind': proof['registry_kind'], 'registration_verified': False,
        'public_registry_verified': True, 'chain_registration_verified': False, 'registration_chain_id': None,
        'provider_chain_event_verified': event_verified, 'provider_wallet': provider,
        'document': {'description': description, 'services': [{'endpoint': url} for url in services]},
        'source_refs': proof['source_refs'], 'background_findings': [
            {'measurement_purpose': 'background', 'criterion': 'chain-registration', 'verdict': 'UNKNOWN',
             'reason': '官方公开服务目录已核；没有据此声称ERC8004链上注册。此缺项不进入A/F/B。'}]}


def verify_service_identity(root, proof_path, expected_reference, *, chain_verifier=None):
    canonical = normalize_reference(expected_reference)
    _check(canonical == expected_reference and canonical, 'Unsupported canonical service identity')
    if not canonical.startswith('eip155:'):
        return verify_public_service_identity(root, proof_path, canonical)
    if chain_verifier is None:
        from reputation_platform.registration_discovery import verify_registration_proof
        chain_verifier = verify_registration_proof
    identity = chain_verifier(root, proof_path, canonical)
    return dict(identity, public_registry_verified=identity['registration_verified'],
                chain_registration_verified=identity['registration_verified'], identity_kind='erc8004',
                registration_chain_id=int(canonical.split(':')[1]))


def identity_limitations(reference, existing):
    if reference.startswith('eip155:'):
        return existing
    return [line for line in existing if 'ownerOf/tokenURI' not in line] + [
        'BACKGROUND：官方公共服务登记已核；chain_registration_verified=false，ERC8004链注册UNKNOWN，不进入A/F/B评分。',
        '公开登记使用官方MCP具体name/version/remote，或ACP UUID/钱包/offering与真实provider事件；不是一般官网自声明。',
    ]


def build_public_service_identity_proof(root, output, *, canonical, registry_kind, registry_observation,
                                        selected_service, offering=None, provider_event=None):
    """Retain only real input observations; verification never fetches or signs."""
    import hashlib
    root = Path(root).resolve()
    refs = {}
    def add(name):
        path = _public_file(root, name)
        key = path.relative_to(root).as_posix()
        refs[key] = hashlib.sha256(path.read_bytes()).hexdigest()
        if key.endswith('.observation.json'):
            observation = json.loads(path.read_bytes())
            if observation.get('response_file'):
                _check(Path(observation['response_file']).name == observation['response_file'], 'Identity body is not a sibling file')
                body = path.parent / observation['response_file']
                add(body)
                _check(refs[body.relative_to(root).as_posix()] == observation['response_sha256'], 'Retained identity body changed')
    add(registry_observation)
    proof = {'schema_version': SCHEMA, 'canonical': canonical, 'registry_kind': registry_kind,
             'registry_observation': registry_observation, 'selected_service': selected_service}
    if offering is not None:
        proof['offering'] = offering
    if provider_event:
        proof['provider_event'] = provider_event
        for name in ('job_observation', 'history_observation'):
            add(provider_event[name])
        for name in provider_event['rpc_observations']:
            add(name)
        add('configs/generic-rpc.json')
        proof['rpc_configuration'] = {'path': 'configs/generic-rpc.json', 'sha256': refs['configs/generic-rpc.json']}
    proof['source_refs'] = [{'path': name, 'sha256': digest} for name, digest in sorted(refs.items())]
    path = (root/output).resolve()
    _check(path.is_relative_to(root/'runtime') and not path.exists() and '.private' not in str(path).lower(),
           'Use a new public runtime identity proof path')
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf8') as stream:
        json.dump(proof, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    return verify_public_service_identity(root, path.relative_to(root).as_posix(), canonical)
