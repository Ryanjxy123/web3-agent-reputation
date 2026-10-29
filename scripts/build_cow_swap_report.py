"""Build an isolated offline CoW report from an already frozen source manifest."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'packages/core/src'), str(ROOT / 'services/platform/src')]
from reputation_platform.cow_swap_report import build_cow_swap_report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = build_cow_swap_report(ROOT, args.source, args.output)
    print(json.dumps({'candidate_key': report.candidate_key, 'task_count': report.shared_assessment.result.task_count,
        'scores': report.scores.model_dump(mode='json')}, ensure_ascii=False))


if __name__ == '__main__':
    main()
