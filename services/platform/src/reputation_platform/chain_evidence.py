"""Offline authentication and publication of a fixed Olas execution cohort."""

from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
import hashlib
import json
from pathlib import Path
from uuid import uuid4

from eth_hash.auto import keccak
from psycopg.types.json import Jsonb

from reputation_core.admission import ProbeObservation, Verdict
from reputation_core.application import AgentProfile
from reputation_core.chain_review import AgentChainEvidence, ChainDimensionEvidence
from reputation_core.chain_view import ChainAction
from reputation_core.ipfs import read_car_file
from reputation_core.omen_execution import (
    CONDITIONAL_TOKENS, WXDAI, SERVICE_REGISTRY, SAFE_FAILURE, SAFE_SUCCESS,
    verify_omen_execution, words,
)
from reputation_core.prediction_chain import calldata
from reputation_core.reporting import ReportFinding


class RetainedExecutionReader:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.hashes: dict[str, str] = {}
        self._cache: dict[str, bytes] = {}

    def read(self, path: str, digest: str | None = None) -> bytes:
        resolved = (self.root / path).resolve()
        if (not resolved.is_relative_to(self.root / 'runtime')
            or any(part.lower() in ('secrets', 'platform-config') or '.private' in part.lower() for part in resolved.parts)):
            raise ValueError('Execution evidence must stay in public runtime')
        raw = self._cache.get(path)
        if raw is None:
            raw = resolved.read_bytes()
            self._cache[path] = raw
        actual = hashlib.sha256(raw).hexdigest()
        if digest is not None and actual != digest:
            raise ValueError('Execution evidence digest mismatch')
        if path in self.hashes and self.hashes[path] != actual:
            raise ValueError('Execution evidence reference conflicts')
        self.hashes[path] = actual
        return raw

    def source(self, reference: dict, *, url: str | None = None) -> tuple[bytes, ProbeObservation]:
        for item in reference['references']:
            self.read(item['path'], item['sha256'])
        for name in ('response_path', 'observation_path'):
            if reference[name] not in self.hashes:
                raise ValueError('Observation or response is not hash-bound')
        observation = ProbeObservation.model_validate_json(self.read(reference['observation_path']))
        raw = self.read(reference['response_path'])
        if (observation.http_status != 200 or observation.error_kind or not observation.body_complete
            or observation.response_sha256 != hashlib.sha256(raw).hexdigest()
            or observation.response_file != Path(reference['response_path']).name
            or url is not None and observation.url != url):
            raise ValueError('Execution source is incomplete or incorrectly bound')
        return raw, observation

    def rpc(self, reference: dict, method: str, params: list):
        raw, observation = self.source(reference, url='https://rpc.gnosischain.com')
        request = json.loads(observation.request_json)
        if (observation.method != 'POST' or request.get('jsonrpc') != '2.0'
            or request.get('method') != method or request.get('params') != params):
            raise ValueError('RPC request does not match its expected chain/task/history parameters')
        envelope = json.loads(raw)
        if (envelope.get('jsonrpc') != '2.0' or envelope.get('id') != request.get('id')
            or 'error' in envelope or envelope.get('result') is None):
            raise ValueError('RPC response does not match the retained request')
        return envelope['result']

    def graphql(self, reference: dict, url: str) -> dict:
        raw, observation = self.source(reference, url=url)
        value = json.loads(raw)
        if (observation.method != 'POST' or value.get('errors')
            or value.get('data', {}).get('_meta', {}).get('hasIndexingErrors') is not False):
            raise ValueError('Public index reported errors or lacks indexing status')
        return value['data']


