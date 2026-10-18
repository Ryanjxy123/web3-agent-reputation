"""Recompute a Chinese prediction-history report from authenticated retained evidence."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import secrets
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'packages/core/src'), str(ROOT / 'services/platform/src')]
from reputation_platform.evaluation_report import render_evaluation_report
from reputation_platform.prediction_evidence import runtime_directory
from reputation_platform.prediction_report import build_prediction_report
from reputation_platform.question_translation import load_verified_translations


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--history-run', type=Path, required=True)
    parser.add_argument('--plan-run', type=Path, required=True)
    parser.add_argument('--availability-run', type=Path)
    parser.add_argument('--identity-run', type=Path)
    parser.add_argument('--translation-run', type=Path)
    args = parser.parse_args()
    paths = {key: runtime_directory(value) if value else None for key, value in vars(args).items()}
    translations = {}
    translation_sources = []
    if paths['translation_run']:
        translations, translation_sources = load_verified_translations(paths['translation_run'])
    report, background, evidence = build_prediction_report(history_run=paths['history_run'], plan_run=paths['plan_run'],
        availability_run=paths['availability_run'], identity_run=paths['identity_run'], translations=translations)
    if paths['translation_run']:
        for source in translation_sources:
            evidence.remember(source.path, source.sha256)
        report.source_references = sorted(set(report.source_references) | {source.path for source in translation_sources})
    now = datetime.now(timezone.utc)
    run = ROOT / 'runtime' / f'evaluation-report-{now:%Y%m%dT%H%M%SZ}-{secrets.token_hex(4)}'
    run.mkdir()
    manifest = {'created_at': now.isoformat(), 'policy_version': report.policy_version, 'network_requests': 0,
        'history_run': paths['history_run'].relative_to(ROOT).as_posix(), 'plan_run': paths['plan_run'].relative_to(ROOT).as_posix(),
        'inputs': [{'path': name, 'sha256': value} for name, value in sorted(evidence.inputs.items())],
        'samples': len(report.samples)}
    for name, value in (('manifest.json', manifest), ('background.json', background)):
        with (run / name).open('x', encoding='utf-8') as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
    (run / 'report.json').write_text(report.model_dump_json(indent=2), encoding='utf-8')
    (run / 'report.html').write_text(render_evaluation_report(report), encoding='utf-8')
    print(json.dumps({'evidence_directory': run.relative_to(ROOT).as_posix(),
                      'scores': report.scores.model_dump(mode='json')}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
