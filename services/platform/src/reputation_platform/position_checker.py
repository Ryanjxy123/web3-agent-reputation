"""Bounded, reviewed position reads, rebuilt from original protocol and RPC bytes."""

from datetime import datetime, timedelta, timezone
import hashlib
import json
from math import isfinite
from pathlib import Path
from urllib.parse import urlsplit

from reputation_core import CapabilityCoverage, MeasurementPurpose, ProbeObservation, ReportFinding, SampleExplanation, ScoredSample, Verdict
from reputation_platform.position_adapters import ADAPTERS, match_position_adapter, parse_position_claim, position_request
from reputation_platform.position_oracle import FACTORY, NPM, canonical_position_id, position_reference, verify_position_record
from reputation_platform.protocol_evaluation import ACCEPT, VERSIONS, _result, _save, _tools
from reputation_platform.query_checker import QueryEvidence, _complete
from reputation_platform.query_oracle import _quantity
from reputation_platform.registration_discovery import RPC_CONFIG, _configuration, _rpc, _write, verify_registration_proof

CHECKER_ID = 'query.pancakeswap-v3-position'
VERSION = 'v1'
CAPABILITY_ID = 'query-pancakeswap-v3-position'
POLICY = 'docs/adr/0013-pancakeswap-v3-position-checker.md'
CONFIG = 'configs/position-read-tasks-v1.json'
PLAN_NAME = 'position-checker-plan.json'
SCOPE = '仅核验BNB Chain PancakeSwap v3 NFT的token0、token1、fee、tickLower、tickUpper及任务ID；独立RPC固定链头减64区块。'
GAPS = ['动态tick、in_range、liquidity、费用、价格、价值及策略建议未评价。',
        '未证明Agent执行归属、交易或履约，不产生B或综合分；F仍遵守七个不同任务门槛。']


class NotApplicable(ValueError):
    """Authentic discovery did not expose this reviewed contract."""


def _time(value):
    result = datetime.fromisoformat(value)
    if result.tzinfo is None:
        raise ValueError('Position evidence time requires an explicit timezone')
    return result


def _finished(obs):
    if obs.observed_at.tzinfo is None or not isfinite(obs.elapsed_ms) or obs.elapsed_ms < 0:
        raise ValueError('Position observation requires a finite duration and timezone')
    return obs.observed_at + timedelta(milliseconds=obs.elapsed_ms)


def _must_stop(obs, raw):
    """Use the same host stop for HTTP and top-level JSON-RPC quota failures."""
    stop = obs.http_status in (401, 402, 403, 429)
    if obs.method == 'POST':
        try:
            data = json.loads(raw)
            error = data.get('error') if isinstance(data, dict) else None
            stop |= isinstance(error, dict) and (error.get('code') in (-32005, -32016, 429)
                or any(term in str(error.get('message', '')).lower() for term in ('rate limit', 'quota', 'too many requests')))
        except (ValueError, TypeError):
            pass
    return stop


