"""Versioned query evaluation: frozen enumeration, independent F and observable B."""

from datetime import datetime, timezone
import json
import os
from pathlib import Path

from reputation_core import CapabilityCoverage, MeasurementPurpose, ProbeObservation, ReportFinding, SampleExplanation, ScoredSample, Verdict
from reputation_core.scoring import SERVICE_FULFILLMENT_POLICY_VERSION as POLICY_VERSION
from reputation_platform.position_checker import (
    CAPABILITY_ID, CHECKER_ID, CONFIG as OLD_CONFIG, NotApplicable, PositionEvidence,
    _discovery, _finished, _fixed_block, _fixed_specs, _prior_availability,
    _registration, _rpc_value, _skip, _time,
)
from reputation_platform.position_oracle import FACTORY, NPM
from reputation_platform.position_contracts import CONFIG as REVIEW_CONFIG, REVIEW_CONFIG_ENV, review_config_path
from reputation_platform.position_planner import RULE, decode_uint256, enumeration_indices, plan_specs, planner_slots, position_expected
from reputation_platform.protocol_evaluation import _save
from reputation_platform.query_checker import _complete
from reputation_platform.query_fulfillment import DEADLINE_MS, should_stop_business, verify_query_fulfillment
from reputation_platform.registration_discovery import RPC_CONFIG, _configuration, _rpc, _write

VERSION = 'v2'
POLICY = 'docs/adr/0020-observable-service-fulfillment.md'
PLAN_NAME = 'position-fulfillment-plan.json'
INTENT_NAME = 'position-fulfillment-intent.json'
SELECTION_NAME = 'position-fulfillment-selection.json'
EXECUTION_NAME = 'position-fulfillment-execution.json'
GAPS = ['仅评价本次仓位查询；不评价动态状态、策略、收益或其他能力。',
        'B仅证明可观察同步服务履约，不证明内部计算、异步Task历史、链上执行或隐蔽行为。']


def _contracts(source, config_path):
    from reputation_platform.position_contracts import load_contract_reviews
    config_path = review_config_path(source.reader.root, config_path)
    config = source.json(config_path)
    if config != load_contract_reviews(source.reader.root, config_path):
        raise ValueError('Adapter configuration differs from its verified local review')
    for adapter in config['adapters']:
        for ref in adapter['review_dependencies']:
            if source.hashes.get(ref['path']) != ref['sha256']:
                raise ValueError('Reviewed adapter provenance absent from manifest')
            source.read(ref['path'])
    return config


def _match(source, identity, descriptor, config_path):
    from reputation_platform.position_contracts import match_contract
    config = _contracts(source, config_path)
    return _discovery(source, identity, descriptor,
                      match=lambda identity, endpoint, catalog: match_contract(identity, endpoint, catalog, config))


def _discover(registration, evidence, config_path):
    source = PositionEvidence(evidence.root, evidence.inputs)
    identity = _registration(source, registration['proof_path'], registration['canonical'])
    for name in list(evidence.inputs):
        if not name.endswith('-tools.observation.json'):
            continue
        obs = ProbeObservation.model_validate_json(source.read(name))
        stem = name.removesuffix('tools.observation.json')
        descriptor = {'protocol': 'MCP', 'endpoint': obs.url, 'catalog_request': stem + 'tools.request-plan.json',
                      'initialize_request': stem + 'initialize.request-plan.json', 'initialized_request': stem + 'initialized.request-plan.json'}
        try:
            adapter, headers, _ = _match(source, identity, descriptor, config_path)
            return descriptor, adapter, headers, None
        except NotApplicable:
            pass
    config = _contracts(source, config_path)
    services = identity.get('services', [])
    for adapter in config['adapters']:
        if adapter['protocol'] != 'A2A' or not any(
            s.get('endpoint') == adapter['endpoint'] and str(s.get('name', '')).lower() == 'a2a' for s in services if isinstance(s, dict)):
            continue
        cards = {s['endpoint'] for s in services if isinstance(s, dict)
                 and str(s.get('name', '')).lower() == 'agent-card' and isinstance(s.get('endpoint'), str)}
        candidates = [name for name in evidence.inputs if name.endswith('.request-plan.json')
                      and source.json(name).get('method') == 'GET'
                      and source.json(name).get('url') in {*cards, adapter['endpoint']}]
        fresh = None
        if not candidates and len(cards) == 1:
            evidence.request('fulfillment-agent-card', next(iter(cards)))
            fresh = (evidence.run / 'fulfillment-agent-card.request-plan.json').relative_to(evidence.root).as_posix()
            candidates.append(fresh)
        for name in candidates:
            descriptor = {'protocol': 'A2A', 'endpoint': adapter['endpoint'], 'card_request': name}
            try:
                selected, headers, _ = _match(source, identity, descriptor, config_path)
                return descriptor, selected, headers, fresh
            except NotApplicable:
                pass
    return None


