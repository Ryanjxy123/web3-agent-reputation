"""Verify/import or distribute the real, execution-only Olas evidence bundle."""

import argparse
import hashlib
import io
import json
from pathlib import Path
import shutil
import sys
import tarfile
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'packages/core/src'), str(ROOT / 'services/platform/src')]

from reputation_platform.chain_evidence import build_execution_reviews, publish_execution_reviews
from reputation_platform.db import Repository
from reputation_platform.settings import load_database_url

INDEX = 'execution-evidence-index.json'


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def public_path(root: Path, name: str) -> Path:
    parts = name.split('/')
    target = (root / name).resolve()
    if (parts[0] != 'runtime' or any(part in ('', '.', '..') or part.startswith('.') for part in parts)
        or not target.is_relative_to(root / 'runtime')
        or any(part.lower() in ('secrets', 'platform-config') or '.private' in part.lower() for part in parts)):
        raise ValueError('Package member is not a retained public evidence path')
    return target


def export_package(root: Path, bundle: Path, output: Path) -> dict:
    reviews = build_execution_reviews(root, bundle)
    sources = {name: value for _, hashes in reviews for name, value in hashes.items()}
    inventory = [{'path': name, 'sha256': sha, 'size': public_path(root, name).stat().st_size}
                 for name, sha in sorted(sources.items())]
    index = {'schema_version': 'chain-execution-package-v1', 'verifier_version': 'olas-safe-omen-evidence-v1',
        'bundle': bundle.resolve().relative_to(root).as_posix(), 'files': inventory}
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('xb') as stream, tarfile.open(fileobj=stream, mode='w:gz') as archive:
        raw = (json.dumps(index, ensure_ascii=False, indent=2) + '\n').encode('utf-8')
        info = tarfile.TarInfo(INDEX)
        info.size = len(raw)
        archive.addfile(info, io.BytesIO(raw))
        for item in inventory:
            source = public_path(root, item['path'])
            if digest(source) != item['sha256']:
                raise ValueError('Evidence changed during export')
            info = tarfile.TarInfo(item['path'])
            info.size = item['size']
            with source.open('rb') as content:
                archive.addfile(info, content)
    summary = {'schema_version': 'chain-execution-release-v1', 'archive_sha256': digest(output),
        'archive_bytes': output.stat().st_size, 'files': len(inventory), 'distinct_agents': len(reviews),
        'verified_execution_samples': sum(view.actions[0].verdict.value == 'PASS' for view, _ in reviews),
        'unknown_execution_samples': sum(view.actions[0].verdict.value == 'UNKNOWN' for view, _ in reviews),
        'new_complete_scores': 0, 'signed_transactions_created': 0,
        'candidates': [{'key': view.candidate_key, 'verdict': view.actions[0].verdict.value} for view, _ in reviews]}
    summary_path = output.with_name(output.name.removesuffix('.tar.gz') + '.json')
    with summary_path.open('x', encoding='utf-8') as stream:
        json.dump(summary, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    return summary


def restore_package(root: Path, supplied: Path) -> Path:
    root = root.resolve()
    with tarfile.open(supplied, mode='r:gz') as archive:
        members = archive.getmembers()
        names = [item.name for item in members]
        if len(names) != len(set(names)) or any(not item.isfile() for item in members):
            raise ValueError('Package contains duplicate paths or non-file members')
        index = json.load(archive.extractfile(INDEX))
        if (index['schema_version'] != 'chain-execution-package-v1'
            or index['verifier_version'] != 'olas-safe-omen-evidence-v1'):
            raise ValueError('Unsupported execution package/verifier version')
        inventory = {item['path']: item for item in index['files']}
        if set(names) != set(inventory) | {INDEX}:
            raise ValueError('Package members differ from its exact inventory')
        temporary = root / 'runtime' / ('chain-evidence-package-' + uuid4().hex)
        temporary.mkdir(parents=True)
        # Validate the complete archive before copying any source into its final path.
        for member in members:
            if member.name == INDEX:
                continue
            item = inventory[member.name]
            if member.size != item['size'] or not 0 <= member.size <= 8_388_608:
                raise ValueError('Unexpected evidence member size')
            target = public_path(root, member.name)
            stage = public_path(temporary, member.name)
            stage.parent.mkdir(parents=True, exist_ok=True)
            with archive.extractfile(member) as source, stage.open('xb') as destination:
                shutil.copyfileobj(source, destination)
            if digest(stage) != item['sha256']:
                raise ValueError('Package evidence digest mismatch')
            if target.exists() and (not target.is_file() or digest(target) != item['sha256']):
                raise ValueError('A different local evidence file already exists')
        for name in inventory:
            target = public_path(root, name)
            if not target.exists():
                target.parent.mkdir(parents=True, exist_ok=True)
                with public_path(temporary, name).open('rb') as source, target.open('xb') as destination:
                    shutil.copyfileobj(source, destination)
    bundle = public_path(root, index['bundle'])
    if index['bundle'] not in inventory:
        raise ValueError('Package bundle is not in the authenticated inventory')
    return bundle


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    export = commands.add_parser('export')
    export.add_argument('--bundle', type=Path, required=True)
    export.add_argument('--output', type=Path, required=True)
    for command in ('verify', 'import'):
        load = commands.add_parser(command)
        load.add_argument('archive', type=Path)
    args = parser.parse_args()
    if args.command == 'export':
        print(json.dumps(export_package(ROOT, ROOT / args.bundle, ROOT / args.output), ensure_ascii=False, indent=2))
        return 0
    bundle = restore_package(ROOT, args.archive)
    reviews = build_execution_reviews(ROOT, bundle)
    result = {'agents': len(reviews), 'verified': sum(v.actions[0].verdict.value == 'PASS' for v, _ in reviews),
              'unknown': sum(v.actions[0].verdict.value == 'UNKNOWN' for v, _ in reviews), 'network_requests': 0,
              'new_complete_scores': 0}
    if args.command == 'import':
        repo = Repository(load_database_url())
        repo.initialize()
        directory = ROOT / 'runtime' / ('chain-execution-review-' + uuid4().hex)
        result['mapping'] = publish_execution_reviews(repo, reviews, directory)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
