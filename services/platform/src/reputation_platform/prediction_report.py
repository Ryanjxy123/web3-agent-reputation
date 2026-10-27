"""Rebuild prediction conclusions from retained HTTP, chain and CAR bytes."""

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re

from eth_hash.auto import keccak

from reputation_core import CandidateRecord, DeclarationAnalysis, MeasurementPurpose, ProbeObservation, SourceDocument, Verdict, validate_analysis
from reputation_core.ipfs import read_car_file, verify_car_file
from reputation_core.planning import PredictionHistoryDescriptor, PlanSelection, select_prediction_plan
from reputation_core.prediction import BinaryPrediction
from reputation_core.prediction_chain import (
    BRIDGER, REGISTRY, SERVICE_REGISTRY, calldata, call_value, extract_task_anchors,
    verify_omen_settlement, verify_prediction_chain, _receipt,
)
from reputation_core.reporting import EvaluationReport, ReportFinding, SampleExplanation
from reputation_core.scoring import ScoredSample
from reputation_platform.prediction_evidence import PredictionProfile, RPC, OMEN_INDEX, _abi_text
from reputation_platform.settings import PROJECT_ROOT
from reputation_platform.model_analysis import prediction_tool_descriptors


class OutputViolation(ValueError):
    """The authenticated file itself contradicts the declared output contract."""


class AuthenticatedJsonError(ValueError):
    """Only CAR-authenticated file bytes, rather than local proof metadata, failed JSON parsing."""


class RetainedEvidence:
    def __init__(self, root: Path = PROJECT_ROOT):
        self.root, self.inputs = root.resolve(), {}

    def path(self, name: str) -> Path:
        path = (self.root / name).resolve()
        public = any(path.is_relative_to(self.root / base) for base in ('runtime', 'configs', 'docs/adr'))
        public = public or (path.is_relative_to(self.root / 'data/declarations') and path.suffix == '.json')
        if (not public
            or not path.is_file() or any(part.lower() in {'secrets', 'platform-config'}
                                        or '.private' in part.lower() for part in path.parts)):
            raise ValueError('Report input must be retained public evidence or policy')
        return path

    def remember(self, name: str, expected: str | None = None) -> Path:
        path = self.path(name)
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if expected is not None and digest != expected:
            raise ValueError('A retained report source changed: ' + name)
        self.inputs[path.relative_to(self.root).as_posix()] = digest
        return path

    def json(self, name: str):
        return json.loads(self.remember(name).read_bytes())

    def manifest(self, run: Path) -> dict:
        value = self.json((run / 'manifest.json').relative_to(self.root).as_posix())
        for item in value['inputs']:
            self.remember(item['path'], item['sha256'])
        return value

    def observation(self, references: list[dict], *, url: str, method: str) -> tuple[ProbeObservation, bytes]:
        paths = [self.remember(item['path'], item['sha256']) for item in references]
        observed = [path for path in paths if path.name.endswith('.observation.json')]
        if len(observed) != 1:
            raise ValueError('Expected one original request observation')
        observation = ProbeObservation.model_validate_json(observed[0].read_bytes())
        if (observation.url != url or observation.method != method or observation.http_status != 200
            or observation.error_kind or not observation.body_complete or not observation.response_file):
            raise ValueError('Missing successful original request for the required public endpoint')
        response = (observed[0].parent / observation.response_file).resolve()
        if response.parent != observed[0].parent or response not in paths:
            raise ValueError('Original response is not in the authenticated proof')
        self.remember(response.relative_to(self.root).as_posix(), observation.response_sha256)
        return observation, response.read_bytes()

    def rpc(self, proof: dict) -> dict:
        observation, raw = self.observation(proof['evidence'], url=RPC, method='POST')
        request, response = json.loads(observation.request_json), json.loads(raw)
        if (request.get('jsonrpc') != '2.0' or request.get('method') != proof['method']
            or request.get('params') != proof['params'] or response.get('jsonrpc') != '2.0'
            or response.get('id') != request.get('id') or 'error' in response
            or response.get('result') is None or response['result'] != proof['value']):
            raise ValueError('RPC envelope, fixed parameters or retained result differ')
        return {**proof, 'value': response['result']}

    def tree(self, value):
        if isinstance(value, list):
            return [self.tree(item) for item in value]
        if not isinstance(value, dict):
            return value
        if {'method', 'params', 'value', 'evidence'} <= value.keys():
            return self.rpc(value)
        result = {key: self.tree(item) for key, item in value.items()}
        if {'transaction', 'receipt', 'header', 'proofs'} <= result.keys():
            for field in ('transaction', 'receipt', 'header'):
                if result[field] != result['proofs'][field]['value']:
                    raise ValueError('Task copy differs from original transaction proof')
        return result

    def market(self, value: dict, profile: PredictionProfile):
        rebuilt = self.tree(value)
        if value['header'] != self.snapshot_header:
            raise ValueError('Market header differs from the authenticated frozen snapshot')
        observation, raw = self.observation(value['index']['evidence'], url=OMEN_INDEX, method='POST')
        request, original = json.loads(observation.request_json), json.loads(raw)
        query = request.get('query', '')
        if ('mutation' in query.lower() or f'id:"{value["market"]}"' not in query
            or original.get('errors') or original.get('data') != value['index']['data']):
            raise ValueError('Original market discovery request differs')
        question = original['data']['fixedProductMarketMaker']['question']
        if question != value['question']:
            raise ValueError('Question differs from its original indexed text')
        return verify_omen_settlement(rebuilt, snapshot_block=profile.snapshot_block,
                                      snapshot_hash=profile.snapshot_hash)

    def content(self, content: dict, digest: str, filename: str) -> dict:
        return self._content_json(content, self.content_bytes(content, digest, filename))

    def content_bytes(self, content: dict, digest: str, filename: str) -> bytes:
        if content.get('layout') == 'unixfs-root-file-v1':
            url = 'https://gateway.autonolas.tech/ipfs/f01701220' + digest[2:] + '?format=car&dag-scope=entity'
            if content['url'] != url:
                raise ValueError('Root CAR URL differs from the on-chain task')
            car_refs = [item for item in content['evidence'] if item['path'] == content['car_file']
                        or item['path'].endswith('.observation.json') and
                        json.loads(self.path(item['path']).read_bytes())['url'] == url]
            _, car = self.observation(car_refs, url=url, method='GET')
            raw = self.remember(content['response_file'], content['sha256']).read_bytes()
            actual, _ = read_car_file(car, digest)
            if actual != raw:
                raise ValueError('Derived root file differs from authenticated CAR bytes')
            return raw
        url = 'https://gateway.autonolas.tech/ipfs/f01701220' + digest[2:] + '/' + filename
        if content['url'] != url:
            raise ValueError('CID file URL differs from the on-chain task')
        json_refs = [item for item in content['evidence'] if item['path'] == content['response_file']
                     or item['path'].endswith('.observation.json') and
                     json.loads(self.path(item['path']).read_bytes())['url'] == url]
        _, raw = self.observation(json_refs, url=url, method='GET')
        car_url = url + '?format=car&dag-scope=entity'
        car_refs = [item for item in content['evidence'] if item['path'] == content['car_file']
                    or item['path'].endswith('.observation.json') and
                    json.loads(self.path(item['path']).read_bytes())['url'] == car_url]
        _, car = self.observation(car_refs, url=car_url, method='GET')
        verify_car_file(car, digest, filename, raw)
        if hashlib.sha256(raw).hexdigest() != content['sha256']:
            raise ValueError('CID-authenticated file digest differs')
        return raw

    @staticmethod
    def _content_json(content: dict, raw: bytes) -> dict:
        if hashlib.sha256(raw).hexdigest() != content['sha256']:
            raise ValueError('CID-authenticated file digest differs')
        try:
            actual = json.loads(raw)
        except (json.JSONDecodeError, UnicodeDecodeError) as error:
            raise AuthenticatedJsonError('Authenticated file is not valid UTF-8 JSON') from error
        if content.get('layout') in ('unixfs-root-file-v1', 'unixfs-directory-v1') and not isinstance(actual, dict):
            raise AuthenticatedJsonError('Authenticated JSON does not have the declared object structure')
        if actual != content['payload']:
            raise ValueError('CID-authenticated content differs from its retained JSON')
        return actual


