"""Offline, hash-bound contract supplements; these snapshots never create scores."""
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import tarfile
import tempfile
from uuid import uuid4

from reputation_core.admission import Verdict
from reputation_core.application import AgentProfile, normalize_reference
from reputation_core.chain_review import AgentChainEvidence, ChainDimensionEvidence
from reputation_platform.chain_evidence import publish_execution_reviews

CHECKER = 'evm.contract-lifecycle-v1'
MANIFEST_SCHEMA = 'contract-lifecycle-snapshot-manifest-v1'
PACKAGE_SCHEMA = 'contract-lifecycle-snapshot-package-v1'
PACKAGE_INDEX = 'contract-lifecycle-package.json'
ADR = 'docs/adr/0027-contract-lifecycle-supplement.md'
MANDATORY_LIMITATIONS = [
    '这是新增链上补测证据，不新增声誉评分或修改原范围分及其分母。',
    '本补测未采集Agent业务HTTP响应，RPC、钱包签名及确认等待不作为A可用性样本。',
    '源码或模拟发现与真实执行事实分别展示，不将未发生的状态或损失写成实测结果。',
]


def _check(value, message):
    if not value:
        raise ValueError(message)


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _path(root, name):
    name = str(name)
    parts = name.split('/')
    _check('\\' not in name and ':' not in name and all(part not in ('', '.', '..') for part in parts),
           'Supplement paths must be canonical repository-relative paths')
    allowed = (name.startswith('runtime/') or name.startswith('configs/') or name.startswith('docs/adr/')
               or name.startswith('data/declarations/') and name.endswith('.json'))
    denied = {'secrets', 'platform-config', '.git', '.venv', 'node_modules', 'platform-postgres'}
    _check(allowed and not PurePosixPath(name).is_absolute()
           and not any(part.startswith('.') or '.private' in part.lower() or part.lower() in denied for part in parts)
           and Path(name).suffix.lower() not in {'.key', '.pem', '.p12', '.pfx', '.log', '.db'},
           'Only selected public supplement sources may be retained')
    path = root / name
    _check(path.resolve().is_relative_to(root.resolve()), 'Supplement source escapes the workspace')
    for parent in (path, *path.parents):
        if parent == root:
            break
        _check(not parent.is_symlink() and not parent.is_junction(), 'Supplement files cannot traverse links')
    return path


def _write(path, value):
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write('\n')


def _collect_sources(root, config_name):
    hashes = {}

    def remember(name, expected=None):
        path = _path(root, name)
        raw = path.read_bytes()
        digest = _sha(raw)
        _check(expected is None or digest == expected, 'Retained supplement source digest changed')
        _check(name not in hashes or hashes[name] == digest, 'Conflicting supplement source digest')
        hashes[name] = digest
        return json.loads(raw) if path.suffix == '.json' else raw

    config = remember(config_name)
    _check(config['schema_version'] == 'contract-lifecycle-supplement-v1' and config['checker_id'] == CHECKER,
           'Unsupported contract supplement checker')
    remember(ADR)
    protocol = remember(config['protocol_config'])
    remember(protocol['abi_path'])
    remember(config['plan_path'])
    # The parent is replayed for identity/declaration attribution, not rescored
    # with the new samples. Its complete immutable input graph remains usable.
    parent_manifest = remember(config['identity_manifest'])
    remember(config['identity_report'])
    for item in parent_manifest['inputs']:
        remember(item['path'], item['sha256'])
    for name in config.get('additional_sources', []):
        remember(name)
    for task in config['tasks']:
        for field in ('intent_path', 'task_path', 'unsigned_transaction', 'plan_path'):
            if task.get(field):
                remember(task[field])
        for name in task['rpc_observations']:
            observation = remember(name)
            if observation.get('response_file'):
                raw_path = _path(root, name).parent / observation['response_file']
                _check(raw_path.parent == _path(root, name).parent, 'RPC response must remain beside its observation')
                remember(raw_path.relative_to(root).as_posix(), observation['response_sha256'])
    return config, hashes


