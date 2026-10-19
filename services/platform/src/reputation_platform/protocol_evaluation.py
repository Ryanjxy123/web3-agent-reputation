"""Read-only protocol discovery; business correctness is never inferred from schemas."""

from datetime import datetime, timezone
import hashlib
import json
from math import isfinite
import secrets
import time
from urllib.parse import urlsplit

from reputation_core import (
    CapabilityCoverage, MeasurementPurpose, ReportFinding, SampleExplanation,
    ScoredSample, Verdict,
)

ACCEPT = {'Accept': 'application/json, text/event-stream'}
VERSIONS = {'2024-11-05', '2025-03-26', '2025-06-18'}
STOP_STATUSES = {401, 402, 403, 429}
BUSINESS_GAPS = ['尚缺实际业务任务、输入输出绑定及必要的独立正确性判据。',
                 '尚缺可归属执行者的真实任务交易及完整履约证据。']


def descriptor_remote(document: dict) -> str | None:
    """Select one explicit HTTPS streamable-HTTP remote; local packages are data only."""
    remotes = set()
    for field in ('remoteEndpoints', 'remotes'):
        entries = document.get(field, [])
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            transport = entry.get('transport')
            kind = transport.get('type') if isinstance(transport, dict) else entry.get('type')
            url = entry.get('url')
            if kind != 'streamable-http' or not isinstance(url, str):
                continue
            try:
                parsed = urlsplit(url)
                if (parsed.scheme == 'https' and parsed.hostname and not parsed.username
                    and not parsed.password and not parsed.fragment and parsed.port in (None, 443)):
                    remotes.add(url)
            except ValueError:
                continue
    return next(iter(remotes)) if len(remotes) == 1 else None


