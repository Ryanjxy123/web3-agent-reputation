"""Registration-led public discovery; operator RPC configuration is never metadata input."""

import base64
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
from urllib.parse import unquote_to_bytes, urlsplit

from reputation_core import MeasurementPurpose, ProbeObservation
from reputation_core.application import normalize_reference
from reputation_core.prediction_chain import calldata
from reputation_platform.safe_http import PublicTarget, SafeHttpClient
from reputation_platform.settings import load_zan_key_file

RPC_CONFIG = Path('configs/generic-rpc.json')
GATEWAY = 'https://gateway.autonolas.tech/ipfs/'
READ_METHODS = {'eth_chainId', 'eth_blockNumber', 'eth_getBlockByNumber', 'eth_call',
                'eth_getTransactionByHash', 'eth_getTransactionReceipt', 'eth_getLogs', 'eth_getCode', 'eth_getBalance'}


def _sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _write(path: Path, value: object) -> None:
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)


def _public_file(root: Path, name: str | Path, expected: str | None = None) -> Path:
    path = (root / name).resolve()
    if (not any(path.is_relative_to(root / base) for base in ('runtime', 'configs')) or not path.is_file()
        or any(part.lower() in {'secrets', 'platform-config'} or '.private' in part.lower() for part in path.parts)):
        raise ValueError('Only retained public evidence and operator configuration may be read')
    if expected is not None and _sha(path.read_bytes()) != expected:
        raise ValueError('Retained registration evidence changed: ' + str(name))
    return path


def _reference(root: Path, path: Path) -> dict:
    return {'path': path.relative_to(root).as_posix(), 'sha256': _sha(path.read_bytes())}


def _configuration(root: Path) -> dict:
    config = json.loads(_public_file(root, RPC_CONFIG).read_bytes())
    allowed = {'100': 'https://rpc.gnosischain.com', '56': 'https://api.zan.top/node/v1/bsc/mainnet',
               '8453': 'https://api.zan.top/node/v1/base/mainnet'}
    if (config.get('configuration_source') != 'operator-static-not-metadata'
        or config.get('confirmation_distance') != 64
        or any(key not in allowed or value.get('rpc_url') != allowed[key]
               or value.get('authentication') != ('public' if key == '100' else 'zan')
               for key, value in config['chains'].items())):
        raise ValueError('RPCs must come from the reviewed static operator configuration')
    return config


def _identity(value: str) -> tuple[str, int, str, int]:
    canonical = normalize_reference(value)
    if canonical is None or not canonical.startswith('eip155:'):
        raise ValueError('Expected a canonical ERC-8004 registration reference')
    _, chain, registry, token = canonical.split(':')
    if int(token) >= 2 ** 256 or int(registry, 16) == 0:
        raise ValueError('Invalid registered identity')
    return canonical, int(chain), registry, int(token)


def _directory_matches(document: dict, canonical: str) -> bool:
    _, chain, registry, token = _identity(canonical)
    return (document.get('chain_id') == chain and str(document.get('token_id')) == str(token)
            and str(document.get('contract_address', '')).lower() == registry)