def _contract_fields(adapter):
    return {'checker_id': CHECKER_ID, 'checker_version': VERSION, 'policy_version': POLICY_VERSION,
            'selection_rule': RULE, 'chain': 56, 'npm': NPM, 'factory': FACTORY,
            'adapter': adapter, 'max_business_calls': 14, 'max_total_requests': 64,
            'deadline_ms': DEADLINE_MS, 'max_body_bytes': 1048576, 'max_timeout_seconds': 45,
            'retries': 0, 'paid_calls': 0, 'mainnet_writes': False}


def _snapshot(values):
    """Existence from the authenticated NPM enumerable contract; no fabricated owner."""
    from reputation_platform.query_oracle import _hex, _quantity
    try:
        block = _fixed_block(values)
        header = values['header']
        if (_quantity(values['chain']) != 56 or not block or header['number'] != block
            or int(_hex(values['factory'], 64), 16) != int(FACTORY, 16)):
            return False
        _hex(header['hash'], 64)
        _quantity(header['timestamp'])
        for field in ('npm_code', 'factory_code'):
            value = values[field]
            if not isinstance(value, str) or len(value) <= 2 or len(value) % 2 or not value.startswith('0x'):
                return False
            bytes.fromhex(value[2:])
        return True
    except (KeyError, TypeError, ValueError):
        return False


def _functional(claim, token_id, raw_position):
    try:
        expected = {'positionId': token_id, **position_expected(raw_position)}
    except (ValueError, TypeError):
        return Verdict.UNKNOWN, '独立确认区块仓位事实不可用。', {}
    if claim is None:
        return Verdict.UNKNOWN, '没有完整可适配的真实业务输出，不能判断五项事实。', {'expected': expected}
    mismatches = [key for key, value in expected.items() if claim.get(key) != value]
    if claim.get('reportedChain', 56) != 56 or claim.get('reportedPositionId', token_id) != token_id:
        mismatches.append('subject')
    detail = {'expected': expected, 'claimed': claim, 'mismatched_fields': mismatches}
    if mismatches:
        return Verdict.FAIL, '真实业务静态事实或对象与独立固定区块参考矛盾。', detail
    return Verdict.PASS, '五项静态事实与独立固定区块参考一致；本任务不进入B分母。', detail


def _sample(slot, observed, raw, adapter, raw_position):
    from reputation_platform.position_contracts import parse_contract
    key = f'fulfillment-business-{slot["slot"]}'
    token_id, purpose = slot['position_id'], MeasurementPurpose(slot['purpose'])
    claim = parse_contract(adapter, raw, key) if _complete(observed) else None
    if not slot['eligible']:
        verdict, reason, detail = Verdict.UNKNOWN, '冻结槽位不可执行：' + slot['reason'], {}
    elif purpose == MeasurementPurpose.FUNCTIONAL:
        verdict, reason, detail = _functional(claim, token_id, raw_position)
    else:
        verdict, reason = verify_query_fulfillment(observed, raw, key, token_id, claim)
        detail = {'request_id': key, 'subject': token_id, 'deadline_ms': DEADLINE_MS,
                  'delivery': claim, 'facts_compared': False}
    return SampleExplanation(sample=ScoredSample(sample_id=key,
        task_key=f'{CHECKER_ID}:56:{NPM}:{token_id}' if slot['eligible'] else f'{CHECKER_ID}:unresolved-slot:{slot["slot"]}',
        purpose=purpose, verdict=verdict, elapsed_ms=observed.elapsed_ms if observed else None, reason=reason, evidence=[]),
        capability_id=CAPABILITY_ID, observed_at=observed.observed_at if observed else None,
        title=f'{"功能事实" if purpose == MeasurementPurpose.FUNCTIONAL else "可观察履约"} · 仓位 #{token_id or "未解析"}',
        input_summary=f'固定NPM枚举索引 {slot["index"]}；positionId {token_id}；{adapter["protocol"]}；认证端点 {adapter["endpoint"]}。',
        claimed_output=json.dumps(claim, ensure_ascii=False, sort_keys=True) if claim else '未取得完整可适配业务交付。',
        independent_result=reason + '；' + json.dumps(detail, ensure_ascii=False, sort_keys=True),
        checks=[ReportFinding(label='独立静态事实' if purpose == MeasurementPurpose.FUNCTIONAL else '独立可观察履约重建', verdict=verdict, explanation=reason)])