def _word(calls: dict, name: str, target: str, signature: str, block: int, *args) -> int:
    value = call_value(calls, name, target, calldata(signature, *args), block)
    if len(value) != 66:
        raise ValueError('Expected one ABI word')
    return int(value, 16)


def load_history_profile(evidence: RetainedEvidence, manifest: dict, bundle: dict) -> PredictionProfile:
    """Load the one authenticated operator profile used by this history bundle."""
    reference = bundle.get('profile_reference')
    if reference is not None:
        path = evidence.path(reference['path'])
        relative = path.relative_to(evidence.root)
        if (len(relative.parts) < 2 or relative.parts[0] != 'runtime'
            or path.name != 'prediction-profile.json' or reference['path'] != relative.as_posix()):
            raise ValueError('Automatic profile must be runtime/**/prediction-profile.json')
        sources = [item for item in manifest['inputs'] if item['path'] == reference['path']]
        if len(sources) != 1 or sources[0]['sha256'] != reference['sha256']:
            raise ValueError('Automatic profile is not uniquely bound to the history manifest')
    else:
        sources = [item for item in manifest['inputs'] if Path(item['path']).parent == Path('configs/pilots')]
        if len(sources) != 1:
            raise ValueError('One immutable operator profile is required')
    profile = PredictionProfile.load(evidence.remember(sources[0]['path'], sources[0]['sha256']))
    if profile.__dict__ != bundle['profile']:
        raise ValueError('Bundle profile differs from its original configuration')
    return profile


def _registration_timing(identity: dict, profile: PredictionProfile, *, derive_time: bool = False) -> dict:
    """Prove the registration date from the mint and service-link transaction."""
    if identity.get('registration_evidence'):
        proofs = identity['registration_evidence']
        part = {name: proofs[name]['value'] for name in ('transaction', 'receipt', 'header')}
        tx_hash = part['transaction']['hash']
        block = int(part['transaction']['blockNumber'], 16)
        for name, method, params in (
            ('transaction', 'eth_getTransactionByHash', [tx_hash]),
            ('receipt', 'eth_getTransactionReceipt', [tx_hash]),
            ('header', 'eth_getBlockByNumber', [hex(block), False]),
        ):
            if proofs[name]['method'] != method or proofs[name]['params'] != params:
                raise ValueError('Registration transaction proof uses different parameters')
        _, receipt, _, timestamp = _receipt(part, profile.confirmation_head)
        transfer_topic = '0x' + keccak(b'Transfer(address,address,uint256)').hex()
        linked_topic = '0x' + keccak(b'ServiceAgentLinked(uint256,uint256)').hex()
        minted = [log for log in receipt['logs'] if log['address'].lower() == REGISTRY and len(log['topics']) == 4
                  and log['topics'][0].lower() == transfer_topic and int(log['topics'][1], 16) == 0
                  and int(log['topics'][2], 16) == int(BRIDGER, 16) and int(log['topics'][3], 16) == profile.agent_id]
        linked = [log for log in receipt['logs'] if log['address'].lower() == BRIDGER and len(log['topics']) == 3
                  and log['topics'][0].lower() == linked_topic and int(log['topics'][1], 16) == profile.service_id
                  and int(log['topics'][2], 16) == profile.agent_id]
        if len(minted) != 1 or len(linked) != 1 or int(minted[0]['logIndex'], 16) >= int(linked[0]['logIndex'], 16):
            raise ValueError('Unique identity mint and ordered same-transaction service link are missing')
        actual_time = datetime.fromtimestamp(timestamp, timezone.utc).isoformat()
        claimed_time = identity.get('registration_time') if derive_time else identity['registration_time']
        if claimed_time != actual_time and not (derive_time and claimed_time is None):
            raise ValueError('Registration date differs from its authenticated block header')
        if derive_time:
            identity['registration_time'] = actual_time
        identity['registration_block'] = block
    else:
        identity.pop('registration_time', None)
    return identity