class PositionEvidence(QueryEvidence):
    """Reuse the old hash/provenance reader, with stricter rules for this new policy."""

    def __init__(self, root, hashes):
        super().__init__(root, hashes)
        self.requests = {}

    def request(self, name, url, purpose, body=None):
        obs, raw, plan = super().request(name, url, purpose, body)
        self._bounds(plan)
        self._response_bounds(plan, obs, raw)
        if obs:
            if name.removesuffix('.request-plan.json') + '.skip.json' in self.hashes:
                raise ValueError('Position request cannot be both sent and explicitly unsent')
            self.times.append(_finished(obs))
            self.requests[name] = (obs, raw)
        else:
            self.skip(name.removesuffix('.request-plan.json') + '.skip.json', plan['key'])
        return obs, raw, plan

    @staticmethod
    def _bounds(plan):
        timeout = plan.get('timeout_seconds', 15)
        size = plan.get('max_body_bytes', 1048576)
        if (type(timeout) not in (int, float) or not isfinite(timeout) or not 0 < timeout <= 45
            or type(size) is not int or not 0 < size <= 1048576):
            raise ValueError('Position request exceeds the retained timeout or body bound')
        _time(plan['created_at'])

    @staticmethod
    def _response_bounds(plan, obs, raw):
        if len(raw) > plan.get('max_body_bytes', 1048576):
            raise ValueError('Retained position response exceeds its frozen body limit')
        if _complete(obs) and obs.elapsed_ms > plan.get('timeout_seconds', 15) * 1000:
            raise ValueError('Complete position response exceeded its frozen request timeout')

    def skip(self, name, key, *, reason=None):
        record = self.json(name)
        if (not name.endswith('.skip.json') or record.get('request_sent') is not False
            or (record.get('key', key) != key) or not isinstance(record.get('reason'), str)
            or record['reason'] not in {'public_reads_disabled', 'host_stopped', 'request_budget_exhausted',
                                        'reference_unavailable', 'reference_dependency_unavailable'}
            or (reason is not None and record['reason'] != reason)
            or name.removesuffix('.skip.json') + '.observation.json' in self.hashes):
            raise ValueError('Unsent position request requires its own explicit skip')
        if 'created_at' in record:
            self.times.append(_time(record['created_at']))
        return record

    def get(self, name, url):
        plan = self.json(name)
        if (not name.endswith('.request-plan.json') or plan['url'] != url or plan['method'] != 'GET'
            or plan['json'] is not None or plan['measurement_purpose'] != 'background'
            or plan['retries'] != 0 or plan.get('headers') is not None):
            raise ValueError('Agent Card read differs from its original registered GET')
        self._bounds(plan)
        stem = name.removesuffix('.request-plan.json')
        if stem + '.observation.json' not in self.hashes:
            self.skip(stem + '.skip.json', plan['key'])
            return None, b'', plan
        obs = ProbeObservation.model_validate_json(self.read(stem + '.observation.json'))
        if stem + '.skip.json' in self.hashes:
            raise ValueError('Agent Card read cannot be both sent and explicitly unsent')
        if (plan['execution_enabled'] is not True or obs.request_key != plan['key'] or obs.url != url
            or obs.method != 'GET' or obs.purpose != MeasurementPurpose.BACKGROUND
            or obs.request_json not in (None, 'null') or _time(plan['created_at']) > obs.observed_at):
            raise ValueError('Agent Card observation belongs to another request')
        self.times.extend((obs.observed_at, _finished(obs)))
        raw = b''
        if obs.response_file:
            path = (self.reader.root / name).parent / obs.response_file
            if path.resolve().parent != (self.reader.root / name).parent.resolve():
                raise ValueError('Agent Card response escaped its original directory')
            raw = self.read(path.relative_to(self.reader.root).as_posix())
            if hashlib.sha256(raw).hexdigest() != obs.response_sha256:
                raise ValueError('Agent Card raw response differs from its observation')
        self.requests[name] = (obs, raw)
        self._response_bounds(plan, obs, raw)
        return obs, raw, plan

    def verify_stops(self, should_stop=_must_stop):
        stopped = set()
        for obs, raw in sorted(self.requests.values(), key=lambda item: item[0].observed_at):
            host = urlsplit(obs.url).hostname
            if host in stopped:
                raise ValueError('Position evidence sent a request after an authentication, payment or rate-limit host stop')
            if should_stop(obs, raw):
                stopped.add(host)


def _registration(source, proof_path, canonical):
    proof = source.json(proof_path)
    refs = [*proof['source_refs'], proof['rpc_configuration']]
    for record in [proof.get('directory'), proof.get('document'), *proof.get('rpc', {}).values()]:
        if record:
            refs.extend(record['evidence'])
    for ref in refs:
        if source.hashes.get(ref['path']) != ref['sha256']:
            raise ValueError('Registration dependency absent from position manifest')
        raw = source.read(ref['path'])
        if ref['path'].endswith('.observation.json'):
            source.times.append(_finished(ProbeObservation.model_validate_json(raw)))
    return verify_registration_proof(source.reader.root, proof_path, canonical)