def _replay(root, config, hashes, generated_at):
    # Static protocol registration; no metadata imports or remote execution.
    from reputation_platform.contract_lifecycle_evidence import replay_contract_lifecycle
    adapters = {CHECKER: replay_contract_lifecycle}
    _check(config.get('schema_version') == 'contract-lifecycle-supplement-v1'
           and config.get('checker_id') in adapters, 'No registered contract supplement checker')
    facts, checks, actions = adapters[config['checker_id']](root, config, hashes)
    canonical = normalize_reference(config['registration_reference'])
    _check(canonical is not None and facts['registration_reference'] == canonical
           and facts['candidate_key'] == config['candidate_key'] and facts['name'] == config['name'],
           'Contract supplement identity differs from independently replayed sources')
    _check(actions and len({action.transaction_hash for action in actions}) == len(actions),
           'A supplement must retain one action per distinct real transaction')
    _check(facts['verified_task_count'] == len(actions) and facts['task_count'] >= len(actions),
           'Supplement task/action count differs')
    _check(facts['task_count'] == len(config['tasks']) == len(facts['tasks']),
           'Supplement omitted a planned task from its factual ledger')
    verdicts = [action.verdict for action in actions]
    observed = len(actions)
    unresolved = [f"任务{task['task_key']}：{task.get('reason','原件尚未核齐')}"
                  for task in facts.get('tasks', []) if task.get('verified') is False]
    conclusion = (Verdict.FAIL if Verdict.FAIL in verdicts else
                  Verdict.UNKNOWN if len(actions) < facts['task_count'] or Verdict.UNKNOWN in verdicts
                  else Verdict.PASS)
    limitations = list(dict.fromkeys(config.get('limitations', []) + facts.get('limitations', []) + MANDATORY_LIMITATIONS))
    profile = AgentProfile(business_summary=facts.get('business_summary',
        '提供链上兑换及订单操作工具，由获授权的用户钱包签名执行；具体已测操作和未测功能分别列明。'),
        ecosystem=facts.get('ecosystem', 'DeFi · 合约工具'), role='asset-execution',
        registration_chain_id=int(canonical.split(':')[1]), execution_chain_ids=[facts['chain_id']],
        capabilities=facts.get('capabilities', [action.title for action in actions]),
        execution_accounts=[facts['buyer']], evidence_status='verified',
        sources=[config['identity_report'], config['protocol_config']],
        boundary='入口关联依据提供方公开声明；用户钱包签名执行，不代表提供方自主决策或自主托管。')
    return AgentChainEvidence(candidate_key=config['candidate_key'], registration_reference=canonical,
        generated_at=generated_at, title=config['title'], profile=profile, actions=actions, checks=checks,
        dimensions=[
            ChainDimensionEvidence(purpose='availability', verdict=Verdict.UNKNOWN, observed=0,
                summary='没有新增Agent业务HTTP访问观测；本次仅补充链上功能与履约事实。',
                missing_evidence=['RPC、签名服务及链确认耗时不能代替Agent A维度业务响应。']),
            ChainDimensionEvidence(purpose='functional', verdict=conclusion, observed=observed,
                summary=facts.get('functional_summary', '仅支持本次明确任务的功能约束核验，不代表该身份全部功能通过。'),
                missing_evidence=facts.get('unmeasured', []) + unresolved),
            ChainDimensionEvidence(purpose='behavioral', verdict=conclusion, observed=observed,
                summary=facts.get('behavioral_summary', '按各任务目标分别核验真实执行终态；订单撤销完成不等于兑换成交。'),
                missing_evidence=facts.get('confirmation_limitations', ['确认距离不是finalized或L1最终性证明。']) + unresolved),
        ], selection=config['selection'], window_summary=facts['window_summary'],
        sources=sorted(hashes), limitations=limitations)


def build_snapshot(root: Path, config_path: Path, directory: Path):
    root = root.resolve()
    config_path = (root / config_path).resolve()
    directory = (root / directory).resolve()
    _check(config_path.is_relative_to(root / 'configs/chain-supplements')
           and directory.is_relative_to(root / 'runtime') and not directory.exists(),
           'Use a reviewed supplement configuration and a new runtime destination')
    config_name = config_path.relative_to(root).as_posix()
    config, hashes = _collect_sources(root, config_name)
    review = _replay(root, config, hashes, datetime.now(timezone.utc))
    directory.mkdir(parents=True, exist_ok=False)
    snapshot = directory / 'snapshot.json'
    snapshot.write_text(review.model_dump_json(indent=2) + '\n', encoding='utf-8')
    _write(directory / 'manifest.json', {'schema_version': MANIFEST_SCHEMA, 'checker_id': CHECKER,
        'configuration': config_name, 'snapshot': {'path':snapshot.relative_to(root).as_posix(),
                                                  'sha256':_sha(snapshot.read_bytes())},
        'inputs':[{'path':name,'sha256':digest} for name,digest in sorted(hashes.items())]})
    return review