def _abi_string(value: str) -> str:
    if not re.fullmatch(r'0x(?:[0-9a-fA-F]{2})+', value):
        raise ValueError('tokenURI did not return ABI bytes')
    raw = bytes.fromhex(value[2:])
    if len(raw) < 64 or int.from_bytes(raw[:32]) != 32:
        raise ValueError('Invalid tokenURI ABI offset')
    size = int.from_bytes(raw[32:64])
    if len(raw) != 64 + ((size + 31) // 32) * 32 or any(raw[64 + size:]):
        raise ValueError('Invalid tokenURI ABI size or padding')
    return raw[64:64 + size].decode('utf-8')


def _uri(uri: str) -> tuple[str, bytes | str]:
    if uri.startswith('data:'):
        prefix, encoded = uri.split(',', 1)
        if prefix.split(';', 1)[0].lower() != 'data:application/json':
            raise ValueError('Only JSON registration data URIs are supported')
        raw = base64.b64decode(encoded, validate=True) if prefix.endswith(';base64') else unquote_to_bytes(encoded)
        return 'data', raw
    if uri.startswith('ipfs://'):
        location = uri[7:].removeprefix('ipfs/')
        parts = location.split('/')
        if (not re.fullmatch('[A-Za-z0-9]+', parts[0]) or any(unquote_to_bytes(part) in (b'.', b'..') for part in parts)
            or any(char in location for char in ('?', '#', '\\'))):
            raise ValueError('Invalid IPFS registration URI')
        return 'ipfs', GATEWAY + location
    parsed = urlsplit(uri)
    if (parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password
        or parsed.fragment or parsed.port not in (None, 443)):
        raise ValueError('Registration URI must be JSON data, public HTTPS or fixed-gateway IPFS')
    return 'https', uri


class DiscoveryEvidence:
    def __init__(self, root: Path, run: Path, proxy: str | None = None, enabled: bool = False, heartbeat=None,
                 *, timeout_seconds: float = 15, max_requests: int | None = None):
        self.root = root.resolve()
        self.run = (self.root / run).resolve()
        if (not self.run.is_relative_to(self.root / 'runtime') or self.run == self.root / 'runtime'
            or any(part.lower() in {'secrets', 'platform-config'} or '.private' in part.lower() for part in self.run.parts)):
            raise ValueError('Discovery output must be a public runtime subdirectory')
        if enabled and not proxy:
            raise ValueError('Public discovery requires an explicit operator proxy')
        if (isinstance(timeout_seconds, bool) or not isinstance(timeout_seconds, (int, float))
            or not math.isfinite(timeout_seconds) or not 0 < timeout_seconds <= 45):
            raise ValueError('Public request timeout must be finite and in (0, 45] seconds')
        if max_requests is not None and (type(max_requests) is not int or not 1 <= max_requests <= 64):
            raise ValueError('Scoped discovery request budget must be an integer in 1..64')
        self.run.mkdir(parents=True, exist_ok=True)
        self.proxy, self.enabled, self.heartbeat = proxy, enabled, heartbeat
        self.timeout_seconds, self.max_requests = timeout_seconds, max_requests
        self.inputs, self.request_count = {}, 0
        self.config = _configuration(self.root)
        self._remember(self.root / RPC_CONFIG)

    def _remember(self, path: Path) -> dict:
        item = _reference(self.root, path)
        self.inputs[item['path']] = item['sha256']
        return item

    def request(self, key: str, url: str, method: str = 'GET', body=None, headers=None,
                *, purpose: MeasurementPurpose = MeasurementPurpose.BACKGROUND) -> dict:
        if not re.fullmatch(r'[a-z0-9-]+', key):
            raise ValueError('Evidence request key must be lowercase ASCII')
        parsed = urlsplit(url)
        if (parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password
            or parsed.fragment or parsed.port not in (None, 443) or method not in ('GET', 'POST')):
            raise ValueError('Discovery only accepts explicit public HTTPS requests')
        rpc = next((value for value in self.config['chains'].values() if value['rpc_url'] == url), None)
        if rpc and (method != 'POST' or not isinstance(body, dict) or body.get('jsonrpc') != '2.0'
                    or body.get('method') not in READ_METHODS):
            raise ValueError('Operator RPC endpoint requires an allowed read-only JSON-RPC method')
        if (not rpc and isinstance(body, dict) and str(body.get('method', '')).startswith('eth_')):
            raise ValueError('RPC endpoints cannot come from registration metadata')
        if headers is not None and (not isinstance(headers, dict) or any(
            not isinstance(name, str) or name.lower() not in {'accept', 'mcp-protocol-version'}
            or not isinstance(value, str) or '\r' in value or '\n' in value
            for name, value in headers.items())):
            raise ValueError('Only public protocol negotiation headers may enter evidence')
        purpose = MeasurementPurpose(purpose)
        if self.heartbeat:
            self.heartbeat()
        plan = self.run / f'{key}.request-plan.json'
        _write(plan, {'created_at': datetime.now(timezone.utc).isoformat(), 'key': key, 'url': url,
            'method': method, 'json': body, 'headers': headers, 'measurement_purpose': purpose.value,
            'execution_enabled': self.enabled, 'retries': 0, 'timeout_seconds': self.timeout_seconds,
            'max_body_bytes': 1048576, 'rpc_configuration_source': 'operator-static-not-metadata' if rpc else None})
        references = [self._remember(plan)]
        stop = self.root / 'runtime/prediction-network-stops' / (parsed.hostname + '.json')
        budget_exhausted = self.max_requests is not None and self.request_count >= self.max_requests
        if not self.enabled or stop.is_file() or budget_exhausted:
            skip = self.run / f'{key}.skip.json'
            _write(skip, {'request_sent': False, 'reason': ('public_reads_disabled' if not self.enabled else
                   'host_stopped' if stop.is_file() else 'request_budget_exhausted')})
            references.append(self._remember(skip))
            return {'raw': b'', 'response_file': None, 'evidence': references, 'observation': None}
        target = PublicTarget(key, url, method, purpose=purpose, json_body=body, headers=headers)
        credential = load_zan_key_file(fallback=rpc['credential_file']) if rpc and rpc['authentication'] == 'zan' else None
        # Reserve before transport: a failed evidence write must not refund a sent request.
        self.request_count += 1
        with SafeHttpClient((target,), enabled=True, proxy=self.proxy, max_requests=1,
                            zan_key_url_file=credential, pin_public_dns=True,
                            timeout_seconds=self.timeout_seconds) as client:
            observed = client.fetch(key, self.run)
        references.append(self._remember(self.run / f'{key}.observation.json'))
        response_file, raw = None, b''
        if observed.response_file:
            response = self.run / observed.response_file
            raw = response.read_bytes()
            response_file = response.relative_to(self.root).as_posix()
            references.append(self._remember(response))
        if observed.http_status in (401, 402, 403, 429):
            stop.parent.mkdir(exist_ok=True)
            if not stop.exists():
                _write(stop, {'host': parsed.hostname, 'reason': f'HTTP {observed.http_status}',
                              'source_run': self.run.relative_to(self.root).as_posix()})
        if self.heartbeat:
            self.heartbeat()
        return {'raw': raw, 'response_file': response_file, 'evidence': references,
                'observation': observed.model_dump(mode='json')}


def _successful(response: dict) -> None:
    obs = response['observation']
    if (obs is None or obs['http_status'] != 200 or obs['error_kind'] or not obs['body_complete']):
        raise ValueError('未取得完整成功的原始响应，保留缺项，不据此判业务失败。')


def _rpc(evidence: DiscoveryEvidence, chain: int, key: str, method: str, params: list) -> dict:
    config = evidence.config['chains'][str(chain)]
    body = {'jsonrpc': '2.0', 'id': key, 'method': method, 'params': params}
    response = evidence.request(key, config['rpc_url'], 'POST', body)
    _successful(response)
    data = json.loads(response['raw'])
    if (not isinstance(data, dict) or data.get('jsonrpc') != '2.0' or data.get('id') != key
        or data.get('error') or data.get('result') is None):
        error = data.get('error', {}) if isinstance(data, dict) else {}
        if isinstance(error, dict) and (error.get('code') in (-32005, -32016, 429)
            or any(term in str(error.get('message', '')).lower() for term in ('rate limit', 'quota', 'too many requests'))):
            stop = evidence.root / 'runtime/prediction-network-stops' / (urlsplit(config['rpc_url']).hostname + '.json')
            stop.parent.mkdir(exist_ok=True)
            if not stop.exists():
                _write(stop, {'reason': 'RPC access or rate limit', 'source_run': evidence.run.relative_to(evidence.root).as_posix()})
        raise ValueError('RPC返回错误或缺少结果；未重试、切换端点或改用metadata中的RPC。')
    return {'method': method, 'params': params, 'value': data['result'], 'evidence': response['evidence']}


def _services(document: dict) -> list[dict]:
    value = document.get('services', [])
    if isinstance(value, dict):
        value = [{'name': name, **(item if isinstance(item, dict) else {'endpoint': item})} for name, item in value.items()]
    result = []
    for item in value if isinstance(value, list) else []:
        if isinstance(item, dict):
            name = next((item[key] for key in ('name', 'type', 'protocol') if isinstance(item.get(key), str)), '')
            endpoint = next((item[key] for key in ('endpoint', 'url', 'uri') if isinstance(item.get(key), str)), '')
            result.append({**item, 'name': name, 'endpoint': endpoint, 'declaration': item})
    return result


def _tools(document: dict) -> list[dict]:
    result, metadata = [], document.get('toolMetadata', {})
    values = document.get('tools', [])
    if isinstance(values, list):
        for item in values:
            if isinstance(item, str):
                detail = metadata.get(item, {}) if isinstance(metadata, dict) else {}
                detail = detail if isinstance(detail, dict) else {}
                result.append({**detail, 'name': item, 'description': detail.get('description', ''), 'declaration': detail})
            elif isinstance(item, dict):
                result.append({**item, 'name': item.get('name') or item.get('id') or '',
                               'description': item.get('description', ''), 'declaration': item})
    for item in document.get('capabilities', []) if isinstance(document.get('capabilities'), list) else []:
        if isinstance(item, dict) and item.get('id'):
            result.append({**item, 'name': item['id'], 'description': item.get('description', ''), 'declaration': item})
    return result


def _materials(directory: dict, document: dict) -> dict:
    raw = directory.get('raw_metadata', {})
    cached = raw.get('offchain_content', {}) if isinstance(raw, dict) else {}
    return document or (cached if isinstance(cached, dict) else {}) or directory


def _capabilities(document: dict) -> list[str | dict]:
    result = []
    for key in ('capabilities', 'skills'):
        value = document.get(key, [])
        result.extend(item for item in (value if isinstance(value, list) else [value]) if isinstance(item, (str, dict)))
    return result


def discover_registration(canonical: str, evidence: DiscoveryEvidence) -> dict:
    canonical, chain, registry, token = _identity(canonical)
    proof = {'schema_version': 'registration-discovery-proof-v1', 'canonical': canonical,
             'rpc_configuration': evidence._remember(evidence.root / RPC_CONFIG),
             'rpc_configuration_source': 'operator-static-not-metadata', 'directory': None,
             'rpc': {}, 'token_uri': None, 'document': None, 'limitations': []}
    directory, document, verified = {}, {}, False
    url = f'https://api.8004scan.io/api/v1/agents/{chain}/{token}'
    try:
        response = evidence.request('registration-directory', url)
        _successful(response)
        payload = json.loads(response['raw'])
        if not isinstance(payload, dict) or not _directory_matches(payload, canonical):
            raise ValueError('目录实际链号、注册合约或tokenId不匹配；不采用该目录线索。')
        directory = payload
        proof['directory'] = {'url': url, 'payload': payload, 'evidence': response['evidence']}
    except (ValueError, KeyError, TypeError, OSError) as error:
        proof['limitations'].append('目录：' + str(error))
    if str(chain) not in evidence.config['chains']:
        proof['limitations'].append('当前没有此链的操作者可信RPC配置，仅保留目录来源，登记链验UNKNOWN。')
    else:
        try:
            rpc = proof['rpc']
            item = _rpc(evidence, chain, 'registration-chain', 'eth_chainId', [])
            if int(item['value'], 16) != chain:
                raise ValueError('可信RPC返回其他链，已停止后续链读取。')
            rpc['chain'] = item
            item = _rpc(evidence, chain, 'registration-head', 'eth_blockNumber', [])
            n = int(item['value'], 16) - 64
            if n < 0:
                raise ValueError('尚不能建立64块确认距离。')
            rpc['head'] = item
            item = _rpc(evidence, chain, 'registration-header', 'eth_getBlockByNumber', [hex(n), False])
            header = item['value']
            if int(header['number'], 16) != n or not re.fullmatch('0x[0-9a-fA-F]{64}', header['hash']):
                raise ValueError('固定区块头不匹配。')
            rpc['header'] = item
            for name, signature in (('owner', 'ownerOf(uint256)'), ('uri', 'tokenURI(uint256)')):
                try:
                    item = _rpc(evidence, chain, 'registration-' + name, 'eth_call',
                                [{'to': registry, 'data': calldata(signature, token)}, hex(n)])
                    if name == 'owner':
                        owner = item['value']
                        if not re.fullmatch('0x0{24}[0-9a-fA-F]{40}', owner) or int(owner, 16) == 0:
                            raise ValueError('ownerOf没有返回有效的非零地址。')
                    else:
                        proof['token_uri'] = _abi_string(item['value'])
                    rpc[name] = item
                except (ValueError, KeyError, TypeError, OSError) as error:
                    proof['limitations'].append(name + '：' + str(error))
            verified = 'owner' in rpc and 'uri' in rpc
        except (ValueError, KeyError, TypeError, OSError) as error:
            proof['limitations'].append('链登记：' + str(error))
    if proof['token_uri'] is not None:
        try:
            transport, target = _uri(proof['token_uri'])
            if transport == 'data':
                path = evidence.run / 'registration-document.embedded.json'
                with path.open('xb') as stream:
                    stream.write(target)
                refs = [evidence._remember(path)]
                raw = target
            else:
                response = evidence.request('registration-document', target)
                _successful(response)
                refs, raw = response['evidence'], response['raw']
            document = json.loads(raw)
            if not isinstance(document, dict):
                raise ValueError('注册文档不是JSON对象。')
            proof['document'] = {'transport': transport, 'url': target if transport != 'data' else None,
                                 'payload': document, 'evidence': refs, 'sha256': _sha(raw)}
            if transport == 'ipfs':
                proof['limitations'].append('本模块核对链上URI和真实网关原件，未另做IPFS CID/DAG内容认证。')
        except (ValueError, KeyError, TypeError, OSError) as error:
            document = {}
            proof['limitations'].append('注册文档：' + str(error))
    selected = _materials(directory, document)
    if not document and directory:
        proof['limitations'].append('当前服务与功能仅为目录缓存线索，不是已取得链上tokenURI对应文档。')
    proof['registration_verified'] = verified
    proof['source_refs'] = [{'path': path, 'sha256': digest} for path, digest in sorted(evidence.inputs.items())]
    path = evidence.run / 'registration-proof.json'
    _write(path, proof)
    proof_ref = evidence._remember(path)
    return {'schema_version': 'registration-discovery-v1', 'canonical': canonical,
        'candidate_key': 'agent-' + _sha(canonical.encode())[:24],
        'name': selected.get('name') or directory.get('name') or canonical,
        'description': selected.get('description') or directory.get('description') or '',
        'registration_verified': verified, 'services': _services(selected), 'claims': [],
        'declared_tools': _tools(selected), 'capabilities': _capabilities(selected),
        'identity_proof': proof, 'proof_path': proof_ref['path'], 'source_refs': [*proof['source_refs'], proof_ref],
        'services_source': 'registered-document' if document else 'directory-unverified',
        'limitations': proof['limitations']}


def _verify_registration_proof(root: Path, proof_path: str | Path, expected_canonical: str) -> dict:
    """Reauthenticate original observations and identity; directory copies never become chain proof."""
    root = root.resolve()
    canonical, chain, registry, token = _identity(expected_canonical)
    proof = json.loads(_public_file(root, proof_path).read_bytes())
    if proof.get('schema_version') != 'registration-discovery-proof-v1' or proof['canonical'] != canonical:
        raise ValueError('Registration proof belongs to a different identity')
    config = _configuration(root)
    if (proof.get('rpc_configuration_source') != 'operator-static-not-metadata'
        or proof['rpc_configuration']['path'] != RPC_CONFIG.as_posix()):
        raise ValueError('RPC configuration is not the fixed operator file')
    _public_file(root, RPC_CONFIG, proof['rpc_configuration']['sha256'])
    for item in proof['source_refs']:
        _public_file(root, item['path'], item['sha256'])

    def http(value: dict, url: str, method: str):
        paths = [_public_file(root, item['path'], item['sha256']) for item in value['evidence']]
        observations = [path for path in paths if path.name.endswith('.observation.json')]
        if len(observations) != 1:
            raise ValueError('One original HTTP observation is required')
        obs = ProbeObservation.model_validate_json(observations[0].read_bytes())
        if (obs.url != url or obs.method != method or obs.http_status != 200 or obs.error_kind
            or not obs.body_complete or not obs.response_file):
            raise ValueError('Retained registration HTTP source is not complete or has another target')
        response = (observations[0].parent / obs.response_file).resolve()
        if response.parent != observations[0].parent or response not in paths:
            raise ValueError('Registration response is outside its original evidence')
        raw = _public_file(root, response, obs.response_sha256).read_bytes()
        plans = [path for path in paths if path.name.endswith('.request-plan.json')]
        if len(plans) != 1:
            raise ValueError('Original exact request plan is required')
        plan = json.loads(plans[0].read_bytes())
        if (plan['key'] != obs.request_key or plan['url'] != url or plan['method'] != method
            or plan['measurement_purpose'] != obs.purpose.value or not plan['execution_enabled']
            or plan['json'] != (json.loads(obs.request_json) if obs.request_json is not None else None)):
            raise ValueError('Original request plan differs from its observation')
        return obs, raw

    directory = proof.get('directory')
    if directory:
        url = f'https://api.8004scan.io/api/v1/agents/{chain}/{token}'
        obs, raw = http(directory, url, 'GET')
        payload = json.loads(raw)
        if obs.request_json is not None or payload != directory['payload'] or not _directory_matches(payload, canonical):
            raise ValueError('Original directory source does not identify this registration')
    verified, uri = False, None
    if proof.get('rpc') and str(chain) not in config['chains']:
        raise ValueError('Unsupported chain cannot carry operator RPC proof')
    if str(chain) in config['chains'] and proof.get('rpc'):
        values = {}
        rpc_url = config['chains'][str(chain)]['rpc_url']
        for name, value in proof['rpc'].items():
            obs, raw = http(value, rpc_url, 'POST')
            request, response = json.loads(obs.request_json), json.loads(raw)
            if (request.get('jsonrpc') != '2.0' or request.get('method') != value['method'] or request.get('params') != value['params']
                or value['method'] not in READ_METHODS or response.get('jsonrpc') != '2.0'
                or response.get('id') != request.get('id') or response.get('error') or response.get('result') != value['value']):
                raise ValueError('Original RPC envelope or result differs from its proof copy')
            values[name] = response['result']
        expected = {'chain': ('eth_chainId', []), 'head': ('eth_blockNumber', [])}
        if 'chain' in values and int(values['chain'], 16) != chain:
            raise ValueError('RPC identity chain differs from canonical registration')
        if 'head' in values:
            if 'chain' not in values:
                raise ValueError('Snapshot head requires its authenticated chain')
            n = int(values['head'], 16) - 64
            if n < 0:
                raise ValueError('Snapshot lacks the required 64-block confirmation distance')
            expected.update({
                'header': ('eth_getBlockByNumber', [hex(n), False]),
                'owner': ('eth_call', [{'to': registry, 'data': calldata('ownerOf(uint256)', token)}, hex(n)]),
                'uri': ('eth_call', [{'to': registry, 'data': calldata('tokenURI(uint256)', token)}, hex(n)])})
        for name in values:
            if name not in expected or (proof['rpc'][name]['method'], proof['rpc'][name]['params']) != expected[name]:
                raise ValueError('Registration RPCs do not bind the expected identity and fixed chain snapshot')
        if 'header' in values and (int(values['header']['number'], 16) != n
            or not re.fullmatch('0x[0-9a-fA-F]{64}', values['header']['hash'])):
            raise ValueError('Retained fixed snapshot header is invalid')
        if ('owner' in values or 'uri' in values) and 'header' not in values:
            raise ValueError('Identity reads require the authenticated snapshot header')
        if 'owner' in values and (not re.fullmatch('0x0{24}[0-9a-fA-F]{40}', values['owner']) or int(values['owner'], 16) == 0):
            raise ValueError('Original ownerOf result does not identify a nonzero owner')
        if 'uri' in values:
            uri = _abi_string(values['uri'])
        verified = {'chain', 'head', 'header', 'owner', 'uri'} <= values.keys()
    if proof.get('token_uri') != uri:
        raise ValueError('Copied token URI differs from the original chain response')
    document = proof.get('document')
    if document:
        transport, target = _uri(uri)
        if document['transport'] != transport:
            raise ValueError('Document transport differs from the registered token URI')
        if transport == 'data':
            if len(document['evidence']) != 1:
                raise ValueError('Data URI requires its retained decoded bytes')
            item = document['evidence'][0]
            raw = _public_file(root, item['path'], item['sha256']).read_bytes()
            if raw != target or document['url'] is not None:
                raise ValueError('Decoded data URI differs from the actual registered URI')
        else:
            if document['url'] != target:
                raise ValueError('Document URL differs from the registered URI or fixed IPFS gateway')
            obs, raw = http(document, target, 'GET')
            if obs.request_json is not None:
                raise ValueError('Registration document was not a plain public GET')
        if _sha(raw) != document['sha256'] or json.loads(raw) != document['payload']:
            raise ValueError('Registration document copy differs from its original retained bytes')
    if proof['registration_verified'] != verified:
        raise ValueError('Stored registration verification differs from original chain evidence')
    if not directory and not verified:
        raise ValueError('No independently readable directory identity or complete chain registration proof')
    selected = _materials(directory['payload'] if directory else {}, document['payload'] if document else {})
    return {'canonical': canonical, 'registration_verified': verified, 'directory_verified': bool(directory),
            'token_uri': uri, 'document': document['payload'] if document else None,
            'services': _services(selected), 'source_refs': proof['source_refs']}


def verify_registration_proof(root: Path, proof_path: str | Path, expected_canonical: str) -> dict:
    """Return verified identity/services, or ValueError for changed or malformed retained evidence."""
    try:
        return _verify_registration_proof(root, proof_path, expected_canonical)
    except (KeyError, TypeError, AttributeError, OSError) as error:
        raise ValueError('Malformed or unavailable original registration evidence') from error
