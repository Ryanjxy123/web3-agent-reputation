"""Assemble public CoW task references offline; export/replay remain separate steps."""
import argparse
import base64
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'packages/core/src'), str(ROOT / 'services/platform/src')]
from reputation_core.swap import integer
from reputation_platform import cow_swap_report as adapter
from reputation_platform.swap_report import SwapEvidence, _lookup


def require(value, message):
    if not value:
        raise ValueError(message)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def read(root, name):
    return json.loads(adapter._public_path(root, name).read_bytes())


def references(item):
    names = [*item.get('http_observations', [])]
    names.extend(item[key] for key in ('task_intent', 'prepared_order') if item.get(key))
    execution = item.get('execution')
    if execution:
        names.extend([execution['order_observation'], *execution['trades_observations'],
                      *execution['rpc_observations'], *execution.get('related_order_observations', {}).values()])
        if execution.get('prestate'):
            names.extend([execution['prestate']['snapshot'], *execution['prestate']['rpc_observations']])
    return names


def evidence_for(root, item, expected_hashes=None):
    hashes = {}

    def add(name):
        path = adapter._public_path(root, name)
        key = path.relative_to(root).as_posix()
        if key in hashes:
            return
        raw = path.read_bytes()
        hashes[key] = digest(raw)
        if expected_hashes is not None:
            require(expected_hashes.get(key) == hashes[key], 'Retained public original differs from explicit source SHA')
        if key.endswith('.observation.json'):
            observation = json.loads(raw)
            if observation.get('response_file'):
                sibling = observation['response_file']
                require(Path(sibling).name == sibling, 'Observation response must remain a sibling')
                body = (path.parent / sibling).relative_to(root).as_posix()
                add(body)
                require(hashes[body] == observation['response_sha256'], 'Public response SHA differs')

    for name in references(item):
        add(name)
    return SwapEvidence(root, hashes)


def retained_items(root, source_path=None, fixture_path=None):
    if fixture_path:
        fixture = read(root, fixture_path)
        files = {row['path']: row for row in fixture['files']}
        require(len(files) == len(fixture['files']), 'Repeated fixture source path')
        entry = files[fixture['source']]
        raw = base64.b64decode(entry['base64'], validate=True)
        require(digest(raw) == entry['sha256'], 'Explicit fixture source metadata SHA differs')
        # Only metadata is decoded. Synthetic fixture plans are never restored or used.
        source = json.loads(raw)
        hashes = {name: row['sha256'] for name, row in files.items()}
    elif source_path:
        source = read(root, source_path)
        hashes = {row['path']: row['sha256'] for row in source['sources']}
    else:
        return {}, None
    require(source.get('schema_version') == 'cow-swap-evidence-v1', 'Expected explicit retained CoW source metadata')
    items = {row['task_key']: row for row in source['tasks']}
    require(len(items) == len(source['tasks']), 'Repeated retained task key')
    return items, hashes


def canonical_time(evidence, item, facts):
    """Rank actual canonical transactions by observation clocks, never state directory names."""
    execution = item.get('execution')
    if not execution or not facts:
        return None
    indexed = adapter._indexed_order(evidence, execution['order_observation'],
                                     {'orderbook_url': facts['orderbook_url']}, facts)
    trades = adapter._api_trades(evidence, execution['trades_observations'],
                                 {'orderbook_url': facts['orderbook_url']}, facts['uid'])
    if not indexed or indexed.get('status') != 'fulfilled' or not trades:
        return None
    require(len(trades) == 1 and trades[0]['orderUid'].lower() == facts['uid'], 'Ambiguous original order trade')
    transaction_hash = trades[0]['txHash'].lower()
    records = adapter._rpc(evidence, execution['rpc_observations'])
    chain = _lookup(records, 'eth_chainId', [])
    transaction = _lookup(records, 'eth_getTransactionByHash', [transaction_hash])
    receipt = _lookup(records, 'eth_getTransactionReceipt', [transaction_hash])
    if chain is None or not transaction or not receipt:
        return None
    block = _lookup(records, 'eth_getBlockByNumber', [receipt['blockNumber'], False])
    if not block:
        return None
    require(integer(chain) == facts['chain_id'] == integer(transaction['chainId'])
            and integer(receipt['status']) == 1
            and transaction['hash'].lower() == receipt['transactionHash'].lower() == transaction_hash
            and transaction['blockHash'].lower() == receipt['blockHash'].lower() == block['hash'].lower()
            and transaction['blockNumber'] == receipt['blockNumber'] == block['number']
            and transaction['transactionIndex'] == receipt['transactionIndex']
            and block['transactions'][integer(receipt['transactionIndex'])].lower() == transaction_hash,
            'Execution observations do not bind one canonical transaction')
    names = [execution['order_observation'], *execution['trades_observations'], *execution['rpc_observations']]
    return max(adapter._time(evidence.json(name)['observed_at']) for name in names)


