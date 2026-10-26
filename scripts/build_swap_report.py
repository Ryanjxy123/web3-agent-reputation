"""Export only public swap evidence and rebuild a frozen campaign report offline."""
import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'packages/core/src'), str(ROOT / 'services/platform/src')]

from reputation_platform.swap_report import build_swap_report, export_swap_campaign


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('campaign', type=Path, help='Frozen runtime campaign.json')
    parser.add_argument('output', type=Path, help='New public runtime report directory')
    args = parser.parse_args()
    try:
        directory = export_swap_campaign(ROOT, ROOT / args.campaign, ROOT / args.output)
        report = build_swap_report(ROOT, directory)
    except (OSError, ValueError, TypeError, KeyError) as error:
        print(f'Swap report not published: {type(error).__name__}. Sources remain retained.', file=sys.stderr)
        return 1
    print(report.scores.model_dump_json(indent=2))
    print(f'report: {directory / "report.json"}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