def collect_position_fulfillment(registration, evidence):
    if not evidence.enabled:
        return [], [], []
    from reputation_platform.position_contracts import load_contract_reviews, request_contract
    # The same 64-request budget spans intake, A, planning, F and B.
    evidence.max_requests = min(evidence.max_requests or 64, 64)
    config_path = review_config_path(evidence.root, os.environ.get(REVIEW_CONFIG_ENV, REVIEW_CONFIG))
    config = load_contract_reviews(evidence.root, config_path)
    for path in (config_path, POLICY, OLD_CONFIG):
        evidence._remember(evidence.root / path)
    for adapter in config['adapters']:
        for ref in adapter['review_dependencies']:
            evidence._remember(evidence.root / ref['path'])
    start = evidence.request_count
    selected = _discover(registration, evidence, config_path)
    if selected is None:
        return [], [], []
    descriptor, adapter, headers, fresh_card = selected
    excluded = json.loads((evidence.root / OLD_CONFIG).read_bytes())['position_ids']
    intent = _save(evidence, INTENT_NAME, {**_contract_fields(adapter),
        'canonical': registration['canonical'], 'proof_path': registration['proof_path'],
        'review_config_path': config_path,
        'created_at': datetime.now(timezone.utc).isoformat(), 'discovery': descriptor, 'new_card_request': fresh_card,
        'request_count_start': start, 'request_count_after_discovery': evidence.request_count,
        'excluded_historical_f': excluded})
    references, values = {}, {}

    def rpc(field, spec):
        key = 'fulfillment-reference-' + field.replace('_', '-')
        if spec is None:
            references[field] = _skip(evidence, key, 'reference_dependency_unavailable', field=field)
            values[field] = None
        else:
            try:
                values[field] = _rpc(evidence, 56, key, *spec)['value']
            except (ValueError, TypeError):
                values[field] = None
            references[field] = (evidence.run / (key + '.request-plan.json')).relative_to(evidence.root).as_posix()

    rpc('chain', ('eth_chainId', []))
    rpc('head', ('eth_blockNumber', []))
    block = _fixed_block(values)
    for field, spec in _fixed_specs(block).items():
        rpc(field, spec if block else None)
    valid = _snapshot(values)
    rpc('supply', plan_specs(block)['supply'] if valid else None)
    try:
        supply = decode_uint256(values['supply'])
    except (ValueError, TypeError):
        supply = 0
    for field, spec in plan_specs(block, supply).items() if block else []:
        if field != 'supply':
            rpc(field, spec if valid else None)
    slots = planner_slots(supply, {index: values.get(f'index-{index}') for index in enumeration_indices(supply) if index is not None}, excluded)
    selection = _save(evidence, SELECTION_NAME, {'created_at': datetime.now(timezone.utc).isoformat(), 'slots': slots})
    for slot in slots[:7]:
        if slot['eligible']:
            field = 'position-' + slot['position_id']
            rpc(field, plan_specs(block, position_ids=[slot['position_id']])[field])
    execution = _save(evidence, EXECUTION_NAME, {'created_at': datetime.now(timezone.utc).isoformat(),
        'intent': intent['path'], 'selection': selection['path'], 'rpc_requests': references, 'slots': slots})
    tasks = []
    for slot in slots:
        key = f'fulfillment-business-{slot["slot"]}'
        ready = slot['eligible']
        if ready and slot['purpose'] == 'functional':
            try:
                position_expected(values.get('position-' + slot['position_id']))
            except (ValueError, TypeError):
                ready = False
        if ready:
            response = evidence.request(key, adapter['endpoint'], 'POST', request_contract(adapter, key, slot['position_id']),
                                        headers, purpose=MeasurementPurpose(slot['purpose']))
            if response['observation']:
                obs = ProbeObservation.model_validate(response['observation'])
                if should_stop_business(obs, response['raw']):
                    from urllib.parse import urlsplit
                    stop = evidence.root / 'runtime/prediction-network-stops' / (urlsplit(adapter['endpoint']).hostname + '.json')
                    stop.parent.mkdir(exist_ok=True)
                    if not stop.exists():
                        _write(stop, {'reason': 'Authentication, payment or rate limit', 'source_run': evidence.run.relative_to(evidence.root).as_posix()})
            ref = (evidence.run / (key + '.request-plan.json')).relative_to(evidence.root).as_posix()
        else:
            ref = _skip(evidence, key, 'reference_unavailable')
        tasks.append({'slot': slot['slot'], 'business_request': ref})
    index = _save(evidence, PLAN_NAME, {'created_at': datetime.now(timezone.utc).isoformat(),
        'execution_plan': execution['path'], 'tasks': tasks, 'request_count_end': evidence.request_count})
    _, capability, samples, inputs, _ = rebuild_position_fulfillment(evidence.root, index['path'], evidence.inputs)
    evidence.inputs.update(inputs)
    return [capability], samples, GAPS