def verify_identity(evidence: RetainedEvidence, bundle: dict, profile: PredictionProfile) -> dict:
    if bundle.get('identity_protocol') == 'mech-registered-v1':
        from reputation_platform.mech_task_identity import verify_mech_identity

        verified = verify_mech_identity(evidence, bundle, profile.registration_reference)
        identity = evidence.tree(bundle['identity'])
        identity['checks'] = [item.model_dump(mode='json') for item in verified['checks']]
        identity.setdefault('historical_note', '当前ERC-8004注册不被前推为历史注册；每项任务另核任务区块的同服务与执行控制。')
        evidence.snapshot_header = identity['header']['value']
        return _registration_timing(identity, profile, derive_time=True)

    identity = evidence.tree(bundle['identity'])
    n, calls = profile.snapshot_block, identity['calls']
    if (int(identity['chain']['value'], 16) != profile.chain_id
        or identity['chain']['method'] != 'eth_chainId' or identity['chain']['params'] != []
        or identity['header']['method'] != 'eth_getBlockByNumber'
        or identity['header']['params'] != [hex(n), False]
        or identity['header']['value']['hash'] != profile.snapshot_hash
        or int(identity['header']['value']['number'], 16) != n):
        raise ValueError('Frozen chain instance differs')
    expected_uri = f'https://marketplace.olas.network/erc8004/gnosis/ai-agents/{profile.service_id}'
    checks = (
        (_word(calls, 'registration-owner', REGISTRY, 'ownerOf(uint256)', n, profile.agent_id), int(BRIDGER, 16)),
        (_word(calls, 'bridger-agent-id', BRIDGER, 'mapServiceIdAgentIds(uint256)', n, profile.service_id), profile.agent_id),
        (_word(calls, 'mech-service-id', profile.mech, 'serviceId()', n), profile.service_id),
        (_word(calls, 'mech-service-registry', profile.mech, 'serviceRegistry()', n), int(SERVICE_REGISTRY, 16)),
    )
    if any(actual != expected for actual, expected in checks):
        raise ValueError('Current registration and historical service identity differ')
    uri = calls['registration-uri']
    call_value(calls, 'registration-uri', REGISTRY, calldata('tokenURI(uint256)', profile.agent_id), n)
    if _abi_text(uri) != expected_uri:
        raise ValueError('Registered service URI differs')
    registration = identity['registration']
    _, raw = evidence.observation(registration['evidence'], url=expected_uri, method='GET')
    evidence.remember(profile.registration_source, profile.registration_sha256)
    if hashlib.sha256(raw).hexdigest() != profile.registration_sha256:
        raise ValueError('Registered document differs from the frozen source')
    document = json.loads(raw)
    if (document != registration['payload'] or not any(item.get('agentId') == profile.agent_id
        and str(item.get('agentRegistry', '')).lower() == f'eip155:100:{REGISTRY}' for item in document.get('registrations', []))):
        raise ValueError('Original registration does not bind the actual ERC-8004 identity')
    endpoints = [str(item.get('endpoint', '')) for item in document.get('services', []) if item.get('name') == 'operator']
    if not any(endpoint.startswith(f'https://{profile.mech[2:]}-100.mech.') for endpoint in endpoints):
        raise ValueError('Original registration does not bind this Mech')
    if 'head' not in identity or identity['head']['method'] != 'eth_blockNumber' or identity['head']['params'] != []:
        raise ValueError('Observed confirmation height proof is missing')
    if int(identity['head']['value'], 16) != profile.confirmation_head:
        raise ValueError('Confirmation height differs from the original observed head')
    evidence.snapshot_header = identity['header']['value']
    return _registration_timing(identity, profile)


def load_selection(evidence: RetainedEvidence, run: Path, profile: PredictionProfile) -> tuple[CandidateRecord, PredictionHistoryDescriptor]:
    manifest = evidence.manifest(run)
    sources_path = next(item['path'] for item in manifest['inputs'] if item['path'].endswith(profile.candidate_key + '.sources.json'))
    analysis_path = next(item['path'] for item in manifest['inputs'] if item['path'].endswith(profile.candidate_key + '.analysis.json'))
    admission_path = next(item['path'] for item in manifest['inputs'] if item['path'].endswith('/admission-report.json'))
    sources = [SourceDocument.model_validate(item) for item in evidence.json(sources_path)]
    analysis = validate_analysis(DeclarationAnalysis.model_validate(evidence.json(analysis_path)), sources)
    payload = next(item for item in evidence.json(admission_path)['candidates'] if item['key'] == profile.candidate_key)
    payload.pop('ready_for_full_score', None)
    candidate = CandidateRecord.model_validate(payload)
    descriptor = PredictionHistoryDescriptor.model_validate(evidence.json((run / 'descriptor.json').relative_to(evidence.root).as_posix()))
    metadata_file = evidence.remember(descriptor.metadata_source_file)
    metadata = json.loads(metadata_file.read_bytes())
    source = next(item for item in sources if item.source_id == descriptor.metadata_source_id)
    if (source.raw_sha256 != hashlib.sha256(metadata_file.read_bytes()).hexdigest()
        or json.loads(source.text) != metadata or descriptor.tools != prediction_tool_descriptors(metadata)):
        raise ValueError('Planning source schemas differ from the actual retained metadata')
    selection = PlanSelection.model_validate(evidence.json((run / 'selection.json').relative_to(evidence.root).as_posix()))
    if (candidate.registration_reference != profile.registration_reference or descriptor.published_mech != profile.mech
        or descriptor.service_id != str(profile.service_id)
        or select_prediction_plan(analysis, candidate, descriptor, policy_version=profile.policy_version) != selection
        or selection.status != 'SELECTED' or selection.policy_id != profile.policy_version):
        raise ValueError('The automatically selected plan does not match this registered service')
    selected_operations = {claim.operation for claim in analysis.claims if claim.claim_id in selection.claim_ids}
    return candidate, descriptor.model_copy(update={'tools': [tool for tool in descriptor.tools if tool.operation in selected_operations]})


