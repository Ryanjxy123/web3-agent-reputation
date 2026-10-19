"""Verify already retained Olas CAR bytes against the reviewed task's CID and file."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import secrets
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'packages/core/src'), str(ROOT / 'services/platform/src')]
from reputation_core.admission import ProbeObservation
from reputation_core.ipfs import verify_car_file


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def retained_directory(value: Path) -> Path:
    path = (ROOT / value).resolve()
    if not path.is_relative_to((ROOT / 'runtime').resolve()) or not path.is_dir():
        raise ValueError('Inputs must be retained directories in this project runtime')
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--car-run', type=Path, required=True)
    parser.add_argument('--task-run', type=Path, required=True)
    parser.add_argument('--check-rejection', action='store_true', help='Run the necessary tamper/path failure controls once')
    args = parser.parse_args()
    car_run, task_run = retained_directory(args.car_run), retained_directory(args.task_run)
    task = json.loads((task_run / 'result.json').read_bytes())
    if task['stopped_reason'] is not None:
        raise ValueError('The reviewed task result did not complete')
    car_manifest = json.loads((car_run / 'manifest.json').read_bytes())
    task_manifest = json.loads((task_run / 'manifest.json').read_bytes())
    inputs = {car_run / 'manifest.json', task_run / 'manifest.json', task_run / 'result.json'}
    for manifest in (car_manifest, task_manifest):
        for item in manifest['inputs']:
            path = (ROOT / item['path']).resolve()
            if not path.is_relative_to(ROOT) or digest(path) != item['sha256']:
                raise ValueError('A retained source digest no longer matches')
            inputs.add(path)
    results = {}
    failures_checked = 0
    for kind in ('request', 'delivery'):
        event = task['checked_chain_events'][kind]['event']
        root_digest = event['data_hex']
        filename = 'metadata.json' if kind == 'request' else str(int(event['request_id'], 16))
        key = kind + '-car'
        observed_path = car_run / f'{key}.observation.json'
        observation = ProbeObservation.model_validate_json(observed_path.read_bytes())
        car_path = car_run / f'{key}.response.bin'
        expected_url = f'https://gateway.autonolas.tech/ipfs/f01701220{root_digest[2:]}/{filename}?format=car&dag-scope=entity'
        if (observation.url != expected_url or observation.method != 'GET' or observation.http_status != 200
            or observation.error_kind or not observation.body_complete or observation.response_sha256 != digest(car_path)):
            raise ValueError('Retained CAR request, response or digest differs from the reviewed task')
        content_key = kind + '-content'
        content_inputs = [path for path in inputs if path.name == content_key + '.response.bin']
        if len(content_inputs) != 1:
            raise ValueError('The reviewed task must bind exactly one input and one output file')
        car, expected = car_path.read_bytes(), content_inputs[0].read_bytes()
        results[kind] = verify_car_file(car, root_digest, filename, expected)
        inputs.update((car_path, observed_path))
        if args.check_rejection:
            for invalid in (
                (car[:-1] + bytes([car[-1] ^ 1]), root_digest, filename, expected),
                (car, root_digest, filename + '-wrong', expected),
                (car, root_digest, filename, expected + b' '),
            ):
                try:
                    verify_car_file(*invalid)
                except ValueError:
                    failures_checked += 1
                else:
                    raise AssertionError('Invalid content, path or block was accepted')
    run = ROOT / 'runtime' / f"olas-car-verification-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}-{secrets.token_hex(4)}"
    run.mkdir()
    manifest = {'inputs': [{'path': path.relative_to(ROOT).as_posix(), 'sha256': digest(path)} for path in sorted(inputs)],
                'network_requests': 0, 'scores_computed': False,
                'implementation': {'path': 'packages/core/src/reputation_core/ipfs.py',
                                   'sha256': digest(ROOT / 'packages/core/src/reputation_core/ipfs.py')},
                'scope': 'CID/DAG authentication of the reviewed first task only; task attribution and prediction quality are separate'}
    (run / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    (run / 'result.json').write_text(json.dumps({'verification': results, 'rejected_failure_controls': failures_checked}, indent=2), encoding='utf-8')
    print(json.dumps({'verification': results, 'rejected_failure_controls': failures_checked,
                      'network_requests': 0, 'evidence_directory': run.relative_to(ROOT).as_posix()}, indent=2))


if __name__ == '__main__':
    main()
