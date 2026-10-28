"""Replay retained public ACP/unsigned-swap evidence into a standalone scope report."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'packages/core/src'), str(ROOT / 'services/platform/src')]
from reputation_platform.unsigned_swap_report import build_unsigned_swap_report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    try:
        report = build_unsigned_swap_report(ROOT, args.source, args.output)
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(f'Unsigned swap report not built: {type(error).__name__}: {error}', file=sys.stderr)
        return 1
    print(json.dumps({'candidate_key': report.candidate_key, 'scores': report.scores.model_dump(mode='json'),
        'task_count': report.shared_assessment.result.task_count}, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