def _discovery(source, identity, descriptor, *, match=match_position_adapter):
    protocol = descriptor.get('protocol')
    endpoint = descriptor.get('endpoint')
    if protocol == 'MCP' and set(descriptor) == {'protocol', 'endpoint', 'initialize_request', 'initialized_request', 'catalog_request'}:
        initial, raw, init = source.request(descriptor['initialize_request'], endpoint, MeasurementPurpose.BACKGROUND)
        try:
            negotiated = _result(raw, init['key']) if _complete(initial) else {}
        except (ValueError, TypeError):
            raise NotApplicable('Position MCP initialization has no complete negotiated result') from None
        version = negotiated.get('protocolVersion')
        if (not _complete(initial) or init['json'].get('method') != 'initialize' or version not in VERSIONS
            or not isinstance(negotiated.get('capabilities'), dict)
            or not isinstance(negotiated['capabilities'].get('tools'), dict) or init['headers'] != ACCEPT):
            raise NotApplicable('Position MCP discovery lacks confirmed initialization')
        headers = {**ACCEPT, 'MCP-Protocol-Version': version}
        notified, _, notification = source.request(descriptor['initialized_request'], endpoint, MeasurementPurpose.BACKGROUND,
            {'jsonrpc': '2.0', 'method': 'notifications/initialized'})
        catalog_obs, raw, catalog = source.request(descriptor['catalog_request'], endpoint, MeasurementPurpose.BACKGROUND)
        if not notified or notified.http_status not in (202, 204) or notified.error_kind or not notified.body_complete or not _complete(catalog_obs):
            raise NotApplicable('Position MCP discovery has an incomplete notification or catalog')
        if (notification['headers'] != headers or _time(notification['created_at']) < _finished(initial)
            or catalog['headers'] != headers
            or catalog['json'] != {'jsonrpc': '2.0', 'id': catalog['key'], 'method': 'tools/list', 'params': {}}
            or _time(catalog['created_at']) < _finished(notified)):
            raise ValueError('Position tool catalog must follow negotiated initialization')
        try:
            catalog_value = _tools(_result(raw, catalog['key']))
        except (ValueError, TypeError):
            raise NotApplicable('Position MCP catalog is not an applicable complete tool list') from None
        completed = _finished(catalog_obs)
    elif protocol == 'A2A' and set(descriptor) == {'protocol', 'endpoint', 'card_request'}:
        plan = source.json(descriptor['card_request'])
        registered = {s.get('endpoint') for s in identity.get('services', [])
                      if isinstance(s, dict) and str(s.get('name', '')).lower() in ('a2a', 'agent-card')}
        if plan['url'] not in registered:
            raise ValueError('Agent Card URL was not explicitly authenticated in registration')
        observed, raw, _ = source.get(descriptor['card_request'], plan['url'])
        if not _complete(observed):
            raise NotApplicable('Position A2A matching requires a complete retained Card')
        try:
            catalog_value = json.loads(raw)
        except (ValueError, TypeError):
            raise NotApplicable('Position Card is not applicable JSON') from None
        headers, completed = None, _finished(observed)
    else:
        raise ValueError('Unknown position discovery contract')
    adapter = match(identity, endpoint, catalog_value)
    if adapter is None:
        raise NotApplicable('No reviewed position adapter matches authenticated endpoint and exact schema')
    return adapter, headers, completed


def _configuration_source(source):
    config = source.json(CONFIG)
    ids = config.get('position_ids')
    if (config.get('schema_version') != 'position-read-tasks-v1' or type(config.get('chain')) is not int
        or config['chain'] != 56 or config.get('npm') != NPM or config.get('factory') != FACTORY
        or not isinstance(ids, list) or not 1 <= len(ids) <= 7
        or any(canonical_position_id(value) != value for value in ids) or len(set(ids)) != len(ids)):
        raise ValueError('Position tasks must be a frozen bounded list for the reviewed chain and contracts')
    selection = config.get('selection_source')
    if selection is not None:
        if source.hashes.get(selection['path']) != selection['sha256']:
            raise ValueError('Position selection provenance absent from verified manifest')
        source.read(selection['path'])
    source.read(POLICY)
    source.read(RPC_CONFIG.as_posix())
    return config


def _fixed_block(values):
    try:
        head = _quantity(values['head'])
        return hex(head - 64) if head >= 64 else None
    except (KeyError, TypeError, ValueError):
        return None


def _fixed_specs(block):
    return {'header': ('eth_getBlockByNumber', [block, False]),
            'npm_code': ('eth_getCode', [NPM, block]),
            'factory': ('eth_call', [{'to': NPM, 'data': '0xc45a0155'}, block]),
            'factory_code': ('eth_getCode', [FACTORY, block])}