def assemble(root, plan_path, plan_sha, *, retained_source=None, retained_fixture=None, measurement_contract=None):
    root = Path(root).resolve()
    path = adapter._public_path(root, plan_path)
    require(path.is_relative_to(root / 'runtime') and digest(path.read_bytes()) == plan_sha, 'Frozen campaign SHA differs')
    plan = json.loads(path.read_bytes())
    require(plan.get('schema_version') == 'cow-swap-campaign-v1' and plan.get('status') == 'FROZEN', 'Expected frozen CoW campaign')
    plan_hashes = {}
    node = path
    while True:
        name = node.relative_to(root).as_posix()
        require(name not in plan_hashes, 'CoW campaign lineage cycle')
        plan_hashes[name] = digest(node.read_bytes())
        previous = read(root, name).get('previous_plan')
        if not previous:
            break
        require(isinstance(previous, dict) and set(previous) == {'path', 'sha256'}, 'Invalid CoW previous plan reference')
        node = adapter._public_path(root, previous['path'])
        require(digest(node.read_bytes()) == previous['sha256'], 'CoW previous plan SHA differs')
    versions = adapter._campaign_lineage(SwapEvidence(root, plan_hashes), path.relative_to(root).as_posix())
    first_versions = {}
    for version in versions:
        for task in version['plan']['tasks']:
            first_versions.setdefault(task['task_key'], version)
    by_plan = {version['path']: version for version in versions}
    if measurement_contract is not None:
        scope = adapter.collect_cow_originals(root, path.relative_to(root).as_posix(), [], measurement_contract=measurement_contract)
        plan, _, _ = adapter._plan(SwapEvidence(root, {r['path']: r['sha256'] for r in scope['sources']}), scope)
    old, old_hashes = retained_items(root, retained_source, retained_fixture)
    tasks = {task['task_key']: task for task in plan['tasks']}
    require(len(tasks) == len(plan['tasks']), 'Repeated campaign task key')
    observed, items, selected, pending = set(), [], [], []
    for task in plan['tasks']:
        key, candidates = task['task_key'], []
        if task['selection_mode'] == 'retained-retrospective':
            if key in old:
                item = dict(old[key], task_id=task['task_id'])
                require(item['task_intent'] == task['retained_intent']['path'], 'Retained original intent path differs')
                require(digest(adapter._public_path(root, item['task_intent']).read_bytes()) == task['retained_intent']['sha256'],
                        'Frozen retained intent SHA differs')
                evidence_for(root, item, old_hashes)
                candidates.append(('explicit-retained-source', item))
            clock = adapter._time(read(root, task['retained_intent']['path'])['frozen_at'])
        else:
            require(task['selection_mode'] == 'prospective', 'Unknown task selection mode')
            clock = first_versions[key]['frozen_at']
            bases = {adapter._public_path(root, version['path']).parent / 'tasks' / key for version in versions
                     if any(t == task for t in version['plan']['tasks'])}
            names = {name for base in bases for pattern in ('source-item-http-*.json', 'states/*/source-item-execution.json')
                     for name in base.glob(pattern)}
            for name in sorted(names):
                item = read(root, name.relative_to(root).as_posix())
                require(item.get('task_id') == task['task_id'] and item.get('task_key') == key,
                        'Task source item differs from frozen UUID/id')
                intent = read(root, item['task_intent'])
                if len(versions) > 1:
                    version = adapter._task_plan_version(task, intent, versions)
                else:
                    version = versions[0]
                    expected = {'task_key': key, 'task_id': task['task_id'], 'campaign_plan': version['path'],
                                'campaign_plan_sha256': version['sha256'], 'chain_id': plan['chain_id'], 'owner': plan['owner'],
                                'expected': task['expected'], 'requests': task['requests']}
                    require(all(intent.get(field) == value for field, value in expected.items()), 'Task intent differs from frozen plan')
                base = adapter._public_path(root, version['path']).parent / 'tasks' / key
                require(item['task_intent'] == (base / 'TASK_INTENT.json').relative_to(root).as_posix(), 'Task intent directory differs')
                candidates.append((name.relative_to(root).as_posix(), item))
        choices = []
        for name, item in candidates:
            evidence = evidence_for(root, item)
            if task['selection_mode'] == 'prospective' and len(versions) > 1:
                intent = read(root, item['task_intent'])
                version = by_plan[intent['campaign_plan']]
                adapter._http_task(evidence, plan, task, item, version['frozen_at'])
            rows = adapter._http_task(evidence, plan, task, item, clock)
            metrics, facts = adapter._metrics(evidence, plan, task, item, rows, clock)
            if facts:
                facts = dict(facts, orderbook_url=plan['protocol_binding']['orderbook_url'])
            proof_clock = canonical_time(evidence, item, facts)
            http_clock = max((row['when'] for row in rows), default=clock)
            choices.append((proof_clock, http_clock, len(rows), name, item))
        if not choices:
            pending.append(task['task_id'])
            continue
        proven = [row for row in choices if row[0] is not None]
        chosen = max(proven, key=lambda row: row[0]) if proven else max(choices, key=lambda row: (row[1], row[2]))
        item = dict(chosen[4])
        if not proven:
            item.pop('execution', None)
        require(not observed.intersection(item.get('http_observations', [])), 'One HTTP observation cannot supply multiple tasks')
        observed.update(item.get('http_observations', []))
        items.append(item)
        selected.append({'task_id': task['task_id'], 'task_key': key, 'source_item': chosen[3],
                         'http_stages': len(item.get('http_observations', [])), 'canonical_execution': bool(proven),
                         'observation_clock': (chosen[0] or chosen[1]).isoformat()})
    summary = {'campaign_plan_sha256': plan_sha, 'planned_tasks': len(plan['tasks']),
                   'observed_tasks': sum(bool(item.get('http_observations')) for item in items),
                   'canonical_execution_items': sum(row['canonical_execution'] for row in selected),
                   'missing_task_items': pending, 'selected': selected, 'network_requests': 0, 'wallet_operations': 0}
    if measurement_contract is not None:
        summary['measurement_contract'] = measurement_contract
    return items, summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', required=True)
    parser.add_argument('--plan-sha', required=True)
    old = parser.add_mutually_exclusive_group()
    old.add_argument('--retained-source')
    old.add_argument('--retained-fixture')
    parser.add_argument('--measurement-contract')
    parser.add_argument('--measurement-contract-sha')
    parser.add_argument('--output', type=Path, help='New task-items JSON metadata; not a formal source or report')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    require(args.dry_run or args.output, 'Choose --dry-run or a new --output file')
    require(bool(args.measurement_contract) == bool(args.measurement_contract_sha), 'Measurement contract path and SHA are required together')
    contract = {'path': args.measurement_contract, 'sha256': args.measurement_contract_sha} if args.measurement_contract else None
    items, summary = assemble(ROOT, args.plan, args.plan_sha, retained_source=args.retained_source,
                              retained_fixture=args.retained_fixture, measurement_contract=contract)
    if not args.dry_run:
        output = adapter._public_path(ROOT, args.output)
        require(output.is_relative_to(ROOT / 'runtime'), 'Task-item metadata must stay in runtime')
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open('x', encoding='utf-8') as stream:
            json.dump(items, stream, ensure_ascii=False, indent=2)
            stream.write('\n')
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == '__main__':
    main()