def build_execution_reviews(root: Path, bundle_path: Path) -> list[tuple[AgentChainEvidence, dict[str, str]]]:
    """Replay exactly the selected cohort; an unavailable source remains a gap."""
    reader = RetainedExecutionReader(root)
    relative = lambda value: value.resolve().relative_to(root.resolve()).as_posix()
    bundle = json.loads(reader.read(relative(bundle_path)))
    if bundle['schema_version'] != 'chain-execution-bundle-v1':
        raise ValueError('Unsupported execution evidence bundle')
    def bundled(name: str):
        item = bundle['inputs'][name]
        return json.loads(reader.read(item['path'], item['sha256']))
    summary, singletons, metadata = bundled('cohort'), bundled('singletons'), bundled('metadata')
    allowances, positions, proxy = bundled('allowances'), bundled('positions'), bundled('proxy')
    if summary['service_registry'].lower() != SERVICE_REGISTRY or summary.get('scores_computed') is not False:
        raise ValueError('Not the reviewed execution-only collection')
    discovery = reader.graphql(summary['selection']['source'], 'https://predict-agents.subgraph.autonolas.tech')
    selected = discovery['traderAgents'][:10]
    if (len(selected) != 10 or len(summary['candidates']) != 10
        or len({row['id'] for row in selected}) != 10
        or [str(row['serviceId']) for row in selected] != [str(row['olas_service_id']) for row in summary['candidates']]):
        raise ValueError('Execution cohort differs from the frozen first ten discovery rows')
    context = summary['chain_context']
    if int(reader.rpc(context['chain_evidence'], 'eth_chainId', []), 16) != 100:
        raise ValueError('Evidence RPC is not Gnosis')
    head = int(reader.rpc(context['head_evidence'], 'eth_blockNumber', []), 16)
    if head != context['head']:
        raise ValueError('Confirmation head was not independently observed')

    descriptor_raw, _ = reader.source(proxy['official_deployment'], url=
        'https://raw.githubusercontent.com/safe-global/safe-deployments/main/src/assets/v1.3.0/proxy_factory.json')
    descriptor = json.loads(descriptor_raw)['deployments']['canonical']
    factory = '0xa6b71e26c5e0845f74c812102ca7114b6a896ab2'
    if descriptor['address'].lower() != factory:
        raise ValueError('Unexpected official Safe proxy factory')
    factory_code = reader.rpc(proxy['factory_code'], 'eth_getCode', [factory, proxy['historical_block']])
    if '0x' + keccak(bytes.fromhex(factory_code[2:])).hex() != descriptor['codeHash'].lower():
        raise ValueError('Historical proxy factory code differs from the official deployment')
    encoded_runtime = reader.rpc(proxy['proxy_runtime_call'], 'eth_call',
        [{'to': factory, 'data': calldata('proxyRuntimeCode()')}, proxy['historical_block']])
    data = bytes.fromhex(encoded_runtime[2:])
    offset = int.from_bytes(data[:32], 'big')
    runtime_size = int.from_bytes(data[offset:offset + 32], 'big')
    runtime = data[offset + 32:offset + 32 + runtime_size]
    if (runtime_size != 171 or len(runtime) != runtime_size
        or '0x' + keccak(runtime).hex() != '0xb89c1b3bdf2cf8827818646bce9a8f6e372885f8c55e5c07acbd307cb133b000'):
        raise ValueError('Proxy runtime does not match the reviewed official factory result')

    configurations = {}
    for configuration in metadata['configurations']:
        for item in configuration['references']:
            reader.read(item['path'], item['sha256'])
        file_ref = configuration['file_ref']
        original = reader.read(file_ref['path'], file_ref['sha256'])
        car = reader.read(configuration['car_response_path'])
        actual, _ = read_car_file(car, configuration['config_hash'])
        if actual != original:
            raise ValueError('Chain-anchored UnixFS metadata differs from the declaration bytes')
        document = json.loads(actual)
        if 'trader' not in document.get('name', '').lower() or 'omen' not in document.get('description', '').lower():
            raise ValueError('The registered service does not declare the reviewed trader capability')
        configurations[configuration['config_hash'].lower()] = (document, file_ref['path'])
    shared = dict(reader.hashes)
    supplements = {str(item['olas_service_id']): item for item in singletons['candidates']}
    allowances = {str(item['olas_service_id']): item for item in allowances['candidates']}
    positions = {str(item['olas_service_id']): item for item in positions['candidates']}
    reviews = []
    for discovered, candidate in zip(selected, summary['candidates'], strict=True):
        reader.hashes = dict(shared)
        service, safe = int(candidate['olas_service_id']), candidate['execution_address'].lower()
        if safe != discovered['id'].lower():
            raise ValueError('Discovered trader Safe was rebound to another account')
        evidence, trade = dict(candidate['evidence']), candidate['latest_buy']
        index = reader.graphql(evidence['buy_index'], 'https://omen.subgraph.autonolas.tech')
        if index['s' + str(service)] != [trade]:
            raise ValueError('Selected buy is not the retained first trade for this identity')
        tx_hash = trade['transactionHash'].lower()
        proof = {'transaction': reader.rpc(evidence['transaction'], 'eth_getTransactionByHash', [tx_hash]),
                 'receipt': reader.rpc(evidence['receipt'], 'eth_getTransactionReceipt', [tx_hash])}
        height = proof['transaction']['blockNumber']
        before = hex(int(height, 16) - 1)
        proof['block'] = reader.rpc(evidence['block'], 'eth_getBlockByNumber', [height, False])
        calls = {
            'service_before': ('eth_call', [{'to': SERVICE_REGISTRY, 'data': calldata('mapServices(uint256)', service)}, before]),
            'agent_instances_before': ('eth_call', [{'to': SERVICE_REGISTRY, 'data': calldata('getAgentInstances(uint256)', service)}, before]),
            'safe_owners_before': ('eth_call', [{'to': safe, 'data': calldata('getOwners()')}, before]),
            'safe_threshold_before': ('eth_call', [{'to': safe, 'data': calldata('getThreshold()')}, before]),
            'safe_code': ('eth_getCode', [safe, height]),
            'market_collateral_before': ('eth_call', [{'to': trade['fpmm']['id'], 'data': calldata('collateralToken()')}, before]),
            'market_conditional_tokens_before': ('eth_call', [{'to': trade['fpmm']['id'], 'data': calldata('conditionalTokens()')}, before]),
            'market_condition_before': ('eth_call', [{'to': trade['fpmm']['id'], 'data': calldata('conditionIds(uint256)', 0)}, before]),
        }
        gaps = list(candidate.get('gaps', []))
        for name, (method, params) in calls.items():
            if name in evidence:
                proof[name] = reader.rpc(evidence[name], method, params)
        proof['market_collateral'] = proof.get('market_collateral_before')
        proof['market_conditional_tokens'] = proof.get('market_conditional_tokens_before')
        proof['market_condition'] = proof.get('market_condition_before')
        supplemental = supplements.get(str(service), {})
        for name, expected in (
            ('safe_master_copy_before', ('eth_call', [{'to': safe, 'data': calldata('masterCopy()')}, before])),
            ('singleton_code_before', ('eth_getCode', ['0xd9db270c1b5e3bd161e8c8503c55ceabee709552', before])),
        ):
            source_name = 'safe_singleton_code_before' if name == 'singleton_code_before' else name
            reference = supplemental.get('evidence', {}).get(source_name) or supplemental.get(source_name)
            if reference:
                proof[name] = reader.rpc(reference, *expected)
        gaps.extend(supplemental.get('gaps', []))
        allowance_ref = allowances.get(str(service), {}).get('evidence', {}).get('collateral_allowance_before')
        if allowance_ref:
            proof['collateral_allowance_before'] = reader.rpc(allowance_ref, 'eth_call',
                [{'to': WXDAI, 'data': calldata('allowance(address,address)', safe, trade['fpmm']['id'])}, before])
        position = positions.get(str(service), {}).get('evidence', {})
        if position:
            condition = proof['market_condition']
            collection = reader.rpc(position['collection_id_before'], 'eth_call',
                [{'to': CONDITIONAL_TOKENS, 'data': calldata('getCollectionId(bytes32,bytes32,uint256)',
                    0, condition, 1 << int(trade['outcomeIndex']))}, before])
            proof['position_id_before'] = reader.rpc(position['position_id_before'], 'eth_call',
                [{'to': CONDITIONAL_TOKENS, 'data': calldata('getPositionId(address,bytes32)', WXDAI, collection)}, before])
        config_hash = '0x' + f"{words(proof['service_before'])[2]:064x}"
        if config_hash not in configurations:
            raise ValueError('Service declaration has no authenticated metadata for its historical configHash')
        declaration, declaration_path = configurations[config_hash]
        verification = verify_omen_execution(proof, safe=safe, service_id=service, trade=trade, confirmation_head=head)
        facts = verification.facts
        checks = [ReportFinding(label='链上配置与功能声明', verdict=Verdict.PASS,
            explanation=f"历史服务配置哈希{config_hash}的UnixFS原件已由CAR/DAG重新认证，声明：{declaration['description']}。"), *verification.checks]
        window = candidate.get('safe_window') or {}
        window_text = '固定历史窗口尚缺完整Safe执行事件。'
        if 'execution_window' in evidence:
            start, end = int(height, 16) - 256, int(before, 16)
            events = reader.rpc(evidence['execution_window'], 'eth_getLogs', [{'address': safe,
                'fromBlock': hex(max(0, start)), 'toBlock': hex(end), 'topics': [[SAFE_SUCCESS, SAFE_FAILURE]]}])
            for event in events:
                if (event['address'].lower() != safe or event.get('removed') is not False
                    or not max(0, start) <= int(event['blockNumber'], 16) <= end
                    or event['topics'][0].lower() not in (SAFE_SUCCESS, SAFE_FAILURE)):
                    raise ValueError('Safe window contains an unrelated or removed event')
            successes = sum(event['topics'][0].lower() == SAFE_SUCCESS for event in events)
            failures = sum(event['topics'][0].lower() == SAFE_FAILURE for event in events)
            window_text = f"另查买入前256块（{max(0, start)}—{end}）全部匹配Safe结果事件：{successes}次成功、{failures}次内层失败。"
        def readable_amount(value: str) -> str:
            return format(Decimal(value).quantize(Decimal('0.000001'), rounding=ROUND_HALF_UP).normalize(), 'f')
        outcomes = trade['fpmm'].get('outcomes', [])
        outcome_index = int(trade['outcomeIndex'])
        outcome_label = outcomes[outcome_index] if outcome_index < len(outcomes) else str(outcome_index)
        outcome_label = {'Yes': '是（Yes）', 'No': '否（No）'}.get(outcome_label, outcome_label)
        action_summary = (
            f"Safe实际支付约{readable_amount(facts['investment'])} wxDAI，买入“{outcome_label}”结果的"
            f"约{readable_amount(facts['tokens'])}份预测市场头寸，费用约{readable_amount(facts['fee'])} wxDAI。"
            f"实收份额达到已签最低接收量；抵押资产、结果方向和到账头寸ID已独立核对。"
        ) if verification.verdict == Verdict.PASS else '真实交易原件已保留；完整归属或业务约束尚不能核齐，见下方缺项。'
        question = trade['fpmm'].get('question', {}).get('data', '').split('␟', 1)[0]
        if question:
            checks.append(ReportFinding(label='市场条件与问题出处', verdict=Verdict.PASS,
                explanation=f"方向编号{outcome_index}，索引标签{outcome_label}；真实市场条件ID {proof['market_condition']}。"
                    f"市场索引问题原文：{question}。这里只记录该问题出处，不判断预测或现实事实是否正确。"))
        key = f'olas-omen-trader-{service}'
        canonical = f'eip155:100:{SERVICE_REGISTRY}:{service}'
        profile = AgentProfile(
            business_summary='使用Gnosis链上的Safe智能账户，在Omen预测市场授权wxDAI并买入条件头寸；注册声明还包含交易策略，本轮核验具体买入执行。',
            ecosystem='Olas · Omen', role='asset-execution', registration_chain_id=100,
            execution_chain_ids=[100], capabilities=['历史资产授权', '预测市场买入', 'Safe签名交易执行'],
            execution_accounts=[safe], evidence_status='verified' if verification.verdict == Verdict.PASS else 'declared',
            sources=[declaration_path, 'https://github.com/valory-xyz/trader'],
            boundary='本次检查历史签名、授权和买入效果；尚不评价预测获利能力、当前在线状态或完整交易失败率。',
        )
        sources = sorted(reader.hashes)
        action = ChainAction(sample_id=f'olas-omen:{service}:{tx_hash}', chain_id=100, action='prediction_market_buy',
            title='使用资产授权买入预测市场头寸', transaction_hash=tx_hash,
            block_number=int(height, 16), executor=safe, target=trade['fpmm']['id'].lower(),
            method=facts.get('execution_path', 'execTransaction：完整调用路径尚待核验'), summary=action_summary,
            verdict=verification.verdict, evidence=sources)
        review = AgentChainEvidence(candidate_key=key, registration_reference=canonical,
            generated_at=datetime.fromisoformat(summary['created_at']), title=f'Olas Omen交易Agent · 服务#{service}',
            profile=profile, actions=[action], checks=checks,
            dimensions=[
                ChainDimensionEvidence(purpose='availability', verdict=Verdict.UNKNOWN, observed=0,
                    summary='历史交易证明它曾执行链上业务，尚不证明当前对外服务可用。',
                    missing_evidence=['可归属于该Agent的实时服务入口或自治运行可用性约定，以及原定可用性样本。']),
                ChainDimensionEvidence(purpose='functional', verdict=verification.verdict, observed=1,
                    summary='核对注册买入能力、已签方向/金额/最低接收约束和实际资产变化。',
                    missing_evidence=[*gaps, '尚未取得7个独立功能任务；此次成功买入发现样本不作总体表现估计。']),
                ChainDimensionEvidence(purpose='behavioral', verdict=Verdict.UNKNOWN, observed=1,
                    summary='已核历史服务→Safe→owner/注册实例、签名执行和内层结果；完整任务尝试范围仍缺。',
                    missing_evidence=[*gaps, '还需任务与全部交易尝试（含外层回滚/未提交/过期），并按固定规则取得与F独立的7个任务。']),
            ], selection='固定公开索引按累计下注次数降序的前10个实例；有缺项不替换，不按得分筛对象。每对象取索引最近一笔买入。',
            window_summary=f"样本执行于{datetime.fromtimestamp(int(proof['block']['timestamp'], 16), timezone.utc).isoformat()}（UTC）；{window_text}",
            sources=sources, limitations=[
                '买入发现索引只含成功买入。Safe事件窗口包括其它业务，且不包含外层回滚或未上链任务，不能拿来计算买入成功率。',
                '本快照是背景采证，F/B展示同一操作的不同事实，均未加入评分分母；三维权重和已发布分数不变。',
                'Safe在真实交易中验证已有签名；平台没有创建签名或发起交易，也未独立恢复签名公钥。',
                '市场问题来自公开索引；资金效果由交易、事件和历史状态验证，不把问题预测、盈利或当前运行状态判为通过。',
                '本版按原calldata分别呈现直接买入与同笔授权后买入；旧展示版本保留，原始证据、样本结论和评分均未更改。',
            ])
        reviews.append((review, dict(reader.hashes)))
    return reviews


