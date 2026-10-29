"""Create a new public atomic source draft from retained evidence only."""
import argparse
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'packages/core/src'),str(ROOT/'services/platform/src')]
from reputation_platform.atomic_swap_export import export_atomic_swap_sources

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan',required=True)
    parser.add_argument('--plan-sha256',required=True)
    parser.add_argument('--registration-proof',required=True)
    parser.add_argument('--http-map',required=True)
    parser.add_argument('--output',required=True)
    args=parser.parse_args()
    try:
        result=export_atomic_swap_sources(ROOT,plan=args.plan,plan_sha256=args.plan_sha256,
            registration_proof=args.registration_proof,http_map=args.http_map,output=args.output)
    except (OSError,ValueError,KeyError,TypeError) as error:
        print(f'Atomic source not exported: {type(error).__name__}: {error}',file=sys.stderr)
        return 1
    print(json.dumps({key:value for key,value in result.items() if key not in ('tasks','missing')},ensure_ascii=False,indent=2))
    return 0

if __name__=='__main__':
    raise SystemExit(main())
