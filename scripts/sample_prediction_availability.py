"""Measure ten frozen public prediction-file reads, without issuing prediction jobs."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import secrets
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'packages/core/src'), str(ROOT / 'services/platform/src')]
from reputation_core import MeasurementPurpose, Verdict
from reputation_core.scoring import ScoredSample
from reputation_platform.safe_http import PublicTarget, SafeHttpClient

POLICY = ROOT / 'docs/adr/0008-prediction-history-policy.md'


def write_json(path: Path, value: object) -> None:
    with path.open('x', encoding='utf-8') as output:
        json.dump(value, output, ensure_ascii=False, indent=2)


def request_number(payload: object) -> int:
    if not isinstance(payload, dict):
        raise ValueError('A public prediction response must be an object')
    value = payload.get('requestId')
    if isinstance(value, bool) or not isinstance(value, (str, int)) or not str(value).isdigit():
        raise ValueError('A full decimal requestId is required')
    return int(value)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sources', type=Path, required=True, help='Retained JSON with candidate_key and at least ten outputs')
    parser.add_argument('--execute-public-readonly', action='store_true')
    parser.add_argument('--proxy')
    args = parser.parse_args()
    source = (ROOT / args.sources).resolve()
    if not source.is_file() or not source.is_relative_to(ROOT / 'runtime'):
        parser.error('Use a retained public source manifest in this project runtime')
    if args.execute_public_readonly and not args.proxy:
        parser.error('An explicit operator proxy is required')
    configuration = json.loads(source.read_bytes())
    outputs = configuration['outputs'][:10]
    if len(outputs) != 10:
        raise ValueError('Ten distinct retained outputs are required before starting this sampling window')
    targets, frozen = [], []
    for slot, item in enumerate(outputs, 1):
        if any(not re.fullmatch(r'0x[0-9a-fA-F]{64}', item[name]) for name in ('request_id', 'root_digest')):
            raise ValueError('Expected full reviewed request and directory identifiers')
        payload_file = (ROOT / item['response_file']).resolve()
        if (not payload_file.is_file() or not payload_file.is_relative_to(ROOT / 'runtime')
            or any(part in {'platform-config', 'secrets'} for part in payload_file.parts)):
            raise ValueError('Only retained public response files may be sampled')
        payload_bytes = payload_file.read_bytes()
        if (hashlib.sha256(payload_bytes).hexdigest() != item['sha256']
            or request_number(json.loads(payload_bytes)) != int(item['request_id'], 16)):
            raise ValueError('The frozen request or content digest differs from its actual source file')
        url = f"https://gateway.autonolas.tech/ipfs/f01701220{item['root_digest'][2:].lower()}/{int(item['request_id'], 16)}"
        targets.append(PublicTarget(f'availability-{slot:03d}', url, purpose=MeasurementPurpose.AVAILABILITY))
        frozen.append({**item, 'response_file': payload_file.relative_to(ROOT).as_posix(), 'url': url,
                       'slot': slot, 'scheduled_offset_seconds': (slot - 1) * 30})
    if len({item['request_id'] for item in outputs}) != 10:
        raise ValueError('Availability files must be ten distinct historical outputs')
    run_id = f"prediction-availability-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}-{secrets.token_hex(4)}"
    plan = {'run_id': run_id, 'policy_version': 'prediction-history-v1', 'candidate_key': configuration['candidate_key'],
            'execution_enabled': args.execute_public_readonly, 'purpose': 'availability', 'retries': 0,
            'request_limit': 10, 'interval_seconds': 30, 'slots': frozen,
            'scope': 'Public historical delivery-file access through the operator gateway; not live inference availability',
            'inputs': [{'path': path.relative_to(ROOT).as_posix(), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
                       for path in (source, POLICY)]}
    print(json.dumps(plan, ensure_ascii=False, indent=2), flush=True)
    if not args.execute_public_readonly:
        return
    run = ROOT / 'runtime' / run_id
    run.mkdir()
    write_json(run / 'manifest.json', plan)
    samples, stopped = [], False
    with SafeHttpClient(tuple(targets), enabled=True, proxy=args.proxy, max_requests=10) as client:
        origin = time.monotonic()
        for item, target in zip(frozen, targets):
            observed_at, elapsed, evidence = datetime.now(timezone.utc).isoformat(), None, []
            if stopped:
                skipped = run / f'{target.key}.skip.json'
                write_json(skipped, {'request_sent': False, 'reason': 'Host stopped after authorization/payment/rate-limit response'})
                verdict, reason = Verdict.UNKNOWN, 'Earlier host stop; this slot was not requested'
                evidence.append(skipped.relative_to(ROOT).as_posix())
            else:
                while (remaining := origin + item['scheduled_offset_seconds'] - time.monotonic()) > 0:
                    time.sleep(min(30.0, remaining))
                observation = client.fetch(target.key, run)
                observed_at, elapsed = observation.observed_at.isoformat(), observation.elapsed_ms
                evidence.append((run / f'{target.key}.observation.json').relative_to(ROOT).as_posix())
                verdict, reason = Verdict.UNKNOWN, observation.error_kind or 'Response was not decisive'
                if observation.response_file:
                    response_path = run / observation.response_file
                    evidence.append(response_path.relative_to(ROOT).as_posix())
                if observation.error_kind in (None, 'http_status_not_success') and observation.body_complete:
                    if observation.http_status is not None and 500 <= observation.http_status <= 599:
                        verdict, reason = Verdict.FAIL, 'The public historical file endpoint returned HTTP 5xx'
                    elif observation.http_status == 200:
                        actual = response_path.read_bytes()
                        try:
                            matches = (hashlib.sha256(actual).hexdigest() == item['sha256']
                                       and request_number(json.loads(actual)) == int(item['request_id'], 16))
                        except (ValueError, TypeError):
                            matches = False
                        verdict = Verdict.PASS if matches else Verdict.FAIL
                        reason = 'Historical task and immutable response bytes match' if matches else 'HTTP200 content did not match the declared historical file'
                stopped = observation.http_status in (401, 402, 403, 429)
            sample = ScoredSample(sample_id=f'{run_id}:{item["slot"]:03d}', task_key=f'availability:{run_id}:{item["slot"]:03d}',
                purpose=MeasurementPurpose.AVAILABILITY, verdict=verdict, elapsed_ms=elapsed, reason=reason, evidence=evidence)
            samples.append(sample.model_dump(mode='json'))
            write_json(run / f'{target.key}.sample.json', {'sample': samples[-1], 'observed_at': observed_at})
            print(f'{target.key}: {verdict.value}; elapsed_ms={elapsed}', flush=True)
    write_json(run / 'samples.json', samples)
    print(f'evidence_directory={run.relative_to(ROOT).as_posix()}', flush=True)


if __name__ == '__main__':
    main()