def _finding(label: str, verdict: Verdict, explanation: str) -> ReportFinding:
    return ReportFinding(label=label, verdict=verdict, explanation=explanation)


def _prompt_contains_title(prompt: str, title: str) -> bool:
    if title in prompt:
        return True
    sections = r'(?m)^--- [A-Z][A-Z0-9 _-]* ---[ \t]*\r?$'
    for heading in re.finditer(sections, prompt):
        fragment = prompt[heading.end():].lstrip()
        if not fragment.startswith('['):
            continue
        try:
            messages, _ = json.JSONDecoder().raw_decode(fragment)
        except ValueError:
            continue
        if isinstance(messages, list) and any(
            isinstance(message, dict) and message.get('role') in ('system', 'user', 'assistant', 'tool')
            and isinstance(message.get('content'), str) and title in message['content'] for message in messages
        ):
            return True
    return False


def _check_behavior_output(evidence: RetainedEvidence, descriptor: PredictionHistoryDescriptor,
                           tool: str, output: dict) -> None:
    catalog = evidence.json(descriptor.metadata_source_file)
    schema = catalog['toolMetadata'][tool]['output']['schema']
    for name in schema.get('required', []):
        if name not in output:
            raise OutputViolation('已认证交付缺少实际工具声明的必备字段：' + name)
    types = {'string': lambda value: isinstance(value, str),
             'integer': lambda value: type(value) is int,
             'number': lambda value: type(value) in (int, float),
             'boolean': lambda value: type(value) is bool,
             'object': lambda value: isinstance(value, dict),
             'array': lambda value: isinstance(value, list),
             'null': lambda value: value is None}
    for name, declaration in schema.get('properties', {}).items():
        expected = declaration.get('type')
        if name not in output or expected is None:
            continue
        if expected not in types:
            raise ValueError('暂未适配该交付字段的声明类型：' + name)
        if not types[expected](output[name]):
            raise OutputViolation('已认证交付字段与实际声明类型不符：' + name)


