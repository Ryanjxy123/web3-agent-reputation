"""Read the reviewed Base candidate registrations; never infer execution wallets."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import secrets
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'packages/core/src'), str(ROOT / 'services/platform/src')]
from reputation_core.admission import ProbeObservation
from reputation_platform.safe_http import PublicTarget, SafeHttpClient
from reputation_platform.settings import load_zan_key_file

RPC = 'https://api.zan.top/node/v1/base/mainnet'
REGISTRY = '0x8004a169fb4a3325136eb29fa0ceb6d2e539a432'


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def decode_uri(value: str) -> str:
    raw = bytes.fromhex(value.removeprefix('0x'))
    if len(raw) < 64 or int.from_bytes(raw[:32]) != 32:
        raise ValueError('Invalid tokenURI ABI offset')
    size = int.from_bytes(raw[32:64])
    if len(raw) != 64 + ((size + 31) // 32) * 32 or any(raw[64 + size:]):
        raise ValueError('Invalid tokenURI ABI length')
    return raw[64:64 + size].decode('utf-8')


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile', type=Path, required=True, help='Explicit reviewed candidate configuration under configs')
    parser.add_argument('--source-run', type=Path, required=True)
    parser.add_argument('--execute-public-readonly', action='store_true')
    parser.add_argument('--proxy')
    parser.add_argument('--zan-key-url-file', type=Path)
    args = parser.parse_args()
    if args.execute_public_readonly and not args.proxy:
        parser.error('An explicit operator proxy is required')
    source = (ROOT / args.source_run).resolve()
    if not source.is_relative_to((ROOT / 'runtime').resolve()) or not source.is_dir():
        parser.error('Use a retained candidate run inside this project runtime')
    config_path = (ROOT / args.profile).resolve()
    if not config_path.is_relative_to(ROOT / 'configs') or config_path.suffix != '.json':
        parser.error('Candidate configuration must be an explicit JSON file under configs')
    config = json.loads(config_path.read_bytes())
    if (config['chain_id'], config['rpc_url'], config['registry']) != (8453, RPC, REGISTRY):
        raise ValueError('The operator config differs from the reviewed Base scope')
    inputs = [{'path': config_path.relative_to(ROOT).as_posix(), 'sha256': sha(config_path)}]
    candidates = config['candidates']
    for candidate in candidates:
        name = candidate['catalog_key']
        observation_path = source / f'{name}.observation.json'
        response_path = source / f'{name}.response.bin'
        observation = ProbeObservation.model_validate_json(observation_path.read_bytes())
        catalog = json.loads(response_path.read_bytes())
        if (observation.url != f"https://api.8004scan.io/api/v1/agents/8453/{candidate['agent_id']}"
            or observation.http_status != 200 or not observation.body_complete or observation.error_kind
            or observation.response_sha256 != sha(response_path)
            or catalog['chain_id'] != 8453 or int(catalog['token_id']) != candidate['agent_id']
            or catalog['contract_address'].lower() != REGISTRY):
            raise ValueError('The retained catalog identity or bytes do not match the reviewed candidate')
        inputs.extend({'path': path.relative_to(ROOT).as_posix(), 'sha256': sha(path)}
                      for path in (observation_path, response_path))
    calls = [('chain-id', 'eth_chainId', []), ('head', 'eth_blockNumber', []),
             ('snapshot', 'eth_getBlockByNumber', ['SNAPSHOT', False])]
    for candidate in candidates:
        for label, selector in [('owner', '6352211e'), ('uri', 'c87b56dd')]:
            calls.append((candidate['key'] + '-' + label, 'eth_call',
                [{'to': REGISTRY, 'data': '0x' + selector + f"{candidate['agent_id']:064x}"}, 'SNAPSHOT']))
    targets = tuple(PublicTarget(key, RPC, 'POST', json_body={'jsonrpc': '2.0', 'id': index,
                    'method': method, 'params': params}) for index, (key, method, params) in enumerate(calls, 1))
    plan = {'execution_enabled': args.execute_public_readonly, 'purpose': 'background',
            'chain_id': 8453, 'retries': 0, 'request_count': len(targets), 'inputs': inputs,
            'snapshot_rule': 'head - 64', 'scores_computed': False,
            'planned_requests': [{'key': item.key, 'url': item.url, 'json': item.json_body} for item in targets]}
    if not args.execute_public_readonly:
        print(json.dumps(plan, ensure_ascii=False, indent=2))
        return 0
    run = ROOT / 'runtime' / f"base-registration-probe-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}-{secrets.token_hex(4)}"
    run.mkdir()
    (run / 'manifest.json').write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding='utf-8')
    facts, stop = {}, None
    with SafeHttpClient(targets, enabled=True, proxy=args.proxy, max_requests=len(targets),
                        zan_key_url_file=load_zan_key_file(args.zan_key_url_file)) as client:
        for target in targets:
            observation = client.fetch(target.key, run)
            if observation.http_status != 200 or observation.error_kind or not observation.body_complete:
                stop = observation.error_kind or 'incomplete_or_unsuccessful_http'
                break
            try:
                payload = json.loads((run / observation.response_file).read_bytes())
                if payload.get('jsonrpc') != '2.0' or payload.get('id') != target.json_body['id'] or 'error' in payload:
                    raise ValueError('Invalid RPC envelope')
                value = payload['result']
                if target.key == 'chain-id':
                    if int(value, 16) != 8453:
                        raise ValueError('Unexpected chain')
                elif target.key == 'head':
                    number = int(value, 16) - 64
                    if number < 0:
                        raise ValueError('Insufficient confirmation offset')
                    facts['snapshot_block'] = number
                    for pending in targets:
                        if pending.key == 'snapshot':
                            pending.json_body['params'][0] = hex(number)
                        elif pending.json_body['method'] == 'eth_call':
                            pending.json_body['params'][1] = hex(number)
                elif target.key == 'snapshot':
                    if value['number'] != hex(facts['snapshot_block']) or not re.fullmatch('0x[0-9a-fA-F]{64}', value['hash']):
                        raise ValueError('Invalid fixed block header')
                    facts['snapshot_hash'] = value['hash']
                elif target.key.endswith('-owner'):
                    if not re.fullmatch('0x0{24}[0-9a-fA-F]{40}', value) or int(value, 16) == 0:
                        raise ValueError('Invalid registry owner')
                    facts[target.key] = '0x' + value[-40:].lower()
                else:
                    facts[target.key] = decode_uri(value)
                print(f'{target.key}: HTTP=200 rpc=ok')
            except (ValueError, TypeError, KeyError):
                stop = 'invalid_rpc_or_registration_result'
                break
    result = {'facts': facts, 'stopped_reason': stop, 'scores_computed': False,
              'limitations': ['Current registration existence and URI only; owner is not an execution wallet',
                              'No service correctness, historical task attribution or full reputation score']}
    (run / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'evidence_directory={run.relative_to(ROOT).as_posix()}; stopped_reason={stop}')
    return 1 if stop else 0


if __name__ == '__main__':
    raise SystemExit(main())