def _token_specs(token_id, block):
    suffix = f'{int(token_id):064x}'
    return {'positions': ('eth_call', [{'to': NPM, 'data': '0x99fbab88' + suffix}, block]),
            'owner': ('eth_call', [{'to': NPM, 'data': '0x6352211e' + suffix}, block])}


def _rpc_value(observed, raw, key):
    if _complete(observed):
        try:
            data = json.loads(raw)
            if isinstance(data, dict) and data.get('jsonrpc') == '2.0' and data.get('id') == key and 'error' not in data:
                return data.get('result')
        except (ValueError, TypeError):
            pass
    return None


def _prior_availability(source, directory, created, endpoint, headers):
    """Authenticate this run's earlier slots so their host stops also bind business reads."""
    slots = {}
    for name in source.hashes:
        if Path(name).parent != directory or not name.endswith('-availability-plan.json'):
            continue
        plan = source.json(name)
        if (plan.get('policy_version') != 'service-contract-v1' or plan.get('purpose') != 'availability'
            or plan.get('url') != endpoint or plan.get('method') != 'POST'
            or plan.get('headers') != headers or _time(plan['created_at']) >= created):
            continue
        for slot in plan.get('slots', []):
            key = slot.get('key')
            body = {'jsonrpc': '2.0', 'id': key, 'method': 'tools/list', 'params': {}}
            if not isinstance(key, str) or not key or key in slots or slot.get('json') != body:
                raise ValueError('Earlier availability slots require unique keys and their original discovery bodies')
            slots[key] = (_time(plan['created_at']), slot)
    for key, (planned, slot) in slots.items():
        stem = (directory / key).as_posix()
        if stem + '.observation.json' not in source.hashes:
            continue
        observed, _, original = source.request(stem + '.request-plan.json', endpoint,
                                               MeasurementPurpose.AVAILABILITY, slot['json'])
        if (not observed or original['key'] != key or original.get('headers') != headers
            or not planned <= _time(original['created_at']) < created or _finished(observed) > created):
            raise ValueError('Earlier availability observation is not bound to its prior slot and completed execution')
    return slots