def explain_task(evidence: RetainedEvidence, task: dict, profile: PredictionProfile,
                 descriptor: PredictionHistoryDescriptor, translation: dict, *,
                 verification_revision: int = 1) -> tuple[SampleExplanation, dict]:
    if (type(verification_revision) is not int or verification_revision not in (1, 2, 3, 4)
        or verification_revision in (3, 4) and profile.policy_version != 'prediction-history-v2'):
        raise ValueError('Unsupported prediction verification revision')
    purpose = MeasurementPurpose(task['purpose'])
    verdict, prediction, observed = Verdict.UNKNOWN, None, None
    claimed, independent, checks, detail = '尚未取得可信交付文件。', '必要证据尚未完整取得，本条不扣成失败。', [], {}
    title, original_input = '本槽位尚缺合资格市场', '固定筛选范围内尚未取得本槽位所需的不同已结算问题。'
    before = set(evidence.inputs)
    try:
        if not task.get('request_id'):
            raise ValueError(task.get('reason', '未取得合资格市场'))
        if any(not isinstance(task.get(name), dict) for name in ('chain_evidence', 'market_evidence', 'input', 'output')):
            raise ValueError('本槽位的请求、交付或独立市场原件尚未完整取得')
        chain = evidence.tree(task['chain_evidence'])
        anchors = extract_task_anchors(chain, mech=profile.mech, request_id=task['request_id'], confirmation_head=profile.confirmation_head)
        settlement = evidence.market(task['market_evidence'], profile)
        if settlement.verdict != Verdict.PASS:
            raise ValueError('市场题干与有效最终结算尚不能完整对应：' + settlement.reason)
        source = evidence.content(task['input'], anchors['input_digest'], 'metadata.json')
        if not isinstance(source, dict):
            raise ValueError('原始请求尚未提供可识别的任务对象与市场上下文')
        context, prompt, tool = source.get('request_context', {}), source.get('prompt'), source.get('tool')
        if profile.policy_version == 'prediction-history-v2' and context == {}:
            from reputation_platform.prediction_question_resolution import verify_exact_question_resolution

            resolution = task['question_resolution']
            market = verify_exact_question_resolution(evidence, resolution, source)
            if settlement.question_id != resolution['question_id'] or settlement.title != resolution['title']:
                raise ValueError('精确原题定位与独立链上问题不一致')
        else:
            if not isinstance(context, dict) or context.get('type') != 'omen' or not isinstance(context.get('market_id'), str):
                raise ValueError('原始请求尚未提供可识别的任务对象与市场上下文')
            market = context['market_id'].lower()
        title_bound = isinstance(prompt, str) and (f'"{settlement.title}"' in prompt
            or profile.policy_version == 'prediction-history-v2'
            and task.get('question_resolution', {}).get('method') == 'omen-exact-direct-question-v1'
            and prompt == settlement.title)
        if (market != settlement.market or task['market'] != settlement.market
            or not title_bound or tool not in {item.operation for item in descriptor.tools}):
            raise ValueError('原始工具、题干或目标市场未与声明方案对应')
        if profile.policy_version == 'prediction-history-v2' and task.get('question_id') != settlement.question_id:
            raise ValueError('冻结的问题ID与独立链上问题不一致')
        if not anchors['delivery_timestamp'] < min(profile.cutoff_timestamp, settlement.opening_timestamp, settlement.finalized_timestamp):
            raise ValueError('预测并未在固定截止、市场关闭及最终结算之前交付')
        observed = datetime.fromtimestamp(anchors['delivery_timestamp'], timezone.utc)
        question_sha = hashlib.sha256(settlement.title.encode()).hexdigest()
        translated = translation.get(question_sha, {})
        title = translated.get('question_zh') or settlement.title
        original_input = ('用户要求为一个是/否问题给出概率：' + title + '\n原问题：' + settlement.title
                          + f'\n调用工具：{tool}；市场关闭：{datetime.fromtimestamp(settlement.opening_timestamp, timezone.utc).isoformat()}。')
        if translated.get('plain_language_zh'):
            original_input += '\n问题解释：' + translated['plain_language_zh']
        try:
            output = evidence.content(task['output'], anchors['output_digest'], str(int(task['request_id'], 16)))
        except AuthenticatedJsonError as error:
            raise OutputViolation('链上 CID 对应的原始交付不是有效 JSON。') from error
        if not isinstance(output, dict):
            raise OutputViolation('已认证的交付 JSON 不是声明中的对象结构。')
        if verification_revision in (3, 4):
            claimed = '原始交付结果：' + str(output.get('result', '缺失'))
        if str(output.get('requestId')) != str(int(task['request_id'], 16)):
            raise OutputViolation('交付文件的任务号与唯一链上交付不一致。')
        if verification_revision == 1:
            if ('tool' in output and output['tool'] != tool) or not isinstance(output.get('prompt'), str) or settlement.title not in output['prompt']:
                raise OutputViolation('交付中的工具或原题干与已绑定的请求不一致。')
        elif verification_revision == 2:
            if 'tool' in output and output['tool'] != tool:
                raise OutputViolation('交付中的工具与已绑定的请求不一致。')
            if purpose == MeasurementPurpose.FUNCTIONAL:
                if not isinstance(output.get('prompt'), str) or not _prompt_contains_title(output['prompt'], settlement.title):
                    raise OutputViolation('交付中的原题干与已绑定的请求不一致。')
            else:
                _check_behavior_output(evidence, descriptor, tool, output)
        else:
            if 'tool' in output and output['tool'] != tool:
                raise OutputViolation('交付中的工具与已绑定的请求不一致。')
            _check_behavior_output(evidence, descriptor, tool, output)
        checks.extend(settlement.checks)
        file_explanation = '原始请求与交付文件逐块通过 CID/DAG 校验；任务编号、工具、题干、市场和预测时序已匹配。'
        if verification_revision == 2:
            file_explanation = ('原始请求与交付文件逐块通过 CID/DAG 校验；任务号和工具绑定一致，原题由已认证请求精确绑定市场及结算。'
                + ('交付的原题按普通文本或明确JSON对话中的content原文精确匹配，不作模糊比较。'
                   if purpose == MeasurementPurpose.FUNCTIONAL else
                   '交付字段按实际声明核对；内部prompt是工具处理记录，不要求它再次回显原题。'))
        if verification_revision in (3, 4):
            file_explanation = ('原始请求与交付逐块通过CID校验；唯一链上任务、任务号和工具证明关联，原题精确绑定独立结算。'
                                '交付按实际声明字段核验，不要求内部prompt逐字回显原题。')
        checks.append(_finding('原任务与文件', Verdict.PASS, file_explanation))
        verification = verify_prediction_chain(chain, mech=profile.mech, service_id=profile.service_id,
            request_id=task['request_id'], confirmation_head=profile.confirmation_head,
            marketplace_event_revision=2 if verification_revision == 4 else 1)
        detail = {'anchors': anchors, 'settlement': settlement.model_dump(mode='json'), 'chain': verification.model_dump(mode='json')}
        claimed = '原始交付结果：' + str(output.get('result', '缺失'))
        if purpose == MeasurementPurpose.FUNCTIONAL:
            try:
                if (verification_revision not in (3, 4) and not isinstance(output.get('prompt'), str)
                    or not isinstance(output.get('result'), str)):
                    raise ValueError('声明中的 prompt/result 字符串字段不完整')
                result = json.loads(output['result'])
                prediction = BinaryPrediction(p_yes=result['p_yes'], p_no=result['p_no'], final_outcome=settlement.final_outcome)
            except (ValueError, KeyError, TypeError):
                verdict, reason = Verdict.FAIL, '已取得并验证原始交付，但其概率输出不符合声明中的字段、数值范围或概率和。'
                independent = reason + '依既定规则本题信用分为 0 分。'
                checks.append(_finding('概率格式', verdict, reason))
            else:
                verdict = Verdict.PASS if prediction.outcome_probability >= 0.5 else Verdict.FAIL
                reason = '给最终结果的概率不少于 50%。' if verdict == Verdict.PASS else '给最终结果的概率低于 50%。'
                winner = '是（Yes）' if prediction.final_outcome == 'yes' else '否（No）'
                claimed = f'Agent 给“是”的概率为 {prediction.p_yes:.1%}，“否”为 {prediction.p_no:.1%}。'
                independent = (f'市场协议的最终结算为“{winner}”；Agent 给这个结果的概率为 {prediction.outcome_probability:.1%}。'
                               f'按冻结的平方概率规则，本题信用分 {prediction.credit:.2f} 分。{reason}'
                               '中性的 50/50 预测得 75 分，因此这里的信用分不是预测准确率。')
                checks.append(_finding('概率与最终结果', verdict, independent))
        else:
            verdict, reason = verification.verdict, verification.reason
            checks.extend(verification.checks)
            independent = ('这次请求至交付的完整链上归属已核验。' if verdict == Verdict.PASS else '这次历史履约尚未得到完整通过结论。') + reason
            independent += f' 原优先服务与实际交付服务分别核对；这项不评价预测是否准确。'
    except OutputViolation as error:
        verdict, reason, prediction = Verdict.FAIL, str(error), None
        independent = '已认证原文件，但其内容违反本任务的输出约定：' + reason
        if purpose == MeasurementPurpose.FUNCTIONAL:
            independent += '依既定规则本题信用分为 0 分。'
        checks.append(_finding('已证实的输出差异', verdict, independent))
    except (ValueError, KeyError, TypeError, AttributeError, IndexError, OSError) as error:
        verdict, reason, prediction = Verdict.UNKNOWN, str(error), None
        independent = '必要证据未能完整对应，本条无法判断，不记为业务失败。缺项：' + reason
        checks.append(_finding('证据完整性', verdict, independent))
    references = sorted(set(evidence.inputs) - before)
    # Shared RPC/CAR files remain explicit in each sample, even if a previous sample already used them.
    def task_refs(value):
        if isinstance(value, dict):
            if set(value) == {'path', 'sha256'} and value['path'] in evidence.inputs:
                references.append(value['path'])
            else:
                for item in value.values(): task_refs(item)
        elif isinstance(value, list):
            for item in value: task_refs(item)
    task_refs(task)
    sample = ScoredSample(sample_id=f"{profile.policy_version}:{profile.candidate_key}:{task['slot']}",
        task_key=task.get('task_key') or f"missing:{profile.candidate_key}:{task['slot']}", purpose=purpose,
        verdict=verdict, elapsed_ms=None, reason=reason, evidence=sorted(set(references)), prediction=prediction)
    return SampleExplanation(sample=sample, observed_at=observed,
        title=('概率与结算' if purpose == MeasurementPurpose.FUNCTIONAL else '完整链上履约') + ' · ' + title,
        input_summary=original_input, claimed_output=claimed, independent_result=independent, checks=checks), detail