def rebuild_position_fulfillment(root, name, hashes):
    from reputation_platform.position_contracts import request_contract
    source = PositionEvidence(root, hashes)
    plan = source.json(name)
    execution = source.json(plan['execution_plan'])
    intent = source.json(execution['intent'])
    config_path = review_config_path(root, intent.get('review_config_path', REVIEW_CONFIG))
    for path in (POLICY, OLD_CONFIG, RPC_CONFIG.as_posix(), config_path):
        source.read(path)
    identity = _registration(source, intent['proof_path'], intent['canonical'])
    adapter, headers, discovery_end = _match(source, identity, intent['discovery'], config_path)
    if any(intent.get(k) != v for k, v in _contract_fields(adapter).items()):
        raise ValueError('Query fulfillment intent differs from the reviewed policy')
    created = _time(intent['created_at'])
    if any(t > created for t in source.times) or discovery_end > created:
        raise ValueError('Query intent must follow authenticated identity and discovery')
    excluded = source.json(OLD_CONFIG)['position_ids']
    if intent['excluded_historical_f'] != excluded:
        raise ValueError('Historical F exclusions changed')
    starts = (intent['request_count_start'], intent['request_count_after_discovery'], plan['request_count_end'])
    if any(type(n) is not int or not 0 <= n <= 64 for n in starts) or not starts[0] <= starts[1] <= starts[2]:
        raise ValueError('Query request counters exceed the shared budget')
    fresh = intent['new_card_request']
    if fresh is not None and (adapter['protocol'] != 'A2A' or fresh != intent['discovery']['card_request']):
        raise ValueError('New discovery must be the registered A2A card')
    if starts[1] - starts[0] != int(fresh is not None and fresh.removesuffix('.request-plan.json') + '.observation.json' in hashes):
        raise ValueError('Discovery counter differs from original observations')
    refs, values, requests, observed, ends = execution['rpc_requests'], {}, [], [], [created]
    rpc_url = _configuration(root)['chains']['56']['rpc_url']

    def rpc(field, spec, earliest):
        ref = refs[field]
        if spec is None:
            skip = source.skip(ref, 'fulfillment-reference-' + field.replace('_', '-'), reason='reference_dependency_unavailable')
            if skip.get('field') != field or _time(skip['created_at']) < earliest:
                raise ValueError('RPC dependency skip differs from the frozen field')
            value, end = None, _time(skip['created_at'])
        else:
            key = 'fulfillment-reference-' + field.replace('_', '-')
            obs, raw, request = source.request(ref, rpc_url, MeasurementPurpose.BACKGROUND,
                {'jsonrpc': '2.0', 'id': key, 'method': spec[0], 'params': spec[1]})
            if (request['key'] != key or request.get('headers') is not None
                or request.get('rpc_configuration_source') != 'operator-static-not-metadata'
                or _time(request['created_at']) < earliest):
                raise ValueError('RPC is not the frozen operator reference')
            value, end = _rpc_value(obs, raw, key), _finished(obs) if obs else _time(request['created_at'])
            requests.append(ref)
            if obs:
                observed.append(obs)
        values[field] = value
        ends.append(end)
        return end

    rpc('chain', ('eth_chainId', []), created)
    rpc('head', ('eth_blockNumber', []), created)
    block, after_head = _fixed_block(values), max(ends)
    expected_fields = {'chain', 'head', 'header', 'npm_code', 'factory', 'factory_code', 'supply'}
    for field, spec in _fixed_specs(block).items():
        rpc(field, spec if block else None, after_head)
    snapshot_end, valid = max(ends), _snapshot(values)
    supply_end = rpc('supply', plan_specs(block)['supply'] if valid else None, snapshot_end)
    try:
        supply = decode_uint256(values['supply'])
    except (TypeError, ValueError):
        supply = 0
    for field, spec in plan_specs(block, supply).items() if block else []:
        if field != 'supply':
            expected_fields.add(field)
            rpc(field, spec if valid else None, supply_end)
    slots = planner_slots(supply, {index: values.get(f'index-{index}') for index in enumeration_indices(supply) if index is not None}, excluded)
    selection = source.json(execution['selection'])
    selected_at = _time(selection['created_at'])
    if selection['slots'] != slots or execution['slots'] != slots or selected_at < max(ends):
        raise ValueError('Task selection changed or was not frozen after independent enumeration')
    for slot in slots[:7]:
        if slot['eligible']:
            field = 'position-' + slot['position_id']
            expected_fields.add(field)
            rpc(field, plan_specs(block, position_ids=[slot['position_id']])[field], selected_at)
    frozen = _time(execution['created_at'])
    if set(refs) != expected_fields or frozen < max([selected_at, *ends]):
        raise ValueError('Business inputs must freeze all original reference fields before execution')
    if [t.get('slot') for t in plan['tasks']] != list(range(14)):
        raise ValueError('Every frozen F/B slot must remain once and in order')
    samples = []
    for slot, task in zip(slots, plan['tasks'], strict=True):
        key, ref = f'fulfillment-business-{slot["slot"]}', task['business_request']
        ready = slot['eligible']
        if ready and slot['purpose'] == 'functional':
            try:
                position_expected(values.get('position-' + slot['position_id']))
            except (TypeError, ValueError):
                ready = False
        obs, raw = None, b''
        if ref.endswith('.skip.json'):
            record = source.skip(ref, key, reason='reference_unavailable')
            if ready or _time(record['created_at']) < frozen:
                raise ValueError('Unsent business task contradicts its frozen reference')
        else:
            if not ready:
                raise ValueError('An ineligible task was executed')
            obs, raw, request = source.request(ref, adapter['endpoint'], MeasurementPurpose(slot['purpose']), request_contract(adapter, key, slot['position_id']))
            if request['key'] != key or request['headers'] != headers or _time(request['created_at']) < frozen:
                raise ValueError('Business request differs from the frozen subject or endpoint')
            requests.append(ref)
            if obs:
                observed.append(obs)
        samples.append(_sample(slot, obs, raw, adapter, values.get('position-' + str(slot['position_id']))))
    indexed = _time(plan['created_at'])
    if (len(requests) != len(set(requests)) or len(observed) != starts[2] - starts[1]
        or any(t > indexed for t in [frozen, selected_at, *source.times])):
        raise ValueError('Retained observations, time or request budget differ from the frozen evaluation')
    directory = Path(name).parent
    # A may use another protocol path on the same host (e.g. MCP A and A2A B).
    for ref in list(hashes):
        if Path(ref).parent == directory and ref.endswith('-availability-plan.json'):
            prior = source.json(ref)
            _prior_availability(source, directory, created, prior['url'], prior['headers'])
    # All scoped requests must be indexed, including failed and explicitly unsent ones.
    retained = set(refs.values()) | {t['business_request'] for t in plan['tasks']}
    retained.update(ref.removesuffix('.request-plan.json') + suffix for ref in list(retained)
                    if ref.endswith('.request-plan.json') for suffix in ('.observation.json', '.skip.json'))
    for ref in hashes:
        if Path(ref).parent == directory and ref.endswith('.observation.json'):
            observation = ProbeObservation.model_validate_json(source.read(ref))
            if observation.observed_at >= created and ref not in retained:
                raise ValueError('Unindexed request during the frozen query evaluation')
            request_ref = ref.removesuffix('.observation.json') + '.request-plan.json'
            if request_ref not in source.requests:
                if observation.method == 'GET':
                    source.get(request_ref, observation.url)
                else:
                    source.request(request_ref, observation.url, observation.purpose)
        if Path(ref).parent == directory and ref.endswith(('.request-plan.json', '.skip.json')):
            record = source.json(ref)
            timestamp = record.get('created_at')
            if timestamp is None and ref.endswith('.skip.json'):
                parent = ref.removesuffix('.skip.json') + '.request-plan.json'
                timestamp = source.json(parent)['created_at'] if parent in hashes else None
            if timestamp is not None and created <= _time(timestamp) <= indexed and ref not in retained:
                raise ValueError('Unindexed request or skip during the frozen query evaluation')
        if Path(ref).parent == directory and Path(ref).name.startswith(('fulfillment-reference-', 'fulfillment-business-')):
            if ref.endswith(('.request-plan.json', '.observation.json', '.skip.json')) and ref not in retained:
                raise ValueError('Unindexed scoped query request or observation')
    if sum(Path(ref).parent == directory and ref.endswith('.observation.json') for ref in hashes) != starts[2]:
        raise ValueError('Global request counter does not match all retained intake and task observations')
    if (sum(Path(ref).parent == directory and ref.endswith('.observation.json')
            and ProbeObservation.model_validate_json(source.read(ref)).observed_at < created for ref in hashes) != starts[1]
        or any(t > indexed for t in source.times)):
        raise ValueError('Intake request counter or retained time differs from the actual window')
    source.verify_stops(should_stop_business)
    paths = sorted(source.reader.inputs)
    for sample in samples:
        sample.sample.evidence = paths
    capability = CapabilityCoverage(capability_id=CAPABILITY_ID, operation=adapter['tool'],
        description='同一仓位查询能力，七个独立功能任务及七个互斥可观察履约任务。', protocol=adapter['protocol'],
        tested_scope='BSC PancakeSwap v3固定区块枚举；F核五项静态事实，B核同步交付关联、完整性及观测窗口。',
        sample_ids=[s.sample.sample_id for s in samples], findings=[ReportFinding(label='身份、审阅契约及独立任务规划', verdict=Verdict.PASS,
        explanation=f'Checker {CHECKER_ID}/{VERSION}；政策 {POLICY_VERSION}；适配器 {adapter["id"]}；规则 {RULE}。')],
        missing_evidence=GAPS, capability_type='Query / Tool', checker_id=CHECKER_ID, checker_version=VERSION)
    return identity['canonical'], capability, samples, source.reader.inputs, [*source.times, created, selected_at, frozen, indexed]


def verify_position_fulfillment_samples(root, report, hashes):
    verified, found = set(), False
    for name in hashes:
        if Path(name).name != PLAN_NAME:
            continue
        canonical, capability, samples, _, times = rebuild_position_fulfillment(root, name, hashes)
        actual = [s for s in report.samples if name in s.sample.evidence]
        matched = [c for c in report.capabilities if c.capability_id == CAPABILITY_ID]
        if (report.policy_version != POLICY_VERSION or canonical != report.registration_reference
            or actual != samples or matched != [capability] or any(t > report.generated_at for t in times)
            or verified.intersection(s.sample.sample_id for s in samples)):
            raise ValueError('Report differs from independently rebuilt query fulfillment sources')
        verified.update(s.sample.sample_id for s in samples)
        found = True
    if any(c.checker_id == CHECKER_ID and c.checker_version == VERSION for c in report.capabilities) and not found:
        raise ValueError('Query fulfillment metadata requires its complete independent evidence plan')
    return verified
