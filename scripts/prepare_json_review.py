"""Prepare model-readable JSON declarations from already retained public responses."""

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
from reputation_core import ProbeObservation, SourceDocument
from reputation_platform.model_analysis import catalog_operations


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--document', nargs=2, action='append', required=True, metavar=('CANDIDATE', 'OBSERVATION'))
    args = parser.parse_args()
    keys = [key for key, _ in args.document]
    if len(set(keys)) != len(keys) or any(not re.fullmatch('[a-z0-9-]+', key) for key in keys):
        parser.error('Use one unique lowercase candidate key for each reviewed document')
    prepared = []
    for key, supplied in args.document:
        observed_path = (ROOT / supplied).resolve()
        if (not observed_path.is_relative_to(ROOT / 'runtime') or not observed_path.name.endswith('.observation.json')
            or any(part.lower() in {'secrets', 'platform-config'} or '.private' in part.lower() for part in observed_path.parts)):
            raise ValueError('Use a retained public observation in this project runtime')
        observation = ProbeObservation.model_validate_json(observed_path.read_bytes())
        if observation.http_status != 200 or observation.error_kind or not observation.body_complete or not observation.response_file:
            raise ValueError('A complete successful source document is required')
        original = (observed_path.parent / observation.response_file).resolve()
        if original.parent != observed_path.parent:
            raise ValueError('The source response must remain in its evidence directory')
        raw = original.read_bytes()
        raw_sha = hashlib.sha256(raw).hexdigest()
        if raw_sha != observation.response_sha256:
            raise ValueError('The original source no longer matches its observation digest')
        document = json.loads(raw)
        projection = json.dumps(document, ensure_ascii=False, indent=2) + '\n'
        source = SourceDocument(source_id=key, url=observation.url, raw_sha256=raw_sha,
                                projection_sha256=hashlib.sha256(projection.encode()).hexdigest(), text=projection)
        operations = catalog_operations([source])
        if not operations:
            raise ValueError('This review requires explicit operations with actual input/output declarations')
        prepared.append((key, observed_path, original, source, operations))
    run = ROOT / 'runtime' / f"model-review-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}-{secrets.token_hex(4)}"
    run.mkdir()
    documents, inputs = [], []
    for key, observed, original, source, operations in prepared:
        projection_file = key + '.projection.json'
        (run / projection_file).write_bytes(source.text.encode('utf-8'))
        documents.append({'candidate': key, 'source_url': source.url, 'raw_file': original.relative_to(ROOT).as_posix(),
                          'raw_sha256': source.raw_sha256, 'projection_file': projection_file,
                          'projection_sha256': source.projection_sha256, 'operations': operations})
        inputs.extend({'path': path.relative_to(ROOT).as_posix(), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
                      for path in (observed, original))
    (run / 'review.json').write_text(json.dumps({'documents': documents}, ensure_ascii=False, indent=2), encoding='utf-8')
    (run / 'manifest.json').write_text(json.dumps({'inputs': inputs, 'network_requests': 0, 'model_requests': 0,
        'scores_computed': False, 'scope': 'Full JSON tool declarations; missing prices/authorization remain gaps, not free access'}, indent=2), encoding='utf-8')
    print(json.dumps({'candidates': keys, 'operation_counts': {key: len(operations) for key, _, _, _, operations in prepared},
                      'evidence_directory': run.relative_to(ROOT).as_posix(), 'network_requests': 0}, indent=2))


if __name__ == '__main__':
    main()