def availability_explanations(evidence: RetainedEvidence, run: Path, profile: PredictionProfile,
                              tasks: list[dict]) -> list[SampleExplanation]:
    manifest = evidence.manifest(run)
    slots = manifest['slots']
    if (manifest['policy_version'] not in ('prediction-history-v1', 'prediction-history-v2')
        or manifest['candidate_key'] != profile.candidate_key or manifest['policy_version'] != profile.policy_version
        or len(slots) != 10 or [item['scheduled_offset_seconds'] for item in slots] != list(range(0, 300, 30))
        or len({item['request_id'] for item in slots}) != 10):
        raise ValueError('Availability plan differs from the fixed ten distinct files and sampling interval')
    selected = {task['request_id']: task for task in tasks if task.get('request_id')}
    explanations = []
    for index, item in enumerate(slots, 1):
        task = selected.get(item['request_id'])
        if (task is None or not task.get('output') or item['sha256'] != task['output']['sha256']
            or item['response_file'] != task['output']['response_file']):
            raise ValueError('Availability file is outside the selected immutable cohort')
        if manifest['policy_version'] == 'prediction-history-v1':
            if item['url'] != task['output']['url']:
                raise ValueError('Availability file is outside the selected immutable cohort')
        else:
            layout = item.get('layout', 'unixfs-directory-v1')
            if (layout not in ('unixfs-directory-v1', 'unixfs-root-file-v1')
                or layout != task['output'].get('layout', 'unixfs-directory-v1')):
                raise ValueError('Availability layout differs from its authenticated historical file')
            chain = evidence.tree(task['chain_evidence'])
            anchors = extract_task_anchors(chain, mech=profile.mech, request_id=item['request_id'],
                                           confirmation_head=profile.confirmation_head)
            digest = anchors['output_digest']
            if item['root_digest'].lower() != digest.lower():
                raise ValueError('Availability source CID differs from its actual on-chain delivery')
            evidence.content_bytes(task['output'], digest, str(int(item['request_id'], 16)))
            expected_url = 'https://gateway.autonolas.tech/ipfs/f01701220' + digest[2:].lower()
            if layout == 'unixfs-directory-v1':
                expected_url += '/' + str(int(item['request_id'], 16))
            if item['url'] != expected_url:
                raise ValueError('Availability must read the actual plain HTTP file URL for its frozen layout')
        key, refs = f'availability-{index:03d}', []
        observed_path = run / f'{key}.observation.json'
        observed, elapsed, verdict = None, None, Verdict.UNKNOWN
        reason = '该槽位因前序权限、付费或限流停止，没有发出请求。'
        if observed_path.is_file():
            evidence.remember(observed_path.relative_to(evidence.root).as_posix())
            refs.append(observed_path.relative_to(evidence.root).as_posix())
            observation = ProbeObservation.model_validate_json(observed_path.read_bytes())
            if (observation.url != item['url'] or observation.method != 'GET'
                or observation.purpose != MeasurementPurpose.AVAILABILITY or observation.request_key != key):
                raise ValueError('Availability observation has another endpoint or purpose')
            observed, elapsed = observation.observed_at, observation.elapsed_ms
            raw = None
            if observation.response_file:
                response = (run / observation.response_file).resolve()
                if response.parent != run:
                    raise ValueError('Availability response escaped its retained run')
                evidence.remember(response.relative_to(evidence.root).as_posix(), observation.response_sha256)
                refs.append(response.relative_to(evidence.root).as_posix())
                raw = response.read_bytes()
            reason = '本次线路没有取得可判定的完整响应：' + str(observation.error_kind or observation.http_status)
            if observation.body_complete and observation.error_kind in (None, 'http_status_not_success'):
                if observation.http_status is not None and 500 <= observation.http_status <= 599:
                    verdict, reason = Verdict.FAIL, '公开历史文件入口返回了 HTTP 5xx。'
                elif observation.http_status == 200:
                    try:
                        actual = json.loads(raw)
                        matches = (hashlib.sha256(raw).hexdigest() == item['sha256']
                                   and str(actual.get('requestId')) == str(int(item['request_id'], 16)))
                    except (ValueError, TypeError, AttributeError):
                        matches = False
                    verdict = Verdict.PASS if matches else Verdict.FAIL
                    reason = '完整文件内容和任务号与预先固定的历史原件一致。' if matches else 'HTTP200 返回内容与预先固定的历史文件不一致。'
        else:
            skipped = run / f'{key}.skip.json'
            evidence.remember(skipped.relative_to(evidence.root).as_posix())
            refs.append(skipped.relative_to(evidence.root).as_posix())
            if json.loads(skipped.read_bytes()).get('request_sent') is not False:
                raise ValueError('Missing availability request must have an explicit retained skip')
        sample = ScoredSample(sample_id=f'{run.name}:{index:03d}', task_key=f'availability:{run.name}:{index:03d}',
            purpose=MeasurementPurpose.AVAILABILITY, verdict=verdict, elapsed_ms=elapsed, reason=reason, evidence=refs)
        explanations.append(SampleExplanation(sample=sample, observed_at=observed,
            title=f'历史交付入口 · 第 {index} 次访问', input_summary='读取事先固定的一份公开历史预测交付文件，核对完整文件摘要与任务号。',
            claimed_output='入口应返回这一历史任务的原始 JSON 文件；本次不提交新的付费推理任务。',
            independent_result=reason + (f' 实际耗时 {elapsed:.0f} 毫秒。' if elapsed is not None else ''),
            checks=[_finding('实际访问与内容核对', verdict, reason)]))
    return explanations


