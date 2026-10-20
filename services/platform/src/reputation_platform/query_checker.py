"""One reviewed query adapter; business verdicts are rebuilt from retained RPC bytes."""

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re

from reputation_core import CapabilityCoverage, MeasurementPurpose, ProbeObservation, ReportFinding, SampleExplanation, ScoredSample, Verdict
from reputation_platform.protocol_evaluation import ACCEPT, VERSIONS, _result, _save, _tools
from reputation_platform.registration_discovery import RPC_CONFIG, _configuration, verify_registration_proof
from reputation_platform.prediction_report import RetainedEvidence
from reputation_platform.query_oracle import verify_transfer_record

CHECKER_ID = 'query.erc20-transfer-record'
VERSION = 'v1'
POLICY = 'docs/adr/0012-query-transfer-record-checker.md'
PLAN_NAME = 'query-checker-plan.json'
EMPTY_SCHEMA = {'type': 'object', 'properties': {}, 'additionalProperties': False}
# Adapters constrain the reviewed call/output mapping, never an Agent ID or its score.
ADAPTERS = ({'id': 'bobai.activity/v1', 'endpoint': 'https://brainonbnb.com/mcp',
             'chain': 56, 'tool': 'bobai_activity', 'token': '0x245c386dcfed896f5c346107596141e5edcbffff',
             'destination': '0x000000000000000000000000000000000000dead'},)
SCOPE = '仅核验公布交易中指定ERC20转入预定地址的全部事件总量，与服务整数披露是否一致。'
GAPS = ['只有一个无参数业务任务，未达到F七个不同任务门槛。',
        '未证明Agent执行归属，不产生B；不证明永久销毁、最新性、历史完整性或全部功能。']


def match_query_adapter(identity: dict, endpoint: str, tools: list[dict]) -> dict | None:
    if (not identity.get('registration_verified') or identity.get('document') is None
        or str(identity.get('token_uri', '')).startswith('ipfs://')):
        return None
    registered = {s.get('endpoint') for s in identity.get('services', []) if str(s.get('name', '')).lower() == 'mcp'}
    for adapter in ADAPTERS:
        matches = [t for t in tools if t.get('name') == adapter['tool']]
        if (endpoint == adapter['endpoint'] and endpoint in registered
            and identity['canonical'].split(':')[1] == str(adapter['chain'])
            and len(matches) == 1 and matches[0].get('inputSchema') == EMPTY_SCHEMA):
            return adapter
    return None


class QueryEvidence:
    def __init__(self, root: Path, hashes: dict[str, str]):
        self.reader, self.hashes, self.times = RetainedEvidence(root), hashes, []

    def read(self, name: str) -> bytes:
        if name not in self.hashes:
            raise ValueError('Query dependency absent from verified manifest: ' + name)
        return self.reader.remember(name, self.hashes[name]).read_bytes()

    def json(self, name: str):
        return json.loads(self.read(name))

    def catalog(self, name: str, endpoint: str):
        if name.endswith('.request-plan.json'):
            return self.request(name, endpoint, MeasurementPurpose.BACKGROUND)
        # The earlier bounded research retained an exact targets manifest, not per-request plans.
        manifest = self.json(name)
        targets = [t for t in manifest.get('targets', []) if t.get('url') == endpoint
                   and t.get('method') == 'POST' and t.get('json', {}).get('method') == 'tools/list']
        if (Path(name).name != 'manifest.json' or manifest.get('business_calls') != 0
            or manifest.get('retries') != 0 or len(targets) != 1):
            raise ValueError('Legacy discovery requires its original bounded targets manifest')
        target = targets[0]
        obs_name = (Path(name).parent / (target['key'] + '.observation.json')).as_posix()
        obs = ProbeObservation.model_validate_json(self.read(obs_name))
        if (obs.url != endpoint or obs.request_key != target['key'] or obs.method != 'POST'
            or obs.purpose != MeasurementPurpose.BACKGROUND or json.loads(obs.request_json) != target['json']
            or not obs.response_file or Path(obs.response_file).name != obs.response_file):
            raise ValueError('Legacy discovery observation differs from its retained target')
        raw = self.read((Path(name).parent / obs.response_file).as_posix())
        if hashlib.sha256(raw).hexdigest() != obs.response_sha256:
            raise ValueError('Legacy tool catalog changed')
        self.times.append(obs.observed_at)
        return obs, raw, target

    def request(self, name: str, url: str, purpose: MeasurementPurpose, body: dict | None = None):
        plan = self.json(name)
        if (not name.endswith('.request-plan.json') or plan['url'] != url or plan['method'] != 'POST'
            or plan['measurement_purpose'] != purpose.value or plan['retries'] != 0
            or plan['json'].get('jsonrpc') != '2.0' or plan['json'].get('id', plan['key']) != plan['key']
            or (body is not None and plan['json'] != body)):
            raise ValueError('Query request differs from its frozen endpoint, purpose or input')
        stem = name.removesuffix('.request-plan.json')
        if stem + '.observation.json' not in self.hashes:
            skip = self.json(stem + '.skip.json')
            if skip.get('request_sent') is not False:
                raise ValueError('Missing query observation requires an explicit unsent record')
            return None, b'', plan
        obs = ProbeObservation.model_validate_json(self.read(stem + '.observation.json'))
        if (not plan['execution_enabled'] or obs.request_key != plan['key'] or obs.url != url
            or obs.method != 'POST' or obs.purpose != purpose
            or json.loads(obs.request_json) != plan['json']
            or datetime.fromisoformat(plan['created_at']) > obs.observed_at):
            raise ValueError('Retained query observation belongs to another request')
        self.times.append(obs.observed_at)
        raw = b''
        if obs.response_file:
            path = (self.reader.root / name).parent / obs.response_file
            if path.resolve().parent != (self.reader.root / name).parent.resolve():
                raise ValueError('Query response escaped its original directory')
            raw = self.read(path.relative_to(self.reader.root).as_posix())
            if hashlib.sha256(raw).hexdigest() != obs.response_sha256:
                raise ValueError('Query raw response differs from its observation')
        return obs, raw, plan


