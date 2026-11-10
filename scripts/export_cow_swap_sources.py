"""Retain explicitly selected public CoW/MCP originals; no network or private discovery."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'packages/core/src'), str(ROOT / 'services/platform/src')]
from reputation_platform.cow_swap_report import export_cow_swap_sources


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', type=Path, required=True)
    parser.add_argument('--task-items', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--measurement-contract')
    parser.add_argument('--measurement-contract-sha')
    args = parser.parse_args()
    if bool(args.measurement_contract) != bool(args.measurement_contract_sha):
        parser.error('Measurement contract path and SHA are required together')
    contract = {'path': args.measurement_contract, 'sha256': args.measurement_contract_sha} if args.measurement_contract else None
    items = json.loads((ROOT / args.task_items).read_bytes())
    source = export_cow_swap_sources(ROOT, args.plan, items, args.output, measurement_contract=contract)
    print(json.dumps({'status': source['status'], 'observed_task_items': len(source['tasks']),
        'public_sources': len(source['sources']), 'network_requests': 0, 'wallet_operations': 0}))


if __name__ == '__main__':
    main()