def build_prediction_report(*, history_run: Path, plan_run: Path, availability_run: Path | None = None,
                            translations: dict | None = None, identity_run: Path | None = None,
                            root: Path = PROJECT_ROOT, verification_revision: int = 1) -> tuple[EvaluationReport, dict, RetainedEvidence]:
    if type(verification_revision) is not int or verification_revision not in (1, 2, 3, 4):
        raise ValueError('Unsupported prediction verification revision')
    evidence = RetainedEvidence(root)
    history_manifest = evidence.manifest(history_run)
    bundle_name = (history_run / 'bundle.json').relative_to(root).as_posix()
    bundle_sources = [item for item in history_manifest.get('outputs', []) if item.get('path') == bundle_name]
    if len(bundle_sources) != 1:
        raise ValueError('Bundle is not bound to one completed history manifest output')
    bundle = json.loads(evidence.remember(bundle_name, bundle_sources[0]['sha256']).read_bytes())
    profile = load_history_profile(evidence, history_manifest, bundle)
    if verification_revision in (3, 4) and profile.policy_version != 'prediction-history-v2':
        raise ValueError('Verification revision 3/4 is limited to explicitly versioned V2 evidence')
    if verification_revision in (3, 4):
        evidence.remember('docs/adr/0017-prediction-question-and-output-contract.md')
    if verification_revision == 4:
        evidence.remember('docs/adr/0018-marketplace-request-event-versions.md')
    plan = bundle['plan']
    if (plan['pilot_only'] or plan['eligibility_uses_outputs'] is not False or len(plan['slots']) != 14
        or [item['purpose'] for item in plan['slots']] != ['functional'] * 7 + ['behavioral'] * 7
        or len(bundle['tasks']) != 14):
        raise ValueError('A nonpilot fourteen-slot disjoint plan is required')
    plan_source = evidence.remember(bundle['plan_reference']['path'], bundle['plan_reference']['sha256'])
    if json.loads(plan_source.read_bytes()) != plan:
        raise ValueError('Task plan differs from its persisted pre-output plan')
    for slot, task in zip(plan['slots'], bundle['tasks']):
        if any(task.get(key) != slot.get(key) for key in ('slot', 'purpose', 'request_id', 'market', 'task_key')):
            raise ValueError('Task differs from the immutable cohort slot')
    markets = [item['market'] for item in plan['slots'] if item.get('market')]
    if len(set(markets)) != len(markets) or any(market in plan['excluded_pilot_markets'] for market in markets):
        raise ValueError('Repeated or pilot market cannot enter formal measurement')
    if profile.policy_version == 'prediction-history-v2':
        questions = [slot['question_id'] for slot in plan['slots'] if slot.get('request_id')]
        if (any(not isinstance(qid, str) or not re.fullmatch(r'0x[0-9a-f]{64}', qid) for qid in questions)
            or len(set(questions)) != len(questions)
            or any(task.get('question_id') != slot.get('question_id') for slot, task in zip(plan['slots'], bundle['tasks']))):
            raise ValueError('V2 requires immutable distinct independent questions')
        evidence.remember('docs/adr/0016-prediction-evidence-v2.md')
    for item in bundle['inputs']:
        evidence.remember(item['path'], item['sha256'])
    # The original collector may predate the head-proof field; an explicit retained identity supplement is allowed.
    if identity_run:
        evidence.manifest(identity_run)
        supplement = evidence.json((identity_run / 'identity-supplement.json').relative_to(root).as_posix())
        bundle['identity'].update(supplement)
    identity = verify_identity(evidence, bundle, profile)
    candidate, descriptor = load_selection(evidence, plan_run, profile)
    samples, details = [], []
    if availability_run:
        samples.extend(availability_explanations(evidence, availability_run, profile, bundle['tasks']))
    for task in bundle['tasks']:
        explanation, detail = explain_task(evidence, task, profile, descriptor, translations or {},
                                           verification_revision=verification_revision)
        if task['purpose'] == 'behavioral' and not identity.get('registration_time'):
            reason = '尚缺 ERC-8004 登记日期的原始交易证明，不能完整说明当前身份与历史服务的时序。'
            explanation.sample.verdict, explanation.sample.reason = Verdict.UNKNOWN, reason
            explanation.independent_result += ' ' + reason + '底层履约结论仍保留，最终不扣成失败。'
            explanation.checks.append(_finding('登记与历史时序', Verdict.UNKNOWN, reason))
        elif identity.get('registration_time') and explanation.observed_at:
            before_registration = explanation.observed_at < datetime.fromisoformat(identity['registration_time'])
            explanation.independent_result += (' 本任务早于当前 ERC-8004 登记，归属依据是同一服务合约和当时执行控制。' if before_registration
                else ' 本任务在该 ERC-8004 身份登记之后交付，登记日期已由铸造与同笔服务关联事件核实。')
        samples.append(explanation)
        details.append(detail)
    dates = [item.observed_at for item in samples if item.sample.purpose != MeasurementPurpose.AVAILABILITY and item.observed_at]
    limits = ['本报告评价公开历史交付文件的访问体验，不评价当前付费推理服务是否在线。',
              '结算依据是已核对题干、选项和市场条件的协议最终结果，不等同于平台独立证明现实世界事件。',
              '每个市场只保留截止前最后一次交付；不同问题仍可能相关，十四题不能代表长期总体水平。',
              '概率信用分的 50/50 中性基准为 75 分；该值不是预测准确率。',
              '同类政策可复用，但不同能力范围的综合分不作无条件横向排名。']
    if verification_revision == 2:
        limits.append('核验修订2：功能题干支持明确JSON对话content的正规解码后精确匹配；行为题干由已认证请求绑定结算，内部prompt处理记录不必再次回显原题。')
    if verification_revision in (3, 4):
        limits.append('核验修订3：以唯一链上任务和输入/输出CID证明任务关联，交付按真实字段声明及概率格式核验；内部prompt没有逐字回显原题的额外义务。Invalid response或服务错误并非有效概率答复，相关失败仍计0信用。')
    if verification_revision == 4:
        limits.append('历史事件核验修订4：支持同一Marketplace官方两版普通请求事件；旧事件的输入CID仍由原调用与独立Mech Request精确交叉核对，其他身份、支付与交付规则保持。')
    if profile.policy_version == 'prediction-history-v2':
        limits.append('证据扩展V2：原件可为CID认证的根文件或目录文件；无明确市场ID时，仅按完整原题、唯一问题和唯一市场精确定位，再独立核链上结算。每个Question只占一个槽，不混用旧版样本。')
    if profile.policy_version == 'prediction-history-v2' and profile.history_max_deliveries == 512:
        evidence.remember('docs/adr/0019-prediction-history-bound.md')
        limits.append(f'本次按用户批准最多检查512条历史交付，实际审查{len(bundle.get("qualifications", []))}条，'
                      f'其中{plan["qualified_market_count"]}个不同问题合格；达到14即停止筛选。实际使用的历史起止见评价时间范围，512不是评分样本数。')
    if not availability_run:
        limits.append('本次尚未完成新的十次公开入口采样，可用性和综合分待评价。')
    if not identity.get('registration_time'):
        limits.append('当前注册关联已核验，ERC-8004 具体登记日期尚缺；历史任务以同一服务合约与当时执行控制证明归属，不将当前注册时间前推。')
    else:
        limits.append('当前身份的 ERC-8004 登记时间：' + str(identity['registration_time']) + '；历史履约另核当时服务和执行者。')
    report = EvaluationReport(policy_version=profile.policy_version, candidate_key=candidate.key, name=candidate.name,
        registration_reference=profile.registration_reference, generated_at=datetime.now(timezone.utc),
        scope='本方案固定十次公开历史预测文件访问、七个不同已结算问题的概率表现，以及另外七个问题的完整链上交付归属。下方逐项展示已取得样本和缺项；全部达到要求才给综合分。',
        scope_exclusions=['新付费推理调用与未抽到的其他工具', '投资收益、资产安全、现实事件的独立事实调查', '将同一问题重复交付当成多个独立事实'],
        evaluation_window=('历史交付：' + min(dates).isoformat() + ' 至 ' + max(dates).isoformat() if dates else '本次尚无可核定的历史交付时间')
            + '；历史截止 UTC 2026-10-01 00:00，独立结算固定于 Gnosis 区块 ' + str(profile.snapshot_block) + '。',
        approach='由有来源的真实工具声明自动匹配方案；先固定不同市场和 7+7 分组，再读预测结果；从原始 RPC、事件、CID/DAG 与独立市场结算重建结论。',
        samples=samples, source_references=sorted(evidence.inputs), limitations=limits)
    return report, {'identity': identity, 'tasks': details, 'qualifications': bundle.get('qualifications', []),
                    'issues': bundle.get('issues', []), 'plan': plan}, evidence