def _complete(obs) -> bool:
    return bool(obs and obs.http_status == 200 and obs.body_complete and not obs.error_kind)


def _last_burn(raw: bytes, request_id) -> tuple[str, int] | None:
    try:
        result = _result(raw, request_id)
        content = result.get('content')
        if result.get('isError') is True or not isinstance(content, list) or len(content) != 1 or content[0].get('type') != 'text':
            return None
        claim = json.loads(content[0]['text'])['last_burn']
        amount, url = claim['bobai_burned'], claim['burn_tx']
        if (type(amount) is not int or not 0 <= amount <= 2 ** 53 - 1
            or not isinstance(url, str) or not re.fullmatch(r'https://bscscan\.com/tx/0x[0-9a-fA-F]{64}', url)):
            return None
        return url.rsplit('/', 1)[1].lower(), amount
    except (ValueError, KeyError, TypeError, AttributeError):
        return None


def _reviewed_discovery(source: QueryEvidence, plan: dict, execution: dict):
    """Authenticate the full discovery dependency closure before any business call."""
    source.read(POLICY)
    source.read(RPC_CONFIG.as_posix())
    proof = source.json(execution['proof_path'])
    refs = [*proof['source_refs'], proof['rpc_configuration']]
    for record in [proof.get('directory'), proof.get('document'), *proof.get('rpc', {}).values()]:
        if record:
            refs.extend(record['evidence'])
    for ref in refs:
        if source.hashes.get(ref['path']) != ref['sha256']:
            raise ValueError('Registration dependency absent from query manifest')
        source.read(ref['path'])
    identity = verify_registration_proof(source.reader.root, execution['proof_path'], execution['canonical'])
    endpoint = execution['endpoint']
    obs, raw, catalog = source.catalog(plan['catalog_request'], endpoint)
    if not _complete(obs):
        raise ValueError('Checker selection requires a successful original tool catalog')
    tools = _tools(_result(raw, catalog['json']['id']))
    adapter = match_query_adapter(identity, endpoint, tools)
    if adapter is None or plan['adapter_id'] != adapter['id'] or catalog['json'].get('method') != 'tools/list':
        raise ValueError('No reviewed query adapter matches authenticated service and schema')
    if (execution.get('arguments') != {} or any(execution.get(k) != adapter[k] for k in ('chain', 'tool', 'token', 'destination'))
        or execution.get('max_business_calls') != 1 or execution.get('retries') != 0
        or execution.get('paid_calls') != 0 or execution.get('mainnet_writes') is not False
        or execution.get('max_requests') != 7):
        raise ValueError('Query execution exceeds the reviewed zero-cost read-only plan')
    initial, initial_raw, init_plan = source.request(plan['initialize_request'], endpoint, MeasurementPurpose.BACKGROUND)
    notified, _, notify_plan = source.request(plan['initialized_request'], endpoint, MeasurementPurpose.BACKGROUND)
    negotiated = _result(initial_raw, init_plan['key']) if _complete(initial) else {}
    if (not _complete(initial) or not notified or notified.http_status not in (202, 204) or notified.error_kind
        or init_plan['json'].get('method') != 'initialize' or negotiated.get('protocolVersion') not in VERSIONS
        or not isinstance(negotiated.get('capabilities'), dict)
        or not isinstance(negotiated.get('capabilities', {}).get('tools'), dict)
        or notify_plan['json'] != {'jsonrpc': '2.0', 'method': 'notifications/initialized'}
        or datetime.fromisoformat(notify_plan['created_at']) < initial.observed_at
        or initial.observed_at > notified.observed_at):
        raise ValueError('Query invocation lacks a confirmed MCP initialization')
    headers = {**ACCEPT, 'MCP-Protocol-Version': negotiated['protocolVersion']}
    if plan['catalog_request'].endswith('.request-plan.json') and (
        notified.observed_at > obs.observed_at or datetime.fromisoformat(catalog['created_at']) < notified.observed_at
        or catalog['headers'] != headers):
        raise ValueError('Fresh tool catalog must follow initialization and use its negotiated headers')
    if notify_plan['headers'] != headers:
        raise ValueError('Initialized notification differs from negotiated protocol headers')
    created = datetime.fromisoformat(execution['created_at'])
    if created.tzinfo is None or obs.observed_at > created or notified.observed_at > created:
        raise ValueError('Query execution plan must follow authenticated discovery')
    return identity, adapter, notified, negotiated


