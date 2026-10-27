"""Offline source replay into a new shared-task scope report; no wallet or network."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'packages/core/src'), str(ROOT / 'services/platform/src')]

from reputation_platform.shared_report import build_shared_report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-report', type=Path, required=True, help='Retained verified protocol report directory')
    parser.add_argument('--declarations', type=Path, required=True, help='Reviewed declaration catalog below configs/')
    parser.add_argument('--output', type=Path, required=True, help='New runtime directory; existing reports are never overwritten')
    args = parser.parse_args()
    try:
        report = build_shared_report(ROOT, args.source_report, args.declarations, args.output)
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(f'Shared report not published: {type(error).__name__}. Sources remain retained.', file=sys.stderr)
        return 1
    result = report.shared_assessment.result
    print(json.dumps({'task_count': result.task_count, 'observation_count': result.observation_count,
        'score_status': result.score_status, 'overall': result.overall.model_dump() if result.overall else None,
        'declaration_coverage': result.declaration_coverage,
        'dimensions': {name: (getattr(result, name).interval.model_dump() if getattr(result, name).interval else None)
                       for name in ('availability', 'functional', 'behavioral')}}, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