def _save(evidence, name: str, value: dict) -> dict:
    path = evidence.run / name
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
    reference = {'path': path.relative_to(evidence.root).as_posix(),
                 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
    evidence.inputs[reference['path']] = reference['sha256']
    return reference


def _result(raw: bytes, request_id) -> dict:
    data = json.loads(raw)
    if (not isinstance(data, dict) or data.get('jsonrpc') != '2.0' or data.get('id') != request_id
        or 'error' in data or not isinstance(data.get('result'), dict)):
        raise ValueError('JSON-RPC响应标识、结果或错误字段不符合本次请求。')
    return data['result']


def _tools(result: dict) -> list[dict]:
    tools = result.get('tools')
    if (not isinstance(tools, list) or any(not isinstance(item, dict)
        or not isinstance(item.get('name'), str) or not item['name'].strip()
        or not isinstance(item.get('inputSchema'), dict) or item['inputSchema'].get('type') != 'object'
        for item in tools) or len({item['name'] for item in tools}) != len(tools)):
        raise ValueError('工具列表缺少唯一名称或标准对象输入Schema。')
    if 'nextCursor' in result and not isinstance(result['nextCursor'], str):
        raise ValueError('工具列表分页游标格式不符合协议。')
    return tools


def availability_verdict(observation: dict | None, raw: bytes) -> tuple[Verdict, str]:
    """Recompute only a fresh MCP tools/list observation, never a business verdict."""
    if (not observation or observation.get('purpose') != 'availability'
        or observation.get('method') != 'POST' or not observation.get('response_file')):
        return Verdict.UNKNOWN, '缺少本次可用性请求、用途或原始响应记录。'
    try:
        request = json.loads(observation.get('request_json') or '')
    except (ValueError, TypeError):
        return Verdict.UNKNOWN, '缺少可核对的实际JSON-RPC请求。'
    if (not isinstance(request, dict) or request.get('jsonrpc') != '2.0'
        or request.get('method') != 'tools/list' or type(request.get('id')) not in (str, int)):
        return Verdict.UNKNOWN, '原始请求不是带标识的MCP工具发现请求。'
    status = observation.get('http_status')
    if status in STOP_STATUSES:
        return Verdict.UNKNOWN, '接口要求鉴权、付费或已限流，停止该主机后续请求。'
    if (observation.get('error_kind') not in (None, 'http_status_not_success')
        or not observation.get('body_complete')):
        return Verdict.UNKNOWN, '传输或响应保存不完整，当前无法判定协议可用性。'
    if isinstance(status, int) and 500 <= status <= 599:
        return Verdict.FAIL, '已确认的协议发现入口返回服务端HTTP 5xx错误。'
    if status != 200:
        return Verdict.UNKNOWN, '当前HTTP响应可能涉及重定向、会话或未支持传输，未认定业务失败。'
    if raw.lstrip().startswith((b'event:', b'data:', b':')):
        return Verdict.UNKNOWN, '当前响应为未适配的SSE传输，未按JSON业务响应评分。'
    try:
        envelope = json.loads(raw)
        if isinstance(envelope, dict) and 'error' in envelope:
            return Verdict.UNKNOWN, '工具发现返回协议错误，尚不能区分会话、授权或服务限制。'
        _tools(_result(raw, request['id']))
    except (ValueError, TypeError):
        return Verdict.FAIL, '已确认入口的HTTP 200响应未匹配本次JSON-RPC标识及标准工具列表。'
    elapsed = observation.get('elapsed_ms')
    if not isinstance(elapsed, (float, int)) or not isfinite(elapsed) or elapsed < 0:
        return Verdict.UNKNOWN, '本次请求缺少有效耗时记录。'
    return Verdict.PASS, '本次MCP工具发现请求及协议结果对应；仅评价该发现接口。'


def _complete(response: dict) -> bool:
    obs = response['observation']
    return bool(obs and obs['http_status'] == 200 and not obs['error_kind'] and obs['body_complete'])


def _sample_availability(evidence, prefix: str, url: str, headers: dict,
                         descriptor: dict | None = None) -> list[SampleExplanation]:
    slots = [{'key': f'{prefix}-availability-{slot:03d}', 'offset_seconds': (slot - 1) * 30,
              'json': {'jsonrpc': '2.0', 'id': f'{prefix}-availability-{slot:03d}', 'method': 'tools/list', 'params': {}}}
             for slot in range(1, 11)]
    policy = evidence.root / 'docs/adr/0010-service-contract-policy.md'
    policy_ref = {'path': policy.relative_to(evidence.root).as_posix(), 'sha256': hashlib.sha256(policy.read_bytes()).hexdigest()}
    evidence.inputs[policy_ref['path']] = policy_ref['sha256']
    plan = _save(evidence, f'{prefix}-availability-plan.json', {
        'policy_version': 'service-contract-v1', 'purpose': 'availability', 'url': url, 'method': 'POST',
        'headers': headers, 'created_at': datetime.now(timezone.utc).isoformat(), 'slots': slots,
        'interval_seconds': 30, 'retries': 0, 'scope': 'MCP tools/list协议发现接口；不代表业务调用可用',
        'policy': policy_ref, 'descriptor': descriptor,
    })
    samples, stopped, origin = [], False, time.monotonic()
    for slot in slots:
        key = slot['key']
        if stopped:
            skip = _save(evidence, f'{key}.skip.json', {'purpose': 'availability', 'request_sent': False,
                         'reason': '此前鉴权、付费或限流响应已触发停止', 'scheduled_offset_seconds': slot['offset_seconds']})
            response = {'observation': None, 'raw': b'', 'evidence': [skip]}
        else:
            while (remaining := origin + slot['offset_seconds'] - time.monotonic()) > 0:
                time.sleep(min(30.0, remaining))
            response = evidence.request(key, url, 'POST', slot['json'], headers,
                                        purpose=MeasurementPurpose.AVAILABILITY)
        obs = response['observation']
        verdict, reason = availability_verdict(obs, response['raw'])
        if obs and obs['http_status'] in STOP_STATUSES:
            stopped = True
        paths = [plan['path'], *(item['path'] for item in response['evidence'])]
        sample = ScoredSample(sample_id=key, task_key=f'availability:{key}', purpose=MeasurementPurpose.AVAILABILITY,
            verdict=verdict, elapsed_ms=obs['elapsed_ms'] if obs else None, reason=reason, evidence=paths)
        explanation = SampleExplanation(sample=sample,
            observed_at=datetime.fromisoformat(obs['observed_at']) if obs else None,
            title=f'MCP发现接口 · 第 {len(samples) + 1} 次访问', input_summary=f'向登记端点发送tools/list请求；槽位标识 {key}。',
            claimed_output='期望返回与请求标识一致的JSON-RPC result.tools列表；不调用任何业务工具。',
            independent_result=reason, checks=[ReportFinding(label='实际协议请求与响应', verdict=verdict, explanation=reason)])
        _save(evidence, f'{key}.sample.json', {'sample': explanation.model_dump(mode='json'),
              'scheduled_offset_seconds': slot['offset_seconds'], 'measurement_purpose': 'availability'})
        samples.append(explanation)
    return samples


def collect_protocol_evaluation(registration: dict, evidence) -> tuple[list[CapabilityCoverage], list[SampleExplanation], list[str]]:
    prefix = 'protocol-' + secrets.token_hex(6)
    capabilities, samples, limitations, discovered_names = [], [], [], set()
    services = registration.get('services', [])
    _save(evidence, f'{prefix}-discovery-plan.json', {'created_at': datetime.now(timezone.utc).isoformat(),
        'services': services, 'measurement_purpose': 'background', 'business_calls': False,
        'methods': ['GET documentation', 'initialize', 'notifications/initialized', 'tools/list'],
        'availability': '仅首个已确认适配的MCP工具发现接口预先安排10个全新槽位', 'retries': 0})

    def add(tool: dict, protocol: str, finding: ReportFinding, extra: list[str] | None = None):
        name = tool['name']
        description = tool.get('description')
        discovered_names.add(name)
        capabilities.append(CapabilityCoverage(capability_id=f'{prefix}-capability-{len(capabilities) + 1:03d}',
            operation=name, description=description if isinstance(description, str) and description else '登记资料尚未提供该操作的业务说明。',
            protocol=protocol, tested_scope='仅取得声明、接口文档或协议发现结果，尚未判定实际业务正确性。',
            sample_ids=[], findings=[finding], missing_evidence=[*BUSINESS_GAPS, *(extra or [])]))

    for index, service in enumerate(services, 1):
        key, name, url = f'{prefix}-service-{index:03d}', str(service.get('name', '')), service.get('endpoint')
        label, tools, extra, ready_headers, response = name.lower(), [], [], None, None
        document, descriptor = None, None
        finding = ReportFinding(label='登记服务与协议发现', verdict=Verdict.UNKNOWN,
                                explanation='当前服务类型尚无受支持的只读协议发现。')
        try:
            if not isinstance(url, str) or not url:
                raise ValueError('登记服务未提供可读取的端点。')
            if label == 'mcp' and urlsplit(url).path.lower().endswith('.json'):
                response = evidence.request(key + '-document', url)
                if not _complete(response):
                    raise ValueError('MCP描述文件未取得完整响应。')
                document = json.loads(response['raw'])
                if not isinstance(document, dict):
                    raise ValueError('MCP描述文件不是JSON对象。')
                remote = descriptor_remote(document)
                if remote is not None:
                    descriptor = {'url': url, 'remote_url': remote,
                        'sha256': hashlib.sha256(response['raw']).hexdigest(), 'evidence': response['evidence']}
                    _save(evidence, key + '-descriptor-binding.json', descriptor)
                    url = remote
            if label == 'mcp' and (descriptor is not None or not urlsplit(url).path.lower().endswith('.json')):
                init = {'jsonrpc': '2.0', 'id': key + '-initialize', 'method': 'initialize',
                        'params': {'protocolVersion': '2025-03-26', 'capabilities': {},
                                   'clientInfo': {'name': 'Web3ReputationReadOnly', 'version': '0.1.0'}}}
                response = evidence.request(key + '-initialize', url, 'POST', init, ACCEPT)
                if not _complete(response):
                    raise ValueError('MCP初始化尚未取得完整JSON响应；可能需要授权、会话或未支持的传输。')
                result = _result(response['raw'], init['id'])
                version = result.get('protocolVersion')
                if version not in VERSIONS or not isinstance(result.get('capabilities'), dict) or not isinstance(result['capabilities'].get('tools'), dict):
                    raise ValueError('初始化未确认受支持版本与工具发现能力。')
                server = result.get('serverInfo')
                if not isinstance(server, dict) or any(not isinstance(server.get(field), str) or not server[field] for field in ('name', 'version')):
                    raise ValueError('初始化缺少标准服务名称或版本。')
                headers = {**ACCEPT, 'MCP-Protocol-Version': version}
                response = evidence.request(key + '-initialized', url, 'POST',
                    {'jsonrpc': '2.0', 'method': 'notifications/initialized'}, headers)
                observed = response['observation']
                if not observed or observed['http_status'] not in (202, 204) or observed['error_kind']:
                    raise ValueError('初始化通知未被确认；会话或传输条件尚未适配。')
                body = {'jsonrpc': '2.0', 'id': key + '-tools', 'method': 'tools/list', 'params': {}}
                response = evidence.request(key + '-tools', url, 'POST', body, headers)
                if not _complete(response):
                    raise ValueError('MCP工具发现未取得完整JSON响应；尚不能安排可用性采样。')
                result = _result(response['raw'], body['id'])
                tools = _tools(result)
                finding = ReportFinding(label='MCP工具发现协议', verdict=Verdict.PASS,
                    explanation=f'已核对初始化及工具列表响应，发现 {len(tools)} 个工具；这不是业务工具调用通过。')
                if result.get('nextCursor'):
                    extra.append('本次只取得工具列表首页，尚未读取后续分页。')
                ready_headers = headers
            elif label in {'mcp', 'a2a', 'http', 'https', 'api', 'openapi', 'web'}:
                if document is None:
                    response = evidence.request(key + '-document', url)
                    if not _complete(response):
                        raise ValueError('登记的接口资料未取得完整响应，保留缺项。')
                    document = json.loads(response['raw'])
                    if not isinstance(document, dict):
                        raise ValueError('接口资料不是已支持的JSON对象文档。')
                declared = document.get('skills' if label == 'a2a' else 'tools', [])
                tools = [item for item in declared if isinstance(item, dict) and isinstance(item.get('name'), str) and item['name'].strip()] if isinstance(declared, list) else []
                if isinstance(document.get('paths'), dict):
                    for route, operations in document['paths'].items():
                        if not isinstance(operations, dict):
                            continue
                        for method, operation in operations.items():
                            if method.lower() not in {'get', 'post', 'put', 'patch', 'delete', 'head', 'options'} or not isinstance(operation, dict):
                                continue
                            operation_id = operation.get('operationId')
                            tools.append({'name': operation_id if isinstance(operation_id, str) and operation_id else f'{method.upper()} {route}',
                                          'description': operation.get('summary') or operation.get('description')})
                finding = ReportFinding(label='接口资料读取', verdict=Verdict.PASS,
                    explanation='已保存JSON接口资料；当前未据Card、文档或Schema形成业务评分。')
                extra.append('当前仅读取接口描述，尚未适配实际业务调用。')
            else:
                extra.append('该服务类型尚无受支持的只读协议发现。')
        except (ValueError, TypeError, KeyError, OSError, PermissionError):
            finding = ReportFinding(label='登记服务与协议发现', verdict=Verdict.UNKNOWN,
                explanation='未取得可确认的标准JSON协议结果；鉴权、会话、SSE或其他接口格式尚未适配，未调用业务工具。')
            extra.append('该服务的协议资料或传输条件仍待核实。')
            if response and response['observation']:
                obs = response['observation']
                extra.append(f'协议资料读取观测：HTTP {obs["http_status"]}；传输状态 {obs["error_kind"] or "已保留响应，协议结果待核实"}。')
        for tool in tools:
            add(tool, name or '未声明协议', finding, extra)
        if not tools:
            extra.append(f'登记的{name or "未命名"}服务尚未确认可识别的业务操作，未计为功能。')
        limitations.extend(extra)
        if ready_headers is not None and not samples:
            samples = _sample_availability(evidence, prefix, url, ready_headers, descriptor)
    for tool in registration.get('declared_tools', []):
        if isinstance(tool, dict) and isinstance(tool.get('name'), str) and tool['name'].strip() and tool['name'] not in discovered_names:
            add(tool, '注册声明', ReportFinding(label='注册功能声明', verdict=Verdict.UNKNOWN,
                explanation='注册资料描述了该操作，尚未取得对应业务调用与独立判据。'))
    if not capabilities:
        limitations.append('当前未取得可识别的业务操作声明或工具列表，功能列表保留为空。')
    limitations.extend(['协议发现与工具Schema不代表实际业务正确或交易履约已通过。',
        '当前尚无功能和交易维度的独立实际任务样本，不计算综合分。'])
    return capabilities, samples, list(dict.fromkeys(limitations))