def publish_execution_reviews(repository, reviews, directory: Path, *, agent_names: dict[str, str] | None = None) -> list[dict]:
    """Append authenticated snapshots and source allowlists in one DB transaction."""
    directory = directory.resolve()
    if not directory.is_relative_to(repository.runtime):
        raise ValueError('Snapshots must be retained in public runtime')
    directory.mkdir(parents=True, exist_ok=False)
    prepared = []
    for review, sources in reviews:
        path = directory / (review.candidate_key + '.json')
        raw = (review.model_dump_json(indent=2) + '\n').encode('utf-8')
        path.write_bytes(raw)
        prepared.append((review, path, hashlib.sha256(raw).hexdigest(), sources))
    mappings = []
    with repository._connect() as connection:
        for review, path, digest, sources in prepared:
            name = (agent_names or {}).get(review.candidate_key, review.title)
            repository._upsert_agent(connection, key=review.candidate_key, name=name,
                reference=review.registration_reference, description=review.profile.business_summary)
            row = connection.execute('''INSERT INTO agent_chain_evidence(id,agent_key,generated_at,snapshot_path,
                snapshot_sha256,validated_json,evidence_files) VALUES (%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT(snapshot_sha256) DO NOTHING RETURNING id''',
                (uuid4(), review.candidate_key, review.generated_at, path.relative_to(repository.root).as_posix(), digest,
                 Jsonb(review.model_dump(mode='json')), Jsonb(sources))).fetchone()
            mappings.append({'candidate_key': review.candidate_key, 'snapshot_path': path.relative_to(repository.root).as_posix(),
                'snapshot_sha256': digest, 'imported': row is not None,
                'sample_verdict': review.actions[0].verdict.value})
    (directory / 'index.json').write_text(json.dumps(mappings, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return mappings