def rebuild_query(root: Path, name: str, hashes: dict[str, str]):
    """Independently rebuild one F sample; integrity failures always raise."""
    source = QueryEvidence(root, hashes)
    plan = source.json(name)
    if (plan.get('schema_version') != 'query-checker-evidence-v1' or plan.get('checker_id') != CHECKER_ID
        or plan.get('checker_version') != VERSION or plan.get('policy_version') != 'service-contract-v1'
        or not isinstance(plan.get('rpc_requests'), dict)
        or set(plan['rpc_requests']) - {'chain', 'head', 'receipt', 'transaction', 'header', 'decimals'}):
        raise ValueError('Unknown query Checker, evidence policy or RPC request')
    execution = source.json(plan['execution_plan'])
    identity, adapter, notified, negotiated = _reviewed_discovery(source, plan, execution)
    endpoint = adapter['endpoint']
    business_name = plan['business_request']
    key = source.json(business_name)['key']
    body = {'jsonrpc': '2.0', 'id': key, 'method': 'tools/call', 'params': {'name': adapter['tool'], 'arguments': {}}}
    business, raw, call_plan = source.request(business_name, endpoint, MeasurementPurpose.FUNCTIONAL, body)
    created = datetime.fromisoformat(execution['created_at'])
    if (datetime.fromisoformat(call_plan['created_at']) < created
        or call_plan['headers'] != {**ACCEPT, 'MCP-Protocol-Version': negotiated['protocolVersion']}):
        raise ValueError('Query plan was not frozen after discovery and before the call')
    claim = _last_burn(raw, key) if _complete(business) else None
    verdict, reason, detail = Verdict.UNKNOWN, '未取得适配的完整业务结果；网络、授权或工具错误不记Agent业务失败。', {}
    if claim:
        txhash, amount = claim
        if not {'chain', 'head', 'receipt', 'transaction'} <= plan['rpc_requests'].keys():
            raise ValueError('A parsed transaction claim requires each planned base oracle request or explicit skip')
        config = _configuration(root)['chains'][str(adapter['chain'])]
        expected = {'chain': ('eth_chainId', []), 'head': ('eth_blockNumber', []),
                    'receipt': ('eth_getTransactionReceipt', [txhash]), 'transaction': ('eth_getTransactionByHash', [txhash])}
        values = {}
        for field in ('chain', 'head', 'receipt', 'transaction', 'header', 'decimals'):
            request_name = plan['rpc_requests'].get(field)
            if request_name is None:
                continue
            if field in ('header', 'decimals'):
                receipt = values.get('receipt')
                if not isinstance(receipt, dict) or not isinstance(receipt.get('blockNumber'), str):
                    raise ValueError('Fixed-block RPC requires its retained receipt')
                block = receipt['blockNumber']
                expected[field] = (('eth_getBlockByNumber', [block, False]) if field == 'header'
                                   else ('eth_call', [{'to': adapter['token'], 'data': '0x313ce567'}, block]))
            method, params = expected[field]
            request = source.json(request_name)
            rpc_body = {'jsonrpc': '2.0', 'id': request['key'], 'method': method, 'params': params}
            observed, response_raw, original = source.request(request_name, config['rpc_url'], MeasurementPurpose.BACKGROUND, rpc_body)
            if original.get('rpc_configuration_source') != 'operator-static-not-metadata':
                raise ValueError('Oracle RPC did not use the operator configuration')
            if business and observed and observed.observed_at < business.observed_at:
                raise ValueError('Oracle read predates its query output')
            if _complete(observed):
                try:
                    response = json.loads(response_raw)
                    if response.get('jsonrpc') == '2.0' and response.get('id') == request['key'] and 'error' not in response:
                        values[field] = response.get('result')
                except (ValueError, AttributeError):
                    pass
        if isinstance(values.get('receipt'), dict) and isinstance(values['receipt'].get('blockNumber'), str):
            if not {'header', 'decimals'} <= plan['rpc_requests'].keys():
                raise ValueError('A retained receipt requires each planned fixed-block oracle request or explicit skip')
        verdict, reason, detail = verify_transfer_record(amount, txhash, adapter['chain'], adapter['token'], (adapter['destination'],), values)
    capability_id = 'query-transfer-record'
    task_key = f"{CHECKER_ID}:{adapter['chain']}:{endpoint}:{adapter['tool']}:{{}}"
    paths = sorted(source.reader.inputs)
    explanation = SampleExplanation(
        sample=ScoredSample(sample_id=key, task_key=task_key, purpose=MeasurementPurpose.FUNCTIONAL,
            verdict=verdict, reason=reason, evidence=paths, elapsed_ms=None),
        capability_id=capability_id, observed_at=business.observed_at if business else None,
        title='公开交易记录查询 · 指定代币转入地址金额',
        input_summary=f"登记端点 {endpoint}；{adapter['tool']}({{}})，只读一次。",
        claimed_output=(f'交易 {claim[0]}；公布整数 {claim[1]}。' if claim else '当前没有可适配且完整的交易披露。'),
        independent_result=reason + ('；独立重建：' + json.dumps(detail, ensure_ascii=False, sort_keys=True) if detail else ''),
        checks=[ReportFinding(label='固定交易区块、回执、事件及金额独立核验', verdict=verdict, explanation=reason)],
    )
    capability = CapabilityCoverage(capability_id=capability_id, operation=adapter['tool'],
        description='查询服务公布的一笔代币转入预定地址记录。', protocol='MCP', tested_scope=SCOPE,
        sample_ids=[key], findings=explanation.checks, missing_evidence=GAPS,
        capability_type='Query / Tool', checker_id=CHECKER_ID, checker_version=VERSION)
    return identity['canonical'], capability, explanation, source.reader.inputs, source.times