def verify_snapshot(root: Path, directory: Path):
    root = root.resolve()
    directory = (root / directory).resolve()
    manifest = json.loads((directory/'manifest.json').read_bytes())
    _check(manifest['schema_version'] == MANIFEST_SCHEMA and manifest['checker_id'] == CHECKER,
           'Unsupported supplement snapshot manifest')
    hashes = {item['path']:item['sha256'] for item in manifest['inputs']}
    _check(len(hashes) == len(manifest['inputs']), 'Duplicate supplement dependency')
    _check(ADR in hashes, 'Contract supplement policy is not hash-bound')
    for name,digest in hashes.items():
        _check(_sha(_path(root,name).read_bytes()) == digest, 'Supplement input changed')
    _check(manifest['configuration'] in hashes, 'Supplement configuration is not hash-bound')
    config = json.loads(_path(root,manifest['configuration']).read_bytes())
    snapshot = _path(root,manifest['snapshot']['path'])
    _check(snapshot.parent == directory and _sha(snapshot.read_bytes()) == manifest['snapshot']['sha256'],
           'Supplement snapshot bytes changed')
    supplied = AgentChainEvidence.model_validate_json(snapshot.read_bytes())
    replayed = _replay(root, config, hashes, supplied.generated_at)
    _check(supplied.model_dump(mode='json') == replayed.model_dump(mode='json'),
           'Supplement facts or presentation differ from source replay')
    return replayed, hashes, config


def import_snapshot(repository, directory: Path):
    review, hashes, config = verify_snapshot(repository.root, directory)
    destination = repository.root/'runtime/contract-lifecycle-imports'/uuid4().hex
    destination.parent.mkdir(parents=True, exist_ok=True)
    return publish_execution_reviews(repository, [(review,hashes)], destination,
                                     agent_names={review.candidate_key:config['name']})


def export_snapshot(root: Path, directory: Path, output: Path):
    root = root.resolve()
    directory = (root/directory).resolve()
    review, hashes, _ = verify_snapshot(root,directory)
    for path in (directory/'snapshot.json',directory/'manifest.json'):
        hashes[path.relative_to(root).as_posix()] = _sha(path.read_bytes())
    inventory = [{'path':name,'sha256':digest,'size':_path(root,name).stat().st_size}
                 for name,digest in sorted(hashes.items())]
    index = {'schema_version':PACKAGE_SCHEMA, 'checker_id':CHECKER,
             'manifest':(directory/'manifest.json').relative_to(root).as_posix(), 'files':inventory}
    output = root/output
    output.parent.mkdir(parents=True,exist_ok=True)
    with output.open('xb') as stream, tarfile.open(fileobj=stream,mode='w:gz') as archive:
        raw = (json.dumps(index,ensure_ascii=False,indent=2)+'\n').encode('utf-8')
        info = tarfile.TarInfo(PACKAGE_INDEX);info.size=len(raw)
        archive.addfile(info,io.BytesIO(raw))
        for item in inventory:
            raw = _path(root,item['path']).read_bytes()
            _check(_sha(raw)==item['sha256'],'Supplement input changed during export')
            info=tarfile.TarInfo(item['path']);info.size=len(raw)
            archive.addfile(info,io.BytesIO(raw))
    return {'archive_sha256':_sha(output.read_bytes()),'archive_bytes':output.stat().st_size,
            'files':len(inventory),'candidate_key':review.candidate_key,'new_scores':0}


def restore_snapshot(root: Path, archive_path: Path):
    """Validate in an isolated tree before restoring any missing public source."""
    root=root.resolve()
    with tarfile.open(root/archive_path,'r:gz') as archive:
        members=archive.getmembers()
        _check(all(member.isfile() for member in members) and len({item.name for item in members})==len(members),
               'Supplement archive contains duplicate or nonregular members')
        index=json.load(archive.extractfile(PACKAGE_INDEX))
        _check(index['schema_version']==PACKAGE_SCHEMA and index['checker_id']==CHECKER,
               'Unsupported supplement package')
        files={item['path']:item for item in index['files']}
        _check(len(files)==len(index['files']) and set(item.name for item in members)=={PACKAGE_INDEX,*files},
               'Supplement inventory differs from archive members')
        root_runtime=root/'runtime';root_runtime.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='contract-supplement-check-',dir=root_runtime) as temporary:
            scratch=Path(temporary)
            for name,item in files.items():
                raw=archive.extractfile(name).read()
                _check(len(raw)==item['size'] and _sha(raw)==item['sha256'],'Supplement archive source changed')
                target=_path(scratch,name);target.parent.mkdir(parents=True,exist_ok=True)
                target.write_bytes(raw)
            review,_,_=verify_snapshot(scratch,_path(scratch,index['manifest']).parent)
            for name,item in files.items():
                target=_path(root,name)
                if target.exists():
                    _check(_sha(target.read_bytes())==item['sha256'],'Existing supplement source differs; never overwrite')
                else:
                    target.parent.mkdir(parents=True,exist_ok=True)
                    with target.open('xb') as stream:
                        stream.write(_path(scratch,name).read_bytes())
    return _path(root,index['manifest']).parent, review
