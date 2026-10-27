"""Build, verify, publish or distribute an unscored chain supplement offline."""
import argparse
import json
from pathlib import Path
import sys
import psycopg

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'packages/core/src'),str(ROOT/'services/platform/src')]

from reputation_platform.contract_lifecycle_snapshot import (
    build_snapshot, export_snapshot, import_snapshot, restore_snapshot, verify_snapshot,
)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='command',required=True)
    build=sub.add_parser('build');build.add_argument('--config',type=Path,required=True);build.add_argument('--output',type=Path,required=True)
    verify=sub.add_parser('verify')
    inputs=verify.add_mutually_exclusive_group(required=True);inputs.add_argument('--directory',type=Path);inputs.add_argument('--archive',type=Path)
    publish=sub.add_parser('import')
    inputs=publish.add_mutually_exclusive_group(required=True);inputs.add_argument('--directory',type=Path);inputs.add_argument('--archive',type=Path)
    export=sub.add_parser('export');export.add_argument('--directory',type=Path,required=True);export.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    try:
        if args.command=='build':
            review=build_snapshot(ROOT,args.config,args.output)
            print(json.dumps({'candidate_key':review.candidate_key,'tasks':len(review.actions),
                'snapshot':str(args.output/'snapshot.json'),'new_scores':0},indent=2));return 0
        if args.command=='export':
            print(json.dumps(export_snapshot(ROOT,args.directory,args.output),indent=2));return 0
        directory=args.directory
        restored=None
        if args.archive:
            directory,restored=restore_snapshot(ROOT,args.archive)
        if args.command=='verify':
            if restored is None:
                review,hashes,_=verify_snapshot(ROOT,directory)
                count=len(hashes)
            else:
                review=restored
                count=len(json.loads((directory/'manifest.json').read_bytes())['inputs'])
            print(f'verified: {review.candidate_key}; tasks={len(review.actions)}; inputs={count}; new_scores=0')
        else:
            from reputation_platform.db import Repository
            from reputation_platform.settings import load_database_url
            print(json.dumps(import_snapshot(Repository(load_database_url(),ROOT),directory),indent=2))
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(f'Contract supplement not completed: {type(error).__name__}: {error}. Retained files were not overwritten.',file=sys.stderr)
        return 1
    except psycopg.Error as error:
        print(f'Contract supplement database import failed: {type(error).__name__}; SQLSTATE={error.sqlstate or "unavailable"}. Local credentials were not printed.',file=sys.stderr)
        return 1
    return 0


if __name__=='__main__':
    raise SystemExit(main())