def verify_query_samples(root: Path, report, hashes: dict[str, str]) -> set[str]:
    verified, verified_capabilities = set(), set()
    for name in hashes:
        if Path(name).name != PLAN_NAME:
            continue
        canonical, capability, sample, _, times = rebuild_query(root, name, hashes)
        actual = [s for s in report.samples if name in s.sample.evidence]
        matched = [c for c in report.capabilities if c.capability_id == capability.capability_id]
        if (canonical != report.registration_reference or len(actual) != 1 or actual[0] != sample
            or len(matched) != 1 or matched[0] != capability
            or any(t > report.generated_at for t in times)):
            raise ValueError('Query report differs from independently reconstructed identity, task or result')
        verified.add(sample.sample.sample_id)
        verified_capabilities.add(capability.capability_id)
    if any(c.checker_id == CHECKER_ID and c.capability_id not in verified_capabilities
           for c in report.capabilities):
        raise ValueError('Query Checker metadata requires an independently reconstructed capability')
    return verified


def collect_query_tasks(registration: dict, evidence):
    """Run at most one reviewed query, only inside an already enabled scoped evaluation."""
    if not evidence.enabled:
        return [], [], []
    identity = verify_registration_proof(evidence.root, registration['proof_path'], registration['canonical'])
    selected = None
    for name in list(evidence.inputs):
        if not name.endswith('-tools.observation.json'):
            continue
        obs = ProbeObservation.model_validate_json((evidence.root / name).read_bytes())
        if obs.purpose != MeasurementPurpose.BACKGROUND or not _complete(obs):
            continue
        try:
            raw = (evidence.root / name).parent.joinpath(obs.response_file).read_bytes()
            adapter = match_query_adapter(identity, obs.url, _tools(_result(raw, obs.request_key)))
            if adapter:
                selected = name, adapter
                break
        except (ValueError, TypeError, KeyError):
            continue
    if selected is None:
        return [], [], []
    name, adapter = selected
    stem = name.removesuffix('tools.observation.json')
    evidence._remember(evidence.root / POLICY)
    execution = _save(evidence, 'query-execution-plan.json', {
        **adapter, 'schema_version': 'query-execution-v1', 'canonical': registration['canonical'],
        'proof_path': registration['proof_path'], 'created_at': datetime.now(timezone.utc).isoformat(),
        'checker_id': CHECKER_ID, 'checker_version': VERSION, 'policy_version': 'service-contract-v1',
        'arguments': {}, 'max_business_calls': 1, 'max_requests': 7, 'paid_calls': 0, 'retries': 0, 'mainnet_writes': False})
    discovery = {'catalog_request': stem + 'tools.request-plan.json',
                 'initialize_request': stem + 'initialize.request-plan.json',
                 'initialized_request': stem + 'initialized.request-plan.json', 'adapter_id': adapter['id']}
    _, adapter, _, negotiated = _reviewed_discovery(QueryEvidence(evidence.root, evidence.inputs), discovery,
                                                   json.loads((evidence.root / execution['path']).read_bytes()))
    key = 'query-business'
    call = evidence.request(key, adapter['endpoint'], 'POST',
        {'jsonrpc': '2.0', 'id': key, 'method': 'tools/call', 'params': {'name': adapter['tool'], 'arguments': {}}},
        {**ACCEPT, 'MCP-Protocol-Version': negotiated['protocolVersion']}, purpose=MeasurementPurpose.FUNCTIONAL)
    claim = _last_burn(call['raw'], key) if call['observation'] and _complete(ProbeObservation.model_validate(call['observation'])) else None
    rpc_requests, values = {}, {}
    if claim:
        specs = [('chain', 'eth_chainId', []), ('head', 'eth_blockNumber', []),
                 ('receipt', 'eth_getTransactionReceipt', [claim[0]]), ('transaction', 'eth_getTransactionByHash', [claim[0]])]
        for field, method, params in specs:
            rpc_key = 'query-reference-' + field
            rpc_requests[field] = (evidence.run / (rpc_key + '.request-plan.json')).relative_to(evidence.root).as_posix()
            config = evidence.config['chains'][str(adapter['chain'])]
            response = evidence.request(rpc_key, config['rpc_url'], 'POST', {'jsonrpc': '2.0', 'id': rpc_key, 'method': method, 'params': params})
            try:
                data = json.loads(response['raw'])
                if (isinstance(data, dict) and response['observation'] and _complete(ProbeObservation.model_validate(response['observation']))
                    and data.get('jsonrpc') == '2.0' and data.get('id') == rpc_key and 'error' not in data):
                    values[field] = data.get('result')
            except (ValueError, TypeError):
                pass
            if field == 'transaction' and isinstance(values.get('receipt'), dict) and isinstance(values['receipt'].get('blockNumber'), str):
                block = values['receipt']['blockNumber']
                specs.extend([('header', 'eth_getBlockByNumber', [block, False]),
                              ('decimals', 'eth_call', [{'to': adapter['token'], 'data': '0x313ce567'}, block])])
    index = _save(evidence, PLAN_NAME, {
        'schema_version': 'query-checker-evidence-v1', 'checker_id': CHECKER_ID, 'checker_version': VERSION,
        'policy_version': 'service-contract-v1', 'adapter_id': adapter['id'], 'execution_plan': execution['path'],
        'catalog_request': stem + 'tools.request-plan.json', 'initialize_request': stem + 'initialize.request-plan.json',
        'initialized_request': stem + 'initialized.request-plan.json',
        'business_request': (evidence.run / (key + '.request-plan.json')).relative_to(evidence.root).as_posix(), 'rpc_requests': rpc_requests})
    evidence._remember(evidence.root / POLICY)
    _, capability, sample, inputs, _ = rebuild_query(evidence.root, index['path'], evidence.inputs)
    evidence.inputs.update(inputs)
    return [capability], [sample], GAPS