def rebuild_position(root: Path, name: str, hashes: dict[str, str]):
    """Rebuild all frozen tasks and the full capability; integrity errors reject publication."""
    source = PositionEvidence(root, hashes)
    plan = source.json(name)
    if (plan.get('schema_version') != 'position-checker-evidence-v1' or plan.get('checker_id') != CHECKER_ID
        or plan.get('checker_version') != VERSION or plan.get('policy_version') != 'service-contract-v1'):
        raise ValueError('Unknown position Checker or evidence policy')
    execution = source.json(plan['execution_plan'])
    config = _configuration_source(source)
    identity = _registration(source, execution['proof_path'], execution['canonical'])
    adapter, headers, discovery_end = _discovery(source, identity, execution['discovery'])
    expected = {**adapter, 'schema_version': 'position-execution-v1', 'checker_id': CHECKER_ID,
                'checker_version': VERSION, 'policy_version': 'service-contract-v1', 'chain': config['chain'],
                'npm': NPM, 'factory': FACTORY, 'position_ids': config['position_ids'],
                'max_business_calls': len(config['position_ids']), 'max_requests': 28, 'max_total_requests': 64,
                'timeout_seconds': 45, 'max_body_bytes': 1048576, 'paid_calls': 0, 'retries': 0, 'mainnet_writes': False,
                'config': {'path': CONFIG, 'sha256': hashes[CONFIG]}, 'policy': {'path': POLICY, 'sha256': hashes[POLICY]}}
    if any(execution.get(key) != value for key, value in expected.items()):
        raise ValueError('Position execution differs from the frozen reviewed zero-cost read-only contract')
    created, indexed = _time(execution['created_at']), _time(plan['created_at'])
    if discovery_end > created or any(t > created for t in source.times):
        raise ValueError('Position execution must be frozen after registration and completed discovery')
    source.times.extend((created, indexed))
    starts = (execution.get('request_count_start'), execution.get('request_count_after_discovery'), plan.get('request_count_end'))
    if any(type(n) is not int or not 0 <= n <= 64 for n in starts) or not starts[0] <= starts[1] <= starts[2]:
        raise ValueError('Position request counters exceed the scoped global budget')
    fresh_card = execution.get('new_card_request')
    if fresh_card is not None and (adapter['protocol'] != 'A2A' or fresh_card != execution['discovery'].get('card_request')):
        raise ValueError('Only the exact registered Card can be a new discovery read')
    card_count = int(fresh_card is not None and fresh_card.removesuffix('.request-plan.json') + '.observation.json' in hashes)
    if starts[1] - starts[0] != card_count:
        raise ValueError('Position Card request counter differs from retained observations')
    requests, observations, samples = [], [], []
    rpc_url = _configuration(root)['chains']['56']['rpc_url']

    def rpc(field, ref, spec, earliest):
        if spec is None:
            record = source.skip(ref, 'position-reference-' + field.replace('_', '-'), reason='reference_dependency_unavailable')
            if record.get('field') != field or _time(record['created_at']) < earliest:
                raise ValueError('Position dependency skip is not bound to its frozen field')
            return None, earliest
        request = source.json(ref)
        body = {'jsonrpc': '2.0', 'id': request['key'], 'method': spec[0], 'params': spec[1]}
        observed, raw, original = source.request(ref, rpc_url, MeasurementPurpose.BACKGROUND, body)
        if (original.get('rpc_configuration_source') != 'operator-static-not-metadata'
            or original.get('headers') is not None or original['key'] != 'position-reference-' + field.replace('_', '-')
            or _time(original['created_at']) < earliest):
            raise ValueError('Position reference must use the fresh operator RPC in dependency order')
        requests.append(ref)
        if observed:
            observations.append(observed)
        return _rpc_value(observed, raw, request['key']), _finished(observed) if observed else earliest

    shared = plan['rpc_requests']
    if set(shared) != {'chain', 'head', 'header', 'npm_code', 'factory', 'factory_code'}:
        raise ValueError('All six planned position reference fields are required')
    values, ends = {}, []
    for field, spec in {'chain': ('eth_chainId', []), 'head': ('eth_blockNumber', [])}.items():
        values[field], end = rpc(field, shared[field], spec, created)
        ends.append(end)
    block = _fixed_block(values)
    for field, spec in _fixed_specs(block).items():
        values[field], end = rpc(field, shared[field], spec if block is not None else None, max(ends))
        ends.append(end)
    shared_end = max(ends)
    tasks = plan['tasks']
    if not isinstance(tasks, list) or [task.get('position_id') for task in tasks] != config['position_ids']:
        raise ValueError('Every frozen position must retain exactly one task in its original order')
    for task in tasks:
        token_id, local = task['position_id'], dict(values)
        if set(task) != {'position_id', 'rpc_requests', 'business_request'} or set(task['rpc_requests']) != {'positions', 'owner'}:
            raise ValueError('Each position requires both original existence and immutable field references')
        ready = shared_end
        for field, spec in _token_specs(token_id, block).items():
            local[field], end = rpc(token_id + '-' + field, task['rpc_requests'][field], spec if block is not None else None, shared_end)
            ready = max(ready, end)
        try:
            position_reference(token_id, 56, NPM, FACTORY, local)
            reference_ready = True
        except ValueError:
            reference_ready = False
        key, business, claim = 'position-business-' + token_id, None, None
        ref = task['business_request']
        if ref.endswith('.skip.json'):
            record = source.skip(ref, key, reason='reference_unavailable')
            if reference_ready or _time(record['created_at']) < ready:
                raise ValueError('Business skip contradicts a complete reference or its dependency timing')
        else:
            business, raw, original = source.request(ref, adapter['endpoint'], MeasurementPurpose.FUNCTIONAL,
                                                   position_request(adapter, key, token_id))
            if (not reference_ready or original['key'] != key or original['headers'] != headers
                or _time(original['created_at']) < ready):
                raise ValueError('Position business read requires a completed valid reference and frozen protocol input')
            requests.append(ref)
            if business:
                observations.append(business)
            claim = parse_position_claim(adapter, raw, key) if _complete(business) else None
        verdict, reason, detail = verify_position_record(claim, token_id, 56, NPM, FACTORY, local)
        check = ReportFinding(label='五项静态仓位事实与固定区块RPC独立核验', verdict=verdict, explanation=reason)
        samples.append(SampleExplanation(sample=ScoredSample(sample_id=key,
            task_key=f'{CHECKER_ID}:56:{NPM}:{token_id}', purpose=MeasurementPurpose.FUNCTIONAL,
            verdict=verdict, reason=reason, evidence=[], elapsed_ms=business.elapsed_ms if business else None),
            capability_id=CAPABILITY_ID, observed_at=business.observed_at if business else None,
            title=f'PancakeSwap v3 静态仓位 · #{token_id}',
            input_summary=f'链56；NPM {NPM}；positionId {token_id}；登记端点 {adapter["endpoint"]}；{adapter["tool"]}只读。',
            claimed_output=json.dumps(claim, ensure_ascii=False, sort_keys=True) if claim else '未取得可适配的完整静态仓位输出；未发送请求或网络、参考、授权、工具结果不足。',
            independent_result=reason + ('；独立重建：' + json.dumps(detail, ensure_ascii=False, sort_keys=True) if detail else ''), checks=[check]))
    if (len(requests) != len(set(requests)) or len(observations) != starts[2] - starts[1]
        or starts[2] - starts[0] > 28 or any(t > indexed for t in source.times)):
        raise ValueError('Position retained requests, completed times or phase budget differ from the frozen plan')
    expected_files = {name for ref in requests for name in (ref,
        ref.removesuffix('.request-plan.json') + '.observation.json', ref.removesuffix('.request-plan.json') + '.skip.json')
        if name in hashes}
    expected_files.update(ref for ref in shared.values() if ref.endswith('.skip.json'))
    for task in tasks:
        expected_files.update(ref for ref in [*task['rpc_requests'].values(), task['business_request']] if ref.endswith('.skip.json'))
    directory = Path(plan['execution_plan']).parent
    prior_slots = _prior_availability(source, directory, created, adapter['endpoint'], headers)
    for ref in hashes:
        if Path(ref).parent != directory or not ref.endswith(('.request-plan.json', '.observation.json', '.skip.json')):
            continue
        record = source.json(ref)
        time_field = 'observed_at' if ref.endswith('.observation.json') else 'created_at'
        if time_field not in record:
            if (not ref.endswith('.skip.json') or record.get('request_sent') is not False
                or ref.removesuffix('.skip.json') + '.observation.json' in hashes):
                raise ValueError('Only an explicitly unsent skip can inherit a retained request or prior slot time')
            # Existing DiscoveryEvidence unsent records inherit their request plan time.
            related = ref.removesuffix('.skip.json') + '.request-plan.json'
            if related in hashes:
                parent = source.json(related)
                if 'created_at' not in parent:
                    raise ValueError('A retained request plan must have its own creation time')
                timestamp = _time(parent['created_at'])
            else:
                prior = prior_slots.get(Path(ref).name.removesuffix('.skip.json'))
                if (prior is None or record.get('purpose') != 'availability'
                    or record.get('scheduled_offset_seconds') != prior[1].get('offset_seconds')):
                    raise ValueError('Untimed skip requires exactly one earlier authenticated availability slot')
                timestamp = prior[0]
        else:
            timestamp = _time(record[time_field])
        if created <= timestamp <= indexed and ref not in expected_files:
            raise ValueError('Position execution window contains an unindexed request, observation or skip')
    source.verify_stops()
    paths = sorted(source.reader.inputs)
    for sample in samples:
        sample.sample.evidence = paths
    capability = CapabilityCoverage(capability_id=CAPABILITY_ID, operation=adapter['tool'],
        description='查询PancakeSwap v3 NFT五项不可变仓位事实；两类协议使用同一独立判据。', protocol=adapter['protocol'],
        tested_scope=SCOPE, sample_ids=[sample.sample.sample_id for sample in samples],
        findings=[ReportFinding(label='认证提供方、适配器及政策', verdict=Verdict.PASS,
            explanation=f'已认证登记端点；提供方 {adapter["provider"]}；适配器 {adapter["id"]}；Checker {CHECKER_ID}/{VERSION}；政策 {POLICY}。')],
        missing_evidence=GAPS, capability_type='Query / Tool', checker_id=CHECKER_ID, checker_version=VERSION)
    return identity['canonical'], capability, samples, source.reader.inputs, source.times


def verify_position_samples(root: Path, report, hashes: dict[str, str]) -> set[str]:
    verified, capabilities = set(), set()
    for name in hashes:
        if Path(name).name != PLAN_NAME:
            continue
        canonical, capability, samples, _, times = rebuild_position(root, name, hashes)
        actual = [sample for sample in report.samples if name in sample.sample.evidence]
        matched = [item for item in report.capabilities if item.capability_id == CAPABILITY_ID]
        if (canonical != report.registration_reference or actual != samples or matched != [capability]
            or any(t > report.generated_at for t in times) or verified.intersection(s.sample.sample_id for s in samples)):
            raise ValueError('Position report differs from its fully reconstructed identity, capability or tasks')
        verified.update(sample.sample.sample_id for sample in samples)
        capabilities.add(CAPABILITY_ID)
    if any(c.checker_id == CHECKER_ID and c.checker_version == VERSION and c.capability_id not in capabilities for c in report.capabilities):
        raise ValueError('Position Checker metadata requires an independently reconstructed plan')
    return verified


def _skip(evidence, key, reason, **extra):
    return _save(evidence, key + '.skip.json', {'created_at': datetime.now(timezone.utc).isoformat(),
                 'key': key, 'request_sent': False, 'reason': reason, **extra})['path']


def collect_position_tasks(registration: dict, evidence):
    """Use only reviewed discovery, then freeze up to seven zero-cost, read-only tasks."""
    if not evidence.enabled:
        return [], [], []
    evidence.max_requests = min(getattr(evidence, 'max_requests', None) or 64, 64)
    start, previous_budget = evidence.request_count, evidence.max_requests
    evidence.max_requests = min(previous_budget, start + 28)
    source = PositionEvidence(evidence.root, evidence.inputs)
    identity = _registration(source, registration['proof_path'], registration['canonical'])
    selected, fresh_card = None, None
    for name in list(evidence.inputs):
        if not name.endswith('-tools.observation.json'):
            continue
        obs = ProbeObservation.model_validate_json(source.read(name))
        if not any(a['protocol'] == 'MCP' and a['endpoint'] == obs.url for a in ADAPTERS):
            continue
        stem = name.removesuffix('tools.observation.json')
        descriptor = {'protocol': 'MCP', 'endpoint': obs.url, 'catalog_request': stem + 'tools.request-plan.json',
                      'initialize_request': stem + 'initialize.request-plan.json', 'initialized_request': stem + 'initialized.request-plan.json'}
        try:
            selected = descriptor, *_discovery(source, identity, descriptor)[:2]
            break
        except NotApplicable:
            continue
    if selected is None:
        endpoints = {s.get('endpoint') for s in identity.get('services', []) if isinstance(s, dict) and str(s.get('name', '')).lower() == 'a2a'}
        for adapter in ADAPTERS:
            if adapter['protocol'] != 'A2A' or adapter['endpoint'] not in endpoints:
                continue
            registered_cards = [s['endpoint'] for s in identity['services'] if isinstance(s, dict)
                                and str(s.get('name', '')).lower() == 'agent-card' and isinstance(s.get('endpoint'), str)]
            allowed = {adapter['endpoint'], *registered_cards}
            candidates = [name for name in evidence.inputs if name.endswith('.request-plan.json')
                          and source.json(name).get('method') == 'GET' and source.json(name).get('url') in allowed]
            for name in candidates:
                descriptor = {'protocol': 'A2A', 'endpoint': adapter['endpoint'], 'card_request': name}
                try:
                    selected = descriptor, *_discovery(source, identity, descriptor)[:2]
                    break
                except NotApplicable:
                    continue
            if selected is None and len(registered_cards) == 1:
                key = 'position-agent-card'
                evidence.request(key, registered_cards[0])
                fresh_card = (evidence.run / (key + '.request-plan.json')).relative_to(evidence.root).as_posix()
                descriptor = {'protocol': 'A2A', 'endpoint': adapter['endpoint'], 'card_request': fresh_card}
                try:
                    selected = descriptor, *_discovery(source, identity, descriptor)[:2]
                except NotApplicable:
                    pass
            break
    if selected is None:
        evidence.max_requests = previous_budget
        return [], [], []
    descriptor, adapter, headers = selected
    for path in (CONFIG, POLICY):
        evidence._remember(evidence.root / path)
    config = json.loads((evidence.root / CONFIG).read_bytes())
    if config.get('selection_source'):
        evidence._remember(evidence.root / config['selection_source']['path'])
    config = _configuration_source(PositionEvidence(evidence.root, evidence.inputs))
    execution = _save(evidence, 'position-execution-plan.json', {**adapter,
        'schema_version': 'position-execution-v1', 'canonical': registration['canonical'], 'proof_path': registration['proof_path'],
        'checker_id': CHECKER_ID, 'checker_version': VERSION, 'policy_version': 'service-contract-v1',
        'created_at': datetime.now(timezone.utc).isoformat(), 'discovery': descriptor, 'new_card_request': fresh_card,
        'request_count_start': start, 'request_count_after_discovery': evidence.request_count,
        'chain': 56, 'npm': NPM, 'factory': FACTORY, 'position_ids': config['position_ids'],
        'config': {'path': CONFIG, 'sha256': evidence.inputs[CONFIG]}, 'policy': {'path': POLICY, 'sha256': evidence.inputs[POLICY]},
        'max_business_calls': len(config['position_ids']), 'max_requests': 28, 'max_total_requests': 64,
        'timeout_seconds': 45, 'max_body_bytes': 1048576, 'paid_calls': 0, 'retries': 0, 'mainnet_writes': False})

    def rpc(field, spec):
        key = 'position-reference-' + field.replace('_', '-')
        if spec is None:
            return _skip(evidence, key, 'reference_dependency_unavailable', field=field), None
        try:
            value = _rpc(evidence, 56, key, spec[0], spec[1])['value']
        except (ValueError, TypeError):
            value = None
        return (evidence.run / (key + '.request-plan.json')).relative_to(evidence.root).as_posix(), value

    shared, values = {}, {}
    for field, spec in {'chain': ('eth_chainId', []), 'head': ('eth_blockNumber', [])}.items():
        shared[field], values[field] = rpc(field, spec)
    block = _fixed_block(values)
    for field, spec in _fixed_specs(block).items():
        shared[field], values[field] = rpc(field, spec if block is not None else None)
    tasks = []
    for token_id in config['position_ids']:
        row, local = {'position_id': token_id, 'rpc_requests': {}}, dict(values)
        for field, spec in _token_specs(token_id, block).items():
            row['rpc_requests'][field], local[field] = rpc(token_id + '-' + field, spec if block is not None else None)
        key = 'position-business-' + token_id
        try:
            position_reference(token_id, 56, NPM, FACTORY, local)
            ready = True
        except ValueError:
            ready = False
        if ready:
            response = evidence.request(key, adapter['endpoint'], 'POST', position_request(adapter, key, token_id), headers,
                                        purpose=MeasurementPurpose.FUNCTIONAL)
            observed = ProbeObservation.model_validate(response['observation']) if response['observation'] else None
            if observed and _must_stop(observed, response['raw']):
                stop = evidence.root / 'runtime/prediction-network-stops' / (urlsplit(adapter['endpoint']).hostname + '.json')
                stop.parent.mkdir(exist_ok=True)
                if not stop.exists():
                    _write(stop, {'reason': 'Authentication, payment or rate limit',
                                  'source_run': evidence.run.relative_to(evidence.root).as_posix()})
            row['business_request'] = (evidence.run / (key + '.request-plan.json')).relative_to(evidence.root).as_posix()
        else:
            row['business_request'] = _skip(evidence, key, 'reference_unavailable')
        tasks.append(row)
    index = _save(evidence, PLAN_NAME, {'schema_version': 'position-checker-evidence-v1',
        'checker_id': CHECKER_ID, 'checker_version': VERSION, 'policy_version': 'service-contract-v1',
        'created_at': datetime.now(timezone.utc).isoformat(), 'execution_plan': execution['path'],
        'rpc_requests': shared, 'tasks': tasks, 'request_count_end': evidence.request_count})
    evidence.max_requests = previous_budget
    _, capability, samples, inputs, _ = rebuild_position(evidence.root, index['path'], evidence.inputs)
    evidence.inputs.update(inputs)
    return [capability], samples, GAPS
